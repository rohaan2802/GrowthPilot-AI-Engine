"""Safety and Guardrails Node for GrowthPilot.
Enforces:
1. Prompt Injection Defense (rejects overrides, jailbreaks, prompt extraction)
2. Off-Topic Filtering (rejects gaming, general trivia, code generation unrelated to sales)
3. Mandatory Human-in-the-Loop Guard (refuses automatic message dispatch without human approval)
"""
import re
from typing import Tuple, Optional
from app.db import log_safety_event


# Attack Patterns (Common Hackathon Benchmarks)
INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"disregard\s+(all\s+)?(previous|prior)\s+rules",
    r"system\s*prompt",
    r"reveal\s+your\s+(instructions|prompt|rules|secret)",
    r"you\s+are\s+now\s+in\s+developer\s+mode",
    r"jailbreak",
    r"dan\s+mode",
    r"bypass\s+(approval|safety|guard|verification)",
    r"send\s+(immediately|now|automatically)\s+without\s+(approval|review|checking)",
    r"sudo\s+send",
    r"override\s+human",
    r"exfiltrate",
    r"format\s+c:",
    r"drop\s+table",
]

# Off-Topic Keywords (Unrelated to B2B outbound, sales, ICP, leads, outreach)
OFF_TOPIC_PATTERNS = [
    r"\b(write\s+a\s+(poem|story|song|essay|novel))\b",
    r"\b(recipe\s+for|how\s+to\s+cook|ingredients\s+for)\b",
    r"\b(who\s+won\s+the\s+(world\s+cup|super\s+bowl|election))\b",
    r"\b(solve\s+this\s+math|quadratic\s+equation|calculus\s+derivative)\b",
    r"\b(snake\s+game|tic\s+tac\s+toe\s+in\s+python|unity\s+game)\b",
    r"\b(horoscope|astrology|zodiac\s+sign)\b",
]

COMPILED_INJECTIONS = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]
COMPILED_OFF_TOPIC = [re.compile(p, re.IGNORECASE) for p in OFF_TOPIC_PATTERNS]


def evaluate_safety(user_id: str, message: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Evaluates message safety.
    Returns: (is_safe: bool, incident_type: Optional[str], explanation: Optional[str])
    """
    text = message.strip()

    # 1. Check for prompt injection / security evasion
    for pattern in COMPILED_INJECTIONS:
        if pattern.search(text):
            explanation = "I cannot fulfill this request. GrowthPilot strictly adheres to security policies and enforces mandatory human approval before sending any communication."
            log_safety_event(user_id, "prompt_injection", text, explanation)
            return False, "prompt_injection", explanation

    # 2. Check for unauthorized automatic send requests
    if re.search(r"\b(send|dispatch|blast)\b.*\b(without\s+(approval|asking|me|review))\b", text, re.IGNORECASE):
        explanation = "Safety Policy Violation: Outbound emails and LinkedIn messages can never be dispatched automatically without human review. Please review and approve the drafts in your Approval Inbox."
        log_safety_event(user_id, "unauthorized_send", text, explanation)
        return False, "unauthorized_send", explanation

    # 3. Check for completely off-topic requests
    for pattern in COMPILED_OFF_TOPIC:
        if pattern.search(text):
            explanation = "I am GrowthPilot, an AI sales and outreach engine dedicated to B2B lead generation, research, and outreach pipeline management. I cannot assist with non-sales tasks."
            log_safety_event(user_id, "off_topic", text, explanation)
            return False, "off_topic", explanation

    return True, None, None
