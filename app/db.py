"""Persistent SQLite / PostgreSQL Storage for GrowthPilot.
Provides strict multi-user data isolation across:
1. Leads & CRM Kanban pipeline
2. Human-in-the-loop Approval Inbox
3. Long-term memory store (ICPs, winning templates, tone)
4. Short-term checkpointer state
5. Token & cost usage telemetry
"""
import sqlite3
import json
import time
from typing import List, Dict, Any, Optional
from pathlib import Path
from app.config import SQLITE_FILE, COST_PER_INPUT_TOKEN, COST_PER_OUTPUT_TOKEN


def get_connection():
    conn = sqlite3.connect(SQLITE_FILE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # 1. Leads Table (CRM Pipeline)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS leads (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        company TEXT NOT NULL,
        contact_name TEXT NOT NULL,
        title TEXT,
        email TEXT,
        linkedin TEXT,
        industry TEXT,
        company_size TEXT,
        location TEXT,
        news TEXT,
        funding TEXT,
        tech_stack TEXT,
        pain_point TEXT,
        outreach_subject TEXT,
        outreach_body TEXT,
        stage TEXT DEFAULT 'Discovered',
        created_at REAL,
        updated_at REAL
    );
    """)

    # 2. Human Approval Inbox Table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS approvals (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        lead_id TEXT NOT NULL,
        contact_name TEXT,
        company TEXT,
        channel TEXT DEFAULT 'email',
        subject TEXT,
        body TEXT NOT NULL,
        status TEXT DEFAULT 'pending', -- pending, approved, rejected, edited
        created_at REAL,
        approved_at REAL,
        FOREIGN KEY(lead_id) REFERENCES leads(id)
    );
    """)

    # 3. Long-Term Memory Table (Strictly isolated by user_id)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS long_term_memory (
        user_id TEXT NOT NULL,
        memory_key TEXT NOT NULL,
        category TEXT NOT NULL, -- icp_preference, winning_template, tone_preference, general
        content TEXT NOT NULL,
        updated_at REAL,
        PRIMARY KEY (user_id, memory_key)
    );
    """)

    # 4. Short-Term Checkpoint Table (Conversation state by thread_id)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS checkpoints (
        thread_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        state_data TEXT NOT NULL,
        turn_count INTEGER DEFAULT 0,
        updated_at REAL
    );
    """)

    # 5. Usage & Cost Metrics
    cur.execute("""
    CREATE TABLE IF NOT EXISTS usage_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        thread_id TEXT,
        tokens_in INTEGER,
        tokens_out INTEGER,
        cost_usd REAL,
        action TEXT,
        timestamp REAL
    );
    """)

    # 6. Safety Audit Log
    cur.execute("""
    CREATE TABLE IF NOT EXISTS safety_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        incident_type TEXT NOT NULL, -- prompt_injection, off_topic, unauthorized_send
        prompt TEXT,
        explanation TEXT,
        timestamp REAL
    );
    """)

    conn.commit()
    conn.close()


# ── Leads CRM Operations (Isolated by user_id) ──

def upsert_lead(user_id: str, lead: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_connection()
    cur = conn.cursor()
    now = time.time()
    lead_id = lead.get("id") or f"lead_{int(now * 1000)}_{abs(hash(lead.get('email', '')) % 10000)}"

    cur.execute("""
        INSERT INTO leads (
            id, user_id, company, contact_name, title, email, linkedin, industry,
            company_size, location, news, funding, tech_stack, pain_point,
            outreach_subject, outreach_body, stage, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            company=excluded.company,
            contact_name=excluded.contact_name,
            title=excluded.title,
            email=excluded.email,
            linkedin=excluded.linkedin,
            industry=excluded.industry,
            company_size=excluded.company_size,
            location=excluded.location,
            news=excluded.news,
            funding=excluded.funding,
            tech_stack=excluded.tech_stack,
            pain_point=excluded.pain_point,
            outreach_subject=excluded.outreach_subject,
            outreach_body=excluded.outreach_body,
            stage=excluded.stage,
            updated_at=excluded.updated_at
    """, (
        lead_id, user_id, lead.get("company", "Unknown"), lead.get("contact_name", "Unknown"),
        lead.get("title", ""), lead.get("email", ""), lead.get("linkedin", ""),
        lead.get("industry", ""), lead.get("company_size", ""), lead.get("location", ""),
        lead.get("news", ""), lead.get("funding", ""), lead.get("tech_stack", ""),
        lead.get("pain_point", ""), lead.get("outreach_subject", ""),
        lead.get("outreach_body", ""), lead.get("stage", "Discovered"),
        now, now
    ))
    conn.commit()
    conn.close()
    lead["id"] = lead_id
    lead["user_id"] = user_id
    return lead


def get_user_leads(user_id: str, stage: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    if stage:
        cur.execute("SELECT * FROM leads WHERE user_id = ? AND stage = ? ORDER BY updated_at DESC", (user_id, stage))
    else:
        cur.execute("SELECT * FROM leads WHERE user_id = ? ORDER BY updated_at DESC", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_lead_stage(user_id: str, lead_id: str, new_stage: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE leads SET stage = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (new_stage, time.time(), lead_id, user_id))
    affected = cur.rowcount > 0
    conn.commit()
    conn.close()
    return affected


# ── Approvals Inbox Operations ──

def create_approval(user_id: str, lead_id: str, contact_name: str, company: str, subject: str, body: str) -> str:
    conn = get_connection()
    cur = conn.cursor()
    now = time.time()
    approval_id = f"appr_{int(now * 1000)}"
    cur.execute("""
        INSERT INTO approvals (id, user_id, lead_id, contact_name, company, subject, body, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
    """, (approval_id, user_id, lead_id, contact_name, company, subject, body, now))
    conn.commit()
    conn.close()
    return approval_id


def get_user_approvals(user_id: str, status: str = "pending") -> List[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM approvals WHERE user_id = ? AND status = ? ORDER BY created_at DESC", (user_id, status))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def resolve_approval(user_id: str, approval_id: str, action: str, edited_body: Optional[str] = None) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    now = time.time()
    status = "approved" if action in ("approve", "send") else "rejected"
    if edited_body:
        cur.execute("""
            UPDATE approvals SET status = ?, body = ?, approved_at = ? WHERE id = ? AND user_id = ?
        """, (status, edited_body, now, approval_id, user_id))
    else:
        cur.execute("""
            UPDATE approvals SET status = ?, approved_at = ? WHERE id = ? AND user_id = ?
        """, (status, now, approval_id, user_id))
    affected = cur.rowcount > 0

    # Also move lead stage to 'Contacted' if approved
    if affected and status == "approved":
        cur.execute("""
            UPDATE leads SET stage = 'Contacted', updated_at = ?
            WHERE id = (SELECT lead_id FROM approvals WHERE id = ?) AND user_id = ?
        """, (now, approval_id, user_id))

    conn.commit()
    conn.close()
    return affected


# ── Long-Term Memory (Persistent, Keyed by user_id) ──

def save_memory(user_id: str, key: str, content: str, category: str = "general"):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO long_term_memory (user_id, memory_key, category, content, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(user_id, memory_key) DO UPDATE SET
            content = excluded.content,
            category = excluded.category,
            updated_at = excluded.updated_at
    """, (user_id, key, category, content, time.time()))
    conn.commit()
    conn.close()


def get_memories(user_id: str, category: Optional[str] = None) -> Dict[str, str]:
    conn = get_connection()
    cur = conn.cursor()
    if category:
        cur.execute("SELECT memory_key, content FROM long_term_memory WHERE user_id = ? AND category = ?",
                    (user_id, category))
    else:
        cur.execute("SELECT memory_key, content FROM long_term_memory WHERE user_id = ?", (user_id,))
    rows = cur.fetchall()
    conn.close()
    return {r["memory_key"]: r["content"] for r in rows}


def delete_memory(user_id: str, key: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM long_term_memory WHERE user_id = ? AND memory_key = ?", (user_id, key))
    affected = cur.rowcount > 0
    conn.commit()
    conn.close()
    return affected


# ── Short-Term Checkpoint State (Conversation State by thread_id) ──

def save_checkpoint(thread_id: str, user_id: str, state_data: dict, turn_count: int):
    conn = get_connection()
    cur = conn.cursor()
    serialized = json.dumps(state_data)
    cur.execute("""
        INSERT INTO checkpoints (thread_id, user_id, state_data, turn_count, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(thread_id) DO UPDATE SET
            state_data = excluded.state_data,
            turn_count = excluded.turn_count,
            updated_at = excluded.updated_at
    """, (thread_id, user_id, serialized, turn_count, time.time()))
    conn.commit()
    conn.close()


def load_checkpoint(thread_id: str, user_id: str) -> Optional[dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT state_data, turn_count FROM checkpoints WHERE thread_id = ? AND user_id = ?",
                (thread_id, user_id))
    row = cur.fetchone()
    conn.close()
    if row:
        data = json.loads(row["state_data"])
        data["turn_count"] = row["turn_count"]
        return data
    return None


# ── Usage & Safety Logging ──

def log_usage(user_id: str, thread_id: str, tokens_in: int, tokens_out: int, action: str = "chat"):
    cost = (tokens_in * COST_PER_INPUT_TOKEN) + (tokens_out * COST_PER_OUTPUT_TOKEN)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO usage_logs (user_id, thread_id, tokens_in, tokens_out, cost_usd, action, timestamp)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, thread_id, tokens_in, tokens_out, cost, action, time.time()))
    conn.commit()
    conn.close()


def log_safety_event(user_id: str, incident_type: str, prompt: str, explanation: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO safety_logs (user_id, incident_type, prompt, explanation, timestamp)
        VALUES (?, ?, ?, ?, ?)
    """, (user_id, incident_type, prompt, explanation, time.time()))
    conn.commit()
    conn.close()


def get_admin_metrics() -> Dict[str, Any]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(DISTINCT user_id) as total_users FROM leads")
    total_users = cur.fetchone()["total_users"] or 0

    cur.execute("SELECT COUNT(*) as total_leads, COUNT(DISTINCT company) as total_companies FROM leads")
    lead_row = cur.fetchone()

    cur.execute("SELECT SUM(tokens_in) as total_in, SUM(tokens_out) as total_out, SUM(cost_usd) as total_cost FROM usage_logs")
    usage_row = cur.fetchone()

    cur.execute("SELECT COUNT(*) as pending_approvals FROM approvals WHERE status = 'pending'")
    approvals_count = cur.fetchone()["pending_approvals"] or 0

    cur.execute("SELECT * FROM safety_logs ORDER BY timestamp DESC LIMIT 10")
    safety_rows = [dict(r) for r in cur.fetchall()]

    conn.close()
    total_cost = usage_row["total_cost"] or 0.0
    return {
        "total_users": max(total_users, 1),
        "total_leads": lead_row["total_leads"] or 0,
        "total_companies": lead_row["total_companies"] or 0,
        "tokens_in": usage_row["total_in"] or 0,
        "tokens_out": usage_row["total_out"] or 0,
        "total_cost_usd": round(total_cost, 4),
        "budget_limit_usd": 2.00,
        "budget_remaining_usd": round(max(0.0, 2.00 - total_cost), 4),
        "pending_approvals": approvals_count,
        "recent_safety_incidents": safety_rows,
    }


# Automatically initialize tables on import
init_db()
