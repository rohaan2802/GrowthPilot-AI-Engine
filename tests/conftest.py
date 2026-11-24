"""Test configuration: isolated temp database + deterministic (no-LLM) mode by default.
Set TEST_DATABASE_URL=postgresql://... to run the suite against Postgres.
Set RUN_LLM_TESTS=1 to also run the few tests that call the real Claude API."""
import os
import tempfile

_db = os.path.join(tempfile.mkdtemp(prefix="gp_test_"), "test.db")
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{_db}"
if os.getenv("RUN_LLM_TESTS") != "1":
    os.environ["DISABLE_LLM"] = "1"
