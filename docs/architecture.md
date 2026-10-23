# Architecture

**Status: Part 4 (Bedrock half) implemented, not live.** Working today: the
FastAPI health and market endpoints, the React market dashboard, and
`POST /agent/decide`, where the Strands Decider 2B chooses which market tool to
run and Amazon Bedrock explains the numbers that tool produced. The Bedrock
half has been tested against a mocked AWS boundary but has **never made a live
AWS call**, because no AWS profile is configured. Not built yet: virtual
trading, portfolio management, AWS deployment, a frontend chat interface.

```
React/Vite (frontend) --HTTP--> FastAPI (backend) --> agent/
                                                    |- Strands Decider 2B: choose next analysis tool  (LIVE)
                                                    '- Amazon Bedrock: explain the computed results     (NOT LIVE)
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
   -> app/agent/explainer.py   build a bounded payload from the computed result
   -> app/services/bedrock.py  Converse API on bedrock-runtime
   -> app/api/agent.py        the endpoint + GET /agent/status
```

The Decider is reached over local HTTP (`strands-decider serve` on 127.0.0.1) in a
separate virtualenv, so the backend venv stays free of `torch`. That split is
**verified on this machine** — see `experiments/decider-spike.md` for the
measured startup, latency and memory, and `decision-pattern.md` for the
reasoning and the remaining open questions.

## The two halves

**The Decider chooses; Bedrock explains.** The split is structural, not a
convention:

- The Decider picks a **tool name** from a fixed allowlist. It is never given
  the market data and never sees a tool description of anything but the
  options.
- The Bedrock layer is never given the tool registry. It receives the
  already-computed response model and a prompt, and it can only describe what
  it was given. It cannot choose a tool, and it cannot run one.
- The figures are computed in the backend. The model is told not to recompute,
  convert or extend them, and the long daily series is truncated to its first
  and last rows with a note saying the rest was not provided — so it cannot
  describe a row it never saw.

A Bedrock failure is reported as a Bedrock failure. The decision and the
market data still come back, `explanation_status` says what happened, and no
explanation is ever fabricated.

## Rules
- AWS credentials live only in the backend environment / AWS profile, never in Git or frontend env vars.
- Strands Decider 2B and Bedrock integration methods must be verified against current official AWS docs before implementation.
- Simulated trading only.
- The bundled prices are synthetic. Every market response says so via `data_source` and `disclaimer`, and the dashboard labels every price as demo data. The explanation prompt says so too.
- The Decider server has no authentication. It must stay bound to `127.0.0.1` and never be exposed. `DECIDER_BASE_URL` is validated at startup and a non-loopback host is refused.
- The Decider chooses a tool **name** only. It never supplies arguments, a command, a URL or code, and a name outside the allowlist is rejected and never executed. Every tool is read-only.
- A failed decision is reported as a failed decision. The backend never falls back to a rule-based guess and never claims the model chose something it did not.
- AWS errors are mapped to hand-written messages. SDK internals — request ids, ARNs, raw exception text — are never echoed to the caller.
- No test may reach AWS. The suite mocks the `bedrock-runtime` boundary with an autouse fixture, so a test run can never incur a cost.

## To fill in later
AWS deployment, real market data, virtual trading and portfolio management,
a frontend chat interface to display the explanation.
