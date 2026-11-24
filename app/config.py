"""Configuration and LLM Provider setup for GrowthPilot.
Supports direct Anthropic API key OR OpenRouter API key.
Optimized for claude-haiku-5-5 / claude-3-5-haiku within $2 budget.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

# Database Path
DB_PATH = os.getenv("DATABASE_URL", f"sqlite:///{ROOT_DIR / 'growthpilot.db'}")
if DB_PATH.startswith("sqlite:///"):
    SQLITE_FILE = DB_PATH.replace("sqlite:///", "")
else:
    SQLITE_FILE = str(ROOT_DIR / "growthpilot.db")

# API Keys & Provider detection
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://openrouter.ai/api/v1").strip()

# Default Model Selection
MODEL_NAME = os.getenv("MODEL_NAME", "claude-3-5-haiku-20241022").strip()

# Port configuration
PORT = int(os.getenv("PORT", 8000))

# Cost parameters for Claude 3.5 Haiku (per 1M tokens)
# Input: $0.80 / 1M ($0.0000008), Output: $4.00 / 1M ($0.000004)
COST_PER_INPUT_TOKEN = 0.80 / 1_000_000
COST_PER_OUTPUT_TOKEN = 4.00 / 1_000_000
MAX_SPEND_LIMIT_USD = 2.00


def get_llm(max_tokens: int = 1000, temperature: float = 0.2):
    """Instantiate the Claude LLM cleanly based on available API key.
    Automatically prioritizes Anthropic direct, then OpenRouter.
    """
    if ANTHROPIC_API_KEY:
        from langchain_anthropic import ChatAnthropic
        # Standardize model names for direct Anthropic API (Canvas specified claude-haiku-5-5)
        model = MODEL_NAME
        if "haiku" in model.lower():
            model = "claude-haiku-5-5"
        return ChatAnthropic(
            model=model,
            anthropic_api_key=ANTHROPIC_API_KEY,
            max_tokens=max_tokens,
            temperature=temperature,
        )
    elif OPENROUTER_API_KEY:
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
        )
    else:
        # Fallback simulator for zero-cost local testing / verification without keys
        return None
