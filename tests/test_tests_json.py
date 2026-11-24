"""Runs every case in tests.json through POST /chat (in-process) and checks its evaluation_criteria."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
CASES = json.loads((Path(__file__).resolve().parent.parent / "tests.json").read_text(encoding="utf-8"))


def test_tests_json_shape():
    assert len(CASES) >= 10
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))
    for c in CASES:
        assert {"id", "category", "name", "input", "expected_behavior", "evaluation_criteria"} <= set(c)
        assert {"user_id", "thread_id", "message"} <= set(c["input"])


@pytest.mark.parametrize("case", CASES, ids=[f"{c['id']}-{c['name'][:30]}" for c in CASES])
def test_case(case):
    payload = case["input"]
    for setup in case.get("setup_messages", []):
        sp = dict(payload)
        sp.update(setup if isinstance(setup, dict) else {"message": setup})
        assert client.post("/chat", json=sp).status_code == 200
    r = client.post("/chat", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"reply", "tool_calls", "tokens"} and set(data["tokens"]) == {"in", "out"}
    reply, tools = data["reply"].lower(), [t["name"] for t in data["tool_calls"]]
    crit = case["evaluation_criteria"]
    for w in crit.get("must_contain", []):
        assert w.lower() in reply, f"missing {w!r} in: {data['reply'][:300]}"
    for w in crit.get("must_not_contain", []):
        assert w.lower() not in reply, f"forbidden {w!r} in: {data['reply'][:300]}"
    for t in crit.get("must_call_tools", []):
        assert t in tools
    for t in crit.get("must_not_call_tools", []):
        assert t not in tools
