"""LangGraph State schema for GrowthPilot.
Defines all fields required by the canvas multi-agent workflow.
"""
from typing import Any, List, Dict, Optional, TypedDict
from langchain_core.messages import BaseMessage


class GrowthPilotState(TypedDict):
    """Workflow state passed through the LangGraph nodes."""
    messages: List[BaseMessage]
    user_id: str
    thread_id: str
    icp: Dict[str, Any]                      # Current parsed Ideal Customer Profile
    discovered_leads: List[Dict[str, Any]]   # Leads found by Research Agent
    enriched_leads: List[Dict[str, Any]]     # Leads enriched with news, funding, tech
    outreach_drafts: List[Dict[str, Any]]    # Personalized messages generated
    pending_approvals: List[Dict[str, Any]]  # Messages awaiting human 'Approve & Send'
    pipeline_updates: List[Dict[str, Any]]   # Stage updates saved in CRM
    tool_calls: List[Dict[str, Any]]         # Tool call audit log for grading response
    tokens_in: int
    tokens_out: int
    action_required: Optional[str]           # e.g., 'human_approval', 'clarification'
    safety_violation: Optional[str]          # Set if injection / off-topic triggered
    final_reply: str                         # Message returned to user
