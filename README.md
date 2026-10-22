# MarketQuest AI

Game-inspired stock-market simulation for Indian stocks. Virtual money only; no real trading.

> **Status: Part 1 scaffold.** Working now: FastAPI `/health` endpoint, React landing page that checks the backend. **Not implemented yet:** stock data, analysis, virtual trading, Strands Decider 2B, Amazon Bedrock, AWS deployment.

Hackathon tags: `#strands-decider-2b` `#tool-selection`

## Structure

| Path | Purpose |
|---|---|
| `backend/` | FastAPI app. `main.py` entry; `app/api` routes, `app/core` config, `app/schemas` models, `app/services` logic, `app/agent` future agent code, `tests/` pytest |
| `frontend/` | React + TypeScript + Vite. `src/pages`, `src/components`, `src/services/api.ts` (API client), `src/types/agent.ts` (future agent types) |
| `data/` | Future local sample stock data |
| `docs/` | `architecture.md`, `decision-pattern.md` (placeholders) |

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
- API docs: http://127.0.0.1:8000/docs
- Website: http://localhost:5173 (badge should read "Backend online")

Optional checks:
```powershell
# backend\, venv active
pytest
# frontend\
npm run build
```

## 8. Common errors
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
| `npm install` fails on network | Check proxy/VPN; retry; `npm cache clean --force` |

## 9. Git + GitHub
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
MIT, see `LICENSE`. Dependencies in Part 1 (FastAPI, Uvicorn, Pydantic, React, Vite, TypeScript) are permissively licensed. **Re-check** the Strands Decider 2B model terms and any Strands/AWS package licenses before Part 2.
