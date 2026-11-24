"""Launch runner for GrowthPilot (Group 904).
Handles port conflict resolution, server health polling, and instant browser opening.
"""
import os
import sys
import time
import socket
import webbrowser
import subprocess
import urllib.request
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

DEFAULT_PORT = int(os.getenv("PORT", 8000))


def is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def find_free_port(start_port: int, max_attempts: int = 20) -> int:
    for port in range(start_port, start_port + max_attempts):
        if not is_port_in_use(port):
            return port
    return start_port


def main():
    print("=" * 68)
    print("       GrowthPilot - AI Sales & Outbound Engine (Group 904)")
    print("              FAST School of Computing, Islamabad")
    print("=" * 68)

    # Detect port
    target_port = DEFAULT_PORT
    if is_port_in_use(target_port):
        # Check if already running GrowthPilot on this port
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{target_port}/health", timeout=1) as resp:
                if resp.status == 200:
                    print(f"[*] GrowthPilot is ALREADY running on http://127.0.0.1:{target_port}")
                    print("[🚀] Opening existing instance in browser...")
                    webbrowser.open(f"http://127.0.0.1:{target_port}")
                    return
        except Exception:
            pass

        # Port is occupied by another app, find alternative
        alt_port = find_free_port(target_port + 1)
        print(f"[!] Notice: Port {target_port} was occupied. Automatically switched to port {alt_port}.")
        target_port = alt_port

    server_url = f"http://127.0.0.1:{target_port}"
    print(f"[*] Starting GrowthPilot server on {server_url} ...")

    # Start Uvicorn process
    cmd = [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(target_port)]
    proc = subprocess.Popen(cmd, cwd=str(ROOT_DIR))

    # Health poll
    print("[*] Waiting for application to initialize and load frontend...", end="", flush=True)
    ready = False
    for _ in range(40):
        try:
            with urllib.request.urlopen(f"{server_url}/health", timeout=1) as resp:
                if resp.status == 200:
                    ready = True
                    break
        except Exception:
            pass
        time.sleep(0.3)
        print(".", end="", flush=True)

    if ready:
        print(" READY! [OK]")
        print("-" * 68)
        print(f"[🚀] Web application is 100% LIVE at: {server_url}")
        print(f"[🚀] Opening dashboard in your default browser...")
        print("-" * 68)
        print("[ℹ] Press Ctrl+C in this terminal window anytime to stop the server.")
        print("=" * 68)
        time.sleep(0.2)
        webbrowser.open(server_url)
    else:
        print("\n[!] Server started but health check timed out. You can manually visit:", server_url)

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\n[*] Stopping GrowthPilot server...")
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("[✓] Server stopped safely. Goodbye!")


if __name__ == "__main__":
    main()
