# Architecture (placeholder)

**Status: planned.** Only the FastAPI health endpoint and the React landing page exist today.

```
React/Vite (frontend) --HTTP--> FastAPI (backend) --> agent/ (Part 2+)
                                                    |- Strands Decider 2B: choose next analysis tool
                                                    '- Amazon Bedrock: explain results + uncertainty
data/  -> local sample historical stock data (Part 3+)
```

## Rules
- AWS credentials live only in the backend environment / AWS profile, never in Git or frontend env vars.
- Strands Decider 2B and Bedrock integration methods must be verified against current official AWS docs before implementation.
- Simulated trading only.

## To fill in later
AWS deployment, data flow, model invocation details.
