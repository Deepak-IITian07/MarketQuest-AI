// Response shapes for the Part 2 market endpoints.
// These mirror backend/app/schemas/market.py exactly.

export interface PricePoint {
  date: string; // ISO date (YYYY-MM-DD)
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface SymbolQuote {
  symbol: string;
  latest_date: string;
  latest_close: number;
  observations: number;
}

export interface SymbolListResponse {
  data_source: string;
  disclaimer: string;
  count: number;
  symbols: SymbolQuote[];
}

export interface PriceHistoryResponse {
  data_source: string;
  disclaimer: string;
  symbol: string;
  currency: string;
  count: number;
  prices: PricePoint[];
}

export interface VolatilityStats {
  daily_volatility: number; // decimal fraction, e.g. 0.0125 = 1.25%
  annualized_volatility: number; // decimal fraction
  window: number;
  observations: number;
  annualization_factor: number;
}

export interface AnalysisResponse {
  data_source: string;
  disclaimer: string;
  symbol: string;
  currency: string;
  observations: number;
  first_date: string;
  last_date: string;
  latest_close: number;
  sma: number;
  sma_window: number;
  volatility: VolatilityStats;
  total_return_pct: number; // already in percent, e.g. 4.2 means +4.2%
  average_volume: number;
}
