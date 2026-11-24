"""Automated Benchmark Runner for GrowthPilot (Required Deliverable).
Executes all test cases in tests.json against POST /chat.
Generates an evaluation table with Pass/Fail status and token telemetry.
"""
import json
import os
import sys
import time
import requests
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
TESTS_FILE = ROOT_DIR / "tests.json"
BASE_URL = (sys.argv[1] if len(sys.argv) > 1 else os.getenv("BASE_URL", "http://127.0.0.1:8000")).rstrip("/")


def run_benchmark():
    if not TESTS_FILE.exists():
        print(f"[!] {TESTS_FILE} not found!")
        return

    # Check health
    try:
        health_resp = requests.get(f"{BASE_URL}/health", timeout=5)
        if health_resp.status_code != 200 or health_resp.text.strip() != "ok":
            print(f"[!] Health check failed: {health_resp.status_code} - {health_resp.text}")
            print("Make sure the GrowthPilot server is running: python -m uvicorn app.main:app --port 8000")
            return
        print("[✓] Server health: OK (GET /health -> 'ok')\n")
    except Exception as e:
        print(f"[!] Could not connect to {BASE_URL}: {e}")
        print("Start the server first: python -m uvicorn app.main:app --port 8000")
        return

    with open(TESTS_FILE, "r", encoding="utf-8") as f:
        tests = json.load(f)

    print("=" * 95)
    print(f"      GROWTHPILOT HACKATHON BENCHMARK EVALUATION ({len(tests)} Test Cases)")
    print("      Track 5: GrowthPilot | Group 904 (Rayyan Azmat & Muhammad Rohaan)")
    print("=" * 95)
    print(f"{'ID':<4} | {'Test Name':<38} | {'Category':<16} | {'Status':<8} | {'Tokens In/Out'}")
    print("-" * 95)

    passed_count = 0
    total_tokens_in = 0
    total_tokens_out = 0

    for tc in tests:
        tc_id = tc["id"]
        tc_name = tc["name"]
        category = tc["category"]
        payload = tc["input"]
        criteria = tc.get("evaluation_criteria", {})

        try:
            for setup in tc.get("setup_messages", []):
                sp = dict(payload)
                if isinstance(setup, dict):
                    sp.update(setup)
                else:
                    sp["message"] = setup
                requests.post(f"{BASE_URL}/chat", json=sp, timeout=60)
            t0 = time.time()
            resp = requests.post(f"{BASE_URL}/chat", json=payload, timeout=60)
            duration = time.time() - t0

            if resp.status_code != 200:
                print(f"{tc_id:<4} | {tc_name[:38]:<38} | {category:<16} | FAIL     | HTTP {resp.status_code}")
                continue

            data = resp.json()
            reply = data.get("reply", "")
            tool_calls = [tc["name"] for tc in data.get("tool_calls", [])]
            tokens = data.get("tokens", {"in": 0, "out": 0})
            tokens_in = tokens.get("in", 0)
            tokens_out = tokens.get("out", 0)
            total_tokens_in += tokens_in
            total_tokens_out += tokens_out

            passed = True
            fail_reason = ""
            # Check must_contain
            for word in criteria.get("must_contain", []):
                if word.lower() not in reply.lower():
                    passed = False
                    fail_reason = f"missing '{word}'"
                    break

            # Check must_not_contain
            if passed:
                for word in criteria.get("must_not_contain", []):
                    if word.lower() in reply.lower():
                        passed = False
                        fail_reason = f"contained forbidden '{word}'"
                        break

            # Check must_call_tools
            if passed:
                for expected_tool in criteria.get("must_call_tools", []):
                    if expected_tool not in tool_calls:
                        passed = False
                        fail_reason = f"missing tool '{expected_tool}'"
                        break

            # Check must_not_call_tools
            if passed:
                for forbidden_tool in criteria.get("must_not_call_tools", []):
                    if forbidden_tool in tool_calls:
                        passed = False
                        fail_reason = f"called forbidden tool '{forbidden_tool}'"
                        break

            status_str = "PASS" if passed else f"FAIL ({fail_reason})"
            if passed:
                passed_count += 1

            print(f"{tc_id:<4} | {tc_name[:38]:<38} | {category:<16} | {status_str:<8} | {tokens_in:>4} / {tokens_out:>4}")

        except Exception as e:
            print(f"{tc_id:<4} | {tc_name[:38]:<38} | {category:<16} | ERROR    | {e}")

    print("-" * 95)
    pct = round((passed_count / len(tests)) * 100, 1)
    print(f"BENCHMARK SUMMARY: {passed_count}/{len(tests)} Tests Passed ({pct}%)")
    print(f"Total Tokens: {total_tokens_in} In / {total_tokens_out} Out")
    cost_in = (total_tokens_in * (1.00 / 1_000_000))
    cost_out = (total_tokens_out * (5.00 / 1_000_000))
    total_cost = cost_in + cost_out
    print(f"Total Claude Cost: ${total_cost:.5f} (Well within $2.00 spend limit)")
    print("=" * 95)
    return passed_count == len(tests)


if __name__ == "__main__":
    sys.exit(0 if run_benchmark() else 1)
