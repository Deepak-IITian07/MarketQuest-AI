"""Drive the Strands Decider 2B spike end to end.

Starts `strands-decider serve` on a local port, waits for /health, sends one
real tool-selection decision to POST /v1/systemone, and records every timing
and the server log for the write-up. Writes spike-result.json.

Run with the spike venv's python (the one that has strands-decider + psutil).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

SPIKE = Path(__file__).resolve().parents[1]
BIN = SPIKE / ".venv" / "Scripts" / "strands-decider.exe"
PORT = 8100
HOST = "127.0.0.1"
CHECKPOINT = "StrandsAgents/strands-decider-2B-qwen3.5-v1-2610"
MODEL_ID = "strands-decider-2B-qwen3.5-v1-2610"

# The decision the spike actually asks the model: which analysis tool should the
# agent call next for a symbol the user picked?
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
    "model": MODEL_ID,
}


def cache_size_mb(root: Path) -> float:
    """On-disk size of a directory, counting each file once.

    The Hugging Face cache stores blobs once under `blobs/` and links to them
    from `snapshots/`, so a naive rglob that follows symlinks counts the same
    weights several times over.
    """
    seen: set[tuple[int, int]] = set()
    total = 0
    for path in root.rglob("*"):
        try:
            stat = path.stat()
        except OSError:
            continue
        if not path.is_file():
            continue
        key = (stat.st_dev, stat.st_ino)
        if key in seen:
            continue
        seen.add(key)
        total += stat.st_size
    return total / (1024 * 1024)


def http_json(url: str, payload: dict | None = None, timeout: float = 30.0) -> tuple[int, dict]:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            return response.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"raw": body}


def main() -> int:
    if not BIN.exists():
        print(f"missing {BIN}", file=sys.stderr)
        return 1

    env = dict(os.environ)
    env["HF_HOME"] = str(SPIKE / "hf-cache")
    env["HF_HUB_DISABLE_TELEMETRY"] = "1"
    env["PYTHONUNBUFFERED"] = "1"

    command = [
        str(BIN),
        "serve",
        CHECKPOINT,
        "--host",
        HOST,
        "--port",
        str(PORT),
        "--device",
        "cpu",
    ]

    log_path = SPIKE / "serve.log"
    log = log_path.open("w", encoding="utf-8", errors="replace")

    started = time.perf_counter()
    process = subprocess.Popen(
        command,
        cwd=str(SPIKE),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )

    # Sample the server's resident memory while it works.
    peak_rss = {"bytes": 0}
    stop_sampling = threading.Event()

    def sample() -> None:
        try:
            import psutil
        except ImportError:
            return
        try:
            handle = psutil.Process(process.pid)
        except psutil.Error:
            return
        while not stop_sampling.is_set():
            try:
                rss = handle.memory_info().rss
                for child in handle.children(recursive=True):
                    try:
                        rss += child.memory_info().rss
                    except psutil.Error:
                        pass
                peak_rss["bytes"] = max(peak_rss["bytes"], rss)
            except psutil.Error:
                return
            stop_sampling.wait(0.5)

    sampler = threading.Thread(target=sample, daemon=True)
    sampler.start()

    result: dict = {
        "command": " ".join(command),
        "checkpoint": CHECKPOINT,
        "device": "cpu",
        "port": PORT,
    }

    # --- wait for the service to answer /health ---------------------------
    health = None
    deadline = time.time() + 1800  # 30 min covers the ~4.8 GB model download
    while time.time() < deadline:
        if process.poll() is not None:
            result["startup"] = {
                "ok": False,
                "error": f"server exited with code {process.returncode} before becoming ready",
                "seconds": round(time.perf_counter() - started, 2),
            }
            break
        try:
            status, body = http_json(f"http://{HOST}:{PORT}/health", timeout=5)
            if status == 200:
                health = body
                result["startup"] = {
                    "ok": True,
                    "seconds": round(time.perf_counter() - started, 2),
                }
                break
        except (urllib.error.URLError, OSError, json.JSONDecodeError):
            pass
        time.sleep(1.0)

    if health is not None:
        result["health"] = health
        print("HEALTH:", json.dumps(health, indent=2), flush=True)

        # --- one real decision --------------------------------------------
        url = f"http://{HOST}:{PORT}/v1/systemone"
        decision_started = time.perf_counter()
        status, body = http_json(url, REQUEST_BODY, timeout=300)
        client_ms = (time.perf_counter() - decision_started) * 1000
        result["decision"] = {
            "http_status": status,
            "client_latency_ms": round(client_ms, 2),
            "server_latency_ms": body.get("latency_ms"),
            "body": body,
        }
        print("DECISION:", json.dumps(body, indent=2), flush=True)

        # --- a second decision, to see a warm latency ----------------------
        decision_started = time.perf_counter()
        status2, body2 = http_json(url, REQUEST_BODY, timeout=300)
        result["decision_repeat"] = {
            "http_status": status2,
            "client_latency_ms": round((time.perf_counter() - decision_started) * 1000, 2),
            "server_latency_ms": body2.get("latency_ms"),
            "body": body2,
        }
        print("DECISION REPEAT:", json.dumps(body2, indent=2), flush=True)

    stop_sampling.set()
    result["peak_rss_mb"] = round(peak_rss["bytes"] / (1024 * 1024), 1)
    result["hf_cache_mb"] = round(cache_size_mb(SPIKE / "hf-cache"), 1)

    process.terminate()
    try:
        process.wait(timeout=20)
    except subprocess.TimeoutExpired:
        process.kill()
    log.close()

    (SPIKE / "spike-result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print("WROTE spike-result.json", flush=True)
    return 0 if result.get("startup", {}).get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
