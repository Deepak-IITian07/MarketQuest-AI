# Sample market data

> ## ⚠️ SYNTHETIC DEMO DATA — NOT REAL MARKET DATA
>
> Every number in `sample_prices.csv` is **fictional**, produced by a seeded random
> walk in `generate_sample_data.py`. It is **not** a historical quote for any real
> company, and it must never be presented, cited, or reused as real market data.
>
> The symbols are invented on purpose (`DEMO*`) so that no fictional price can be
> mistaken for a real NSE/BSE quote. `DEMOTECH`, `DEMOBANK`, `DEMOPHARMA` and
> `DEMOENERGY` are **not real companies**.

## Contents

| File | Purpose |
|---|---|
| `sample_prices.csv` | The dataset the backend reads. 4 symbols x 30 trading days = 120 rows. |
| `generate_sample_data.py` | Regenerates the CSV. Deterministic (seed `20261023`). |
| `.gitkeep` | Keeps the folder in Git. |

## Format

| Column | Type | Notes |
|---|---|---|
| `date` | `YYYY-MM-DD` | Weekdays only, no market holidays modelled. |
| `symbol` | string | Uppercase ticker, `DEMO*` prefix. |
| `open` | float | INR, 2 decimals. |
| `high` | float | INR. Always `>= max(open, close)`. |
| `low` | float | INR. Always `<= min(open, close)`. |
| `close` | float | INR, 2 decimals. Always `> 0`. |
| `volume` | int | Synthetic share volume, always `> 0`. |

Currency is INR. Prices are fictional levels, not real market levels.

## Regenerating

```powershell
python data/generate_sample_data.py
```

The script is standard-library only and rewrites `sample_prices.csv` in place with
the same content every time (fixed seed).

## Replacing with real data later

When real market data is added, replace this file, drop the `DEMO*` symbols, and
update the `data_source` / `disclaimer` fields in `backend/app/schemas/market.py`
so the API stops advertising synthetic data. The loader in
`backend/app/services/market_data.py` validates the same column contract either
way, so no code change is needed beyond those two strings.
