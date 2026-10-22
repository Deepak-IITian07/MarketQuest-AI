"""Pure analysis functions over closing prices.

Every function here is side-effect free, takes plain numbers, and raises a
domain error instead of returning a misleading value when the data is not
sufficient. No prices are ever interpolated, extrapolated, or invented.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import sqrt
from statistics import fmean, stdev

#: Assumed number of trading days per year, used to annualise volatility.
TRADING_DAYS_PER_YEAR = 252


class AnalysisError(Exception):
    """Base class for analysis problems."""


class InvalidWindowError(AnalysisError):
    """The requested window is not usable (for example a window below 1)."""


class InsufficientDataError(AnalysisError):
    """The requested window needs more observations than are available."""


@dataclass(frozen=True, slots=True)
class VolatilityResult:
    """Volatility measured over a window of daily returns."""

    daily_volatility: float
    annualized_volatility: float
    window: int
    observations: int
    annualization_factor: int = TRADING_DAYS_PER_YEAR


@dataclass(frozen=True, slots=True)
class AnalysisSummary:
    """Everything the analysis endpoint reports for one symbol."""

    symbol: str
    observations: int
    first_date: str
    last_date: str
    latest_close: float
    sma: float
    sma_window: int
    volatility: VolatilityResult
    total_return_pct: float
    average_volume: float


def daily_returns(closes: Sequence[float]) -> list[float]:
    """Convert closing prices into simple daily percentage returns.

    The result has `len(closes) - 1` entries, where entry `i` is the return from
    `closes[i]` to `closes[i + 1]`, expressed as a decimal fraction
    (0.01 means +1%).

    Raises:
        InsufficientDataError: Fewer than two closing prices were supplied.
        AnalysisError: A previous close is zero, so the return is undefined.
    """
    if len(closes) < 2:
        raise InsufficientDataError(
            f"Daily returns need at least 2 closing prices, got {len(closes)}."
        )

    returns: list[float] = []
    for previous, current in zip(closes, closes[1:]):
        if previous == 0:
            raise AnalysisError("Cannot compute a daily return from a closing price of 0.")
        returns.append((current - previous) / previous)
    return returns


def simple_moving_average(closes: Sequence[float], window: int) -> float:
    """Average of the most recent `window` closing prices.

    Raises:
        InvalidWindowError: `window` is below 1.
        InsufficientDataError: Fewer than `window` closing prices are available.
    """
    if window < 1:
        raise InvalidWindowError(f"Moving average window must be at least 1, got {window}.")
    if len(closes) < window:
        raise InsufficientDataError(
            f"Moving average window {window} needs {window} observations, "
            f"but only {len(closes)} are available."
        )
    return fmean(closes[-window:])


def historical_volatility(closes: Sequence[float], window: int) -> VolatilityResult:
    """Sample standard deviation of daily returns over the most recent `window` returns.

    `window` counts *returns*, not closing prices, so `window + 1` closing prices
    are needed. The daily figure uses the sample standard deviation (n - 1);
    the annualised figure multiplies it by the square root of 252.

    Raises:
        InvalidWindowError: `window` is below 2 (a single return has no spread).
        InsufficientDataError: Fewer than `window` returns are available.
    """
    if window < 2:
        raise InvalidWindowError(
            f"Volatility window must be at least 2 returns, got {window}."
        )

    returns = daily_returns(closes)
    if len(returns) < window:
        raise InsufficientDataError(
            f"Volatility window {window} needs {window} daily returns "
            f"({window + 1} closing prices), but only {len(returns)} returns "
            f"({len(closes)} closing prices) are available."
        )

    sample = returns[-window:]
    daily = stdev(sample)
    return VolatilityResult(
        daily_volatility=daily,
        annualized_volatility=daily * sqrt(TRADING_DAYS_PER_YEAR),
        window=window,
        observations=len(sample),
    )


def total_return_pct(closes: Sequence[float]) -> float:
    """Total percentage return across the whole sample, in percent.

    Raises:
        InsufficientDataError: Fewer than two closing prices were supplied.
    """
    if len(closes) < 2:
        raise InsufficientDataError(
            f"Total return needs at least 2 closing prices, got {len(closes)}."
        )
    first, last = closes[0], closes[-1]
    if first == 0:
        raise AnalysisError("Cannot compute a total return from a starting close of 0.")
    return (last - first) / first * 100.0
