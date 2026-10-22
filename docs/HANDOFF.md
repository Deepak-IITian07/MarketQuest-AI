# Handoff

**Date:** 2026-10-23 · **Repo:** MarketQuest AI · **Branch:** `main`

Where the project stands, what was measured, what is blocked, and what to do
next. Full detail lives in the linked documents.

---

## 1. Completed work

| Part | State | Detail |
|---|---|---|
| **Part 1** — scaffold | Done | FastAPI `/health`, React scaffold, config, data generator |
| **Part 2** — market backend | Done | `/market/*` endpoints, stdlib-only analysis, 46 tests |
| **Part 2** — market dashboard | Done | React dashboard reading the three `/market` endpoints |
| **Decider 2B spike** | Done | Real model, real HTTP decision, measured |
| **Bedrock research** | Done | Plan + citations, nothing implemented |
| **Part 3 (Decider half)** | **Done, verified against the running model** | `POST /agent/decide`: the Decider chooses the tool, the backend runs it |

Committed as `1a6071d` → `4a76851` → `df2988d`. The Part 3 work is in the
working tree, uncommitted.

### What Part 3 added

```
POST /agent/decide
   -> app/agent/decider.py    HTTP client for the local Decider service
   -> app/agent/tools.py      the allowlist of read-only market operations
   -> app/agent/runner.py     ask the model, check the answer, run the tool
   -> app/services/market_queries.py   response builders shared with /market
   -> app/api/agent.py        the endpoint + GET /agent/status
```

The model chooses a **tool name** and nothing else. The name is looked up by
exact match in a fixed allowlist; anything else is rejected with
`502 invalid_decision` and never executed. Every tool is read-only.

**The dashboard is unchanged** — no frontend chat interface was added, as
instructed.

---

## 2. Test and build results

```
backend   pytest          -> 67 passed, 1 warning (1.83s)
          46 pre-existing + 21 new in tests/test_agent.py
          (warning is Starlette/httpx deprecation - pre-existing, not ours)

frontend  npm run build   -> tsc --noEmit && vite build, built in 264ms
          dist/assets/index-cSMHH8p3.js  233.46 kB | gzip 73.26 kB
          dist/assets/index-H85w7uhX.css   8.34 kB | gzip  2.57 kB
          (byte-identical to the Part 2 build - no frontend file was touched)
```

The 21 new tests mock the HTTP boundary with `httpx.MockTransport`, so the real
client code — request body, response parsing, error mapping — is exercised
without loading the model or running any inference. They cover: successful
selection, each tool executing correctly, an invalid choice, a timeout, an
unavailable service, a malformed answer, a non-choice answer, non-JSON, the
`no_action` path, empty-question and unknown-symbol validation, symbol
normalisation, the status endpoint, and the loopback-only URL rule.

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
| Decision through `/agent/decide` | **6,384 – 8,546 ms** (5 real calls) |
| Peak resident memory | **5,589 MB** |
| Disk | 4,561.7 MB cache + 841.3 MB venv |

### Real decisions taken through the endpoint

| Question | Chose | p | Confidence |
|---|---|---:|---:|
| "Tell me how volatile DEMOTECH has been." | `get_analysis` | 0.7565 | 0.6956 |
| "Show me the full daily price history for DEMOBANK…" | `get_prices` | 0.9807 | 0.9759 |
| "What symbols are available to look at?" | `get_symbols` | 0.8587 | 0.8233 |
| "How much did DEMOENERGY gain or lose day to day?" | `get_returns` | 0.6341 | 0.5426 |
| "What is the weather in Mumbai tomorrow?" | `no_action` | 0.8254 | 0.7817 |

The model discriminates — it is not always picking the same tool — and it
correctly declines to fetch data for a question no tool can answer.

### Two constraints the implementation respects

1. **Every tool option needs a real description.** The spike asked the same
   question over HTTP (which carries a description per option) and via the
   `ask` CLI (bare option names only). With descriptions the model chose
   `get_analysis` at confidence 0.61; with bare names it chose `get_prices` at
   0.29. Descriptions are what make the choice well-posed, so every entry in
   `app/agent/tools.py` has one.
2. **The service has no authentication.** It stays bound to `127.0.0.1`, and
   `DECIDER_BASE_URL` is validated at startup — a non-loopback host is refused.
   If the service is unreachable, the backend says so and never fabricates a
   choice.

### Failure behaviour

| Status | `error` | Meaning |
|---|---|---|
| `400` | `missing_symbol` | The chosen tool needs a symbol and none was given. The model's choice is still reported. |
| `502` | `invalid_decision` | The model named something not on the allowlist. |
| `502` | `invalid_response` | The service answered with something that was not a choice. |
| `503` | `decider_timeout` | No answer within `DECIDER_TIMEOUT_SECONDS` (default 15). |
| `503` | `decider_unavailable` | The service could not be reached. |

Every failure body has `"decision_made": false` and a message that says in
words that the model did not make a usable decision.

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
| 2 | A decision takes 6–9 s on CPU, so any UI needs a waiting state | Known |
| 3 | The `state` prefix is rebuilt per question, so the service's prefix cache rarely helps | Low |
| 4 | `noul` and `score` question types were never exercised — only `choice` | Low |
| 5 | Full licence sweep of the pinned dependency tree not run | Low |
| 6 | Strands `BedrockModel` import path — upstream doc URL 404s | Low |
| 7 | Not measured: `--max-batch` tuning, CUDA latency, the vision tower | Info |
| 8 | DevRelay MCP is unauthenticated — all DEV/MLH tools return "Not connected to MLH", so the community-wisdom lookup could not run. Run `! devrelay login` to enable it | Info |

---

## 6. Next task — Part 3, the Bedrock half

**Goal:** Bedrock explains the numbers the Decider's chosen tool produced.
The Decider chooses the tool; Bedrock only explains. Bedrock must never
choose a tool and must never invent a number.

Blocked on §4. When the AWS side is ready:

1. Add `boto3` to `backend/requirements.txt` (it is the only new dependency;
   `boto3` is not installed yet and nothing was installed for this).
2. Add a `app/services/bedrock.py` that calls `bedrock-runtime` `converse`
   with the analysis result supplied as data, and returns a plain-text
   explanation. The research doc has a minimal, credential-safe example.
3. Extend the agent flow: the Decider picks the tool, the tool runs, and
   Bedrock turns the result into an explanation. Return both the model's
   probabilities and the explanation, so the decision is still auditable.
4. Keep the synthetic-data warning in the Bedrock prompt. The model must not
   present demo prices as real quotes.
5. Never log or echo the AWS credentials, and never let a Bedrock failure
   produce a fabricated explanation — say the explanation was not generated.

### Also still to do
- Virtual trading and portfolio management (the game layer).
- A demo video under three minutes, and a Builder Center article — both are
  submission requirements, and the measured latency table in §3 is the
  material for the *"Effective use of Decider 2B"* criterion.
- `#strands-decider-2b` + `#tool-selection` tags are already in the README.

---

## 7. Repository hygiene

Safe to commit. Verified on 2026-10-23:

- The git index is **empty** — nothing is staged.
- The current change set is **16 paths**: 9 modified, 7 new, all source and
  documentation.
- **Not tracked and not tracked by accident:** `backend/.env`, `frontend/.env`,
  every `.venv/`, `node_modules/`, `frontend/dist/`,
  `experiments/decider-spike/hf-cache/` (4.56 GB), the spike logs and pip
  reports, and every `__pycache__/`. All are covered by `.gitignore` and
  confirmed with `git check-ignore -v`.
- The two `.env.example` files **are** tracked, by design. Every AWS value in
  them is an empty placeholder.
- No credential-shaped strings (AWS key IDs, private keys, bearer tokens,
  GitHub/Slack/OpenAI tokens, JWTs) in any changed file.

Local-only artifacts still on disk (safe to delete later, not tracked):
`experiments/decider-spike/.venv/` (841 MB), `experiments/decider-spike/hf-cache/`
(4.56 GB), `backend/.venv/`, `frontend/node_modules/`, `frontend/dist/`.
