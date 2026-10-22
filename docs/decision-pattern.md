# Decision pattern: `#tool-selection` + Strands Decider 2B research

**Status: Part 2 research complete, and the runtime spike has now verified the
setup end to end on this machine. The Decider is NOT yet integrated into the
backend.**

This file has two parts:

1. **Verified findings** on Strands Decider 2B — what was checked, against which
   official source, and on what date. Everything in this section was read from
   the official repositories listed in [Sources](#sources). Anything that could
   not be confirmed is in [Unresolved questions](#unresolved-questions) and is
   clearly marked.
2. **The decision pattern** this project will use, and the **recommended
   integration approach** for a Windows development machine.

Research performed on **2026-10-23**. Model and package versions move fast, so
re-check the sources before the Part that actually wires the model in.

> **Runtime verification (added after the spike).** The setup described in
> [§2](#2-recommended-integration-approach-windows) has now been run for real on
> this machine: the model was installed in a separate Python 3.12 venv, the
> service was started on CPU, and a real tool-selection decision was taken over
> HTTP. Measured startup, latency, memory and the exact request/response are in
> [`experiments/decider-spike.md`](../experiments/decider-spike.md). Several
> questions in [Unresolved questions](#unresolved-questions) are answered by
> that run; they are marked **RESOLVED** below.

## 1. Verified findings

### 1.1 The model

| Field | Value | Source |
|---|---|---|
| Hub repo id | `StrandsAgents/strands-decider-2B-qwen3.5-v1-2610` | HF API |
| Exact revision (sha) | `216d1ccb46a9e9b036eb9187b248db98480f77d4` | HF API `sha` |
| Last modified | `2026-10-09T22:55:03Z` | HF API `lastModified` |
| Weight licence | **Apache-2.0** | HF metadata `license: apache-2.0`; repo `LICENSE.md` contains the full Apache 2.0 text |
| Base model | `Qwen/Qwen3.5-2B-Base` | HF metadata `base_model:` tag |
| Base model licence | **Apache-2.0** | HF metadata `license: apache-2.0`, `licenseLink` → Qwen licence |
| Base model revision | `b1485b2fa6dfa1287294f269f5fb618e03d52d7c` | HF API |
| Pipeline tag | `text-classification` | HF API |
| Architecture | LoRA-adapted decoder torso + a pointer/readout head, **not** a language-model head | Model card + `LICENSE.md` |

**The repo does not contain full weights.** It ships `lora/adapter_model.safetensors`
(a rank-48 averaged PEFT adapter), `head.safetensors` (the readout head), the
tokenizer, `provenance.json`, `MANIFEST.sha256`, plus `training/` and `eval/`
artefacts. The base weights (`Qwen/Qwen3.5-2B-Base`, ~2B params) are pulled from
the Hub at first use, so a first run needs network access and several GB of disk.

### 1.2 Question types and inference

The model is a **decision** model, not a text generator. It supports three
question types: `choice` (pick one option), `noul` (yes/no), and `score` (a value
on an ordered rubric). The README describes inference as *"One forward pass, no
generation, no decoding loop."*

Three documented ways to run it:

1. **CLI** — `strands-decider ask <model-id> --state "<text>" --choice "<question>"`
2. **Local HTTP server** — `strands-decider serve <model-id> --port 8000`, which
   listens on `127.0.0.1` and accepts `POST /v1/systemone` with a JSON body
   containing `state` and a `questions` object. **No authentication** — it is
   intended for local experiments only.
3. **Python** — `strands_decider.modeling.StrandsDeciderModel.load(...)`

Supported devices: `cpu`, `cuda`, `mps`, `mlx`.

### 1.3 Packages and licences

| Package | Version | Licence | Notes |
|---|---|---|---|
| `strands-decider` | **0.2.0** (released 2026-10-19) | **Apache-2.0** (`license_expression`) | `requires-python >= 3.10` |
| `strands-agents` | 1.62.0 | **Apache-2.0** | `requires-python >= 3.10`; pulls in `boto3`/`botocore` for Bedrock |
| `strands-labs/strands-decider` (source) | `main` | **Apache-2.0** | 35 commits; no release tag exposed on the page |

`strands-decider` runtime dependencies (from PyPI metadata):

```
torch>=2.7
transformers<6,>=5.15
peft>=0.21
accelerate>=0.34
huggingface_hub>=1.5
pydantic>=2.7
typer>=0.12
rich>=13.7
pyyaml>=6.0
fastapi>=0.115
uvicorn[standard]>=0.30
numpy>=1.24
safetensors>=0.4
```

Extras: `train`, `vision`, `mlx`, `cuda`, `mps`, `cpu`, `dev`. Two of these are
platform-gated in the metadata:

- `mlx` → `mlx>=0.32.2`, `mlx-lm<0.33,>=0.32`, only when
  `sys_platform == "darwin" and platform_machine == "arm64"`.
- `cuda` → `flash-linear-attention>=0.5`, only when `sys_platform == "linux"`.

`vision` adds `pillow>=10` and requires `transformers` 5.18 or later. The `cpu`,
`mps` and `train` extras declare **no extra requirements of their own** beyond
the base list (plus `datasets>=2.20` for `train`).

### 1.4 Training-data terms (relevant if the dataset is ever redistributed)

`LICENSE.md` states the model was trained on public datasets under Apache-2.0,
MIT, BSD-3-Clause, CC0-1.0, CC-BY 4.0 and CC-BY-SA (3.0/4.0), plus some sources
with custom or unstated terms. **Some sources are ShareAlike** (SQuAD 2.0, SNLI,
ShARC, FEVER, and 2WikiMultihopQA's Wikipedia text). Synthetic rows were
generated by `google/gemma-4-31B-it` (Apache-2.0). The licence advises reading a
source's own terms before redistributing data built on it. This affects the
*dataset*, not our use of the model — but it must be respected if the training
data is ever published.

### 1.5 Hardware and performance

Published figures from the upstream README (Gemma 4 family, bf16 weights, one H100):

| Model | Weight VRAM | Median H100 latency |
|---|---:|---:|
| `strands-decider-E2B-gemma4-v1-2610` | ~9 GB | 102 ms |
| `strands-decider-E4B-gemma4-v1-2610` | ~15 GB | 139 ms |
| `strands-decider-12B-gemma4-v1-2610` | ~23 GB | 136 ms |
| `strands-decider-26B-A4B-gemma4-v1-2610` | ~51 GB | 245 ms |

The original 2B family reports a **median ~115 ms per JevBench question on an
RTX 3090**. The README states that all four Gemma 4 variants *"serve on CPU"*
and that the 2B family *"serves on an Apple-silicon Mac or on CPU"*, with the
smallest model recommended *"where memory is tightest, or on CPU"*.

### 1.6 Hackathon rules (Agent Experience Hackathon)

Checked against the official rules tab. Requirements that affect how we build:

- The submission must be **"An agent that uses Strands Decider 2B for at least one
  meaningful decision, paired with Amazon Bedrock."** Decider 2B alone is not enough.
- Decider 2B is **"an innovation and experimentation starter, not a production
  product."** Its confidence output is only presented as reliable for short,
  previously unseen classification tasks; the README advises *"below that, confirm
  or ask a person."* JevBench has 231 tasks and *"a difference under about 10
  tasks between two single runs [is] unresolved."*
- One of five decision patterns must be demonstrated: **tool selection,
  guardrails, policy, model routing, or context/memory.** This project uses
  **tool selection**.
- Submission artefacts: a Builder Center article, a **public repository** with
  *"at least one reusable Decider 2B decision pattern others can use in their own
  agents"*, and a **public demo video under three minutes**.
- Tags: `#strands-decider-2b` plus one pattern tag.
- *"An original agent that has not been published before."* Entrants must be 18+
  with a Builder Center profile.
- Judging: creativity 30%, effective use of Decider 2B 30% (*"A measured latency
  or cost improvement counts as a bonus here"*), communication 25%, originality 15%.
- No rule requires hosted inference, and no additional restriction on the model's
  licensing or commercial use is stated on that page. The rules call the model
  *"small, open, experimental."*

### 1.7 Licensing summary

Everything we would depend on is **permissive (Apache-2.0)**: the model weights,
the base model, the `strands-decider` package, the `strands-labs/strands-decider`
source, and `strands-agents`. The transitive runtime dependencies
(`torch`, `transformers`, `peft`, `accelerate`, `safetensors`, `huggingface_hub`,
`typer`, `rich`, `pyyaml`, `numpy`) are permissively licensed as well, though we
have not enumerated each one in this pass — `torch` in particular is BSD-3-Clause
and `transformers` is Apache-2.0, but treat that as an assumption until checked
against the exact pinned versions we install.

The one caveat is not a licence but a **terms** issue: the model's own licence
file flags ShareAlike training sources. That constrains redistribution of
*derived datasets*, not our use of the model.

**No credentials or secrets were used, exposed, or committed during this research.**
Everything above came from public, unauthenticated reads.

---

## 2. Recommended integration approach (Windows)

### Constraints that shape the recommendation

- The backend venv is Python **3.14.5**; `strands-decider` supports `>=3.10`, but
  `torch>=2.7` and `transformers>=5.15` wheels for 3.14 on Windows are **not
  confirmed** to exist yet. `py -3.12` is also installed on this machine.
- `strands-decider` pulls in `torch`, `transformers`, `peft`, `accelerate` and
  `numpy` — a heavyweight install that the Part 2 brief explicitly excludes.
- The documented `cuda` extra's `flash-linear-attention` dependency is
  **Linux-only**, and it is a training dependency, not an inference one.
- CPU inference is documented as supported, but no native-Windows procedure is
  documented anywhere upstream.

### Recommendation

**Run Decider in a separate virtual environment and talk to it over HTTP.**

1. A dedicated venv (Python 3.12, *not* the backend venv):
   ```powershell
   python -m venv .venv-decider      # run with py -3.12
   .\.venv-decider\Scripts\Activate.ps1
   pip install "strands-decider[cpu]"
   ```
2. Start the model as a local server:
   ```powershell
   strands-decider serve StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --port 8100
   ```
   It binds `127.0.0.1` only and has no auth, so it must never be exposed beyond
   the loopback interface.
3. The FastAPI backend calls `POST http://127.0.0.1:8100/v1/systemone` with
   `httpx` — already a project dependency — using the `state` + `questions`
   payload. If the Decider server is not running, the backend must **degrade
   gracefully** (skip the decision, say so) rather than fail the request or
   fabricate a choice.

**Why this shape:**

- Keeps `torch`/`transformers` out of the backend venv, so `pytest` stays fast
  and the backend image stays small.
- `serve` loads the model once; the per-decision cost is then a single forward
  pass instead of paying model load per request, which is what the `ask` CLI
  would cost. **Measured on this machine (CPU, no GPU): 5.8 s for the first
  decision in a process and 3.7 s for a repeat** — seconds, not milliseconds.
  The ~115 ms figure published upstream is an RTX 3090 number and must never be
  quoted for CPU. See [`experiments/decider-spike.md`](../experiments/decider-spike.md).
- A local HTTP boundary is also the seam where a hosted endpoint can be swapped
  in later without changing the agent code.

**Fallbacks, in order of preference:**

- **WSL2 + NVIDIA GPU** — the upstream-documented path for training, and the
  best latency for inference. Only relevant if this machine has an NVIDIA GPU.
- **CPU in the separate venv** — the baseline. Expect seconds, not milliseconds,
  per decision on CPU; the ~115 ms figure is an RTX 3090 number and must not be
  quoted for CPU.
- **`ask` CLI as a subprocess** — simplest fallback, but it reloads the model per
  call. Only viable for a demo, not for a loop.

**Do not** install `strands-decider` into `backend/.venv` for Part 3. If the
backend needs to import it, the venv split has to be revisited deliberately.

---

## 3. The decision pattern (planned, not yet implemented)

**Purpose:** given a user's stock question and a structured list of analysis
tools, select the next appropriate tool, or a valid **no-action** option when
none applies.

### Input
- A `state` string: the user question plus the current agent context.
- A `questions` object containing one `choice` question whose options are the
  candidate tool ids, plus a `no_action` option.
- **Every option must carry a description.** The API takes
  `criteria: {option_id: description}`. The spike showed this is not optional:
  with descriptions the model chose the right tool at confidence 0.61, and with
  bare option names it chose a different tool at confidence 0.29. The
  descriptions are what tell the model *what each tool returns*.

### Output
- Exactly one tool id, or `no_action`. No free text — the model does not generate
  prose, and Bedrock does that separately.

### Fallback / validation
- The chosen tool must be a member of the offered option set. Anything else is
  rejected and the agent falls back to `no_action`.
- If the Decider server is unreachable or times out, fall back to a
  deterministic rule (or `no_action`) and record that the decision was not made
  by the model. **Never fake a Decider decision.**
- The Decider's confidence is advisory only. Per the upstream README, treat
  low-confidence decisions as "confirm or ask a person" — so the pattern should
  route low-confidence cases to Bedrock for a clarifying explanation, not to a
  tool call.

### Example decisions
Against the four bundled demo symbols (`DEMOTECH`, `DEMOBANK`, `DEMOPHARMA`,
`DEMOENERGY`):

- *"Show me DEMOTECH and tell me how volatile it has been."* → `get_analysis`
  (verified by the spike: chosen with p = 0.6846, confidence 0.6057)
- *"What is the average volume for DEMOPHARMA?"* → `get_prices`
- *"List every demo company."* → `get_symbols`
- *"Show me the daily returns for DEMOBANK."* → `get_returns`
- *"Should I buy DEMOTECH right now?"* → `no_action` (out of scope: this project
  does not give investment advice, and trading is not implemented)

### Reuse guidance
The pattern is deliberately small: **one choice question, one valid fallback,
strict validation of the output against the offered options.** That is enough to
be reusable in another agent without pulling in the rest of this project.

---

## Unresolved questions

Marked honestly. **RESOLVED** items were answered by the runtime spike
([`experiments/decider-spike.md`](../experiments/decider-spike.md)); the rest
were **not** confirmed and still are not.

1. **Native Windows support. — RESOLVED.** It works. `strands-decider[cpu]`
   installed cleanly on native Windows 11 with Python 3.12.6, and
   `transformers` 5.20.2 loaded the Qwen3.5 architecture on CPU without any
   patch. WSL2 is not required for inference.
2. **Python 3.14 wheels. — STILL UNRESOLVED.** Whether `torch>=2.7` and
   `transformers>=5.15` publish Windows wheels for Python 3.14 was not tested.
   It does not matter for us: the Decider venv uses Python 3.12, so the
   question is avoided entirely.
3. **The `cpu` extra's contents. — RESOLVED.** It adds no requirements of its
   own, exactly as the PyPI metadata suggested. The resolved tree contained
   **no `nvidia-*` packages at all**, and the Windows `torch` wheel is already
   the CPU build (`2.14.1+cpu`). Installing `[cpu]` documents the intent; it
   does not change the dependency set.
4. **Base model download size and gating. — RESOLVED.** `Qwen/Qwen3.5-2B-Base`
   is **4,571,206,192 B (≈ 4.57 GB)** and is **not** gated behind an access
   request — it downloaded anonymously. The adapter repo adds 224 MB. Total
   cache on disk: **4,561.7 MB**. The first run therefore needs ~4.6 GB of
   disk and one network fetch; every run after that is offline.
5. **CPU latency on this machine. — RESOLVED.** Measured: **5,826.81 ms** for
   the first decision in a process, **3,702.23 ms** for a repeat (the server's
   prefix cache reuses the repeated state prefix), and 5,789.91 ms in a fresh
   warm-start process. Startup is **253.9 s cold** (including the download) and
   **28.1 s warm**. Peak server memory: **5,589 MB**. This is the number to
   quote in the Builder Center article — and note it is the *worst* case, since
   this machine has no NVIDIA GPU.
6. **Transitive dependency licences. — STILL UNRESOLVED.** Only the direct
   `strands-decider` dependencies were reviewed in the research pass. The
   installed tree was checked for NVIDIA CUDA packages (there are none), but a
   full licence sweep of the pinned tree has not been run.
7. **Gemma 4 checkpoints. — STILL UNRESOLVED.** The README says Gemma 4
   support is not yet on a normal PyPI release and must be installed from the
   Git repository. Whether that is still true for `0.2.0` was not checked — and
   it does not affect the recommended 2B Qwen3.5 path.
8. **Do the option descriptions matter? — RESOLVED, and yes.** The spike asked
   the same question twice: once through `POST /v1/systemone` (which carries a
   description for every option) and once through the `ask` CLI (whose
   `--choice` flag can only carry option *names*). The HTTP call chose
   `get_analysis` with confidence 0.6057; the CLI, given bare names, chose
   `get_prices` with confidence 0.2924. The option descriptions are not
   decoration — they are what makes the choice well-posed. **The tool registry
   must give every tool a real, specific description.**

### Measured performance (CPU, this machine)

| | |
|---|---:|
| Startup, cold (incl. 4.56 GB download) | 253.9 s |
| Startup, warm (weights on disk) | 28.1 s |
| Decision, first in a process | 5,826.81 ms |
| Decision, repeat (prefix cache) | 3,702.23 ms |
| Peak resident memory | 5,589 MB |
| Decision cost | 196 input tokens, 1 output token (one slot index) |

---

## Sources

All read on 2026-10-23.

- Strands Decider repository — https://github.com/strands-labs/strands-decider
- Strands Decider README (raw) — https://raw.githubusercontent.com/strands-labs/strands-decider/main/README.md
- Hugging Face organisation — https://huggingface.co/StrandsAgents
- Model card (2B Qwen3.5) — https://huggingface.co/StrandsAgents/strands-decider-2B-qwen3.5-v1-2610
- Model licence (raw) — https://huggingface.co/StrandsAgents/strands-decider-2B-qwen3.5-v1-2610/raw/main/LICENSE.md
- Model API (revision, licence, files) — https://huggingface.co/api/models/StrandsAgents/strands-decider-2B-qwen3.5-v1-2610
- Base model API — https://huggingface.co/api/models/Qwen/Qwen3.5-2B-Base
- `strands-decider` on PyPI — https://pypi.org/project/strands-decider/
- `strands-decider` PyPI JSON — https://pypi.org/pypi/strands-decider/json
- `strands-agents` PyPI JSON — https://pypi.org/pypi/strands-agents/json
- Agent Experience Hackathon rules — https://builder.aws.com/build/hackathons/4f50957c-1d08-37ab-b11c-97516b9adeb4/agent-experience-hackathon?tab=rules

Hackathon tags: `#strands-decider-2b` `#tool-selection`
