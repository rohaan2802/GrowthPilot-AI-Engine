"""Persistent storage for GrowthPilot (SQLite locally, PostgreSQL/Neon/Supabase in production).

Strict multi-user isolation: EVERY read/write is scoped by user_id.
Tables:
1. leads               - CRM pipeline (per user)
2. approvals           - Human-in-the-loop approval inbox (per user)
3. long_term_memory    - Long-term memory facts (PK: user_id + memory_key)
4. thread_checkpoints  - Short-term conversation state (PK: user_id + thread_id)
5. usage_logs          - token / cost telemetry
6. safety_logs         - blocked prompt audit log
"""
import hashlib
import json
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from typing import List, Dict, Any, Optional

from app.config import (
    SQLITE_FILE, DATABASE_URL, IS_POSTGRES,
    COST_PER_INPUT_TOKEN, COST_PER_OUTPUT_TOKEN, MAX_SPEND_LIMIT_USD,
)

PIPELINE_STAGES = [
    "Discovered", "Enriched", "Needs Approval", "Contacted",
    "Replied", "Meeting Booked", "Closed Won", "Closed Lost",
]

_pool = None
_pool_lock = threading.Lock()


def _get_pg_pool():
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                from psycopg_pool import ConnectionPool
                from psycopg.rows import dict_row
                _pool = ConnectionPool(
                    DATABASE_URL, min_size=1, max_size=5, open=True,
                    kwargs={"row_factory": dict_row, "autocommit": False},
                )
    return _pool


class _Cursor:
    """Tiny adapter so the same SQL ('?' placeholders) works on SQLite and Postgres."""

    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql: str, params: tuple = ()):
        if IS_POSTGRES:
            sql = sql.replace("?", "%s")
        self._cur.execute(sql, params)
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(r) for r in self._cur.fetchall()]

    @property
    def rowcount(self):
        return self._cur.rowcount


@contextmanager
def db_cursor():
    """Yields a cursor inside a transaction (commit on success, rollback on error)."""
    if IS_POSTGRES:
        with _get_pg_pool().connection() as conn:
            cur = conn.cursor()
            try:
                yield _Cursor(cur)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    else:
        conn = sqlite3.connect(SQLITE_FILE, timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.cursor()
            yield _Cursor(cur)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def get_connection():
    """Backwards-compatible raw SQLite connection (local only)."""
    conn = sqlite3.connect(SQLITE_FILE, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    autoinc = "BIGSERIAL PRIMARY KEY" if IS_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    real = "DOUBLE PRECISION" if IS_POSTGRES else "REAL"
    if not IS_POSTGRES:
        try:
            c = sqlite3.connect(SQLITE_FILE, timeout=30)
            c.execute("PRAGMA journal_mode=WAL;")
            c.close()
        except Exception:
            pass
    with db_cursor() as cur:
        cur.execute(f"""
        CREATE TABLE IF NOT EXISTS leads (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            company TEXT NOT NULL,
            contact_name TEXT NOT NULL,
            title TEXT, email TEXT, linkedin TEXT, industry TEXT,
            company_size TEXT, location TEXT, news TEXT, funding TEXT,
            tech_stack TEXT, pain_point TEXT,
            outreach_subject TEXT, outreach_body TEXT,
            stage TEXT DEFAULT 'Discovered',
            created_at {real}, updated_at {real}
        )""")
        cur.execute(f"""
        CREATE TABLE IF NOT EXISTS approvals (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            lead_id TEXT NOT NULL,
            contact_name TEXT, company TEXT,
            channel TEXT DEFAULT 'email',
            subject TEXT, body TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at {real}, approved_at {real}
        )""")
        cur.execute(f"""
        CREATE TABLE IF NOT EXISTS long_term_memory (
            user_id TEXT NOT NULL,
            memory_key TEXT NOT NULL,
            category TEXT NOT NULL,
            content TEXT NOT NULL,
            updated_at {real},
            PRIMARY KEY (user_id, memory_key)
        )""")
        # NOTE: composite key -> two users re-using the same thread_id never share state.
        cur.execute(f"""
        CREATE TABLE IF NOT EXISTS thread_checkpoints (
            user_id TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            state_data TEXT NOT NULL,
            turn_count INTEGER DEFAULT 0,
            updated_at {real},
            PRIMARY KEY (user_id, thread_id)
        )""")
        cur.execute(f"""
        CREATE TABLE IF NOT EXISTS usage_logs (
            id {autoinc},
            user_id TEXT NOT NULL, thread_id TEXT,
            tokens_in INTEGER, tokens_out INTEGER, cost_usd {real},
            action TEXT, timestamp {real}
        )""")
        cur.execute(f"""
        CREATE TABLE IF NOT EXISTS safety_logs (
            id {autoinc},
            user_id TEXT NOT NULL, incident_type TEXT NOT NULL,
            prompt TEXT, explanation TEXT, timestamp {real}
        )""")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_leads_user ON leads(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_appr_user ON approvals(user_id, status)")


def _stable_lead_id(user_id: str, lead: Dict[str, Any]) -> str:
    basis = f"{user_id}|{(lead.get('email') or '').lower()}|{(lead.get('company') or '').lower()}|{(lead.get('contact_name') or '').lower()}"
    return "lead_" + hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


# ── Leads CRM Operations (Isolated by user_id) ──

def upsert_lead(user_id: str, lead: Dict[str, Any]) -> Dict[str, Any]:
    now = time.time()
    lead_id = str(lead.get("id") or "").strip() or _stable_lead_id(user_id, lead)
    with db_cursor() as cur:
        # Never let a client overwrite another user's lead by re-using its id.
        cur.execute("SELECT user_id FROM leads WHERE id = ?", (lead_id,))
        owner = cur.fetchone()
        if owner and owner["user_id"] != user_id:
            lead_id = "lead_" + uuid.uuid4().hex[:16]
        stage = lead.get("stage") or "Discovered"
        cur.execute("""
            INSERT INTO leads (
                id, user_id, company, contact_name, title, email, linkedin, industry,
                company_size, location, news, funding, tech_stack, pain_point,
                outreach_subject, outreach_body, stage, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                company=excluded.company, contact_name=excluded.contact_name,
                title=excluded.title, email=excluded.email, linkedin=excluded.linkedin,
                industry=excluded.industry, company_size=excluded.company_size,
                location=excluded.location, news=excluded.news, funding=excluded.funding,
                tech_stack=excluded.tech_stack, pain_point=excluded.pain_point,
                outreach_subject=excluded.outreach_subject, outreach_body=excluded.outreach_body,
                stage=excluded.stage, updated_at=excluded.updated_at
        """, (
            lead_id, user_id, str(lead.get("company") or "Unknown"), str(lead.get("contact_name") or "Unknown"),
            str(lead.get("title") or ""), str(lead.get("email") or ""), str(lead.get("linkedin") or ""),
            str(lead.get("industry") or ""), str(lead.get("company_size") or ""), str(lead.get("location") or ""),
            str(lead.get("news") or ""), str(lead.get("funding") or ""), str(lead.get("tech_stack") or ""),
            str(lead.get("pain_point") or ""), str(lead.get("outreach_subject") or ""),
            str(lead.get("outreach_body") or ""), stage, now, now,
        ))
    lead["id"] = lead_id
    lead["user_id"] = user_id
    lead["stage"] = stage
    return lead


def get_user_leads(user_id: str, stage: Optional[str] = None) -> List[Dict[str, Any]]:
    with db_cursor() as cur:
        if stage:
            cur.execute("SELECT * FROM leads WHERE user_id = ? AND stage = ? ORDER BY updated_at DESC", (user_id, stage))
        else:
            cur.execute("SELECT * FROM leads WHERE user_id = ? ORDER BY updated_at DESC", (user_id,))
        return cur.fetchall()


def update_lead_stage(user_id: str, lead_id: str, new_stage: str) -> bool:
    with db_cursor() as cur:
        cur.execute("UPDATE leads SET stage = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                    (new_stage, time.time(), lead_id, user_id))
        return cur.rowcount > 0


def delete_user_leads(user_id: str) -> int:
    with db_cursor() as cur:
        cur.execute("DELETE FROM approvals WHERE user_id = ?", (user_id,))
        cur.execute("DELETE FROM leads WHERE user_id = ?", (user_id,))
        return cur.rowcount


# ── Approvals Inbox Operations ──

def create_approval(user_id: str, lead_id: str, contact_name: str, company: str, subject: str, body: str) -> str:
    approval_id = "appr_" + uuid.uuid4().hex[:12]
    with db_cursor() as cur:
        # Replace an older pending draft for the same lead instead of piling up duplicates
        cur.execute("DELETE FROM approvals WHERE user_id = ? AND lead_id = ? AND status = 'pending'", (user_id, lead_id))
        cur.execute("""
            INSERT INTO approvals (id, user_id, lead_id, contact_name, company, subject, body, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """, (approval_id, user_id, lead_id, contact_name, company, subject, body, time.time()))
    return approval_id


def get_user_approvals(user_id: str, status: str = "pending") -> List[Dict[str, Any]]:
    with db_cursor() as cur:
        cur.execute("SELECT * FROM approvals WHERE user_id = ? AND status = ? ORDER BY created_at DESC", (user_id, status))
        return cur.fetchall()


def resolve_approval(user_id: str, approval_id: str, action: str, edited_body: Optional[str] = None) -> bool:
    action = (action or "").strip().lower()
    if action in ("approve", "send", "approved", "edit"):
        status = "approved"
    elif action in ("reject", "rejected", "discard"):
        status = "rejected"
    else:
        return False
    now = time.time()
    with db_cursor() as cur:
        if edited_body:
            cur.execute("UPDATE approvals SET status = ?, body = ?, approved_at = ? WHERE id = ? AND user_id = ? AND status = 'pending'",
                        (status, edited_body, now, approval_id, user_id))
        else:
            cur.execute("UPDATE approvals SET status = ?, approved_at = ? WHERE id = ? AND user_id = ? AND status = 'pending'",
                        (status, now, approval_id, user_id))
        affected = cur.rowcount > 0
        if affected and status == "approved":
            cur.execute("""
                UPDATE leads SET stage = 'Contacted', updated_at = ?
                WHERE id = (SELECT lead_id FROM approvals WHERE id = ? AND user_id = ?) AND user_id = ?
            """, (now, approval_id, user_id, user_id))
    return affected


# ── Long-Term Memory (Persistent, Keyed by user_id) ──

def save_memory(user_id: str, key: str, content: str, category: str = "general"):
    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO long_term_memory (user_id, memory_key, category, content, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, memory_key) DO UPDATE SET
                content = excluded.content, category = excluded.category, updated_at = excluded.updated_at
        """, (user_id, str(key)[:100], str(category)[:50], str(content)[:1000], time.time()))


def get_memories(user_id: str, category: Optional[str] = None) -> Dict[str, str]:
    with db_cursor() as cur:
        if category:
            cur.execute("SELECT memory_key, content FROM long_term_memory WHERE user_id = ? AND category = ? ORDER BY updated_at",
                        (user_id, category))
        else:
            cur.execute("SELECT memory_key, content FROM long_term_memory WHERE user_id = ? ORDER BY updated_at", (user_id,))
        return {r["memory_key"]: r["content"] for r in cur.fetchall()}


def delete_memory(user_id: str, key: str) -> bool:
    with db_cursor() as cur:
        cur.execute("DELETE FROM long_term_memory WHERE user_id = ? AND memory_key = ?", (user_id, key))
        return cur.rowcount > 0


def delete_all_memories(user_id: str) -> int:
    with db_cursor() as cur:
        cur.execute("DELETE FROM long_term_memory WHERE user_id = ?", (user_id,))
        return cur.rowcount


# ── Short-Term Checkpoint State (per user_id + thread_id) ──

def save_checkpoint(thread_id: str, user_id: str, state_data: dict, turn_count: int):
    with db_cursor() as cur:
        cur.execute("""
            INSERT INTO thread_checkpoints (user_id, thread_id, state_data, turn_count, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, thread_id) DO UPDATE SET
                state_data = excluded.state_data, turn_count = excluded.turn_count, updated_at = excluded.updated_at
        """, (user_id, thread_id, json.dumps(state_data, default=str), turn_count, time.time()))


def load_checkpoint(thread_id: str, user_id: str) -> Optional[dict]:
    with db_cursor() as cur:
        cur.execute("SELECT state_data, turn_count FROM thread_checkpoints WHERE thread_id = ? AND user_id = ?",
                    (thread_id, user_id))
        row = cur.fetchone()
    if row:
        try:
            data = json.loads(row["state_data"])
        except Exception:
            return None
        data["turn_count"] = row["turn_count"]
        return data
    return None


# ── Usage & Safety Logging ──

def log_usage(user_id: str, thread_id: str, tokens_in: int, tokens_out: int, action: str = "chat"):
    cost = (tokens_in * COST_PER_INPUT_TOKEN) + (tokens_out * COST_PER_OUTPUT_TOKEN)
    try:
        with db_cursor() as cur:
            cur.execute("""
                INSERT INTO usage_logs (user_id, thread_id, tokens_in, tokens_out, cost_usd, action, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, thread_id, tokens_in, tokens_out, cost, action, time.time()))
    except Exception:
        pass  # telemetry must never break a chat turn


def log_safety_event(user_id: str, incident_type: str, prompt: str, explanation: str):
    try:
        with db_cursor() as cur:
            cur.execute("""
                INSERT INTO safety_logs (user_id, incident_type, prompt, explanation, timestamp)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, incident_type, (prompt or "")[:500], explanation, time.time()))
    except Exception:
        pass


def get_admin_metrics() -> Dict[str, Any]:
    with db_cursor() as cur:
        cur.execute("SELECT COUNT(DISTINCT user_id) AS total_users FROM leads")
        total_users = (cur.fetchone() or {}).get("total_users") or 0
        cur.execute("SELECT COUNT(*) AS total_leads, COUNT(DISTINCT company) AS total_companies FROM leads")
        lead_row = cur.fetchone() or {}
        cur.execute("SELECT SUM(tokens_in) AS total_in, SUM(tokens_out) AS total_out, SUM(cost_usd) AS total_cost FROM usage_logs")
        usage_row = cur.fetchone() or {}
        cur.execute("SELECT COUNT(*) AS pending_approvals FROM approvals WHERE status = 'pending'")
        approvals_count = (cur.fetchone() or {}).get("pending_approvals") or 0
        cur.execute("SELECT * FROM safety_logs ORDER BY timestamp DESC LIMIT 10")
        safety_rows = cur.fetchall()
    total_cost = float(usage_row.get("total_cost") or 0.0)
    return {
        "total_users": int(total_users),
        "total_leads": int(lead_row.get("total_leads") or 0),
        "total_companies": int(lead_row.get("total_companies") or 0),
        "tokens_in": int(usage_row.get("total_in") or 0),
        "tokens_out": int(usage_row.get("total_out") or 0),
        "total_cost_usd": round(total_cost, 4),
        "budget_limit_usd": MAX_SPEND_LIMIT_USD,
        "budget_remaining_usd": round(max(0.0, MAX_SPEND_LIMIT_USD - total_cost), 4),
        "pending_approvals": int(approvals_count),
        "recent_safety_incidents": safety_rows,
    }



def delete_lead(user_id: str, lead_id: str) -> bool:
    with db_cursor() as cur:
        cur.execute("DELETE FROM approvals WHERE user_id = ? AND lead_id = ?", (user_id, lead_id))
        cur.execute("DELETE FROM leads WHERE user_id = ? AND id = ?", (user_id, lead_id))
        return cur.rowcount > 0


# Automatically initialize tables on import
init_db()
