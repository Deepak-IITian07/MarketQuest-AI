"""Market data and analysis endpoints backed by the local sample dataset."""

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.market import (
    AnalysisResponse,
    PriceHistoryResponse,
    ReturnsResponse,
    SymbolListResponse,
)
from app.services import market_queries
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
        return market_queries.build_symbols_response()
    except DataValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sample price data could not be loaded: {exc}",
        ) from exc


@router.get("/prices/{symbol}", response_model=PriceHistoryResponse)
def get_prices(symbol: str) -> PriceHistoryResponse:
    """Return the full sample price history for one symbol, oldest first."""
    try:
        return market_queries.build_prices_response(symbol)
    except SymbolNotFoundError as exc:
        raise _not_found(exc) from exc
    except DataValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sample price data could not be loaded: {exc}",
        ) from exc


@router.get("/returns/{symbol}", response_model=ReturnsResponse)
def get_returns(symbol: str) -> ReturnsResponse:
    """Return the simple daily percentage returns derived from closing prices."""
    try:
        return market_queries.build_returns_response(symbol)
    except SymbolNotFoundError as exc:
        raise _not_found(exc) from exc
    except DataValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sample price data could not be loaded: {exc}",
        ) from exc
    except InsufficientDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except AnalysisError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc


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
        description="Number of daily returns used by the volatility estimate.",
    ),
) -> AnalysisResponse:
    """Return a basic analysis summary for one symbol."""
    try:
        return market_queries.build_analysis_response(
            symbol,
            sma_window=sma_window,
            volatility_window=volatility_window,
        )
    except SymbolNotFoundError as exc:
        raise _not_found(exc) from exc
    except DataValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sample price data could not be loaded: {exc}",
        ) from exc
    except InvalidWindowError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except InsufficientDataError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
    except AnalysisError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc
