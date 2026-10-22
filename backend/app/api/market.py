"""Market data and analysis endpoints backed by the local sample dataset."""

from fastapi import APIRouter, HTTPException, Query, status

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
from app.services.analysis import (
    AnalysisError,
    InsufficientDataError,
    InvalidWindowError,
)
from app.services.market_data import DataValidationError, SymbolNotFoundError

router = APIRouter(prefix="/market", tags=["market"])

DEFAULT_SMA_WINDOW = 20
DEFAULT_VOLATILITY_WINDOW = 20
MAX_WINDOW = 365


def _not_found(exc: SymbolNotFoundError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=(
            f"Unknown symbol '{exc.symbol}'. "
            f"Available symbols: {', '.join(exc.available) if exc.available else 'none'}."
        ),
    )


@router.get("/symbols", response_model=SymbolListResponse)
def list_symbols() -> SymbolListResponse:
    """List every symbol in the sample dataset with its latest sample price."""
    try:
        latest = market_data.get_latest_prices()
    except DataValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sample price data could not be loaded: {exc}",
        ) from exc

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


@router.get("/prices/{symbol}", response_model=PriceHistoryResponse)
def get_prices(symbol: str) -> PriceHistoryResponse:
    """Return the full sample price history for one symbol, oldest first."""
    try:
        bars = market_data.get_price_history(symbol)
    except SymbolNotFoundError as exc:
        raise _not_found(exc) from exc
    except DataValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sample price data could not be loaded: {exc}",
        ) from exc

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


@router.get("/returns/{symbol}", response_model=ReturnsResponse)
def get_returns(symbol: str) -> ReturnsResponse:
    """Return the simple daily percentage returns derived from closing prices."""
    try:
        bars = market_data.get_price_history(symbol)
    except SymbolNotFoundError as exc:
        raise _not_found(exc) from exc
    except DataValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sample price data could not be loaded: {exc}",
        ) from exc

    closes = [bar.close for bar in bars]
    try:
        returns = analysis_service.daily_returns(closes)
    except InsufficientDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except AnalysisError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    # A return is realised on the date of the *later* close.
    dated = [
        DailyReturn(date=bars[index + 1].date.isoformat(), return_pct=value)
        for index, value in enumerate(returns)
    ]
    return ReturnsResponse(symbol=bars[0].symbol, count=len(dated), returns=dated)


@router.get("/analysis/{symbol}", response_model=AnalysisResponse)
def get_analysis(
    symbol: str,
    sma_window: int = Query(
        default=DEFAULT_SMA_WINDOW,
        ge=1,
        le=MAX_WINDOW,
        description="Number of closing prices averaged by the simple moving average.",
    ),
    volatility_window: int = Query(
        default=DEFAULT_VOLATILITY_WINDOW,
        ge=2,
        le=MAX_WINDOW,
        description="Number of daily returns used for the volatility estimate.",
    ),
) -> AnalysisResponse:
    """Return a basic analysis summary for one symbol."""
    try:
        bars = market_data.get_price_history(symbol)
    except SymbolNotFoundError as exc:
        raise _not_found(exc) from exc
    except DataValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sample price data could not be loaded: {exc}",
        ) from exc

    closes = [bar.close for bar in bars]
    try:
        sma = analysis_service.simple_moving_average(closes, sma_window)
        volatility = analysis_service.historical_volatility(closes, volatility_window)
        total_return = analysis_service.total_return_pct(closes)
    except InvalidWindowError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except InsufficientDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"{exc} "
                f"Symbol '{bars[0].symbol}' has {len(closes)} sample observations "
                f"({len(closes) - 1} daily returns). Lower the window to continue."
            ),
        ) from exc
    except AnalysisError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
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
