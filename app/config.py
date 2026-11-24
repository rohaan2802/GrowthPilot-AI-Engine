"""Configuration and LLM Provider setup for GrowthPilot.
Supports direct Anthropic API key (preferred) OR OpenRouter API key.
Model: claude-haiku-5-5 (hackathon requirement, $2 key budget).
"""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# ── Database ──
# sqlite:///path.db (default, local)  OR  postgresql://... (Neon / Supabase, recommended on Render)
DATABASE_URL = os.getenv("DATABASE_URL", "").strip() or f"sqlite:///{ROOT_DIR / 'growthpilot.db'}"
IS_POSTGRES = DATABASE_URL.startswith(("postgres://", "postgresql://"))
if DATABASE_URL.startswith("sqlite:///"):
    _p = DATABASE_URL[len("sqlite:///"):]
    SQLITE_FILE = str((ROOT_DIR / _p).resolve()) if not os.path.isabs(_p) else _p
else:
    SQLITE_FILE = str(ROOT_DIR / "growthpilot.db")
DB_PATH = DATABASE_URL  # backwards compatibility

# ── API Keys & Provider detection ──
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1").strip()

# Required model for the hackathon
REQUIRED_MODEL = "claude-haiku-5-5"
MODEL_NAME = os.getenv("MODEL_NAME", REQUIRED_MODEL).strip() or REQUIRED_MODEL
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "25"))
# Set DISABLE_LLM=1 to force the deterministic engine (used by the offline test-suite)
DISABLE_LLM = os.getenv("DISABLE_LLM", "").strip().lower() in ("1", "true", "yes")

# Port configuration
PORT = int(os.getenv("PORT", 8000))

# Hard limit on accepted message length (protects the $2 budget and latency)
MAX_MESSAGE_CHARS = int(os.getenv("MAX_MESSAGE_CHARS", "4000"))

# Estimated cost per token for Claude Haiku-class models (USD per token)
COST_PER_INPUT_TOKEN = 1.00 / 1_000_000
COST_PER_OUTPUT_TOKEN = 5.00 / 1_000_000
MAX_SPEND_LIMIT_USD = 2.00


def get_llm(max_tokens: int = 500, temperature: float = 0.0):
    """Return a chat model (Anthropic direct preferred, then OpenRouter) or None when unavailable."""
    if DISABLE_LLM:
        return None
    try:
        if ANTHROPIC_API_KEY:
            from langchain_anthropic import ChatAnthropic
            model = MODEL_NAME
            if "haiku" in model.lower() or "/" in model:
                model = REQUIRED_MODEL
            return ChatAnthropic(
                model=model,
                anthropic_api_key=ANTHROPIC_API_KEY,
                max_tokens=max_tokens,
                # NOTE: claude-haiku-5-5 rejects the `temperature` parameter (HTTP 400), so it is not sent.
                timeout=LLM_TIMEOUT_SECONDS,
                max_retries=1,
            )
        if OPENROUTER_API_KEY:
            from langchain_openai import ChatOpenAI
            model = MODEL_NAME
            if "claude" in model.lower() and "/" not in model:
                model = "anthropic/claude-haiku-5.5"
            return ChatOpenAI(
                model=model,
                openai_api_key=OPENROUTER_API_KEY,
                openai_api_base=OPENAI_BASE_URL,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=LLM_TIMEOUT_SECONDS,
                max_retries=1,
            )
    except Exception:
        return None
    return None
