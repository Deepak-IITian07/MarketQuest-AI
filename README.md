# MarketQuest AI

Game-inspired stock-market simulation for Indian stocks. Virtual money only; no real trading.

> **Status: Part 2 complete, plus a verified Strands Decider 2B runtime spike.**
>
> **Working now:** the FastAPI `/health` and `/market/*` endpoints, and a React
> market dashboard that reads them.
>
> **Proven but not wired in:** the Decider 2B service was installed and run for
> real, and it took a genuine tool-selection decision over local HTTP. That is a
> **spike**, not a feature — no backend code calls it yet. Measured numbers in
> [§10](#10-the-decider-2b-spike).
>
> **Not built yet:** the agent itself, virtual trading, portfolio management,
> Amazon Bedrock calls, AWS deployment.
>
> ⚠️ The bundled prices are **synthetic demo data**, not real market data. See [`data/README.md`](data/README.md).

Hackathon tags: `#strands-decider-2b` `#tool-selection`

## Structure

| Path | Purpose |
|---|---|
| `backend/` | FastAPI app. `main.py` entry; `app/api` routes, `app/core` config, `app/schemas` models, `app/services` logic, `app/agent` future agent code, `tests/` pytest |
| `frontend/` | React + TypeScript + Vite. `src/pages/Dashboard.tsx`, `src/components/`, `src/services/api.ts` (API client), `src/types/`, `src/utils/format.ts` |
| `data/` | Local **synthetic** sample stock data (`sample_prices.csv`) + the generator script that produced it |
| `docs/` | `architecture.md`, `decision-pattern.md` (Decider research + tool-selection pattern), `bedrock-research.md` (Bedrock integration plan), `HANDOFF.md` (state of play and next task) |
| `experiments/` | `decider-spike.md` — the measured Decider 2B runtime spike, plus the scripts that produced it |

## 1. Required tools

| Tool | Version | Check |
|---|---|---|
| Python | 3.12 (3.10+ works) | `python --version` |
| Node.js | 22 LTS (needs `^20.19` or `>=22.12`) | `node --version` |
| npm | 10+ (ships with Node) | `npm --version` |
| Git | any recent | `git --version` |

Optional, only for [§10](#10-the-decider-2b-spike): **Python 3.12** specifically
(`py -3.12`), and ~6 GB of free disk.

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
- AWS values in `backend/.env` are empty placeholders for later parts. Prefer an AWS profile/SSO over raw keys.

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

Optional checks:
```powershell
# backend\, venv active  -> 46 tests, all passing
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

## 10. The Decider 2B spike

**This is an experiment, not part of the running app.** Nothing in `backend/`
talks to the Decider yet — that is Part 3. What the spike proved is that the
documented setup actually works on this machine, and it produced the numbers
below so the Builder Center article can quote measured figures rather than
upstream marketing numbers.

Full report with exact commands and verbatim responses:
**[`experiments/decider-spike.md`](experiments/decider-spike.md)**.

### Measured on this machine (CPU only — no NVIDIA GPU)

| | |
|---|---:|
| Model | `StrandsAgents/strands-decider-2B-qwen3.5-v1-2610` @ `216d1ccb46a9e9b036eb9187b248db98480f77d4` |
| Base model | `Qwen/Qwen3.5-2B-Base` (Apache-2.0) |
| Startup, cold (incl. 4.56 GB download) | 253.9 s |
| Startup, warm (weights on disk) | 28.1 s |
| Decision latency, first in a process | 5,826.81 ms |
| Decision latency, repeat | 3,702.23 ms |
| Peak server memory | 5,589 MB |
| Disk used | 4,561.7 MB (model) + 841.3 MB (venv) |

### Reproducing it

```powershell
$SPIKE = "path\to\MarketQuest-AI\experiments\decider-spike"
py -3.12 -m venv "$SPIKE\.venv"
& "$SPIKE\.venv\Scripts\python.exe" -m pip install "strands-decider[cpu]"

# start the service (separate venv, binds 127.0.0.1 only, no auth)
$env:HF_HOME = "$SPIKE\hf-cache"
& "$SPIKE\.venv\Scripts\strands-decider.exe" serve `
    StrandsAgents/strands-decider-2B-qwen3.5-v1-2610 --host 127.0.0.1 --port 8100 --device cpu
```

Then, in another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8100/health | ConvertTo-Json -Depth 5
```

The service exposes `GET /health` and `POST /v1/systemone`. The full request
and the full response are in the spike report.

**The `experiments/decider-spike/.venv/` and `experiments/decider-spike/hf-cache/`
directories are git-ignored** — the venv is 841 MB and the model cache 4.56 GB.
Do not commit them.

### Two things Part 3 must respect

1. **Every tool option needs a real description.** The spike asked the same
   question twice: over HTTP (which carries a description per option) and via
   the `ask` CLI (whose `--choice` flag can only carry option *names*). With
   descriptions the model chose `get_analysis` at confidence 0.61; with bare
   names it chose `get_prices` at confidence 0.29. The descriptions are what
   make the choice well-posed.
2. **The service has no authentication and must stay on `127.0.0.1`.** Anyone
   who can reach the port can drive the model. If the Decider is unreachable,
   the backend must degrade gracefully and say the decision was not made by the
   model — never fabricate a choice.

---

## 11. Amazon Bedrock readiness (research only)

Nothing is implemented. [`docs/bedrock-research.md`](docs/bedrock-research.md)
is the plan: supported SDK, IAM permissions, model access checks, profile/SSO
authentication, a minimal request/response example, and the division of labour
between the Decider (chooses the tool) and Bedrock (explains the results).

**No AWS call has been made and no credential has been read, printed, or
created.** The account-side setup below is still outstanding.

### Blockers before Bedrock can work

| # | Blocker | Who does it |
|---|---|---|
| 1 | **No AWS profile or SSO configured.** The AWS CLI is not installed, and neither `%USERPROFILE%\.aws\config` nor `credentials` exists on this machine. | You |
| 2 | **No IAM policy granting `bedrock:Converse`** (plus the read-only discovery actions) to the profile's role. Least-privilege example is in the research doc. | You |
| 3 | **Anthropic first-time-use form** not yet submitted for the account. Until it is, invocations return `AccessDeniedException`. | You |
| 4 | **Region choice.** For an India-focused project `ap-south-1` is natural — but Claude 5.5 models there support **Global inference only**, so `modelId` must be `global.anthropic.claude-haiku-5-5`, not `us.…`. | You |
| 5 | **Model access not verified.** `get-foundation-model-availability` has not been run, because it needs a working profile. | You, then us |

Set `AWS_REGION`, `AWS_PROFILE` and `BEDROCK_MODEL_ID` in `backend/.env` once
the above are done — those placeholders already exist.

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

## 13. Git + GitHub
The repo is already initialised and connected to `origin/main`
(`main` → `origin/main`, up to date). To commit the current work:

```powershell
git add -A
git status          # confirm no .env, .venv, node_modules or model weights are listed
git commit -m "Add market dashboard, Decider 2B spike and Bedrock research"
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
