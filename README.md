# MarketQuest AI

Game-inspired stock-market simulation for Indian stocks. Virtual money only; no real trading.

> **Status: the agent is built. The Decider half is verified against the real
> model; the Bedrock half is implemented and tested with mocks but has never
> made a live AWS call.**
>
> **Working now:** the FastAPI `/health` and `/market/*` endpoints, a React
> market dashboard that reads them, and `POST /agent/decide`, which asks the
> Strands Decider 2B which market tool to run, runs that tool, and then asks
> Amazon Bedrock to explain the numbers it produced.
>
> **Live and verified:** the Decider's tool selection. The model was run for
> real, over local HTTP, and its decisions are recorded in
> [`experiments/decider-spike.md`](experiments/decider-spike.md).
>
> **Implemented but not live:** Amazon Bedrock. The code, the prompts and the
> error handling are done and covered by 38 mocked tests, but this machine has
> no AWS profile, so **no AWS call has ever been made**. Until an AWS account
> is configured, `/agent/decide` returns the real market data with
> `explanation_status: "unavailable"` and says why. See
> [§11](#11-amazon-bedrock-implemented-not-yet-live).
>
> **Not built yet:** virtual trading, portfolio management, AWS deployment, and
> a frontend chat interface.
>
> ⚠️ The bundled prices are **synthetic demo data**, not real market data. See [`data/README.md`](data/README.md).

Hackathon tags: `#strands-decider-2b` `#tool-selection`

## Structure

| Path | Purpose |
|---|---|
| `backend/` | FastAPI app. `main.py` entry; `app/api` routes, `app/core` config, `app/schemas` models, `app/services` logic, `app/agent` the Decider client, the tool allowlist and the Bedrock explanation layer, `tests/` pytest |
| `frontend/` | React + TypeScript + Vite. `src/pages/Dashboard.tsx`, `src/components/`, `src/services/api.ts` (API client), `src/types/`, `src/utils/format.ts` |
| `data/` | Local **synthetic** sample stock data (`sample_prices.csv`) + the generator script that produced it |
| `docs/` | `architecture.md`, `decision-pattern.md` (Decider research + tool-selection pattern), `bedrock-research.md` (Bedrock integration: research + what was built), `HANDOFF.md` (state of play and next task) |
| `experiments/` | `decider-spike.md` — the measured Decider 2B runtime spike, plus the scripts that produced it |

## 1. Required tools

| Tool | Version | Check |
|---|---|---|
| Python | 3.12 (3.10+ works) | `python --version` |
| Node.js | 22 LTS (needs `^20.19` or `>=22.12`) | `node --version` |
| npm | 10+ (ships with Node) | `npm --version` |
| Git | any recent | `git --version` |

Optional, only for [§10](#10-the-decider-2b-service-and-the-agent-endpoint):
**Python 3.12** specifically (`py -3.12`), and ~6 GB of free disk.

## 2. Open in VS Code
```powershell
cd path\to\MarketQuest-AI
code .
```
Open terminals with **Terminal > New Terminal** (PowerShell).

## 3. Backend setup (Terminal 1)
Run from `MarketQuest-AI\backend`:
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```
Prompt shows `(.venv)` when active.

## 4. Frontend setup (Terminal 2)
Run from `MarketQuest-AI\frontend`:
```powershell
cd frontend
npm install
Copy-Item .env.example .env
```

## 5. Environment variables
- `backend/.env` and `frontend/.env` are git-ignored. Only `.env.example` files are committed.
- **Never** put AWS keys or secrets in `frontend/.env`: Vite bundles those into browser code.
- AWS values in `backend/.env` name a **profile**, not a key. `boto3` resolves the credential itself from the ambient chain (environment, shared profile, or an IAM Identity Center session). See [§11](#11-amazon-bedrock-implemented-not-yet-live).

## 6. Run
Backend, from `backend\` with venv active:
```powershell
uvicorn main:app --reload --port 8000
```
Frontend, from `frontend\`:
```powershell
npm run dev
```
Then open **http://localhost:5173**.

## 7. Verify
- Health: open http://127.0.0.1:8000/health, expect `{"status":"ok","service":"marketquest-ai-backend","environment":"development"}`
- Market data: open http://127.0.0.1:8000/market/symbols, expect 4 symbols with `data_source: "synthetic_demo"`
- Analysis: open http://127.0.0.1:8000/market/analysis/DEMOTECH, expect an SMA and a volatility block
- API docs: http://127.0.0.1:8000/docs
- Website: http://localhost:5173 — the badge should read "Backend online", four demo symbols should be listed, and clicking one should draw its price history.
- Decider (only with the service running): open http://127.0.0.1:8000/agent/status, expect `"decider_reachable": true`.

Optional checks:
```powershell
# backend\, venv active  -> 105 tests, all passing
pytest
# frontend\  -> type-checks then builds to frontend/dist
npm run build
```

## 8. Market API endpoints (Part 2)

All market endpoints read the local sample dataset. Every response carries
`"data_source": "synthetic_demo"` and a `disclaimer` field, so demo prices can
never be mistaken for real quotes.

| Method | Path | What it returns |
|---|---|---|
| `GET` | `/health` | Service status (unchanged from Part 1) |
| `GET` | `/market/symbols` | Every symbol with its latest sample close and observation count |
| `GET` | `/market/prices/{symbol}` | Full daily OHLCV history for one symbol, oldest first |
| `GET` | `/market/returns/{symbol}` | Simple daily percentage returns derived from closing prices |
| `GET` | `/market/analysis/{symbol}` | Summary: latest close, simple moving average, volatility, total return |

`{symbol}` is case-insensitive (`demotech` works). Available symbols in the
bundled dataset: `DEMOBANK`, `DEMOENERGY`, `DEMOPHARMA`, `DEMOTECH`.

### Example requests

```powershell
# from backend\, venv active — start the server first
uvicorn main:app --reload --port 8000
```

```powershell
# list symbols and their latest sample prices
Invoke-RestMethod http://127.0.0.1:8000/market/symbols | ConvertTo-Json -Depth 5

# price history for one symbol
Invoke-RestMethod http://127.0.0.1:8000/market/prices/DEMOTECH | ConvertTo-Json -Depth 5

# daily percentage returns
Invoke-RestMethod http://127.0.0.1:8000/market/returns/DEMOTECH | ConvertTo-Json -Depth 5

# analysis summary (default windows: SMA 20, volatility 20 returns)
Invoke-RestMethod http://127.0.0.1:8000/market/analysis/DEMOTECH | ConvertTo-Json -Depth 5

# custom windows
Invoke-RestMethod "http://127.0.0.1:8000/market/analysis/DEMOTECH?sma_window=5&volatility_window=10" | ConvertTo-Json -Depth 5
```

Or in a browser: <http://127.0.0.1:8000/docs> (interactive Swagger UI).

### Analysis parameters

| Parameter | Default | Range | Meaning |
|---|---|---|---|
| `sma_window` | 20 | 1–365 | Number of closing prices averaged by the simple moving average |
| `volatility_window` | 20 | 2–365 | Number of **daily returns** used for the volatility estimate (so `window + 1` closing prices are needed) |

Volatility is the sample standard deviation of daily returns (n − 1). The
annualized figure multiplies it by √252. `TRADING_DAYS_PER_YEAR` is a stated
assumption, not a fact about the exchange calendar.

### Status codes

| Code | When |
|---|---|
| `200` | Success |
| `404` | Unknown symbol (the error names the available symbols) |
| `422` | A window outside its allowed range, or a non-numeric window |
| `400` | The requested window needs more observations than the sample has (the error states how many are available) |
| `500` | The sample dataset is missing or malformed |

The API never interpolates or invents prices. If there is not enough data for a
requested window, it says so instead of returning a misleading number.

### The sample dataset

`data/sample_prices.csv` — 4 fictional symbols × 30 weekdays, columns
`date, symbol, open, high, low, close, volume`, prices in INR. It is generated by
`data/generate_sample_data.py` (standard library only, fixed seed, deterministic).

```powershell
# regenerate after editing the generator
python data/generate_sample_data.py
```

The path can be overridden with the `DATA_DIR` environment variable; it defaults
to the repo's `data/` folder and is resolved independently of the working
directory.

---

## 9. The market dashboard (Part 2 frontend)

`frontend/src/pages/Dashboard.tsx` is the app's only page. It reads exactly
three backend endpoints — `GET /market/symbols`, `GET /market/prices/{symbol}`
and `GET /market/analysis/{symbol}` — and nothing else. There is no chat
widget, no external API, and no authentication.

| Piece | What it shows |
|---|---|
| Symbol selector | The four demo symbols with their latest sample close, observation count and date. Each is tagged **DEMO**. |
| Latest sample close | The big figure, its date, session count and currency, plus two deltas: change vs the previous session, and vs the moving average. |
| Price history | A hand-rolled SVG line + area chart with a hover tooltip (date, close, change vs previous, volume), y-axis gridlines, date ticks, and a toggleable rolling moving-average overlay. |
| Metric tiles | Moving average, daily volatility, annualised volatility, total return, average volume, and the data source. |
| States | Loading skeletons, an error panel with a retry button, and an empty state, for both the symbol list and the detail panel. |

**Synthetic-data labelling.** Every symbol card carries a `DEMO` tag, the top
bar carries a "Synthetic demo data" badge, the footer repeats the backend's own
`disclaimer` verbatim, and the data-source metric tile shows `synthetic_demo`.
No figure on the page is presented as a real quote.

**No chart library.** The project has no charting dependency, so the chart is
plain SVG in `frontend/src/components/PriceChart.tsx`. `package.json` is
unchanged — Part 2's frontend added **no** new dependency.

**Backend types.** `frontend/src/types/market.ts` mirrors
`backend/app/schemas/market.py` field for field. If you change one, change the
other.

---

## 10. The Decider 2B service and the agent endpoint

The Decider runs as a **separate local service**, in its own Python 3.12
virtual environment, and the backend reaches it over plain HTTP on
`127.0.0.1:8100`. The backend environment never installs `torch`.

### 10.1 Starting the service

```powershell
$SPIKE = "path\to\MarketQuest-AI\experiments\decider-spike"

# one-time: create the isolated venv and install the CPU dependencies
py -3.12 -m venv "$SPIKE\.venv"
& "$SPIKE\.venv\Scripts\python.exe" -m pip install "strands-decider[cpu]"

# start the service (binds 127.0.0.1 only, no auth)
$env:HF_HOME = "$SPIKE\hf-cache"
& "$SPIKE\.venv\Scripts\strands-decider.exe" serve `
    StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --host 127.0.0.1 --port 8100 --device cpu
```

Check it is up (it takes ~28 s to start once the weights are on disk, and about
4 minutes the first time, because it downloads 4.56 GB):

```powershell
Invoke-RestMethod http://127.0.0.1:8100/health | ConvertTo-Json -Depth 5
```

The service exposes `GET /health` and `POST /v1/systemone`. **Start it before a
demo, not during one.** `GET /agent/status` on the backend is the equivalent
pre-flight check.

**The `experiments/decider-spike/.venv/` and `experiments/decider-spike/hf-cache/`
directories are git-ignored** — the venv is 841 MB and the model cache 4.56 GB.
Do not commit them.

### 10.2 `POST /agent/decide` — the model picks the tool

The backend asks the Decider which market tool answers the user's question,
checks the answer against an allowlist, and then runs that tool through the
same services the `/market` endpoints use.

```powershell
# from backend\, venv active, with the Decider service running
$body = @{
  question = "Tell me how volatile DEMOTECH has been."
  symbol   = "DEMOTECH"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/agent/decide `
  -ContentType "application/json" -Body $body | ConvertTo-Json -Depth 6
```

The response carries the model's own reasoning, not just its answer:

```json
{
  "decision_made": true,
  "question": "Tell me how volatile DEMOTECH has been.",
  "symbol": "DEMOTECH",
  "tool": "get_analysis",
  "executed": true,
  "decision": {
    "question_name": "next_tool",
    "tool": "get_analysis",
    "confidence": 0.6956,
    "probabilities": {
      "get_symbols": 0.0074, "get_prices": 0.2113, "get_analysis": 0.7565,
      "get_returns": 0.0221, "no_action": 0.0028
    },
    "model": "strands-decider-2B-qwen3.5-v1-2610",
    "latency_ms": 6976.48,
    "input_tokens": 355,
    "output_tokens": 1
  },
  "result": {
    "kind": "analysis",
    "data": { "symbol": "DEMOTECH", "sma": 1447.1035, "volatility": { "...": "..." } }
  },
  "explanation": "DEMOTECH closed at 1447.10, which is about 2.3% above its 20-session average of 1414.67. Daily volatility is 1.82% (29.4% annualised) over the 29 returns in the sample, and the total return across the 30 sessions is 6.41%. These figures come from synthetic demo data, not a real market feed.",
  "explanation_status": "generated",
  "explanation_error": null,
  "bedrock": {
    "model_id": "global.anthropic.claude-haiku-5-5",
    "region": "ap-south-1",
    "stop_reason": "end_turn",
    "input_tokens": 412,
    "output_tokens": 57,
    "latency_ms": 1180.4
  },
  "data_source": "synthetic_demo",
  "disclaimer": "Synthetic demo data generated locally for development. Not real market data."
}
```

The `explanation` field above is illustrative — it shows the shape of a real
response. **On a machine with no AWS profile the endpoint still returns `200`
with the full market data**, and `explanation_status` is `"unavailable"` with
`explanation` set to `null`. See [§11](#11-amazon-bedrock-implemented-not-yet-live).

`GET /agent/status` reports whether the Decider service is reachable and what
it is serving, and whether Bedrock is configured.

#### The tools the model may choose

| Option | What it does | Needs a symbol |
|---|---|---|
| `get_symbols` | Every symbol with its latest sample close | no |
| `get_prices` | The full daily OHLCV history | yes |
| `get_analysis` | Latest close, moving average, volatility, total return | yes |
| `get_returns` | The daily percentage returns | yes |
| `no_action` | Nothing here can answer the question | no |

**The model chooses a name; it never supplies arguments, a command, a URL or
code.** The name is looked up by exact match in a fixed allowlist, and an
answer that is not on the list is rejected with `502 invalid_decision` and
never executed. All five tools are read-only.

#### When it cannot decide

The endpoint never invents a choice. Each failure has its own reason:

| Status | `error` | What happened |
|---|---|---|
| `400` | `missing_symbol` | The model chose a tool that needs a symbol and none was given. The model's choice is still reported in `decision`. |
| `502` | `invalid_decision` | The model named something that is not an allowlisted tool. |
| `502` | `invalid_response` | The service answered with something that was not a choice. |
| `503` | `decider_timeout` | The service did not answer within the timeout. |
| `503` | `decider_unavailable` | The service could not be reached. |

Every failure body has `"decision_made": false` and a message that says in
words that the model did not make a usable decision.

#### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `DECIDER_BASE_URL` | `http://127.0.0.1:8100` | Where the service is. **Loopback only** — the service has no authentication, so a remote URL is rejected at startup. |
| `DECIDER_TIMEOUT_SECONDS` | `15` | How long to wait for a decision. |
| `STRANDS_DECIDER_MODEL` | `StrandsAgents/strands-decider-2B-qwen3.5-v1-2610` | The model id sent in the request. |

### 10.3 Measured on this machine (CPU only — no NVIDIA GPU)

From the spike, and confirmed again through the endpoint:

| | |
|---|---:|
| Model | `StrandsAgents/strands-decider-2B-qwen3.5-v1-2610` @ `216d1ccb46a9e9b036eb9187b248db98480f77d4` |
| Base model | `Qwen/Qwen3.5-2B-Base` (Apache-2.0) |
| Startup, cold (incl. 4.56 GB download) | 253.9 s |
| Startup, warm (weights on disk) | 28.1 s |
| Decision latency, first in a process | 5,826.81 ms |
| Decision latency, repeat | 3,702.23 ms |
| Decision latency through `/agent/decide` | 6,384 – 8,546 ms |
| Peak server memory | 5,589 MB |
| Disk used | 4,561.7 MB (model) + 841.3 MB (venv) |

Real decisions taken through `POST /agent/decide` on this machine — the model
does discriminate, it does not always pick the same tool:

| Question | Chose | p | Confidence |
|---|---|---:|---:|
| "Tell me how volatile DEMOTECH has been." | `get_analysis` | 0.7565 | 0.6956 |
| "Show me the full daily price history for DEMOBANK…" | `get_prices` | 0.9807 | 0.9759 |
| "What symbols are available to look at?" | `get_symbols` | 0.8587 | 0.8233 |
| "How much did DEMOENERGY gain or lose day to day?" | `get_returns` | 0.6341 | 0.5426 |
| "What is the weather in Mumbai tomorrow?" | `no_action` | 0.8254 | 0.7817 |

Full report with exact commands and verbatim responses:
**[`experiments/decider-spike.md`](experiments/decider-spike.md)**.

### 10.4 Two things the integration respects

1. **Every tool option needs a real description.** The spike asked the same
   question twice: over HTTP (which carries a description per option) and via
   the `ask` CLI (whose `--choice` flag can only carry option *names*). With
   descriptions the model chose `get_analysis` at confidence 0.61; with bare
   names it chose `get_prices` at confidence 0.29. The descriptions are what
   make the choice well-posed — see `backend/app/agent/tools.py`.
2. **The service has no authentication and must stay on `127.0.0.1`.** Anyone
   who can reach the port can drive the model. `DECIDER_BASE_URL` is validated
   at startup and a non-loopback host is refused. If the Decider is unreachable,
   the backend degrades gracefully and says the decision was not made by the
   model — it never fabricates a choice.

### 10.5 Known limitations

- A decision takes 6–9 s on CPU, so a caller must show a waiting state.
- The model is a **decision head, not a text generator**. It returns a choice
  and calibrated probabilities; it never writes a sentence. Explaining the
  numbers in words is Bedrock's job, and that half is implemented but has not
  yet run against a live AWS account — see [§11](#11-amazon-bedrock-implemented-not-yet-live).
- The Decider must be started separately. If it is not running, `/agent/decide`
  returns `503` rather than falling back to a rule-based guess.
- The `state` prefix is rebuilt per question, so the service's prefix cache
  only helps within a repeated prefix.

---

## 11. Amazon Bedrock (implemented, not yet live)

The **Decider chooses the tool; Bedrock explains the numbers.** That split is
enforced by the code, not by convention: the Bedrock layer is never given a
list of tools to choose from, and it only ever receives results the backend
has already computed.

**The integration is written and tested. It has never made a live AWS call**,
because this machine has no AWS profile — see the blockers below. Until an
account is set up, `/agent/decide` still works: it returns the real market
data, and `explanation_status` says what happened.

### How it works

```
POST /agent/decide
   -> app/agent/decider.py     the Decider picks a tool name        (LIVE)
   -> app/agent/tools.py       the allowlist of read-only operations
   -> app/agent/runner.py      run the tool, get the numbers
   -> app/services/market_queries.py   the same builders /market uses
   -> app/agent/explainer.py   build a bounded payload + the prompt
   -> app/services/bedrock.py  Converse API on bedrock-runtime      (NOT LIVE)
```

The prompt is a `system` block (role and hard constraints) plus a `user`
block carrying the computed result as JSON. Three things keep the model
honest:

- **It never produces a number.** The payload carries the figures the backend
  already computed, and the model is told not to recompute, convert or extend
  them. Percentages are converted to percentages *in the backend*, once, so
  the model only ever quotes a number.
- **The series is bounded.** All 30 daily rows exist in the backend, but only
  the first 8 and last 8 are sent, and the payload says so — so the model
  cannot describe a row it was not given.
- **It cannot give advice.** The system prompt forbids recommendations, price
  targets and predictions, and requires the synthetic-data warning to be
  stated.

### The response

`POST /agent/decide` gains three fields and one object. Everything else,
including the Decider's probabilities and confidence, is unchanged.

| Field | Meaning |
|---|---|
| `explanation` | The Bedrock text. Present **only** when the status is `generated`. |
| `explanation_status` | `generated`, `skipped`, `disabled`, `unavailable` or `failed`. |
| `explanation_error` | Why there is no explanation, when the status is not `generated`. |
| `bedrock` | The model id, region, stop reason and token counts. Present only on success. |

**A Bedrock failure never fails the request and never produces a fabricated
explanation.** The decision and the market data are real whatever the
explanation layer does.

| `explanation_status` | Cause | Was a call made? |
|---|---|---|
| `generated` | It worked. | yes |
| `skipped` | The caller sent `"explain": false`, or the Decider chose `no_action` and there is nothing to explain. | **no** — nothing is charged |
| `disabled` | `BEDROCK_ENABLED=false`. | no |
| `unavailable` | Bedrock could not be used: no credentials, unknown model, or access denied. | no successful call |
| `failed` | Throttled, timed out, service error, or a response that was not in the documented shape. | yes |

Error messages are written by hand rather than taken from the AWS exception,
so request ids and internal detail are never echoed to the caller.

### Configuration

| Variable | Default | Meaning |
|---|---|---|
| `AWS_REGION` | `ap-south-1` | The region to call. |
| `AWS_PROFILE` | *(empty)* | The AWS profile or SSO profile to use. **A profile name, not a credential.** Empty means "use the ambient chain". |
| `BEDROCK_MODEL_ID` | `global.anthropic.claude-haiku-5-5` | The model or inference profile to call. |
| `BEDROCK_TIMEOUT_SECONDS` | `30` | How long to wait for an explanation. |
| `BEDROCK_MAX_TOKENS` | `600` | Upper bound on the explanation length. |
| `BEDROCK_TEMPERATURE` | `0.2` | Low, because this is a factual summary, not creative writing. |
| `BEDROCK_ENABLED` | `true` | Set to `false` to turn the explanation layer off. |

> **The `global.` prefix matters.** In `ap-south-1` the Claude 5.5 models are
> available through the **Global** cross-region inference profile only — not
> in-region, and not through a geo profile. A bare `anthropic.claude-haiku-5-5`
> will not route from that region.

### Blockers before it can be live

| # | Blocker | Who does it |
|---|---|---|
| 1 | **No AWS profile or SSO configured.** The AWS CLI is not installed, and neither `%USERPROFILE%\.aws\config` nor `credentials` exists on this machine. | You |
| 2 | **No IAM policy** granting `bedrock:Converse` and `bedrock:InvokeModel` (plus the read-only discovery actions) to the profile's role. Least-privilege example is in the research doc. | You |
| 3 | **Anthropic first-time-use form** not yet submitted for the account. Until it is, invocations return `AccessDeniedException`. | You |
| 4 | **Region choice.** `ap-south-1` is natural for an India-focused project — but see the `global.` prefix note above. | You |
| 5 | **Model access not verified.** `get-foundation-model-availability` has not been run, because it needs a working profile. | You, then us |

The research, the IAM policy, the model-access checks and the full
request/response reference are in
[`docs/bedrock-research.md`](docs/bedrock-research.md) §10.

### What has and has not been tested

**Tested with mocks.** 38 tests cover the exact Converse request shape, a
successful response, seven malformed responses, and the AWS failures
(missing credentials, access denied, unknown model, throttling, read timeout,
connect timeout, unreachable endpoint, unrecognised error). The AWS boundary
is a fake `bedrock-runtime` client; the **real** `BedrockClient` sits in front
of it, so request building, response parsing and error mapping all run. The
fixture is autouse, so no test in the suite can reach AWS or incur a charge.

**Not tested live.** Whether the account's IAM policy allows `Converse`,
whether the first-time-use form has been submitted, whether the model is
enabled in `ap-south-1`, and the real latency and token cost. A live call
would exercise all four.

---

## 12. Common errors
| Problem | Fix |
|---|---|
| `Activate.ps1 cannot be loaded... running scripts is disabled` | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then reactivate |
| `python` not found | Reinstall Python, tick **Add python.exe to PATH**; or try `py -3.12 -m venv .venv` |
| `uvicorn` not recognized | venv not active; run `.\.venv\Scripts\Activate.ps1` |
| `ModuleNotFoundError: app` | Run uvicorn from `backend\`, not the repo root |
| Port 8000/5173 in use | Change port: `--port 8001` (also update `VITE_API_BASE_URL`) or `Get-NetTCPConnection -LocalPort 8000` to find the process |
| Badge says "Backend offline" | Backend not running, or `CORS_ORIGINS` in `backend/.env` doesn't include your frontend URL. Restart backend after editing `.env` |
| Vite/Node engine error | Upgrade Node to 22 LTS |
| Edited `frontend/.env` but no change | Restart `npm run dev` |
| Market endpoint returns 500 | The sample CSV is missing or malformed. Check `data/sample_prices.csv` exists and run `python data/generate_sample_data.py` to regenerate it |
| Market endpoint returns 400 "needs N observations" | The requested window is larger than the sample. Lower `sma_window` / `volatility_window` |
| `npm install` fails on network | Check proxy/VPN; retry; `npm cache clean --force` |
| Dashboard shows the error panel | The backend is not running or `CORS_ORIGINS` excludes the frontend origin. The panel shows the backend's own error text |
| `strands-decider` will not start | It needs ~6 GB free disk and ~5.6 GB RAM. On first run it downloads 4.56 GB — expect a 4-minute wait, then ~28 s |
| `import strands_decider` fails in `backend/` | Correct, and deliberate. The Decider lives in its own venv under `experiments/decider-spike/` and is reached over HTTP |
| `/agent/decide` returns 503 `decider_unavailable` | The Decider service is not running. Start it — see [§10.1](#101-starting-the-service) — then retry |
| `/agent/decide` returns 503 `decider_timeout` | The service did not answer in `DECIDER_TIMEOUT_SECONDS` (default 15). A cold first decision can take ~6 s, so raise the timeout if the machine is loaded |
| The backend refuses to start with a `decider_base_url` error | `DECIDER_BASE_URL` must be a loopback address. The Decider has no authentication, so a remote host is refused on purpose |
| `/agent/status` says `decider_reachable: false` | The service is down or still starting (about 28 s). It is the pre-flight check to run before a demo |
| `/agent/decide` returns `explanation_status: "unavailable"` | Bedrock could not be used — usually no AWS credentials. The market data is still correct. See [§11](#11-amazon-bedrock-implemented-not-yet-live) |
| `explanation_status: "failed"` | A Bedrock call was made and did not return a usable explanation (throttled, timed out, or a malformed response). `explanation_error` says which. The market data is still correct |
| `explanation_status: "skipped"` | Either `"explain": false` was sent, or the Decider chose `no_action`. Neither makes a Bedrock call, so neither costs anything |
| `ModuleNotFoundError: boto3` | The backend venv is missing the AWS SDK. Run `pip install -r requirements.txt` from `backend/` |
| Bedrock returns `AccessDeniedException` | The profile's role lacks `bedrock:Converse`/`bedrock:InvokeModel`, the Anthropic first-time-use form has not been submitted, or the model is not enabled in the region |

## 13. Git + GitHub
The repo is already initialised and connected to `origin/main`
(`main` → `origin/main`, up to date as of the last commit). To commit the
current work:

```powershell
git add -A
git status          # confirm no .env, .venv, node_modules or model weights are listed
git commit -m "Add the Amazon Bedrock explanation layer for /agent/decide"
git push
```

**Before you commit, check that these are *not* staged:** `backend/.env`,
`frontend/.env`, any `.venv/`, `node_modules/`, `frontend/dist/`, and
`experiments/decider-spike/hf-cache/` (4.56 GB of model weights). All of them
are covered by `.gitignore`; `git status` should show only source files.

If you are starting a brand-new copy of the project instead, the original
first-time setup was `git init` → `git add .` → `git commit` → `git branch -M
main` → `git remote add origin <url>` → `git push -u origin main`, against an
empty **public** GitHub repo (no README/license, since they already exist here).

## License
MIT, see `LICENSE`. Dependencies in Parts 1–2 (FastAPI, Uvicorn, Pydantic, React, Vite, TypeScript) are permissively licensed. Part 2 added **no new dependencies** — the market analysis uses only the Python standard library (`csv`, `statistics`, `dataclasses`), and the frontend chart is hand-written SVG.

The Strands Decider 2B model, its base model `Qwen/Qwen3.5-2B-Base`, the
`strands-decider` package and `strands-agents` are **Apache-2.0**. That was
verified from the official repositories *and* confirmed in practice: the spike
installed `strands-decider` 0.2.0 and ran the model. Full findings, the exact
model revision, the measured performance and the open questions are in
[`docs/decision-pattern.md`](docs/decision-pattern.md) and
[`experiments/decider-spike.md`](experiments/decider-spike.md).

Part 4 added **`boto3` (Apache-2.0)**, the AWS SDK for Python.

### Licensing questions that are still open

Stated plainly, because they are not all settled:

- **The full dependency tree has not been swept.** Each direct dependency's
  licence was checked individually; the licences of every transitive
  dependency of `boto3` and `uvicorn[standard]` have not been enumerated.
- **The Bedrock model terms have not been verified.** The Claude models are
  offered through AWS Marketplace under a provider EULA that is separate from
  the Apache-2.0 licensing of the open-weight models used here. Read the
  EULA in your account before shipping anything built on it.
- **The Strands Decider 2B adapter's own licence was confirmed Apache-2.0**,
  but the model card's terms were not read line by line.
- **The IAM action needed for the Converse API is ambiguous in AWS's own
  documentation** — `bedrock:Converse` and `bedrock:InvokeModel` are each
  named in different places, so the project grants both. This is an IAM
  question, not a licence question, but it is unresolved in the same way.

Nothing here is legal advice, and no licence claim is made beyond what the
sources above actually say.
