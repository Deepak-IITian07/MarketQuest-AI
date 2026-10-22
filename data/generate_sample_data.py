"""Generate the SYNTHETIC demo market dataset used by the backend.

IMPORTANT
---------
The prices this script writes are **completely fictional**. They are produced by a
seeded random walk. They are NOT historical quotes for any real company and must
never be presented as real market data.

The symbols are deliberately invented (``DEMO*``) so that no fictional number can
ever be mistaken for a real NSE/BSE quote.

Run from the repository root::

    python data/generate_sample_data.py

The output is deterministic: the same seed always produces the same CSV.
"""

from __future__ import annotations

import csv
import random
from datetime import date, timedelta
from pathlib import Path

SEED = 20261023
START_DATE = date(2026, 9, 7)
TRADING_DAYS = 30
OUTPUT_PATH = Path(__file__).resolve().parent / "sample_prices.csv"

FIELDNAMES = ["date", "symbol", "open", "high", "low", "close", "volume"]

# (symbol, start price in INR, daily drift, daily volatility, average volume)
SYMBOLS: list[tuple[str, float, float, float, int]] = [
    ("DEMOTECH", 1450.0, 0.0012, 0.014, 220_000),
    ("DEMOBANK", 860.0, 0.0004, 0.011, 480_000),
    ("DEMOPHARMA", 2300.0, 0.0008, 0.016, 130_000),
    ("DEMOENERGY", 310.0, -0.0003, 0.019, 650_000),
]


def trading_dates(start: date, count: int) -> list[date]:
    """Return `count` consecutive weekdays starting at `start` (weekends skipped)."""
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:  # Monday..Friday
            days.append(current)
        current += timedelta(days=1)
    return days


def simulate(
    rng: random.Random,
    dates: list[date],
    symbol: str,
    start_price: float,
    drift: float,
    volatility: float,
    base_volume: int,
) -> list[dict[str, object]]:
    """Build a synthetic OHLCV series that is internally consistent."""
    rows: list[dict[str, object]] = []
    previous_close = start_price

    for day in dates:
        overnight_gap = rng.gauss(0, volatility * 0.4)
        open_price = previous_close * (1 + overnight_gap)
        close_price = previous_close * (1 + drift + rng.gauss(0, volatility))

        open_price = max(1.0, open_price)
        close_price = max(1.0, close_price)

        high_price = max(open_price, close_price) * (1 + abs(rng.gauss(0, volatility * 0.5)))
        low_price = min(open_price, close_price) * (1 - abs(rng.gauss(0, volatility * 0.5)))
        low_price = max(0.5, low_price)

        volume = int(base_volume * (1 + rng.gauss(0, 0.28)))
        volume = max(1_000, volume)

        rows.append(
            {
                "date": day.isoformat(),
                "symbol": symbol,
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "close": round(close_price, 2),
                "volume": volume,
            }
        )
        previous_close = close_price

    return rows


def main() -> None:
    rng = random.Random(SEED)
    dates = trading_dates(START_DATE, TRADING_DAYS)

    rows: list[dict[str, object]] = []
    for symbol, start_price, drift, volatility, base_volume in SYMBOLS:
        rows.extend(
            simulate(rng, dates, symbol, start_price, drift, volatility, base_volume)
        )

    rows.sort(key=lambda row: (str(row["symbol"]), str(row["date"])))

    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} synthetic rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
