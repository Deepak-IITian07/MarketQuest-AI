# Architecture (placeholder)

**Status: Part 3 (Decider half) complete.** Working today: the FastAPI health
and market endpoints, the React market dashboard, and `POST /agent/decide`, where
the Strands Decider 2B chooses which market tool to run. Not built yet: virtual
trading, portfolio management, Bedrock calls, AWS deployment.

```
React/Vite (frontend) --HTTP--> FastAPI (backend) --> agent/
                                                    |- Strands Decider 2B: choose next analysis tool  (LIVE)
                                                    '- Amazon Bedrock: explain results + uncertainty  (NOT BUILT)
data/  -> local SYNTHETIC sample stock data (Part 2) -> real data (later)
```

## Current shape

```
data/sample_prices.csv
   -> app/services/market_data.py   load + validate + query
   -> app/services/analysis.py      returns, SMA, volatility (pure functions)
   -> app/services/market_queries.py build the response models (shared)
   -> app/api/market.py             /market/symbols, /market/prices, /market/returns, /market/analysis

frontend/src/pages/Dashboard.tsx    symbol selector + price history + metrics
   -> frontend/src/services/api.ts  reads the three /market endpoints above

POST /agent/decide
   -> app/agent/decider.py    HTTP client for the local Decider service
   -> app/agent/tools.py      the allowlist of read-only market operations
   -> app/agent/runner.py     ask the model, check the answer, run the tool
   -> app/services/market_queries.py   the same builders the /market routes use
```

The Decider is reached over local HTTP (`strands-decider serve` on 127.0.0.1) in a
separate virtualenv, so the backend venv stays free of `torch`. That split is
**verified on this machine** — see `experiments/decider-spike.md` for the
measured startup, latency and memory, and `decision-pattern.md` for the
reasoning and the remaining open questions.

## Rules
- AWS credentials live only in the backend environment / AWS profile, never in Git or frontend env vars.
- Strands Decider 2B and Bedrock integration methods must be verified against current official AWS docs before implementation.
- Simulated trading only.
- The bundled prices are synthetic. Every market response says so via `data_source` and `disclaimer`, and the dashboard labels every price as demo data.
- The Decider server has no authentication. It must stay bound to `127.0.0.1` and never be exposed. `DECIDER_BASE_URL` is validated at startup and a non-loopback host is refused.
- The Decider chooses a tool **name** only. It never supplies arguments, a command, a URL or code, and a name outside the allowlist is rejected and never executed. Every tool is read-only.
- A failed decision is reported as a failed decision. The backend never falls back to a rule-based guess and never claims the model chose something it did not.

## To fill in later
AWS deployment, data flow, model invocation details.
