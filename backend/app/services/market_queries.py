"""Response builders for the market dataset.

The HTTP endpoints and the Decider-backed agent both need to turn the local
sample dataset into the same response models. Keeping the assembly in one
place means the agent can never return a different shape -- or a different
data-source warning -- from the plain market endpoints.

The builders raise the same domain errors the services raise; the HTTP layer
maps them to status codes.
"""

from __future__ import annotations

from app.schemas.market import (
    AnalysisResponse,
    DailyReturn,
    PriceHistoryResponse,
    PricePoint,
    ReturnsResponse,
    SymbolListResponse,
    SymbolQuote,
    VolatilityStats,
)
from app.services import analysis as analysis_service
from app.services import market_data
from app.services.analysis import AnalysisError, InsufficientDataError
from app.services.market_data import DataValidationError, SymbolNotFoundError

__all__ = [
    "build_analysis_response",
    "build_prices_response",
    "build_returns_response",
    "build_symbols_response",
]


def build_symbols_response() -> SymbolListResponse:
    """Every symbol in the dataset with its latest sample price.

    Raises:
        DataValidationError: The sample dataset is missing or malformed.
    """
    latest = market_data.get_latest_prices()

    counts: dict[str, int] = {}
    for bar in market_data.load_price_bars():
        counts[bar.symbol] = counts.get(bar.symbol, 0) + 1

    quotes = [
        SymbolQuote(
            symbol=symbol,
            latest_date=bar.date.isoformat(),
            latest_close=bar.close,
            observations=counts.get(symbol, 0),
        )
        for symbol, bar in latest.items()
    ]
    return SymbolListResponse(count=len(quotes), symbols=quotes)


def build_prices_response(symbol: str) -> PriceHistoryResponse:
    """The full sample price history for one symbol, oldest first.

    Raises:
        SymbolNotFoundError: The symbol is not in the dataset.
        DataValidationError: The sample dataset is missing or malformed.
    """
    bars = market_data.get_price_history(symbol)
    return PriceHistoryResponse(
        symbol=bars[0].symbol,
        count=len(bars),
        prices=[
            PricePoint(
                date=bar.date.isoformat(),
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            for bar in bars
        ],
    )


def build_returns_response(symbol: str) -> ReturnsResponse:
    """The simple daily percentage returns derived from closing prices.

    Raises:
        SymbolNotFoundError: The symbol is not in the dataset.
        DataValidationError: The sample dataset is missing or malformed.
        InsufficientDataError: Fewer than two closing prices are available.
        AnalysisError: A previous close is zero, so a return is undefined.
    """
    bars = market_data.get_price_history(symbol)

    closes = [bar.close for bar in bars]
    returns = analysis_service.daily_returns(closes)

    # A return is realised on the date of the *later* close.
    dated = [
        DailyReturn(date=bars[index + 1].date.isoformat(), return_pct=value)
        for index, value in enumerate(returns)
    ]
    return ReturnsResponse(symbol=bars[0].symbol, count=len(dated), returns=dated)


def build_analysis_response(
    symbol: str,
    *,
    sma_window: int = 20,
    volatility_window: int = 20,
) -> AnalysisResponse:
    """The analysis summary for one symbol.

    Raises:
        SymbolNotFoundError: The symbol is not in the dataset.
        DataValidationError: The sample dataset is missing or malformed.
        InvalidWindowError: A window is below its minimum.
        InsufficientDataError: A window needs more observations than exist.
        AnalysisError: A previous close is zero, so a return is undefined.
    """
    bars = market_data.get_price_history(symbol)

    closes = [bar.close for bar in bars]
    try:
        sma = analysis_service.simple_moving_average(closes, sma_window)
        volatility = analysis_service.historical_volatility(closes, volatility_window)
        total_return = analysis_service.total_return_pct(closes)
    except InsufficientDataError as exc:
        # Say how much data there actually is, so the caller can lower the window.
        raise InsufficientDataError(
            f"{exc} "
            f"Symbol '{bars[0].symbol}' has {len(closes)} sample observations "
            f"({len(closes) - 1} daily returns). Lower the window to continue."
        ) from exc

    average_volume = sum(bar.volume for bar in bars) / len(bars)

    return AnalysisResponse(
        symbol=bars[0].symbol,
        observations=len(bars),
        first_date=bars[0].date.isoformat(),
        last_date=bars[-1].date.isoformat(),
        latest_close=closes[-1],
        sma=sma,
        sma_window=sma_window,
        volatility=VolatilityStats(
            daily_volatility=volatility.daily_volatility,
            annualized_volatility=volatility.annualized_volatility,
            window=volatility.window,
            observations=volatility.observations,
            annualization_factor=volatility.annualization_factor,
        ),
        total_return_pct=total_return,
        average_volume=average_volume,
    )
