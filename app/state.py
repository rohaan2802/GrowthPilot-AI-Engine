"""LangGraph state schema for the GrowthPilot multi-agent workflow."""
from typing import Any, Dict, List, Optional, TypedDict


class GrowthPilotState(TypedDict, total=False):
    # request
    user_id: str
    thread_id: str
    message: str
    text: str                                # normalised lower-case message
    # memory
    checkpoint: Dict[str, Any]               # short-term memory (per user_id + thread_id)
    memories: Dict[str, str]                 # long-term memory (per user_id)
    new_facts: Dict[str, str]                # facts learned this turn
    saved_note: Optional[str]
    # routing
    intent: str
    blocked: bool
    incident: Optional[str]
    # ICP + agent work products
    icp: Dict[str, Any]
    discovered_leads: List[Dict[str, Any]]
    enriched_leads: List[Dict[str, Any]]
    outreach_drafts: List[Dict[str, Any]]
    approvals_created: List[Dict[str, Any]]
    search_note: str
    # output
    tool_calls: List[Dict[str, Any]]
    tokens_in: int
    tokens_out: int
    reply: str
