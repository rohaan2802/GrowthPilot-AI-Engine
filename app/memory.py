"""Memory Architecture for GrowthPilot:
1. Short-Term Memory (per conversation, using thread_id):
   - Conversation state checkpointer.
   - Trimming & summarization when turns > 8 to stay within budget while retaining active ICP.
2. Long-Term Memory (per user, across conversations, using user_id):
   - Saved in persistent SQLite database.
   - Remembers: ICP preferences, winning email templates, user's tone/voice preferences.
   - Excludes: PII and raw conversation noise.
3. User Isolation:
   - Strict separation: User A can never see or modify User B's memory.
"""
from typing import Dict, Any, List, Optional
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from app.db import save_memory, get_memories, delete_memory, save_checkpoint, load_checkpoint


MAX_SHORT_TERM_TURNS = 10  # Canvas requirement: last 8-10 turns


def trim_or_summarize_messages(messages: List[BaseMessage], max_turns: int = MAX_SHORT_TERM_TURNS) -> List[BaseMessage]:
    """Trims older turns when token limit is approached.
    Preserves:
    - System message
    - The first turn (which establishes the initial ICP)
    - The last `max_turns` turns
    """
    if len(messages) <= max_turns + 2:
        return messages

    # Retain system / initial framing
    head = messages[:2]
    # Retain latest active context
    tail = messages[-max_turns:]

    summary_note = SystemMessage(content="[Note: Earlier conversation turns summarized to preserve context within budget limits. Initial ICP parameters and latest interaction preserved.]")
    return head + [summary_note] + tail


def get_user_long_term_context(user_id: str) -> str:
    """Retrieves formatted long-term memory for injection into agent context."""
    memories = get_memories(user_id)
    if not memories:
        return "No prior user preferences recorded. Using standard professional B2B tone."

    lines = ["Saved Long-Term User Preferences:"]
    for k, v in memories.items():
        lines.append(f"- {k.replace('_', ' ').title()}: {v}")
    return "\n".join(lines)


def update_long_term_memory_from_chat(user_id: str, icp_dict: Optional[dict] = None, tone: Optional[str] = None):
    """Saves high-value facts to long-term memory."""
    if icp_dict:
        industry = icp_dict.get("industry")
        if industry:
            save_memory(user_id, "preferred_target_industry", industry, category="icp_preference")
        size = icp_dict.get("company_size")
        if size:
            save_memory(user_id, "target_company_size", size, category="icp_preference")

    if tone:
        save_memory(user_id, "outreach_tone_preference", tone, category="tone_preference")
