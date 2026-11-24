"""Real tools used by the GrowthPilot LangGraph agents.

1. search_companies_and_leads  - find companies + decision makers matching an ICP (demo B2B directory)
2. enrich_lead                 - news, funding, tech stack, pain point for a company
3. draft_outreach              - personalised (<120 words) cold email, tone-aware
4. crm_upsert                  - save / update a lead in the user's isolated CRM pipeline
5. crm_get_pipeline            - read the user's pipeline grouped by stage
6. crm_update_stage            - move one of the user's leads to another pipeline stage
7. generate_followup_sequence  - 3-touch follow-up cadence (Day 3 / 7 / 14)

NOTE: the lead directory below is a curated *demo* dataset (fictional companies) so that results are
deterministic and never hallucinated. Searches outside these segments return "no verified match"
instead of unrelated leads.
"""
import re
from typing import List, Dict, Any, Optional, Tuple

from app.db import upsert_lead, get_user_leads, update_lead_stage, PIPELINE_STAGES

SEED_LEADS_CATALOG = [
    {
        "company": "CloudScale",
        "domain": "cloudscale.io",
        "industry": "DevOps & Infrastructure",
        "company_size": "20-50",
        "location": "Seattle, WA",
        "contact_name": "Sarah Chen",
        "title": "VP of Engineering & DevOps",
        "email": "sarah.chen@cloudscale.io",
        "linkedin": "https://linkedin.com/in/sarah-chen-cloudscale",
        "news": "Raised $14M Series A to expand automated multi-cloud cost reduction engine.",
        "funding": "$14M Series A",
        "tech_stack": "Kubernetes, AWS, Terraform, Datadog, Go",
        "pain_point": "Complex cloud migration bottlenecks and engineering talent shortage.",
        "segment": "DevOps & Infrastructure"
    },
    {
        "company": "SecureAuth SaaS",
        "domain": "secureauthsaas.io",
        "industry": "Cybersecurity / B2B SaaS",
        "company_size": "25-50",
        "location": "Austin, TX",
        "contact_name": "Marcus Vance",
        "title": "VP of Revenue & Growth",
        "email": "marcus.v@secureauthsaas.io",
        "linkedin": "https://linkedin.com/in/marcus-vance-saas",
        "news": "Closed $8.5M Series A funding led by Insight Partners last month.",
        "funding": "$8.5M Series A",
        "tech_stack": "AWS, Segment, HubSpot, Auth0, Stripe",
        "pain_point": "Scaling outbound pipeline to hit new $2M ARR target post-Series A.",
        "segment": "Cybersecurity / B2B SaaS"
    },
    {
        "company": "CloudMetrics AI",
        "domain": "cloudmetrics.ai",
        "industry": "DevOps & Infrastructure",
        "company_size": "15-30",
        "location": "San Francisco, CA",
        "contact_name": "Elena Rostova",
        "title": "Co-Founder & CEO",
        "email": "elena@cloudmetrics.ai",
        "linkedin": "https://linkedin.com/in/elena-rostova-cloud",
        "news": "Featured on TechCrunch for real-time Kubernetes cost optimization.",
        "funding": "$3.2M Seed Round",
        "tech_stack": "GCP, Datadog, Snowflake, Apollo, Intercom",
        "pain_point": "SDR bandwidth bottleneck; founders still doing manual cold outreach.",
        "segment": "DevOps & Infrastructure"
    },
    {
        "company": "Nexus Agency Global",
        "domain": "nexusdigital.co",
        "industry": "Digital Marketing Agency",
        "company_size": "40-75",
        "location": "New York, NY",
        "contact_name": "David Sterling",
        "title": "Managing Director",
        "email": "d.sterling@nexusdigital.co",
        "linkedin": "https://linkedin.com/in/david-sterling-nexus",
        "news": "Expanded enterprise client roster into European eCommerce brands.",
        "funding": "Bootstrapped / Profitable ($6M ARR)",
        "tech_stack": "Webflow, Marketo, Google Workspace, Monday.com",
        "pain_point": "High lead churn and inconsistent cold outreach reply rates.",
        "segment": "Digital Marketing Agency"
    },
    {
        "company": "FinFlow Automation",
        "domain": "finflowpay.com",
        "industry": "FinTech / B2B SaaS",
        "company_size": "30-60",
        "location": "Chicago, IL",
        "contact_name": "Sarah Jenkins",
        "title": "Head of Demand Generation",
        "email": "sjenkins@finflowpay.com",
        "linkedin": "https://linkedin.com/in/sarah-jenkins-fintech",
        "news": "Launched compliance automation API for mid-market banks.",
        "funding": "$12M Series A",
        "tech_stack": "Stripe, Salesforce, Pardot, BigQuery, AWS",
        "pain_point": "Long enterprise sales cycles; need hyper-personalized outreach to VP of Finance.",
        "segment": "FinTech / B2B SaaS"
    },
    {
        "company": "PulseHealth Tech",
        "domain": "pulsehealth.care",
        "industry": "HealthTech / Telehealth SaaS",
        "company_size": "20-45",
        "location": "Boston, MA",
        "contact_name": "Dr. Tariq Mahmood",
        "title": "Chief Commercial Officer",
        "email": "tariq@pulsehealth.care",
        "linkedin": "https://linkedin.com/in/tariq-mahmood-health",
        "news": "Partnered with 15 regional healthcare networks for outpatient monitoring.",
        "funding": "$5M Seed+",
        "tech_stack": "Azure Health Data Services, HubSpot, Zoom Healthcare",
        "pain_point": "Need qualified clinical practice manager leads without spamming.",
        "segment": "HealthTech / Telehealth SaaS"
    },
    {
        "company": "ScaleReach Media",
        "domain": "scalereach.io",
        "industry": "Digital Agency / Performance Marketing",
        "company_size": "10-25",
        "location": "Toronto, Canada",
        "contact_name": "Chloe Martin",
        "title": "Founder & Growth Strategist",
        "email": "chloe@scalereach.io",
        "linkedin": "https://linkedin.com/in/chloe-martin-growth",
        "news": "Ranked in Top 50 B2B Marketing Agencies by Clutch 2026.",
        "funding": "Bootstrapped",
        "tech_stack": "Meta Ads Manager, Slack, ClickUp, ActiveCampaign",
        "pain_point": "Wasting 5 hours daily finding B2B e-commerce brand founders.",
        "segment": "Digital Marketing Agency"
    },
    {
        "company": "ShopNest Commerce",
        "domain": "shopnest.pk",
        "industry": "E-commerce / Retail SaaS",
        "segment": "E-commerce / Retail SaaS",
        "company_size": "30-80",
        "location": "Lahore, Pakistan",
        "contact_name": "Ayesha Khan",
        "title": "Head of Growth",
        "email": "ayesha.khan@shopnest.pk",
        "linkedin": "https://linkedin.com/in/ayesha-khan-shopnest",
        "news": "Launched a multi-vendor storefront builder for 2,000+ Pakistani SMEs.",
        "funding": "$2.1M Seed",
        "tech_stack": "Shopify APIs, Next.js, AWS, Klaviyo",
        "pain_point": "Converting free-trial merchants into paying subscribers."
    },
    {
        "company": "TalentBridge HR",
        "domain": "talentbridgehr.com",
        "industry": "HR Tech / B2B SaaS",
        "segment": "HR Tech / B2B SaaS",
        "company_size": "20-60",
        "location": "Karachi, Pakistan",
        "contact_name": "Bilal Ahmed",
        "title": "Director of Sales",
        "email": "bilal.ahmed@talentbridgehr.com",
        "linkedin": "https://linkedin.com/in/bilal-ahmed-talentbridge",
        "news": "Signed 40 new enterprise payroll clients across the GCC this year.",
        "funding": "$4M Series A",
        "tech_stack": "Salesforce, React, Azure, Twilio",
        "pain_point": "Long enterprise sales cycles and too few qualified demos per rep."
    },
    {
        "company": "LearnLoop EdTech",
        "domain": "learnloop.io",
        "industry": "EdTech / B2B SaaS",
        "segment": "EdTech / B2B SaaS",
        "company_size": "15-40",
        "location": "Islamabad, Pakistan",
        "contact_name": "Hira Siddiqui",
        "title": "Co-founder & CEO",
        "email": "hira@learnloop.io",
        "linkedin": "https://linkedin.com/in/hira-siddiqui-learnloop",
        "news": "Partnered with 120 private schools to roll out its LMS platform.",
        "funding": "$1.5M Pre-Seed",
        "tech_stack": "Django, PostgreSQL, GCP, Intercom",
        "pain_point": "Reaching school decision-makers without a dedicated outbound team."
    },
    {
        "company": "Propello Realty Cloud",
        "domain": "propellorealty.ae",
        "industry": "Real Estate / PropTech SaaS",
        "segment": "Real Estate / PropTech SaaS",
        "company_size": "25-70",
        "location": "Dubai, UAE",
        "contact_name": "Omar Farouk",
        "title": "VP of Sales",
        "email": "omar.farouk@propellorealty.ae",
        "linkedin": "https://linkedin.com/in/omar-farouk-propello",
        "news": "Expanded its broker CRM to Saudi Arabia after 3x revenue growth.",
        "funding": "$9M Series A",
        "tech_stack": "HubSpot, Vue.js, AWS, WhatsApp Business API",
        "pain_point": "Following up with hundreds of inbound property leads fast enough."
    },
    {
        "company": "FleetPulse Logistics",
        "domain": "fleetpulse.co.uk",
        "industry": "Logistics / Supply Chain SaaS",
        "segment": "Logistics / Supply Chain SaaS",
        "company_size": "50-120",
        "location": "London, UK",
        "contact_name": "James Whitaker",
        "title": "Chief Revenue Officer",
        "email": "james.whitaker@fleetpulse.co.uk",
        "linkedin": "https://linkedin.com/in/james-whitaker-fleetpulse",
        "news": "Won a 3-year fleet-tracking contract with a top-5 UK grocery chain.",
        "funding": "$22M Series B",
        "tech_stack": "Salesforce, Kafka, AWS IoT, Outreach.io",
        "pain_point": "Building a repeatable mid-market pipeline beyond referral deals."
    },
    {
        "company": "NeuralDesk AI",
        "domain": "neuraldesk.ai",
        "industry": "AI / Machine Learning SaaS",
        "segment": "AI / Machine Learning SaaS",
        "company_size": "10-30",
        "location": "Berlin, Germany",
        "contact_name": "Lena Fischer",
        "title": "Head of Partnerships",
        "email": "lena.fischer@neuraldesk.ai",
        "linkedin": "https://linkedin.com/in/lena-fischer-neuraldesk",
        "news": "Released an AI support copilot now used by 300 B2B help desks.",
        "funding": "$6M Seed",
        "tech_stack": "Python, PyTorch, GCP, Zendesk APIs",
        "pain_point": "Turning product-led signups into enterprise contracts."
    }
]

# Canonical segment -> keyword regexes (word-bounded)
SEGMENT_KEYWORDS: Dict[str, List[str]] = {
    "Cybersecurity / B2B SaaS": [r"cyber\w*", r"security", r"infosec", r"auth(entication)?", r"zero[\s-]?trust"],
    "DevOps & Infrastructure": [r"devops", r"infra(structure)?", r"cloud", r"kubernetes", r"sre", r"platform\s+engineering"],
    "FinTech / B2B SaaS": [r"fin[\s-]?tech", r"finance", r"financial", r"payments?", r"banking", r"accounting", r"invoic\w*"],
    "HealthTech / Telehealth SaaS": [r"health[\s-]?tech", r"health", r"healthcare", r"tele[\s-]?health", r"medical", r"clinics?", r"hospitals?"],
    "Digital Marketing Agency": [r"agenc(y|ies)", r"digital\s+marketing", r"marketing\s+agenc(y|ies)", r"advertising", r"performance\s+marketing", r"media\s+buying"],
    "E-commerce / Retail SaaS": [r"e[\s-]?commerce", r"retail", r"shopify", r"online\s+stores?", r"d2c", r"marketplaces?"],
    "HR Tech / B2B SaaS": [r"hr", r"hr[\s-]?tech", r"human\s+resources?", r"recruit\w*", r"payroll", r"talent"],
    "EdTech / B2B SaaS": [r"ed[\s-]?tech", r"education\w*", r"e[\s-]?learning", r"lms", r"schools?"],
    "Real Estate / PropTech SaaS": [r"real[\s-]?estate", r"prop[\s-]?tech", r"property", r"properties", r"realty", r"brokers?"],
    "Logistics / Supply Chain SaaS": [r"logistics", r"supply[\s-]?chain", r"fleet", r"shipping", r"freight", r"trucking"],
    "AI / Machine Learning SaaS": [r"ai\s+(startups?|companies|company|saas|firms?)", r"machine\s+learning", r"artificial\s+intelligence", r"llm", r"gen[\s-]?ai"],
}
_SEGMENT_RES = {seg: [re.compile(rf"\b{p}\b", re.I) for p in pats] for seg, pats in SEGMENT_KEYWORDS.items()}

_US = [", wa", ", tx", ", ca", ", ny", ", il", ", ma"]
# Location aliases -> tokens that must appear in a lead's location ([] = known place with no demo leads)
LOCATION_ALIASES: Dict[str, List[str]] = {
    "usa": _US, "us": _US, "united states": _US, "america": _US,
    "texas": [", tx"], "california": [", ca"], "new york": ["new york"], "seattle": ["seattle"], "austin": ["austin"],
    "san francisco": ["san francisco"], "chicago": ["chicago"], "boston": ["boston"],
    "canada": ["canada"], "toronto": ["toronto"],
    "pakistan": ["pakistan"], "karachi": ["karachi"], "lahore": ["lahore"], "islamabad": ["islamabad"],
    "uae": ["uae"], "dubai": ["dubai"], "uk": [", uk"], "united kingdom": [", uk"], "england": [", uk"], "london": ["london"],
    "germany": ["germany"], "berlin": ["berlin"], "europe": [", uk", "germany"],
    "india": [], "france": [], "paris": [], "australia": [], "sydney": [], "singapore": [], "saudi arabia": [],
    "riyadh": [], "china": [], "japan": [], "brazil": [], "nigeria": [], "egypt": [], "turkey": [], "spain": [],
    "italy": [], "netherlands": [], "mexico": [], "qatar": [], "bangladesh": [], "peshawar": [], "rawalpindi": [],
    "multan": [], "faisalabad": [], "los angeles": [], "miami": [],
}
_LOCATION_NAMES = sorted(LOCATION_ALIASES.keys(), key=len, reverse=True)


def detect_segments(text: str) -> List[str]:
    """Canonical segments mentioned in text, in order of first appearance."""
    text = text or ""
    found = []
    for seg, regs in _SEGMENT_RES.items():
        pos = [m.start() for r in regs for m in [r.search(text)] if m]
        if pos:
            found.append((min(pos), seg))
    return [s for _, s in sorted(found)]


def detect_location(text: str) -> Optional[str]:
    t = (text or "").lower()
    for name in _LOCATION_NAMES:
        if name == "us":
            if re.search(r"\b(in|from|across|based\s+in)\s+(the\s+)?us\b", t):
                return name
            continue
        if re.search(rf"\b{re.escape(name)}\b", t):
            return name
    return None


def parse_size_range(text: str) -> Optional[Tuple[int, int]]:
    """'20-50 employees', '20 to 50 people', 'between 20 and 50', 'under 50', 'over 100 employees', '50+ employees'."""
    t = (text or "").lower().replace(",", "")
    unit = r"(?:employees?|people|staff|persons?|ppl|headcount|members|seats)"
    m = (re.search(r"\bbetween\s+(\d{1,6})\s+(?:and|&)\s+(\d{1,6})\b", t)
         or re.search(rf"\b(\d{{1,6}})\s*(?:-|–|to)\s*(\d{{1,6}})\s*{unit}", t)
         or re.search(r"(?:size|employees|headcount|team\s+of)\s*(?:of\s*)?(\d{1,6})\s*(?:-|–|to)\s*(\d{1,6})\b", t)
         or re.search(r"^\s*(\d{1,6})\s*(?:-|–|to)\s*(\d{1,6})\s*$", t))
    if m:
        lo, hi = sorted((int(m.group(1)), int(m.group(2))))
        if hi > 0:
            return lo, hi
    m = re.search(rf"\b(?:under|less\s+than|below|fewer\s+than|up\s+to|max(?:imum)?(?:\s+of)?)\s+(\d{{1,6}})\s*{unit}", t)
    if m:
        return 1, int(m.group(1))
    m = (re.search(rf"\b(?:over|more\s+than|above|at\s+least|min(?:imum)?(?:\s+of)?)\s+(\d{{1,6}})\s*{unit}", t)
         or re.search(rf"\b(\d{{1,6}})\s*\+\s*{unit}", t))
    if m:
        return int(m.group(1)), 10_000_000
    return None


def size_to_text(rng: Optional[Tuple[int, int]]) -> Optional[str]:
    if not rng:
        return None
    lo, hi = rng
    if hi >= 10_000_000:
        return f"{lo}+"
    return f"{lo}-{hi}"


def _size_overlap(item_size: str, rng: Optional[Tuple[int, int]]) -> bool:
    if not rng:
        return True
    try:
        lo, hi = [int(x) for x in item_size.split("-")]
    except Exception:
        return True
    return not (hi < rng[0] or lo > rng[1])


def _location_match(item: Dict[str, Any], location: Optional[str]) -> bool:
    if not location:
        return True
    tokens = LOCATION_ALIASES.get(location.lower(), [location.lower()])
    loc = (item.get("location") or "").lower()
    return any(tok in loc for tok in tokens)


def _name_score(item: Dict[str, Any], query: str) -> int:
    q = (query or "").lower()
    comp = item["company"].lower()
    first_word = comp.split()[0]
    contact = item["contact_name"].lower().replace("dr. ", "")
    if comp in q or contact in q:
        return 100
    if len(first_word) > 3 and re.search(rf"\b{re.escape(first_word)}\b", q):
        return 80
    parts = [p for p in contact.split() if len(p) > 2]
    if parts and re.search(rf"\b{re.escape(parts[-1])}\b", q):  # surname
        return 60
    if parts and re.search(rf"\b{re.escape(parts[0])}\b", q):   # first name
        return 50
    return 0


def find_catalog_by_name(query: str) -> List[Dict[str, Any]]:
    """Directory leads whose company or contact is explicitly named in the query (best first)."""
    scored = [(_name_score(i, query), i) for i in SEED_LEADS_CATALOG]
    scored = [s for s in scored if s[0] > 0]
    if not scored:
        return []
    top = max(s[0] for s in scored)
    return [dict(i) for sc, i in scored if sc == top]


# ── TOOL 1: Search Companies and Leads ──

def tool_search_companies_and_leads(
    industry: Optional[str] = None,
    company_size: Optional[str] = None,
    keywords: Optional[str] = None,
    limit: int = 3,
    location: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Search the B2B directory. Returns ONLY leads that genuinely match the requested
    segment / size / location; an empty list when nothing matches (never unrelated leads)."""
    try:
        limit = max(1, min(int(limit or 3), 10))
    except Exception:
        limit = 3
    query = f"{industry or ''} {keywords or ''}"
    segments = detect_segments(query)
    rng = parse_size_range(company_size) if company_size else None
    if company_size and not rng:
        rng = parse_size_range(f"{company_size} employees")
    loc = location or detect_location(keywords or "")

    named = find_catalog_by_name(keywords or "")
    if named and not segments:
        return [i for i in named if _location_match(i, loc)][:limit]

    generic = bool(re.search(r"\b(b2b|saas)\b|\b(software|tech)\s+(companies|startups|firms|leads)\b", query, re.I))
    results = []
    for item in SEED_LEADS_CATALOG:
        if segments and item["segment"] not in segments:
            continue
        if not segments and not generic:
            continue
        if not _size_overlap(item.get("company_size", ""), rng):
            continue
        if not _location_match(item, loc):
            continue
        score = 10 + _name_score(item, keywords or "")
        if segments:
            score += 20 * (len(segments) - segments.index(item["segment"]))
        results.append((score, dict(item)))
    results.sort(key=lambda x: -x[0])
    return [r for _, r in results[:limit]]


# ── TOOL 2: Enrich Lead ──

def tool_enrich_lead(company_name: str, domain: Optional[str] = None) -> Dict[str, Any]:
    """News, funding, tech stack and pain point for a company (found=False if not in directory)."""
    normalized = (company_name or "").lower().strip()
    for item in SEED_LEADS_CATALOG:
        contact = item["contact_name"].lower()
        if normalized and (normalized in item["company"].lower() or normalized == contact
                           or normalized in contact.replace("dr. ", "")
                           or (domain and domain.lower().strip() == item.get("domain", "").lower())):
            return {
                "found": True,
                "company": item["company"],
                "contact_name": item["contact_name"],
                "title": item["title"],
                "email": item["email"],
                "funding": item["funding"],
                "news": item["news"],
                "tech_stack": item["tech_stack"],
                "pain_point": item["pain_point"],
                "growth_signals": [item["funding"], item["news"]],
                "outreach_hook": f"Saw your recent milestone: '{item['news']}'. As you scale, addressing {item['pain_point'].lower().rstrip('.')} is critical.",
            }
    return {
        "found": False,
        "company": company_name,
        "funding": "Unknown (not in verified directory)",
        "news": "No verified news found in the GrowthPilot directory.",
        "tech_stack": "Unknown",
        "pain_point": "Unknown - research needed",
        "growth_signals": [],
        "outreach_hook": "",
    }


# ── TOOL 3: Draft Outreach (tone-aware, < 120 words) ──

def _first_name(full: Optional[str]) -> str:
    if (full or "").startswith("["):
        return full
    parts = (full or "there").split()
    if parts and parts[0].lower().rstrip(".") == "dr" and len(parts) > 2:
        return f"Dr. {parts[-1]}"
    return parts[0] if parts else "there"


def tool_draft_outreach(lead: Dict[str, Any], tone: Optional[str] = None, sender_name: Optional[str] = None,
                        sender_company: Optional[str] = None, product: Optional[str] = None) -> Dict[str, Any]:
    tone_l = (tone or "").lower()
    first = _first_name(lead.get("contact_name"))
    company = lead.get("company") or "your company"
    news = (lead.get("news") or "").rstrip(".")
    pain = (lead.get("pain_point") or "growing pipeline").rstrip(".")
    pain = pain[0].lower() + pain[1:] if pain else pain
    offer = product or (sender_company or "GrowthPilot")
    sign = sender_name or "Growth Team"
    if sender_company and sender_name:
        sign += f", {sender_company}"
    if re.search(r"formal|professional|corporate|polite", tone_l):
        subject = f"Supporting {company}'s next phase of growth"
        body = (f"Dear {first},\n\nCongratulations on the recent milestone: {news}.\n\n"
                f"Teams at a similar stage often find that {pain} limits growth. {offer} helps address this "
                f"with targeted, research-driven outbound.\n\nWould you be available for a brief 15-minute call next week?\n\n"
                f"Kind regards,\n{sign}")
    elif re.search(r"friendly|casual|warm|conversational", tone_l):
        subject = f"Loved the news at {company}!"
        body = (f"Hi {first},\n\nJust saw this: {news}. Huge congrats!\n\n"
                f"Curious - is {pain} on your radar right now? {offer} has been helping similar teams with exactly that.\n\n"
                f"Happy to share what's working - up for a quick chat this week?\n\nCheers,\n{sign}")
    else:  # default: punchy, direct, no fluff
        subject = f"Quick question re: {company}'s growth milestone"
        body = (f"Hi {first},\n\nCongrats on this: {news}.\n\n"
                f"As {company} scales, {pain} usually becomes the bottleneck. {offer} automates targeted outbound so "
                f"your team can focus on closing.\n\nOpen to a 7-minute intro this week?\n\nBest,\n{sign}")
    return {"subject": subject, "body": body, "word_count": len(body.split())}


# ── TOOL 4: CRM Upsert ──

def tool_crm_upsert(user_id: str, lead: Dict[str, Any]) -> Dict[str, Any]:
    saved = upsert_lead(user_id, lead)
    return {
        "status": "success",
        "lead_id": saved["id"],
        "company": saved.get("company"),
        "contact_name": saved.get("contact_name"),
        "stage": saved.get("stage", "Discovered"),
        "message": f"Lead '{saved.get('company')}' saved in CRM under stage '{saved.get('stage')}'.",
    }


# ── TOOL 5: CRM Get Pipeline ──

def tool_crm_get_pipeline(user_id: str) -> Dict[str, Any]:
    leads = get_user_leads(user_id)
    by_stage: Dict[str, List[str]] = {}
    for l in leads:
        by_stage.setdefault(l.get("stage") or "Discovered", []).append(f"{l['contact_name']} ({l['company']})")
    return {"total": len(leads), "by_stage": by_stage, "leads": leads}


# ── TOOL 6: CRM Update Stage ──

def normalize_stage(text: str) -> Optional[str]:
    t = (text or "").lower()
    table = [
        (r"closed[\s-]*won|\bwon\b|deal\s+(won|closed)|\bsigned\b|\bconverted\b", "Closed Won"),
        (r"closed[\s-]*lost|\blost\b|not\s+interested|disqualif", "Closed Lost"),
        (r"meeting|call\s+booked|demo\s+(booked|scheduled)|\bbooked\b|\bscheduled\b", "Meeting Booked"),
        (r"\breplied\b|\bresponded\b|\breply\b|got\s+back", "Replied"),
        (r"\bcontacted\b|reached\s+out|\bemailed\b", "Contacted"),
        (r"needs?\s+approval|pending\s+approval", "Needs Approval"),
        (r"\benriched\b", "Enriched"),
        (r"\bdiscovered\b|new\s+lead", "Discovered"),
    ]
    for pat, stage in table:
        if re.search(pat, t):
            return stage
    return None


def find_user_lead(user_id: str, ref: str) -> List[Dict[str, Any]]:
    """Leads in THIS user's CRM referenced by company / contact name in `ref`."""
    q = (ref or "").lower()
    out = []
    for l in get_user_leads(user_id):
        comp = (l.get("company") or "").lower()
        contact = (l.get("contact_name") or "").lower().replace("dr. ", "")
        words = [w for w in comp.split() + contact.split() if len(w) > 3 and w not in ("saas", "tech", "global", "media", "agency", "cloud")]
        if (comp and comp in q) or (contact and contact in q) or any(re.search(rf"\b{re.escape(w)}\b", q) for w in words):
            out.append(l)
    return out


def tool_crm_update_stage(user_id: str, lead_id: str, stage: str) -> Dict[str, Any]:
    if stage not in PIPELINE_STAGES:
        return {"status": "error", "message": f"Unknown stage '{stage}'. Valid: {', '.join(PIPELINE_STAGES)}"}
    ok = update_lead_stage(user_id, lead_id, stage)
    return {"status": "success" if ok else "not_found", "lead_id": lead_id, "stage": stage}


# ── TOOL 7: Follow-Up Sequence ──

def tool_generate_followup_sequence(contact_name: str, company: str, pain_point: str) -> List[Dict[str, str]]:
    first = _first_name(contact_name)
    pain = (pain_point or "scaling outbound").rstrip(".")
    pain = pain[0].lower() + pain[1:] if pain else pain
    return [
        {"step": "Touch 2 (Day 3)",
         "subject": f"Quick follow up re: {company}'s outbound pipeline",
         "body": f"Hi {first},\n\nWanted to make sure my note didn't get buried. Given your focus on {pain}, we can take the manual prospect research off your team's plate.\n\nOpen to a brief 7-minute intro this Thursday?"},
        {"step": "Touch 3 (Day 7 - Value Add)",
         "subject": f"An idea for {company}",
         "body": f"Hi {first},\n\nOne idea: teams like {company} often start with a small, tightly targeted outbound pilot before scaling.\n\nWorth a quick chat to see if it fits your roadmap?"},
        {"step": "Touch 4 (Day 14 - Polite Breakup)",
         "subject": "Permission to close the file?",
         "body": f"Hi {first},\n\nI haven't heard back, so I assume this isn't a priority right now. I'll pause follow-ups so I don't clutter your inbox.\n\nFeel free to reach out whenever timing is better."},
    ]
