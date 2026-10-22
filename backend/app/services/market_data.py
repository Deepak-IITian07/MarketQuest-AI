"""Loading, validating and querying the local sample market dataset.

The dataset is the synthetic demo CSV described in `data/README.md`. Nothing in
this module talks to the network and nothing here invents prices: if a symbol or
an observation is missing, the caller gets a clear error instead of a guess.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

#: Column contract every price CSV must satisfy.
REQUIRED_COLUMNS: tuple[str, ...] = (
    "date",
    "symbol",
    "open",
    "high",
    "low",
    "close",
    "volume",
)

#: Marker returned by the API so no consumer mistakes the demo data for real quotes.
DATA_SOURCE = "synthetic_demo"


class MarketDataError(Exception):
    """Base class for every market data problem."""


class DataValidationError(MarketDataError):
    """The dataset is missing, malformed, or contains an invalid row."""


class SymbolNotFoundError(MarketDataError):
    """The requested symbol is not present in the dataset."""

    def __init__(self, symbol: str, available: Sequence[str]) -> None:
        super().__init__(f"Unknown symbol '{symbol}'. Available symbols: {', '.join(available)}")
        self.symbol = symbol
        self.available = list(available)


@dataclass(frozen=True, slots=True)
class PriceBar:
    """One validated daily price observation."""

    date: date
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int


def normalize_symbol(symbol: str) -> str:
    """Normalise a user supplied symbol (trim + upper case)."""
    return symbol.strip().upper()


def _parse_float(raw: str | None, column: str, line: int) -> float:
    if raw is None or raw.strip() == "":
        raise DataValidationError(f"Line {line}: column '{column}' is empty.")
    try:
        return float(raw)
    except ValueError as exc:
        raise DataValidationError(
            f"Line {line}: column '{column}' is not a number: {raw!r}."
        ) from exc


def _parse_int(raw: str | None, column: str, line: int) -> int:
    value = _parse_float(raw, column, line)
    if not value.is_integer():
        raise DataValidationError(
            f"Line {line}: column '{column}' must be a whole number, got {raw!r}."
        )
    return int(value)


def _parse_date(raw: str | None, line: int) -> date:
    if raw is None or raw.strip() == "":
        raise DataValidationError("Line %d: column 'date' is empty." % line)
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as exc:
        raise DataValidationError(
            f"Line {line}: column 'date' is not an ISO date (YYYY-MM-DD): {raw!r}."
        ) from exc


def _validate_bar(bar: PriceBar, line: int) -> PriceBar:
    if bar.close <= 0:
        raise DataValidationError(f"Line {line}: close must be greater than 0, got {bar.close}.")
    if bar.low <= 0:
        raise DataValidationError(f"Line {line}: low must be greater than 0, got {bar.low}.")
    if bar.high < bar.low:
        raise DataValidationError(
            f"Line {line}: high ({bar.high}) is lower than low ({bar.low})."
        )
    if bar.high < max(bar.open, bar.close):
        raise DataValidationError(
            f"Line {line}: high ({bar.high}) is below max(open, close) "
            f"({max(bar.open, bar.close)})."
        )
    if bar.low > min(bar.open, bar.close):
        raise DataValidationError(
            f"Line {line}: low ({bar.low}) is above min(open, close) "
            f"({min(bar.open, bar.close)})."
        )
    if bar.volume < 0:
        raise DataValidationError(
            f"Line {line}: volume cannot be negative, got {bar.volume}."
        )
    return bar


def _parse_rows(rows: Iterable[Sequence[str]], header: Sequence[str]) -> list[PriceBar]:
    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        raise DataValidationError(
            "Sample price file is missing required column(s): " + ", ".join(missing) + "."
        )

    index = {name: position for position, name in enumerate(header)}
    bars: list[PriceBar] = []
    seen: set[tuple[date, str]] = set()

    for offset, row in enumerate(rows):
        line = offset + 2  # +1 for the header, +1 to be 1-based
        if not row or all(not cell.strip() for cell in row):
            continue  # tolerate blank lines

        if len(row) < len(header):
            raise DataValidationError(
                f"Line {line}: expected {len(header)} columns, found {len(row)}."
            )

        symbol = (row[index["symbol"]] or "").strip().upper()
        if not symbol:
            raise DataValidationError(f"Line {line}: column 'symbol' is empty.")

        bar = _validate_bar(
            PriceBar(
                date=_parse_date(row[index["date"]], line),
                symbol=symbol,
                open=_parse_float(row[index["open"]], "open", line),
                high=_parse_float(row[index["high"]], "high", line),
                low=_parse_float(row[index["low"]], "low", line),
                close=_parse_float(row[index["close"]], "close", line),
                volume=_parse_int(row[index["volume"]], "volume", line),
            ),
            line,
        )

        key = (bar.date, bar.symbol)
        if key in seen:
            raise DataValidationError(
                f"Line {line}: duplicate observation for {bar.symbol} on {bar.date.isoformat()}."
            )
        seen.add(key)
        bars.append(bar)

    if not bars:
        raise DataValidationError("Sample price file contains no price rows.")

    return bars


@lru_cache(maxsize=8)
def _load_bars_cached(path_str: str) -> tuple[PriceBar, ...]:
    path = Path(path_str)
    if not path.is_file():
        raise DataValidationError(f"Sample price file not found: {path}")

    try:
        with path.open("r", newline="", encoding="utf-8-sig") as handle:
            reader = csv.reader(handle)
            header = next(reader, None)
            if header is None:
                raise DataValidationError(f"Sample price file is empty: {path}")
            header = [column.strip().lower() for column in header]
            bars = _parse_rows(reader, header)
    except UnicodeDecodeError as exc:
        raise DataValidationError(f"Sample price file is not valid UTF-8: {path}") from exc

    return tuple(bars)


def load_price_bars(path: Path | None = None) -> list[PriceBar]:
    """Load and validate every price bar from the sample CSV.

    Args:
        path: Optional override for the dataset location. Defaults to the
            configured `data/sample_prices.csv`.

    Returns:
        All bars, sorted by symbol then date.

    Raises:
        DataValidationError: The file is missing, malformed, or holds an invalid row.
    """
    resolved = Path(path) if path is not None else get_settings().sample_prices_path
    return list(_load_bars_cached(str(resolved.resolve())))


def clear_cache() -> None:
    """Drop the cached dataset (used by tests and after the CSV changes on disk)."""
    _load_bars_cached.cache_clear()


def get_symbols(path: Path | None = None) -> list[str]:
    """Return every symbol present in the dataset, sorted alphabetically."""
    return sorted({bar.symbol for bar in load_price_bars(path)})


def get_price_history(symbol: str, path: Path | None = None) -> list[PriceBar]:
    """Return every bar for `symbol`, oldest first.

    Raises:
        SymbolNotFoundError: The symbol is not in the dataset.
    """
    wanted = normalize_symbol(symbol)
    bars = [bar for bar in load_price_bars(path) if bar.symbol == wanted]
    if not bars:
        raise SymbolNotFoundError(wanted, get_symbols(path))
    return sorted(bars, key=lambda bar: bar.date)


def get_latest_price(symbol: str, path: Path | None = None) -> PriceBar:
    """Return the most recent bar for `symbol`."""
    history = get_price_history(symbol, path)
    return history[-1]


def get_latest_prices(path: Path | None = None) -> dict[str, PriceBar]:
    """Return the most recent bar for every symbol, keyed by symbol."""
    latest: dict[str, PriceBar] = {}
    for bar in load_price_bars(path):
        current = latest.get(bar.symbol)
        if current is None or bar.date > current.date:
            latest[bar.symbol] = bar
    return dict(sorted(latest.items()))
