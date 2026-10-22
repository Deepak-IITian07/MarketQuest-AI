# Handoff

**Date:** 2026-10-23 · **Repo:** MarketQuest AI · **Branch:** `main` (origin/main up to date, nothing committed yet)

One-page summary of where the project stands, what was measured, what is
blocked, and what to do next. Full detail lives in the linked documents.

---

## 1. Completed work

| Part | State | Detail |
|---|---|---|
| **Part 1** — scaffold | Done, untouched | FastAPI `/health`, React landing scaffold, config, data generator |
| **Part 2** — market backend | Done, untouched | `/market/*` endpoints, stdlib-only analysis, 46 tests |
| **Part 2** — market dashboard | Done this session | React dashboard reading the three `/market` endpoints |
| **Decider 2B spike** | Done this session | Real model, real HTTP decision, measured |
| **Bedrock research** | Done this session | Plan + citations, nothing implemented |

### What the dashboard does
`frontend/src/pages/Dashboard.tsx` reads **only** `GET /market/symbols`,
`GET /market/prices/{symbol}` and `GET /market/analysis/{symbol}`. It shows a
symbol selector, the latest sample close with two deltas, an SVG price-history
chart with a hover tooltip and a toggleable moving-average overlay, six metric
tiles, and loading / error / empty states. No chart library, no new npm
dependency, no chat widget, no external API, no auth.

**Synthetic-data labelling is in four places:** the "Synthetic demo data" badge,
a `DEMO` tag on each symbol card, the data-source tile showing `synthetic_demo`,
and the footer quoting the backend's own `disclaimer` verbatim.

---

## 2. Test and build results

```
backend   pytest          -> 46 passed, 1 warning (0.90s)
          (warning is Starlette/httpx deprecation - pre-existing, not ours)

frontend  npm run build   -> tsc --noEmit && vite build, built in 201ms
          dist/assets/index-cSMHH8p3.js  233.46 kB | gzip 73.26 kB
          dist/assets/index-H85w7uhX.css   8.34 kB | gzip  2.57 kB
```

Browser-verified against the live backend: the page calls only the three
`/market` endpoints plus `/health`; rendered figures match the API exactly
(₹854.23 / ₹858.58); the chart draws all 30 points; the error state shows an
actionable message and a working retry button; no horizontal scroll at 390 px;
0 console errors.

---

## 3. Decider 2B — verified runtime measurements

**Real inference, not simulated.** Full report: [`../experiments/decider-spike.md`](../experiments/decider-spike.md).

| | |
|---|---|
| Model | `StrandsAgents/strands-decider-2B-qwen3.5-v1-2610` |
| Revision | `216d1ccb46a9e9b036eb9187b248db98480f77d4` |
| Base model | `Qwen/Qwen3.5-2B-Base` (Apache-2.0) |
| Device | CPU only (no NVIDIA GPU on this machine) |
| Startup, cold (incl. 4.56 GB download) | **253.9 s** |
| Startup, warm (weights on disk) | **28.1 s** |
| Decision, first in a process | **5,826.81 ms** |
| Decision, repeat (prefix cache) | **3,702.23 ms** |
| Peak resident memory | **5,589 MB** |
| Disk | 4,561.7 MB cache + 841.3 MB venv |

**The decision that was taken.** Given *"Show me DEMOTECH and tell me how
volatile it has been"*, the model chose **`get_analysis`** (p = 0.6846,
confidence 0.6057) over `get_prices` (0.2234) — correct, since `get_analysis`
returns volatility. Byte-identical across three calls in two separate
processes. It returns a choice and calibrated probabilities, **no text**.

### Two constraints for Part 3
1. **Every tool option needs a real description.** The same question asked
   over HTTP (which carries a description per option) chose `get_analysis` at
   confidence 0.61; asked via the `ask` CLI (bare option names only) it chose
   `get_prices` at 0.29. Descriptions are what make the choice well-posed.
2. **The service has no authentication.** It must stay bound to `127.0.0.1`. If
   it is unreachable, the backend must degrade gracefully and say the decision
   was not made by the model — never fabricate a choice.

---

## 4. Bedrock — blockers

**Nothing implemented. No AWS call has ever been made; no credential has been
read, printed, or created.** Plan: [`bedrock-research.md`](bedrock-research.md).

| # | Blocker | Owner |
|---|---|---|
| 1 | No AWS profile or SSO configured — CLI not installed, no `~/.aws/config` or `credentials` on this machine | You |
| 2 | No IAM policy granting `bedrock:Converse` + read-only discovery actions | You |
| 3 | Anthropic first-time-use form not submitted for the account | You |
| 4 | Region choice — `ap-south-1` is natural, but Claude 5.5 there is **Global-inference-only**, so `modelId` must be `global.anthropic.claude-haiku-5-5` | You |
| 5 | Model access unverified — `get-foundation-model-availability` not run, because it needs a working profile | You, then us |

Afterwards set `AWS_REGION`, `AWS_PROFILE`, `BEDROCK_MODEL_ID` in `backend/.env`
(the placeholders already exist). Never put AWS secrets in `frontend/.env` —
Vite bundles frontend env vars into browser code.

---

## 5. Open issues

| # | Issue | Severity |
|---|---|---|
| 1 | No AWS profile on this machine — blocks all Bedrock work | Blocker |
| 2 | Decider not wired into the backend — Part 3 unstarted | Expected |
| 3 | Python 3.14 wheels for `torch`/`transformers` untested; moot (Decider venv is 3.12) | Low |
| 4 | Full licence sweep of the pinned dependency tree not run | Low |
| 5 | Gemma 4 checkpoint install path still unverified; does not affect the 2B Qwen3.5 path | Low |
| 6 | Strands `BedrockModel` import path — upstream doc URL 404s | Low |
| 7 | Not measured: `noul` / `score` question types, `--max-batch` tuning, CUDA latency, vision tower | Info |
| 8 | DevRelay MCP is unauthenticated — all DEV/MLH tools return "Not connected to MLH", so the community-wisdom lookup could not run. Run `! devrelay login` to enable it | Info |

---

## 6. Next task — Part 3 integration

**Goal:** the backend uses Decider 2B for at least one meaningful decision,
paired with Amazon Bedrock. That pairing is the hackathon submission
requirement — Decider alone is not enough.

### 6.1 The Decider side (no blockers — start here)

The venv and weights are already on disk, so this costs no new install.

1. **Start the service** (separate venv, binds loopback only):
   ```powershell
   $SPIKE = "path\to\MarketQuest-AI\experiments\decider-spike"
   $env:HF_HOME = "$SPIKE\hf-cache"
   & "$SPIKE\.venv\Scripts\strands-decider.exe" serve `
       StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --host 127.0.0.1 --port 8100 --device cpu
   ```
   Cold start is ~4 min (downloads); warm start is 28 s. **Start it before a
   demo, not during one.**

2. **Add a Decider client to the backend.** `httpx` is already a backend
   dependency — no new package needed. Keep it in `app/services/`, with a
   `POST http://127.0.0.1:8100/v1/systemone` wrapper, a short timeout, and
   graceful degradation when the service is down.

3. **Build the tool registry** with a real description per tool. This is the
   single most important input to the model's quality — see §3, constraint 1.
   Candidate tools, matching the existing endpoints:
   `get_symbols`, `get_prices`, `get_analysis`, `get_returns`, plus a
   `no_action` option.

4. **Add one endpoint** (e.g. `POST /agent/analyze`) that asks the Decider
   which tool to call, validates the answer against the offered option set,
   executes that tool against the existing service layer, and returns both the
   result **and** the Decider's probabilities and confidence.

5. **Surface the decision.** Return the probabilities and confidence, not just
   the winning choice — that is the interesting part of the Decider and it is
   what makes the decision auditable. The frontend already has an error state
   and a retry button ready for the ~3.7 s decision latency.

### 6.2 The Bedrock side (blocked on §4)

Only start once the AWS account-side items are done. The research doc has a
minimal, credential-safe `converse()` example and the prompt shape: the Decider
chooses the tool, Bedrock explains the numbers that tool produced. Bedrock must
never choose the tool, and must never invent a number.

### 6.3 Also still to do
- Virtual trading and portfolio management (the game layer).
- A demo video under three minutes, and a Builder Center article — both are
  submission requirements, and the measured latency table in §3 is the
  material for the *"Effective use of Decider 2B"* criterion.
- `#strands-decider-2b` + `#tool-selection` tags are already in the README.

---

## 7. Repository hygiene

Safe to commit. Verified on 2026-10-23:

- The git index is **empty** — nothing is staged yet.
- 22 paths in the change set: 14 new files (largest is `docs/bedrock-research.md`
  at 30 KB) and 8 modified or deleted tracked files. Total well under 200 KB.
- **Not tracked and not tracked-by-accident:** `backend/.env`, `frontend/.env`,
  every `.venv/`, `node_modules/`, `frontend/dist/`,
  `experiments/decider-spike/hf-cache/` (4.56 GB), the spike logs, and the pip
  reports. All are covered by `.gitignore` and confirmed with
  `git check-ignore -v`.
- The two `.env.example` files **are** tracked, by design. Every AWS value in
  them is an empty placeholder; the only non-empty values are `APP_ENV`,
  `CORS_ORIGINS` and `VITE_API_BASE_URL`.
- A pattern scan (AWS key IDs, private keys, bearer tokens, GitHub/Slack/OpenAI
  tokens, JWTs) across all 22 changed files found **nothing**.
- The on-disk `.env` files contain **0** non-empty secret-ish assignments.

Local-only artifacts still on disk (safe to delete later, not tracked):
`experiments/decider-spike/.venv/` (841 MB), `experiments/decider-spike/hf-cache/`
(4.56 GB), `backend/.venv/`, `frontend/node_modules/`, `frontend/dist/`.
