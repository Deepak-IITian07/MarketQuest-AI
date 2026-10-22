# Architecture (placeholder)

**Status: Part 2 complete, plus a verified Decider runtime spike.** Working
today: the FastAPI health and market endpoints, the React market dashboard, and
a proven Decider 2B decision over local HTTP. Not built yet: the agent itself,
virtual trading, portfolio management, Bedrock calls, AWS deployment.

```
React/Vite (frontend) --HTTP--> FastAPI (backend) --> agent/ (Part 3+)
                                                    |- Strands Decider 2B: choose next analysis tool
                                                    '- Amazon Bedrock: explain results + uncertainty
data/  -> local SYNTHETIC sample stock data (Part 2) -> real data (Part 3+)
```

## Current shape

```
data/sample_prices.csv
   -> app/services/market_data.py   load + validate + query
   -> app/services/analysis.py      returns, SMA, volatility (pure functions)
   -> app/api/market.py             /market/symbols, /market/prices, /market/returns, /market/analysis

frontend/src/pages/Dashboard.tsx    symbol selector + price history + metrics
   -> frontend/src/services/api.ts  reads the three /market endpoints above
```

The Decider is reached over local HTTP (`strands-decider serve` on 127.0.0.1) in a
separate virtualenv, so the backend venv stays free of `torch`. That split is
now **verified on this machine** — see `experiments/decider-spike.md` for the
measured startup, latency and memory, and `decision-pattern.md` for the
reasoning and the remaining open questions.

## Rules
- AWS credentials live only in the backend environment / AWS profile, never in Git or frontend env vars.
- Strands Decider 2B and Bedrock integration methods must be verified against current official AWS docs before implementation.
- Simulated trading only.
- The bundled prices are synthetic. Every market response says so via `data_source` and `disclaimer`, and the dashboard labels every price as demo data.
- The Decider server has no authentication. It must stay bound to `127.0.0.1` and never be exposed.

## To fill in later
AWS deployment, data flow, model invocation details.
