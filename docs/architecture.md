# Architecture (placeholder)

**Status: Part 2.** The FastAPI health endpoint, the React landing page, and the
local sample market data + analysis endpoints exist today.

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
```

The Decider is reached over local HTTP (`strands-decider serve` on 127.0.0.1) in a
separate virtualenv, so the backend venv stays free of `torch`. See
`decision-pattern.md` for the reasoning and the open questions.

## Rules
- AWS credentials live only in the backend environment / AWS profile, never in Git or frontend env vars.
- Strands Decider 2B and Bedrock integration methods must be verified against current official AWS docs before implementation.
- Simulated trading only.
- The bundled prices are synthetic. Every market response says so via `data_source` and `disclaimer`.

## To fill in later
AWS deployment, data flow, model invocation details.
