"""Measure a WARM startup of the Decider server (model already in the HF cache).

The first spike downloaded ~4.6 GB, so its startup number included the
download. This script reuses the same cache and measures only the service
start-up, then sends one decision so the warm decision latency is recorded
too.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SPIKE = Path(__file__).resolve().parents[1]
BIN = SPIKE / ".venv" / "Scripts" / "strands-decider.exe"
PORT = 8101
HOST = "127.0.0.1"
CHECKPOINT = "StrandsAgents/strands-decider-2B-qwen3.5-v1-2610"

REQUEST_BODY = {
    "state": (
        "The user has selected the demo symbol DEMOTECH and asked: "
        "'Show me DEMOTECH and tell me how volatile it has been.' "
        "Available tools: get_symbols, get_prices, get_analysis, get_returns, no_action. "
        "The symbol is already known, so listing symbols would be wasted work."
    ),
    "questions": {
        "next_tool": {
            "type": "choice",
            "instructions": (
                "Which single tool should the agent call next to answer the user's request?"
            ),
            "criteria": {
                "get_symbols": "List every available symbol and its latest price.",
                "get_prices": "Return the full price history for one symbol.",
                "get_analysis": (
                    "Return the moving average, volatility and total return for one symbol."
                ),
                "get_returns": "Return the daily percentage returns for one symbol.",
                "no_action": (
                    "Take no action because none of the tools can serve this request."
                ),
            },
        }
    },
    "model": "strands-decider-2B-qwen3.5-v1-2610",
}


def get_json(url: str, payload: dict | None = None, timeout: float = 30.0) -> tuple[int, dict]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, {"raw": exc.read().decode("utf-8", errors="replace")}


def main() -> int:
    env = dict(os.environ)
    env["HF_HOME"] = str(SPIKE / "hf-cache")
    env["HF_HUB_DISABLE_TELEMETRY"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    command = [
        str(BIN), "serve", CHECKPOINT,
        "--host", HOST, "--port", str(PORT), "--device", "cpu",
    ]

    log = (SPIKE / "serve-warm.log").open("w", encoding="utf-8", errors="replace")
    started = time.perf_counter()
    process = subprocess.Popen(
        command, cwd=str(SPIKE), env=env, stdout=log, stderr=subprocess.STDOUT
    )

    result: dict = {"command": " ".join(command), "cache": "warm (already downloaded)"}

    while time.perf_counter() - started < 600:
        if process.poll() is not None:
            result["startup"] = {
                "ok": False,
                "error": f"server exited with code {process.returncode}",
                "seconds": round(time.perf_counter() - started, 2),
            }
            break
        try:
            status, body = get_json(f"http://{HOST}:{PORT}/health", timeout=5)
            if status == 200:
                result["startup"] = {
                    "ok": True,
                    "seconds": round(time.perf_counter() - started, 2),
                }
                result["health"] = body
                break
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            pass
        time.sleep(0.5)

    if result.get("startup", {}).get("ok"):
        decision_started = time.perf_counter()
        status, body = get_json(
            f"http://{HOST}:{PORT}/v1/systemone", REQUEST_BODY, timeout=300
        )
        result["decision"] = {
            "http_status": status,
            "client_latency_ms": round((time.perf_counter() - decision_started) * 1000, 2),
            "server_latency_ms": body.get("latency_ms"),
            "body": body,
        }

    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
    log.close()

    (SPIKE / "warm-start-result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
