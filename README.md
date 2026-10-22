# MarketQuest AI

Game-inspired stock-market simulation for Indian stocks. Virtual money only; no real trading.

> **Status: Part 2.** Working now: FastAPI `/health` endpoint, local sample market data with analysis endpoints (`/market/*`), React landing page that checks the backend. **Not implemented yet:** virtual trading, portfolio management, Strands Decider 2B, Amazon Bedrock, AWS deployment.
>
> ⚠️ The bundled prices are **synthetic demo data**, not real market data. See [`data/README.md`](data/README.md).

Hackathon tags: `#strands-decider-2b` `#tool-selection`

## Structure

| Path | Purpose |
|---|---|
| `backend/` | FastAPI app. `main.py` entry; `app/api` routes, `app/core` config, `app/schemas` models, `app/services` logic, `app/agent` future agent code, `tests/` pytest |
| `frontend/` | React + TypeScript + Vite. `src/pages`, `src/components`, `src/services/api.ts` (API client), `src/types/agent.ts` (future agent types) |
| `data/` | Local **synthetic** sample stock data (`sample_prices.csv`) + the generator script that produced it |
| `docs/` | `architecture.md`, `decision-pattern.md` (Decider research + tool-selection pattern) |

## 1. Required tools

| Tool | Version | Check |
|---|---|---|
| Python | 3.12 (3.10+ works) | `python --version` |
| Node.js | 22 LTS (needs `^20.19` or `>=22.12`) | `node --version` |
| npm | 10+ (ships with Node) | `npm --version` |
| Git | any recent | `git --version` |

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

## 7. Verify
- Health: open http://127.0.0.1:8000/health, expect `{"status":"ok","service":"marketquest-ai-backend","environment":"development"}`
- Market data: open http://127.0.0.1:8000/market/symbols, expect 4 symbols with `data_source: "synthetic_demo"`
- Analysis: open http://127.0.0.1:8000/market/analysis/DEMOTECH, expect an SMA and a volatility block
- API docs: http://127.0.0.1:8000/docs
- Website: http://localhost:5173 (badge should read "Backend online")

Optional checks:
```powershell
# backend\, venv active
pytest
# frontend\
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

## 9. Common errors
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

## 10. Git + GitHub
From the repo root `MarketQuest-AI\`:
```powershell
git init
git add .
git status          # confirm no .env, .venv or node_modules are listed
git commit -m "Initial project scaffold"
git branch -M main
git remote add origin https://github.com/<your-username>/MarketQuest-AI.git
git push -u origin main
```
Create the empty **public** GitHub repo first (no README/license, since they already exist here).

## License
MIT, see `LICENSE`. Dependencies in Parts 1–2 (FastAPI, Uvicorn, Pydantic, React, Vite, TypeScript) are permissively licensed. Part 2 added **no new dependencies** — the market analysis uses only the Python standard library (`csv`, `statistics`, `dataclasses`).

The Strands Decider 2B model and its packages were researched in Part 2 and are
**Apache-2.0** (model weights, base model `Qwen/Qwen3.5-2B-Base`, the
`strands-decider` package, and `strands-agents`). The model is **not installed
yet**. Full findings, exact model revision, and the open questions are in
[`docs/decision-pattern.md`](docs/decision-pattern.md).
