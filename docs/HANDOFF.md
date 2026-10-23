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
| **Bedrock research** | Done | Plan + citations, verified against the live AWS docs |
| **Part 3 (Decider half)** | **Done, verified against the running model** | `POST /agent/decide`: the Decider chooses the tool, the backend runs it |
| **Part 4 (Bedrock half)** | **Implemented, tested with mocks. Not live** | The same endpoint now explains the numbers. No AWS call has been made. |
| **Submission-readiness pass** | **Done** | README, `architecture.md` and the licence notes rewritten to match the code; local machine paths removed; the stale frontend agent types replaced with the real ones. Nothing staged, nothing committed. |

Committed as `1a6071d` → `4a76851` → `df2988d` → `b7f1072`. The Part 3 work
is committed. **The Part 4 work and the documentation pass are in the working
tree, uncommitted.**

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
backend   pytest          -> 105 passed, 1 warning (7.3s)
          46 pre-existing + 21 in tests/test_agent.py + 38 in tests/test_bedrock.py
          (warning is Starlette/httpx deprecation - pre-existing, not ours)

frontend  npm run build   -> tsc --noEmit && vite build   PASSED
          (the submission pass replaced the stale provisional agent types in
          frontend/src/types/agent.ts, so the build was re-run: tsc clean,
          23 modules, 233 kB JS / 74 kB gzipped)
```

The 21 agent tests mock the HTTP boundary with `httpx.MockTransport`, so the real
client code — request body, response parsing, error mapping — is exercised
without loading the model or running any inference. They cover: successful
selection, each tool executing correctly, an invalid choice, a timeout, an
unavailable service, a malformed answer, a non-choice answer, non-JSON, the
`no_action` path, empty-question and unknown-symbol validation, symbol
normalisation, the status endpoint, and the loopback-only URL rule.

The 38 Bedrock tests mock the AWS boundary with a fake `bedrock-runtime`
client. The **real** `BedrockClient` sits in front of the fake, so the request
building, response parsing and AWS error mapping all run — without a
credential and without a billable call. The fixture is **autouse**, so no test
in the suite can reach AWS.

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

## 4. Bedrock — implemented, blocked on the account

**The code is written and covered by mocked tests. No AWS call has ever been
made; no credential has been read, printed, or created.** Detail:
[`bedrock-research.md`](bedrock-research.md) §10.

What works today, end to end: the Decider picks the tool, the backend runs it,
and `POST /agent/decide` then asks Bedrock to explain the numbers. What does
not work is the one thing that needs the account.

| # | Blocker | Owner |
|---|---|---|
| 1 | No AWS profile or SSO configured — CLI not installed, no `~/.aws/config` or `credentials` on this machine | You |
| 2 | No IAM policy granting `bedrock:Converse` (and `bedrock:InvokeModel`) + read-only discovery actions | You |
| 3 | Anthropic first-time-use form not submitted for the account | You |
| 4 | Region choice — `ap-south-1` is natural, but Claude 5.5 there is **Global-inference-only**, so `modelId` must be `global.anthropic.claude-haiku-5-5` | You |
| 5 | Model access unverified — `get-foundation-model-availability` not run, because it needs a working profile | You, then us |

`AWS_REGION`, `AWS_PROFILE`, `BEDROCK_MODEL_ID` and the rest already exist in
`backend/.env.example` with working defaults. Never put AWS secrets in
`frontend/.env` — Vite bundles frontend env vars into browser code.

**Until the account is ready, the endpoint still works.** A Bedrock failure
never fails the request and never produces a fabricated explanation: the
decision and the market data come back, and `explanation_status` says what
happened (`unavailable` when Bedrock cannot be used, `failed` when a call was
made and did not produce one).

---

## 5. Open issues

| # | Issue | Severity |
|---|---|---|
| 1 | No AWS profile on this machine — blocks the *live* Bedrock call. The code is ready for it | Blocker |
| 2 | A decision takes 6–9 s on CPU, so any UI needs a waiting state | Known |
| 3 | The `state` prefix is rebuilt per question, so the service's prefix cache rarely helps | Low |
| 4 | `noul` and `score` question types were never exercised — only `choice` | Low |
| 5 | Full licence sweep of the pinned dependency tree not run | Low |
| 6 | Strands `BedrockModel` import path — upstream doc URL 404s | Low |
| 7 | Not measured: `--max-batch` tuning, CUDA latency, the vision tower | Info |
| 8 | DevRelay MCP is unauthenticated — all DEV/MLH tools return "Not connected to MLH", so the community-wisdom lookup could not run. Run `! devrelay login` to enable it | Info |

---

## 6. Next task — make Bedrock live, then submit

**Goal:** get one real Bedrock call through, so the demo shows a genuine
explanation rather than a mocked one.

The code is done. What is left is the account side in §4:

1. Install the AWS CLI v2 and configure a profile or SSO, then
   `aws sso login --profile <name>`.
2. Grant the least-privilege policy in `bedrock-research.md` §5. It now lists
   **both** `bedrock:Converse` and `bedrock:InvokeModel` — the AWS docs name
   each of them, and which one the account needs is unverified.
3. Submit the Anthropic first-time-use form (once per account).
4. Verify access with `aws bedrock get-foundation-model-availability
   --model-id anthropic.claude-haiku-5-5`.
5. Set `AWS_PROFILE` in `backend/.env` and make one `POST /agent/decide` call.
   **Report the intended model, region and cost before the first billable
   call.**

### Also still to do
- Virtual trading and portfolio management (the game layer).
- A demo video under three minutes, and a Builder Center article — both are
  submission requirements, and the measured latency table in §3 is the
  material for the *"Effective use of Decider 2B"* criterion.
- `#strands-decider-2b` + `#tool-selection` tags are already in the README.
- **The frontend has no chat interface.** The explanation is returned by the
  API but nothing displays it yet, so a demo video cannot show it. Adding one
  is the highest-value remaining work.

---

## 7. Repository hygiene

Safe to commit. Verified on 2026-10-23:

- The git index is **empty** — nothing is staged.
- The current change set is **21 paths**: 16 modified, 5 new, all source and
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
- **Local machine paths removed** from the four files that carried them:
  `experiments/decider-spike.md` (2 places) and the `command` field in
  `experiments/decider-spike/spike-result.json` and `warm-start-result.json`.
  They now use a repo-relative or `path\to\...` form.
  **This does not remove them from the existing Git history** — commit
  `df2988d` still contains the absolute path, and rewriting history is not
  worth it for a path that is no longer valid anywhere.

### What the submission pass changed

| File | Change |
|---|---|
| `README.md` | Status header, structure table, environment variables, the `/agent/decide` response example, a rewritten §11 (Bedrock: implemented, not live), Bedrock rows in the error table, the licence section, and the git section |
| `docs/architecture.md` | The Bedrock layer added to the diagram and the rules; the "not built yet" list corrected |
| `docs/decision-pattern.md` | §3 retitled from "planned, not yet implemented" to "implemented in Part 3", and its fallback section corrected — the shipped code rejects an invalid choice and never falls back to a rule, and low-confidence routing to Bedrock is *not* implemented |
| `frontend/src/types/agent.ts` | Replaced the provisional Part 1 placeholder types with types that mirror `backend/app/schemas/agent.py` |
| `frontend/src/services/api.ts` | Replaced `analyzeStock()` — which pointed at `/agent/analyze`, an endpoint that does not exist — with `decide()`, which points at the real `/agent/decide` |
| `experiments/*` | Local absolute paths removed |

The two frontend changes are the only source files the pass touched, and the
frontend build was re-run after them.
