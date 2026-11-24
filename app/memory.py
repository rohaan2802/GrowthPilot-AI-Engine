"""Memory architecture for GrowthPilot.

Short-term memory (per conversation, key = user_id + thread_id):
  - Stored in the `thread_checkpoints` table: chat history, active ICP, last leads found,
    pending risky action awaiting confirmation.
  - Long chats: only the last MAX_SHORT_TERM_TURNS turns are sent to the LLM; older turns are
    condensed into a compact rolling summary so the ICP and key facts survive.

Long-term memory (per user, key = user_id, across all threads):
  - Stored in the `long_term_memory` table.
  - Saves: user name, company, product, role, outreach tone, target industry / size / region,
    and explicit "remember that ..." notes.
  - Does NOT save: raw chat transcripts, blocked/unsafe prompts, prospects' personal data,
    secrets / API keys.

User isolation: every read/write is filtered by user_id; thread state is keyed by (user_id, thread_id).
"""
import re
import hashlib
from typing import Dict, Any, List, Optional

from langchain_core.messages import BaseMessage, SystemMessage
from app.db import save_memory, get_memories

MAX_SHORT_TERM_TURNS = 10          # turns (user+assistant pairs) kept verbatim for the LLM
MAX_STORED_MESSAGES = 40           # messages persisted in the checkpoint

FACT_LABELS = {
    "user_name": "Name",
    "user_company": "Company",
    "user_product": "Product / offer",
    "user_role": "Role",
    "outreach_tone_preference": "Preferred outreach tone",
    "preferred_target_industry": "Target industry",
    "target_company_size": "Target company size",
    "target_region": "Target region",
}

_STOP = r"(?=\s*(?:[.,;!?\n]|\band\b|\bbut\b|\bwe\b|\bi\b|\bwho\b|\bwhich\b|\bthat\b|\bhai\b|\bhay\b|\bhe\b|\bhoon\b|\bhun\b|$))"
_NOT_NAMES = {"looking", "trying", "here", "interested", "a", "an", "the", "not", "from", "working", "building",
              "selling", "new", "ready", "good", "fine", "back", "testing", "going", "your", "you"}


def _clean(value: str, max_len: int = 80) -> str:
    value = re.sub(r"\s+", " ", value or "").strip(" .,'\"!?:;-")
    return value[:max_len]


def _title(value: str) -> str:
    return " ".join(w if any(c.isupper() for c in w) else w.capitalize() for w in value.split())


def extract_facts(text: str) -> Dict[str, str]:
    """Deterministically extract user-profile facts worth keeping in long-term memory."""
    t = (text or "").strip()
    facts: Dict[str, str] = {}

    m = re.search(r"\b(?:my\s+name\s+is|my\s+name's|call\s+me|mera\s+naam|mera\s+name|meri\s+name)\s+(?:is\s+)?([A-Za-z][A-Za-z'\-]+(?:\s+[A-Za-z][A-Za-z'\-]+)?)" + _STOP, t, re.I)
    if m:
        name = _clean(m.group(1), 40)
        words = [w for w in name.split() if w.lower() not in ("hai", "hay", "is", "and")]
        if words and words[0].lower() not in _NOT_NAMES and words[0].lower() not in ("kya", "what"):
            facts["user_name"] = _title(" ".join(words))

    m = re.search(r"\b(?:my\s+company(?:'s)?(?:\s+name)?\s+is|our\s+company(?:'s)?(?:\s+name)?\s+is|company\s+name\s+is|i\s+work\s+(?:at|for)|i\s+run|i\s+own|i\s+founded|i'm\s+the\s+founder\s+of|i\s+am\s+the\s+founder\s+of|meri\s+company(?:\s+ka\s+naam)?)\s+([A-Za-z0-9][\w&.'\-]*(?:\s+[A-Z0-9][\w&.'\-]*){0,3})", t, re.I)
    if m:
        comp = _clean(m.group(1), 60)
        if comp.lower() not in ("a", "an", "the", "kya", "what") and not comp.lower().startswith(("a ", "an ")):
            facts["user_company"] = comp

    m = re.search(r"\b(?:we\s+sell|i\s+sell|we\s+offer|i\s+offer|our\s+product\s+is|my\s+product\s+is|we\s+provide|we\s+build|we\s+make)\s+([^.;!?\n]{3,80}?)(?=\s+(?:to|for)\s+|[.;!?\n]|$)", t, re.I)
    if m:
        facts["user_product"] = _clean(m.group(1))

    m = re.search(r"\bi(?:'m|\s+am)\s+(?:the\s+|a\s+|an\s+)?(founder|co-?founder|ceo|cto|coo|cmo|sales\s+manager|head\s+of\s+sales|sdr|bdr|account\s+executive|marketer|freelancer|agency\s+owner|consultant|growth\s+lead)\b", t, re.I)
    if m:
        facts["user_role"] = _title(m.group(1))

    m = (re.search(r"\b(?:preferred\s+)?(?:tone|style|voice)\b(?:\s+(?:for|of|in)\s+[\w\s-]{1,30}?)?\s+(?:is|should\s+be|=|:|must\s+be)\s+([^.;!?\n]{3,80})", t, re.I)
         or re.search(r"\b(?:use|write\s+in|keep\s+it|make\s+it|i\s+prefer|prefer)\s+(?:a\s+|an\s+)?((?:very\s+)?(?:formal|friendly|casual|punchy|professional|direct|warm|concise|short|polite)(?:\s*(?:,|and)\s*(?:formal|friendly|casual|punchy|professional|direct|warm|concise|short|polite))*)\s*(?:tone|style|emails?|messages?)?", t, re.I))
    if m:
        facts["outreach_tone_preference"] = _clean(m.group(1))

    return facts


def extract_note(text: str) -> Optional[str]:
    """Free-form 'remember that ...' note (used when no structured fact matched)."""
    m = re.search(r"\b(?:please\s+)?(?:remember|note\s+down|keep\s+in\s+mind|save\s+(?:this|that)|yaad\s+rakh\w*)\b[:,]?\s*(?:that\s+)?(.{3,200})", text or "", re.I)
    if m:
        return _clean(m.group(1), 200)
    return None


def save_facts(user_id: str, facts: Dict[str, str]) -> None:
    for k, v in facts.items():
        cat = "tone_preference" if k == "outreach_tone_preference" else ("icp_preference" if k.startswith(("preferred_", "target_")) else "profile")
        save_memory(user_id, k, v, category=cat)


def save_note(user_id: str, note: str) -> str:
    key = "note_" + hashlib.sha1(note.lower().encode()).hexdigest()[:8]
    save_memory(user_id, key, note, category="general")
    return key


def format_memories(mem: Dict[str, str]) -> List[str]:
    lines = []
    for k, v in mem.items():
        label = FACT_LABELS.get(k) or ("Note" if k.startswith("note_") else k.replace("_", " ").title())
        lines.append(f"- **{label}:** {v}")
    return lines


def get_user_long_term_context(user_id: str) -> str:
    memories = get_memories(user_id)
    if not memories:
        return "Long-term memory: nothing saved yet for this user."
    return "Long-term memory for this user:\n" + "\n".join(l.replace("**", "") for l in format_memories(memories))


def update_long_term_memory_from_chat(user_id: str, icp_dict: Optional[dict] = None, tone: Optional[str] = None):
    """Persist ICP / tone preferences (kept for backwards compatibility)."""
    if icp_dict:
        if icp_dict.get("industry"):
            save_memory(user_id, "preferred_target_industry", icp_dict["industry"], category="icp_preference")
        if icp_dict.get("company_size"):
            save_memory(user_id, "target_company_size", icp_dict["company_size"], category="icp_preference")
        if icp_dict.get("location"):
            save_memory(user_id, "target_region", icp_dict["location"], category="icp_preference")
    if tone:
        save_memory(user_id, "outreach_tone_preference", tone, category="tone_preference")


def trim_or_summarize_messages(messages: List[BaseMessage], max_turns: int = MAX_SHORT_TERM_TURNS) -> List[BaseMessage]:
    """Keep the first exchange (usually sets the ICP) + the last `max_turns` turns."""
    keep_tail = max_turns * 2
    if len(messages) <= keep_tail + 2:
        return messages
    head = messages[:2]
    tail = messages[-keep_tail:]
    note = SystemMessage(content="[Earlier turns condensed to stay within budget; first exchange and latest turns kept.]")
    return head + [note] + tail


def compact_history(history: List[Dict[str, str]], summary: str) -> (List[Dict[str, str]], str):
    """Rolling summary: when stored history is too long, move the oldest messages into `summary`."""
    if len(history) <= MAX_STORED_MESSAGES:
        return history, summary
    overflow = history[:-MAX_STORED_MESSAGES]
    kept = history[-MAX_STORED_MESSAGES:]
    bits = [f"{m['role']}: {m['content'][:120]}" for m in overflow if m.get("role") == "user"]
    summary = (summary + "\n" if summary else "") + "\n".join(bits)
    return kept, summary[-3000:]
