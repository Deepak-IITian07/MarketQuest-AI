"""The Decider-backed agent.

Three small pieces, in dependency order:

- `decider` talks to the local Strands Decider 2B service over HTTP.
- `tools` is the allowlist of read-only market operations it may choose.
- `runner` asks the model, checks the answer against the allowlist, and runs
  the chosen tool.

The Decider itself lives in its own Python 3.12 environment under
`experiments/decider-spike/`. Nothing here imports it, so the backend
environment never needs `torch`.
"""
