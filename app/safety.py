"""Safety & Guardrail node for GrowthPilot.

Deterministic, zero-cost first line of defence (runs before any tool or LLM call):
1. Prompt injection / jailbreak / system-prompt or secret extraction
2. Cross-user data access attempts (user isolation)
3. Unauthorized automatic sending (mandatory human-in-the-loop)
4. Harmful outreach (spam, phishing, scraping personal data)
5. Clearly off-topic requests (poems, recipes, sports, maths, games ...)

Ambiguous off-topic prompts that slip through are caught by the LLM response node,
which is instructed to answer with the same off-topic refusal.

Returns ``(is_safe, incident_type, explanation)``; ``incident_type``/``explanation`` are
``None`` when the prompt is safe.
"""
import re
import unicodedata
from typing import Optional, Tuple

from app.db import log_safety_event

INJECTION_REFUSAL = (
    "I cannot fulfill this request. GrowthPilot strictly adheres to security policies: "
    "I never reveal my instructions or secrets, never switch off safety rules, and always enforce "
    "mandatory human approval before sending any communication."
)
ISOLATION_REFUSAL = (
    "I cannot fulfill this request. GrowthPilot strictly adheres to security policies: each user's "
    "leads, approvals and memory are isolated, so I can only access your own workspace data."
)
UNAUTHORIZED_SEND_REFUSAL = (
    "Safety Policy Violation: Outbound emails and LinkedIn messages can never be dispatched automatically "
    "without human review. Please review and approve the drafts in your Approval Inbox."
)
HARMFUL_REFUSAL = (
    "I cannot fulfill this request. GrowthPilot strictly adheres to security policies and only supports "
    "compliant, permission-based B2B outreach (no spam, phishing, deception or scraping of personal data)."
)
OFF_TOPIC_REFUSAL = (
    "I am GrowthPilot, an AI sales and outreach engine dedicated to B2B lead generation, research, "
    "and outreach pipeline management. I cannot assist with non-sales tasks. Try: "
    "'Find cybersecurity SaaS companies with 20-50 employees'."
)

INJECTION_PATTERNS = [
    r"\b(ignore|disregard|forget|override|overwrite|skip|drop)\b.{0,40}\b(previous|prior|above|earlier|preceding|initial|original|system|all|your|the)\b.{0,25}\b(instructions?|rules|prompts?|guidelines|directives|constraints|polic(y|ies)|programming)\b",
    r"\b(new|updated)\s+(system\s+)?(instructions|rules)\s*:",
    r"\bsystem\s*(prompt|message|instructions?)\b",
    r"\b(initial|hidden|original|developer|secret)\s+(prompt|instructions?|message)\b",
    r"\b(reveal|show|print|display|repeat|output|leak|tell|give|dump|share|expose|paste)\b.{0,20}\b(your|ur)\s+(own\s+)?(instructions|prompt|rules|configuration|config|guidelines|secrets?|api[\s_-]*keys?|passwords?|credentials|tokens?|source\s+code)\b",
    r"\b(reveal|show|print|display|leak|tell|give|dump|share|expose|what\s+is|what's)\b.{0,30}\b(api[\s_-]*keys?|secret[\s_-]*keys?|passwords?|credentials|access\s+tokens?)\b",
    r"\bwhat\s+(are|is|were)\s+your\s+(instructions|rules|system|prompt|guidelines)\b",
    r"\b(repeat|print|output)\s+(the\s+)?(text|everything|words)\s+(above|before)\b",
    r"\byou\s+are\s+now\b",
    r"\b(act|behave|respond)\s+as\s+(an?\s+)?(unfiltered|unrestricted|uncensored|evil|different|new|jailbroken|dan|root|admin)\b",
    r"\b(pretend|roleplay|role-play|imagine)\b.{0,40}\b(no\s+(rules|restrictions|limits|filters)|unrestricted|unfiltered|uncensored|without\s+(any\s+)?(rules|restrictions|limits|filters)|evil|jailbroken|dan)\b",
    r"\b(developer|dan|god|admin|debug|maintenance|unrestricted)\s+mode\b",
    r"\bjail\s*break",
    r"\bdo\s+anything\s+now\b",
    r"\b(bypass|disable|deactivate|turn\s+off|switch\s+off|circumvent|remove|skip|ignore)\b.{0,25}\b(approval|approvals|safety|guard(rail)?s?|filters?|verification|human\s+review|restrictions|checks?|polic(y|ies)|moderation)\b",
    r"\bsudo\b",
    r"\boverride\s+(the\s+)?human\b",
    r"\bexfiltrat",
    r"\bformat\s+c:",
    r"\b(drop|truncate)\s+table\b",
    r"\bdelete\s+from\s+(leads|users|approvals|long_term_memory|thread_checkpoints|checkpoints|usage_logs|safety_logs)\b",
    r";\s*(delete|drop|update|insert|alter)\b",
    r"\bunion\s+(all\s+)?select\b",
    r"'\s*or\s*'?1'?\s*=\s*'?1",
    r"<\s*/?\s*(script|system|iframe|img[^>]*onerror)",
    r"javascript\s*:",
    r"\b(anthropic|openai|openrouter|claude)\s*(api)?\s*key\b",
    r"\.env\b|\benvironment\s+variables?\b|\bos\.environ\b",
    r"\bprompt\s+injection\b",
    r"\b(hidden|internal|secret|backend)\s+(configuration|config|settings|instructions|rules|prompt)\b",
    # Roman Urdu / Urdu
    r"\b(pichli|pichhli|pehli|sari|saari|tamam)\b.{0,25}\b(hidayat|hidayaat|instructions?|rules)\b.{0,25}\b(ignore|bhool|bhul|chor|chhor|nazarandaz)",
    r"\b(apna|apne|apni)\s+(system\s+)?(prompt|instructions?|hidayat|rules)\s+(batao|bataein|dikhao|bata\s+do|share\s+karo)",
]

ISOLATION_PATTERNS = [
    r"\b(other|another|different|all|every|someone\s+else'?s?)\s+(users?|tenants?)('s|')?\b.{0,40}\b(data|leads?|memor(y|ies)|pipeline|crm|approvals?|preferences|info|emails?|history|conversations?|names?)\b",
    r"\b(data|leads?|memor(y|ies)|pipeline|crm|approvals?|preferences|history|conversations?)\b.{0,30}\b(of|for|from|belonging\s+to)\s+(other|another|all|every)\s+(users?|accounts?|customers?)\b",
    r"\b(leads?|memor(y|ies)|pipeline|crm|approvals?|preferences|data|history)\b.{0,30}\b(of|for|from|belonging\s+to)\s+(user[_:=-][\w-]+|user\s+\w*\d\w*|test_user_\w+)",
    r"\b(switch|change|login|log\s+in|impersonate)\b.{0,20}\b(user[\s_-]?id|another\s+user|as\s+user)\b",
    r"\buser[\s_]?id\s*[=:]\s*\S+",
    r"\bdusre\s+(user|users)\b",
]

UNAUTHORIZED_SEND_PATTERNS = [
    r"\b(send|dispatch|blast|fire\s+off|email|message|deliver|push)\b.{0,80}\bwithout\b.{0,25}\b(approval|approving|asking|me|review|reviewing|checking|confirmation|confirming|permission|my\s+ok|human)\b",
    r"\b(send|dispatch|email)\b.{0,40}\b(automatically|auto[\s-]?send|right\s+away\s+without)\b",
    r"\bauto[\s-]?(send|dispatch|blast)\b",
    r"\bautomatically\s+(send|dispatch|email|blast|message)\b",
    r"\b(no|skip(ping)?|without)\s+(human\s+)?(approval|review)\b.{0,40}\b(send|dispatch|email)",
    r"\b(bina|baghair|baghayr|begair)\b.{0,25}\b(approval|ijazat|review|pooche|puche)\b",
    r"\b(approval|ijazat)\s+(ke|k)\s+(baghair|bagair|begair|bina)\b",
]

HARMFUL_PATTERNS = [
    r"\bphish(ing)?\b",
    r"\b(send|blast|write|create|run)\b.{0,20}\bspam\b",
    r"\bspam\s+(people|everyone|them|campaign|blast|bomb)\b",
    r"\b(fake|forged|spoof(ed)?)\s+(invoice|sender|identity|email\s+address|domain)\b",
    r"\b(buy|purchase|scrape|harvest|steal)\b.{0,30}\b(email\s+lists?|personal\s+(data|emails?|phone)|phone\s+numbers|contacts?\s+lists?)\b",
    r"\b(malware|ransomware|keylogger|ddos)\b",
    r"\bhack\s+(into|someone|an?\s+account)\b",
    r"\b(impersonat(e|ing)|pose\s+as)\b.{0,30}\b(ceo|bank|government|irs|police|microsoft|google)\b",
    r"\b(send|blast)\b.{0,20}\b(\d{4,}|thousands|millions)\b.{0,20}\b(emails?|messages?)\b",
]

OFF_TOPIC_PATTERNS = [
    r"\b(write|compose|create|generate|tell|give)\s+(me\s+)?(a|an|some)?\s*(short\s+|funny\s+|love\s+)?(poem|story|song|essay|novel|haiku|limerick|rap|lyrics|bedtime\s+story|fairy\s+tale)\b",
    r"\btell\s+(me\s+)?(a\s+)?joke\b|\bjokes?\s+(about|on)\b",
    r"\brecipes?\b(?!.{0,30}\b(saas|software|app|platform|company|companies|startup|business|leads?)\b)",
    r"\bhow\s+(do\s+i|to|can\s+i)\s+(cook|bake|make\s+(a\s+)?(cake|pizza|biryani|cookies|pasta|tea|coffee))\b",
    r"\bingredients\s+(for|of)\b",
    r"\bwho\s+won\s+the\s+(world\s+cup|match|game|election|super\s+bowl|oscars?|championship|toss|series|league)\b|\b(world\s+cup|super\s+bowl|champions\s+league|ipl|psl)\b.{0,20}\b(score|winner|won|final|match)\b|\b(cricket|football)\s+(score|match)\b|\b(fifa|olympics?|nba|nfl|wimbledon)\b",
    r"\bweather\s+(in|today|tomorrow|forecast)\b|\bwhat'?s\s+the\s+weather\b",
    r"\b(solve|calculate|compute)\s+(this|the|my)?\s*(math|equation|integral|derivative|problem)\b|\bquadratic\s+equation\b|\bcalculus\b|\bderivative\s+of\b|\bintegral\s+of\b",
    r"^\s*(what\s+is|what's|calculate|solve)\s+\d+(\.\d+)?\s*[\+\-\*/x×÷^]\s*\d+",
    r"^\s*\d+(\.\d+)?\s*[\+\*/×÷^]\s*\d+(\.\d+)?\s*[=?]?\s*$",
    r"\b(snake\s+game|tic[\s-]*tac[\s-]*toe|unity\s+game|chess\s+engine|minecraft|fortnite)\b",
    r"^(?!.*\b(leads?|crm|pipeline|outreach|prospects?|cold\s+emails?)\b).*\b(write|create|generate|build|give)\b.{0,30}\b(python|java|javascript|c\+\+|c#|html|css|php|rust|golang|sql)\b.{0,20}\b(code|program|script|function|app|game)\b",
    r"\b(horoscope|astrology|zodiac|tarot)\b",
    r"\b(capital|president|prime\s+minister|population)\s+of\s+(france|pakistan|india|usa|china|japan|germany|england|the\s+us|[a-z]+land)\b",
    r"\b(movie|film|netflix|anime|tv\s+show|series)\s+(recommendations?|suggestions?|to\s+watch)\b",
    r"\b(symptoms\s+of|cure\s+for|medicine\s+for|treatment\s+for|diagnose\s+(my|this)\s+(pain|disease|illness|rash|fever|headache))\b",
    r"\b(homework|assignment|exam)\b.{0,20}\b(help|solve|answer|do)\b",
    r"\b(dating|relationship|girlfriend|boyfriend)\s+(advice|tips)\b",
    r"\b(trip|travel|vacation|holiday)\s+(plan|itinerary)\b|\bplan\s+(a|my)\s+(trip|vacation|holiday)\b",
    r"\b(translate)\b.{0,40}\b(to|into)\s+(french|spanish|german|chinese|arabic|urdu|hindi)\b(?!.{0,40}\b(email|outreach|message|pitch)\b)",
    # Roman Urdu
    r"\b(lateefa|latifa|lateefay|shayari|shairi|ghazal|gana|gaana)\b",
    r"\b(biryani|karahi|nihari|haleem)\b",
]

_C = lambda pats: [re.compile(p, re.IGNORECASE | re.DOTALL) for p in pats]
COMPILED_INJECTIONS = _C(INJECTION_PATTERNS)
COMPILED_ISOLATION = _C(ISOLATION_PATTERNS)
COMPILED_UNAUTHORIZED_SEND = _C(UNAUTHORIZED_SEND_PATTERNS)
COMPILED_HARMFUL = _C(HARMFUL_PATTERNS)
COMPILED_OFF_TOPIC = _C(OFF_TOPIC_PATTERNS)

_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"), None)


def normalize_text(text: str) -> str:
    """NFKC-normalise, remove zero-width characters and collapse whitespace (defeats simple obfuscation)."""
    text = unicodedata.normalize("NFKC", text or "").translate(_ZERO_WIDTH)
    return re.sub(r"\s+", " ", text).strip()


def _match(compiled, text: str) -> bool:
    return any(p.search(text) for p in compiled)


def evaluate_safety(user_id: str, message: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Evaluate a user message. Returns (is_safe, incident_type, explanation)."""
    text = normalize_text(message)
    checks = (
        (COMPILED_INJECTIONS, "prompt_injection", INJECTION_REFUSAL),
        (COMPILED_ISOLATION, "data_isolation", ISOLATION_REFUSAL),
        (COMPILED_UNAUTHORIZED_SEND, "unauthorized_send", UNAUTHORIZED_SEND_REFUSAL),
        (COMPILED_HARMFUL, "harmful_request", HARMFUL_REFUSAL),
        (COMPILED_OFF_TOPIC, "off_topic", OFF_TOPIC_REFUSAL),
    )
    for compiled, incident, explanation in checks:
        if _match(compiled, text):
            log_safety_event(user_id, incident, text, explanation)
            return False, incident, explanation
    return True, None, None
