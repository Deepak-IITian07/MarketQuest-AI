# Strands Decider 2B spike — findings

**Status: the service genuinely works.** A real decision was taken over HTTP
from the real `strands-decider-2B-qwen3.5-v1-2610` checkpoint running on CPU,
and the answer was correct for the question asked.

This is a spike report. It is the only file this spike was asked to write.
Nothing in `backend/`, `backend/requirements.txt`, or `README.md` was touched.

---

## 1. Verdict at a glance

| Question | Answer |
|---|---|
| Does the documented setup work? | **Yes**, unchanged. `pip install "strands-decider[cpu]"` + `strands-decider serve` on CPU. |
| Is the service genuinely running? | **Yes.** `GET /health` → 200; `POST /v1/systemone` → 200 with a real probability distribution. |
| Was the decision correct? | **Yes** for the prompt that was sent. See [§9](#9-the-real-decision-over-http). |
| Cold startup (incl. 4.56 GB download) | **253.9 s** (4 min 14 s) |
| Warm startup (weights already on disk) | **28.1 s** |
| Decision latency (CPU) | **5.8 s** first decision, **3.7 s** repeated |
| Peak server memory | **5,589 MB** (5.6 GB) resident |
| Disk used by the model | **4,561.7 MB** (HF cache) |
| Can the backend venv stay clean? | **Yes.** The whole thing runs from a separate Python 3.12 venv and the backend talks to it over plain HTTP on 127.0.0.1. |
| Blockers found | **None.** Two rough edges worth knowing, both in [§13](#13-rough-edges-and-open-questions). |

---

## 2. What was run, exactly

Every command below was run in PowerShell on this machine (Windows 11, x64).
`$SPIKE` is the experiment directory:

```powershell
$SPIKE = "C:\Users\DELL\OneDrive\Desktop\Crezy Dev\Local\MarketQuest-AI\MarketQuest-AI\experiments\decider-spike"
```

### 2.1 Isolated environment (Python 3.12, separate from the backend venv)

```powershell
py -3.12 -m venv "$SPIKE\.venv"
& "$SPIKE\.venv\Scripts\python.exe" --version   # Python 3.12.6
& "$SPIKE\.venv\Scripts\python.exe" -m pip install --upgrade pip   # pip 26.2.2
```

The backend venv is Python **3.14.5** and was **not** touched. The Decider
needs 3.12 here for its own reasons; keeping it separate is what stops
`torch` from entering the backend environment.

### 2.2 Install

```powershell
& "$SPIKE\.venv\Scripts\python.exe" -m pip install "strands-decider[cpu]" --report "$SPIKE\install-report.json"
```

**Result: exit code 0, 408.4 s (6 min 48 s).** venv size after install:
**841.3 MB**.

Resolved versions that matter:

| Package | Version | Note |
|---|---|---|
| `strands-decider` | **0.2.0** (distribution) | `strands_decider.__version__` reports `0.1.0` — the two disagree in the package itself, not a mistake here |
| `torch` | **2.14.1+cpu** | Windows CPU wheel; **no `nvidia-*` packages anywhere in the tree** |
| `transformers` | 5.20.2 | |
| `peft` | 0.21.2 | loads the LoRA adapter |
| `huggingface_hub` | 2.2.0 | |
| `accelerate` | 1.15.0 | |
| `tokenizers` | 0.23.3 | |
| `numpy` | 2.5.4 | |
| `fastapi` / `uvicorn` | 0.161.1 / 0.54.0 | the `serve` command's own server |

**This resolves an open question from `docs/decision-pattern.md`.** The `cpu`
extra adds no requirements of its own — the resolved tree is the base
dependencies, and on Windows the `torch` wheel is already the CPU build. The
`+cpu` suffix is still the right thing to install, because it is what
documents the intent and it is what the package's own extras declare.

### 2.3 Launch the service

```powershell
$env:HF_HOME = "$SPIKE\hf-cache"
& "$SPIKE\.venv\Scripts\strands-decider.exe" serve `
    StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 `
    --host 127.0.0.1 --port 8100 --device cpu
```

Run inside the driver script `scripts/run_spike.py` so startup and decision
latency could be measured; the script writes `spike-result.json` and
`serve.log`.

---

## 3. Disk space, checked before any download

Checked **before** the weights were pulled, as required.

| Check | Value |
|---|---|
| Free space on `C:` before download | **127.7 GB** |
| Expected adapter repo size (`GET /api/models/...?blobs=true`) | **224 MB** (29 files) |
| Expected base model size (`Qwen/Qwen3.5-2B-Base`) | **4,571,206,192 B ≈ 4.57 GB** |
| Expected total | **≈ 4.8 GB** |
| Headroom | ~26× the expected total. **Safe to proceed.** |

After the run: `C:` free = **119.3 GB**, HF cache = **4,561.7 MB**, venv =
**841.3 MB**.

> The `spike-result.json` file reports `hf_cache_mb: 4561.7`. That field was
> **corrected after the run**: it originally read `13684.4`, because the
> measurement followed the Hugging Face cache's symlinks and counted the same
> blobs more than once. The true on-disk size is **4,561.7 MB**, confirmed by
> de-duplicating on (device, inode). The measurement code in
> `scripts/run_spike.py` has been fixed, and the JSON carries a note saying so.
> Every other field in that file is the raw, unmodified output of the run.

---

## 4. Model ID and revision

| Field | Value |
|---|---|
| Checkpoint (adapter) | **`StrandsAgents/strands-decider-2B-qwen3.5-v1-2610`** |
| Repository revision (sha) | **`216d1ccb46a9e9b036eb9187b248db98480f77d4`** |
| Repository last modified | 2026-10-09T22:55:03Z |
| Base model | **`Qwen/Qwen3.5-2B-Base`** |
| Licence | Apache-2.0 (adapter repo, base model, and the package) |
| Library / pipeline tag | `peft` / `text-classification` |

The revision was taken from the Hugging Face API
(`https://huggingface.co/api/models/StrandsAgents/strands-decider-2B-qwen3.5-v1-2610`)
before the download. The adapter repo contains the LoRA weights
(`lora/adapter_model.safetensors`, 192.5 MB), the readout head
(`head.safetensors`, 12 MB), the tokenizer (19.1 MB), the config, and the
training provenance.

`GET /health` confirms the base model the server actually loaded:

```json
{
  "status": "ok",
  "model": "strands-decider-2B-qwen3.5-v1-2610",
  "checkpoint": "StrandsAgents/strands-decider-2B-qwen3.5-v1-2610",
  "base_model": "Qwen/Qwen3.5-2B-Base",
  "num_slots": 24,
  "max_length": 4096,
  "temperature": 1.0545210242263665,
  "device": "cpu",
  "prefix_cache": true,
  "vision": false
}
```

---

## 5. Service startup

| Scenario | Time to `GET /health` → 200 | What was included |
|---|---|---|
| **Cold** (first run) | **253.9 s** | full download of 4.56 GB (adapter + base model) + weight load + server bind |
| **Warm** (second run, same `HF_HOME`) | **28.1 s** | weight load from local disk only + server bind |

Weight loading alone was ~15 s of the warm 28 s (visible as the
`Loading weights: 320/320` progress bar in `serve.log`).

**Practical consequence:** the 28 s warm start is the number that matters for
the demo. The service must be started *before* the demo, not during it — a
cold start on a fresh machine is a 4-minute wait.

---

## 6. The HTTP contract (read from the installed source, not guessed)

`strands_decider/server.py` and `strands_decider/schema.py`, read directly:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Readiness + which model/checkpoint/base model is loaded |
| `POST` | `/v1/systemone` | The decision |

The server binds **`127.0.0.1` by default and has no authentication at all**.
It is a local-only service. Do not expose it.

Request shape (`SystemOneRequest`):

```json
{
  "state": "<string or structured content>",
  "questions": { "<name>": { "type": "choice|noul|score", "instructions": "...", "criteria": {...} } },
  "model": "strands-decider-latest",
  "images": []
}
```

Response shape (`SystemOneResponse`), plus two server-added fields:

```json
{
  "model": "...",
  "answers": { "<name>": { "type": "choice", "choice": "...", "probabilities": {...}, "confidence": 0.0 } },
  "usage": { "input_tokens": 0, "output_tokens": 0 },
  "latency_ms": 0.0
}
```

`latency_ms` is added by the server (measured around the forward pass).
`output_tokens` is **1** for a choice question — the model emits one slot
index, not text.

---

## 7. The decision that was actually asked

The question posed to the model was the real tool-selection question this
project needs: *the user has already picked a symbol; which analysis tool
should the agent call next?*

**State (verbatim):**

> The user has selected the demo symbol DEMOTECH and asked: 'Show me DEMOTECH
> and tell me how volatile it has been.' Available tools: get_symbols,
> get_prices, get_analysis, get_returns, no_action. The symbol is already
> known, so listing symbols would be wasted work.

**Question:** `choice` — *"Which single tool should the agent call next to
answer the user's request?"*

**Options, with the description of each (this matters — see [§12](#12-a-cross-check-that-did-not-agree)):**

| Option | Description given to the model |
|---|---|
| `get_symbols` | List every available symbol and its latest price. |
| `get_prices` | Return the full price history for one symbol. |
| `get_analysis` | Return the moving average, volatility and total return for one symbol. |
| `get_returns` | Return the daily percentage returns for one symbol. |
| `no_action` | Take no action because none of the tools can serve this request. |

---

## 8. Exact request

```powershell
$body = @'
{
  "state": "The user has selected the demo symbol DEMOTECH and asked: 'Show me DEMOTECH and tell me how volatile it has been.' Available tools: get_symbols, get_prices, get_analysis, get_returns, no_action. The symbol is already known, so listing symbols would be wasted work.",
  "questions": {
    "next_tool": {
      "type": "choice",
      "instructions": "Which single tool should the agent call next to answer the user's request?",
      "criteria": {
        "get_symbols": "List every available symbol and its latest price.",
        "get_prices": "Return the full price history for one symbol.",
        "get_analysis": "Return the moving average, volatility and total return for one symbol.",
        "get_returns": "Return the daily percentage returns for one symbol.",
        "no_action": "Take no action because none of the tools can serve this request."
      }
    }
  },
  "model": "strands-decider-2B-qwen3.5-v1-2610"
}
'@

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8100/v1/systemone `
  -ContentType "application/json" -Body $body
```

---

## 9. The real decision over HTTP

**HTTP 200.** Response body, verbatim:

```json
{
  "model": "strands-decider-2B-qwen3.5-v1-2610",
  "answers": {
    "next_tool": {
      "type": "choice",
      "choice": "get_analysis",
      "probabilities": {
        "get_symbols": 0.003,
        "get_prices": 0.2234,
        "get_analysis": 0.6846,
        "get_returns": 0.085,
        "no_action": 0.004
      },
      "confidence": 0.6057
    }
  },
  "usage": {
    "input_tokens": 196,
    "output_tokens": 1
  },
  "latency_ms": 5826.81
}
```

**The model chose `get_analysis`** — which returns the moving average,
volatility and total return for one symbol. The user asked *"how volatile it
has been"*, and `get_analysis` is the tool that returns volatility. The choice
is correct, and the runner-up `get_prices` (0.2234) is defensible too, because
the user also said *"show me DEMOTECH"*.

Note the shape of the answer: **no text was generated.** The model returned a
choice plus a calibrated probability per option. This is the whole point of
Decider 2B — it is a decision head, not a chat model.

**Reproducibility:** the same request was sent three times across two separate
server processes (cold run, cold run's second call, and the warm run). All
three returned **byte-identical** probabilities and the same confidence
(0.6057). The decision is deterministic on CPU.

---

## 10. Latency

| Measurement | Server-side (`latency_ms`) | Client-side (wall clock) |
|---|---|---|
| Decision 1, fresh process | **5,826.81 ms** | 5,866.02 ms |
| Decision 2, same process, same state | **3,702.23 ms** | 3,706.31 ms |
| Decision 1, warm-start process | **5,789.91 ms** | 5,799.92 ms |

The second call on the same process is **~36 % faster** because the server's
`prefix_cache` reuses the KV cache for the repeated state prefix (the state
and instructions are identical; only the question is re-encoded).

**Practical number for the demo: ~3.7 s per decision once the service is warm.**
That is slow enough that the UI must show a "thinking" state, and fast enough
to be tolerable.

**This is CPU-only.** The box has no NVIDIA GPU (`torch` is the `+cpu` build
and no `nvidia-*` packages are installed), so these are the worst-case
numbers. On a CUDA machine the same forward pass would be dramatically
faster.

---

## 11. Resource requirements

| Resource | Measured |
|---|---|
| Peak resident memory, server process + children | **5,589.3 MB (5.6 GB)** |
| Disk, Hugging Face cache | **4,561.7 MB** |
| Disk, venv | **841.3 MB** |
| Disk, total for the spike | **≈ 5.4 GB** |
| CPU | 100 % of one core during a forward pass; no GPU used |
| Network | 4.56 GB one-time download; then **fully offline** |
| Threads | Uvicorn single worker, `workers=1` (the model owns the device) |

**Free RAM is the real constraint, not disk.** The service needs ~5.6 GB
resident. A machine with 8 GB will run it, but not comfortably alongside a
browser and a Node dev server.

---

## 12. A cross-check that did not agree

The same decision was also asked through the CLI:

```powershell
& "$SPIKE\.venv\Scripts\strands-decider.exe" ask `
    "StrandsAgents/strands-decider-2B-qwen3.5-v1-2610" --device cpu --json `
    --state "The user has selected the demo symbol DEMOTECH and asked: ..." `
    --choice "Which single tool should the agent call next to answer the user's request?=get_symbols,get_prices,get_analysis,get_returns,no_action"
```

**The CLI chose `get_prices` (0.434), not `get_analysis` (0.685), with a much
lower confidence of 0.2924.**

This is not a bug and not flakiness — it is a **different prompt**. The CLI's
`--choice` flag can only carry option *names*; it has no way to express the
`criteria` descriptions. The rendered prompt had **138 input tokens** instead
of 196, because the five option descriptions were missing. A model reading
bare names `get_prices|get_analysis|get_returns` has no way to know that
`get_analysis` is the one that returns volatility.

**Two conclusions, both important for Part 3:**

1. **The HTTP API is the interface to use.** It carries `criteria`
   descriptions; the CLI does not. The richer prompt produced both the better
   answer and roughly twice the confidence.
2. **The answer is sensitive to how the options are described.** The option
   descriptions are not decoration — they are what makes the choice
   well-posed. The backend must pass real, specific descriptions for every
   tool, not just names. This is a design constraint on the tool registry, not
   an implementation detail.

---

## 13. Rough edges and open questions

1. **The `serve` process has no authentication and binds `127.0.0.1` by
   default.** Keep it on the loopback. If it is ever bound to `0.0.0.0`,
   anyone who can reach the port can drive the model.
2. **`strands_decider.__version__` is `0.1.0` but the distribution is
   `0.2.0`.** Cosmetic, but it means you cannot trust `__version__` to
   identify what is installed. Use `pip show strands-decider`.
3. **28 s warm start.** The service has to be started before a demo, not
   during one. A tiny "is the Decider up?" pre-flight check at app start
   would make the demo smoother.
4. **~3.7 s per decision on CPU.** The agent loop will feel slow if it makes
   several Decider calls in sequence. Consider one Decider call per user
   request, not one per tool.
5. **`prefix_cache` gives a real speedup** (~36 %) when the state prefix is
   repeated. If the agent sends a *different* state every turn, that speedup
   disappears. Worth keeping the state format stable between turns.
6. **Not measured:** the effect of `--max-batch` / `--max-batch-tokens` on
   latency for long states; behaviour on a CUDA machine; the vision tower
   (`--vision`); and the `noul` and `score` question types. The `choice` type
   is the one this project needs first.
7. **Not measured:** whether the 4.56 GB download would succeed on a
   restricted corporate network. It worked here over a normal connection.

---

## 14. What this means for the Part 3 integration

The Windows approach documented in `docs/decision-pattern.md` is **validated
by this spike**:

```
backend (FastAPI, its own venv, no torch)
    │  HTTP POST http://127.0.0.1:8100/v1/systemone
    ▼
strands-decider serve  (separate Python 3.12 venv, owns the weights)
```

- The backend venv stays free of `torch` — confirmed, the backend venv was
  never modified.
- The contract is small and stable: one POST, one JSON body, one JSON
  response with a choice and calibrated probabilities.
- The backend should send **rich `criteria` descriptions** for every tool.
- The backend should surface `probabilities` and `confidence`, not just the
  winning choice — that is the interesting part of the Decider, and it is
  what makes the decision auditable.
- The decision latency (~3.7 s warm) and the 28 s startup should be visible
  to the user, not hidden.

---

## 15. What this spike did **not** do

- Did not modify `backend/requirements.txt`, any backend application file, or
  `README.md`.
- Did not add the Strands agent, Bedrock calls, virtual trading, or any
  frontend feature.
- Did not fake, simulate, or mock the decision — every number in
  [§9](#9-the-real-decision-over-http) came from the real model over real
  HTTP.
- Did not claim a benchmark it did not run. The latency figures are three
  real requests on this machine, CPU-only.

---

## 16. Files in this spike

| Path | What it is |
|---|---|
| `experiments/decider-spike.md` | This report |
| `experiments/decider-spike/.venv/` | The isolated Python 3.12 environment (841 MB, git-ignored) |
| `experiments/decider-spike/hf-cache/` | The Hugging Face cache, 4.56 GB (git-ignored) |
| `experiments/decider-spike/scripts/run_spike.py` | Cold-run driver: start, wait for `/health`, take two decisions, record timings |
| `experiments/decider-spike/scripts/warm_start.py` | Warm-run driver: restart with the cache populated, measure startup and one decision |
| `experiments/decider-spike/spike-result.json` | Raw output of the cold run |
| `experiments/decider-spike/warm-start-result.json` | Raw output of the warm run |
| `experiments/decider-spike/serve.log`, `serve-warm.log` | Server stdout/stderr — **git-ignored** |
| `experiments/decider-spike/pip-install.log`, `install-report.json` | Install log and pip's dependency report — **git-ignored** |
| `experiments/decider-spike/dryrun-report.json` | Pre-download disk/size check — **git-ignored** |

To reproduce from scratch:

```powershell
$SPIKE = "C:\Users\DELL\OneDrive\Desktop\Crezy Dev\Local\MarketQuest-AI\MarketQuest-AI\experiments\decider-spike"
py -3.12 -m venv "$SPIKE\.venv"
& "$SPIKE\.venv\Scripts\python.exe" -m pip install "strands-decider[cpu]"
& "$SPIKE\.venv\Scripts\python.exe" -I "$SPIKE\scripts\run_spike.py"
& "$SPIKE\.venv\Scripts\python.exe" -I "$SPIKE\scripts\warm_start.py"
```

---

## 17. Sources

- Hugging Face model API for the adapter (revision, file sizes):
  `https://huggingface.co/api/models/StrandsAgents/strands-decider-2B-qwen3.5-v1-2610?blobs=true`
- Hugging Face model API for the base model:
  `https://huggingface.co/api/models/Qwen/Qwen3.5-2B-Base`
- Installed package source, read locally for the HTTP contract:
  `.venv/Lib/site-packages/strands_decider/server.py`,
  `.venv/Lib/site-packages/strands_decider/schema.py`,
  `.venv/Lib/site-packages/strands_decider/cli.py`
- `strands-decider --help`, `serve --help`, `ask --help`
- Existing project research: [`docs/decision-pattern.md`](../docs/decision-pattern.md)
