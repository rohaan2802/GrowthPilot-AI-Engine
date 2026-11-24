"""FastAPI Application for GrowthPilot.
Implements the Required Grading Agent API:
- POST /chat
- GET /health

Plus comprehensive REST APIs for the Customer Facing Page & Admin Dashboard.
"""
import os
import time
from typing import Optional, List, Dict, Any
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, PlainTextResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, ConfigDict

from app.agent import run_growthpilot_workflow
from app.db import (
    get_user_leads, upsert_lead, update_lead_stage,
    get_user_approvals, resolve_approval,
    get_memories, save_memory, delete_memory,
    get_admin_metrics
)

app = FastAPI(
    title="GrowthPilot - AI Sales & Outreach Engine",
    description="Design to Production Hackathon (Group 904 - Rayyan Azmat & Muhammad Rohaan)",
    version="1.0.0"
)

# Enable CORS for universal frontend connectivity
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic Request / Response Models ──

class ChatRequest(BaseModel):
    user_id: str = Field(..., description="Unique user identifier for multi-user isolation")
    thread_id: str = Field(..., description="Unique session identifier for short-term memory")
    message: str = Field(..., description="User prompt or sales instruction")


class TokenCount(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    in_: int = Field(0, alias="in")
    out: int = 0


class ChatResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    reply: str
    tool_calls: List[Dict[str, Any]] = []
    tokens: TokenCount


class LeadStageUpdate(BaseModel):
    stage: str


class ApprovalAction(BaseModel):
    user_id: str
    approval_id: str
    action: str  # approve, reject, edit
    edited_body: Optional[str] = None


class MemoryItem(BaseModel):
    user_id: str
    key: str
    content: str
    category: str = "general"


# ── MANDATORY HACKATHON GRADING ENDPOINTS ──

@app.get("/health", response_class=PlainTextResponse)
def health():
    """Required grading endpoint: GET /health returns 'ok'."""
    return "ok"


@app.post("/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest):
    """Required grading endpoint:
    POST /chat body: {"user_id": "...", "thread_id": "...", "message": "..."}
    returns: {"reply": "...", "tool_calls": [...], "tokens": {"in": 0, "out": 0}}
    """
    if not req.user_id or not req.thread_id or not req.message:
        raise HTTPException(status_code=400, detail="user_id, thread_id, and message are required.")

    result = run_growthpilot_workflow(
        user_id=req.user_id.strip(),
        thread_id=req.thread_id.strip(),
        user_message=req.message.strip()
    )

    tokens_dict = result.get("tokens", {"in": 0, "out": 0})
    return ChatResponse(
        reply=result["reply"],
        tool_calls=result.get("tool_calls", []),
        tokens=TokenCount(**{"in": tokens_dict.get("in", 0), "out": tokens_dict.get("out", 0)})
    )


# ── CUSTOMER & PIPELINE REST ENDPOINTS ──

@app.get("/api/leads")
def get_leads(user_id: str = Query(..., description="User ID for isolation"), stage: Optional[str] = None):
    """Retrieve all CRM leads for the active user."""
    return {"user_id": user_id, "leads": get_user_leads(user_id, stage)}


@app.post("/api/leads")
def create_lead(lead_data: Dict[str, Any], user_id: str = Query(...)):
    """Create or manually add a lead."""
    saved = upsert_lead(user_id, lead_data)
    return {"status": "success", "lead": saved}


@app.post("/api/leads/{lead_id}/stage")
def update_stage(lead_id: str, payload: LeadStageUpdate, user_id: str = Query(...)):
    """Move a lead across Kanban pipeline stages."""
    success = update_lead_stage(user_id, lead_id, payload.stage)
    if not success:
        raise HTTPException(status_code=404, detail="Lead not found or unauthorized")
    return {"status": "success", "lead_id": lead_id, "new_stage": payload.stage}


@app.get("/api/approvals")
def get_approvals(user_id: str = Query(...), status: str = "pending"):
    """Fetch pending outreach drafts in the Human Approval Inbox."""
    return {"user_id": user_id, "approvals": get_user_approvals(user_id, status)}


@app.post("/api/approve")
def handle_approval(payload: ApprovalAction):
    """Human-in-the-loop action: Approve, Reject, or Edit & Send outreach."""
    success = resolve_approval(
        user_id=payload.user_id,
        approval_id=payload.approval_id,
        action=payload.action,
        edited_body=payload.edited_body
    )
    if not success:
        raise HTTPException(status_code=404, detail="Approval not found or unauthorized")
    return {"status": "success", "action": payload.action, "approval_id": payload.approval_id}


@app.get("/api/memories")
def fetch_memories(user_id: str = Query(...)):
    """Fetch persistent long-term memory facts for the user."""
    return {"user_id": user_id, "memories": get_memories(user_id)}


@app.post("/api/memories")
def set_memory(item: MemoryItem):
    """Save an ICP preference, tone, or winning template."""
    save_memory(item.user_id, item.key, item.content, item.category)
    return {"status": "success", "key": item.key}


@app.delete("/api/memories/{key}")
def remove_memory(key: str, user_id: str = Query(...)):
    """Delete a memory item."""
    delete_memory(user_id, key)
    return {"status": "success", "deleted": key}


# ── ADMIN DASHBOARD ENDPOINTS ──

@app.get("/api/admin/metrics")
def get_metrics():
    """Retrieve system health, token spend, cost against $2 limit, and safety incidents."""
    return get_admin_metrics()


# Mount static directory for the single-page application
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def serve_frontend():
        index_file = STATIC_DIR / "index.html"
        if index_file.exists():
            return HTMLResponse(content=index_file.read_text(encoding="utf-8"))
        return HTMLResponse("<h3>GrowthPilot API Active. Navigate to /docs for Swagger UI.</h3>")
