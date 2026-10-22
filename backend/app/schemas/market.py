"""Response models for the market data and analysis endpoints."""

from pydantic import BaseModel, Field

#: Every market response carries this so a consumer can never mistake the
#: bundled demo prices for real market data.
DATA_SOURCE = "synthetic_demo"
DATA_DISCLAIMER = (
    "Synthetic demo data generated locally for development. Not real market data."
)


class PricePoint(BaseModel):
    """One daily observation."""

    date: str = Field(..., description="ISO date (YYYY-MM-DD).")
    open: float
    high: float
    low: float
    close: float
    volume: int


class SymbolQuote(BaseModel):
    """A symbol and its most recent sample price."""

    symbol: str
    latest_date: str
    latest_close: float
    observations: int


class SymbolListResponse(BaseModel):
    """Response for `GET /market/symbols`."""

    data_source: str = DATA_SOURCE
    disclaimer: str = DATA_DISCLAIMER
    count: int
    symbols: list[SymbolQuote]


class PriceHistoryResponse(BaseModel):
    """Response for `GET /market/prices/{symbol}`."""

    data_source: str = DATA_SOURCE
    disclaimer: str = DATA_DISCLAIMER
    symbol: str
    currency: str = "INR"
    count: int
    prices: list[PricePoint]


class DailyReturn(BaseModel):
    """A single daily percentage return."""

    date: str
    return_pct: float = Field(..., description="Decimal fraction, e.g. 0.0125 = +1.25%.")


class ReturnsResponse(BaseModel):
    """Response for `GET /market/returns/{symbol}`."""

    data_source: str = DATA_SOURCE
    disclaimer: str = DATA_DISCLAIMER
    symbol: str
    count: int
    returns: list[DailyReturn]


class VolatilityStats(BaseModel):
    """Volatility over a window of daily returns."""

    daily_volatility: float
    annualized_volatility: float
    window: int = Field(..., description="Number of daily returns used.")
    observations: int
    annualization_factor: int = Field(..., description="Trading days per year (252).")


class AnalysisResponse(BaseModel):
    """Response for `GET /market/analysis/{symbol}`."""

    data_source: str = DATA_SOURCE
    disclaimer: str = DATA_DISCLAIMER
    symbol: str
    currency: str = "INR"
    observations: int
    first_date: str
    last_date: str
    latest_close: float
    sma: float = Field(..., description="Simple moving average of closing prices.")
    sma_window: int
    volatility: VolatilityStats
    total_return_pct: float = Field(..., description="Total return over the whole sample.")
    average_volume: float
