import { useCallback, useEffect, useMemo, useState } from "react";
import MetricTile from "../components/MetricTile";
import PanelState from "../components/PanelState";
import PriceChart from "../components/PriceChart";
import StatusBadge from "../components/StatusBadge";
import SymbolSelector from "../components/SymbolSelector";
import AgentPanel from "../components/AgentPanel";
import { ApiError, getAnalysis, getPrices, getSymbols } from "../services/api";
import type { AnalysisResponse, PricePoint, SymbolQuote } from "../types/market";
import {
  formatCount,
  formatDateLong,
  formatFractionAsPct,
  formatINR,
  formatSignedPct,
} from "../utils/format";

type LoadState = "loading" | "ready" | "error";

type SymbolState = {
  status: LoadState;
  symbols: SymbolQuote[];
  disclaimer: string;
  error: string | null;
};

type DetailState = {
  status: LoadState;
  prices: PricePoint[];
  analysis: AnalysisResponse | null;
  error: string | null;
};

const EMPTY_SYMBOLS: SymbolState = {
  status: "loading",
  symbols: [],
  disclaimer: "",
  error: null,
};

const EMPTY_DETAIL: DetailState = {
  status: "loading",
  prices: [],
  analysis: null,
  error: null,
};

function messageFor(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return "Something went wrong.";
}

export default function Dashboard() {
  const [symbolState, setSymbolState] = useState<SymbolState>(EMPTY_SYMBOLS);
  const [detail, setDetail] = useState<DetailState>(EMPTY_DETAIL);
  const [selected, setSelected] = useState<string | null>(null);
  const [showSma, setShowSma] = useState(true);
  const [reloadToken, setReloadToken] = useState(0);

  // Load the symbol list, then keep the current selection if it still exists.
  useEffect(() => {
    const controller = new AbortController();
    setSymbolState(EMPTY_SYMBOLS);

    getSymbols(controller.signal)
      .then((data) => {
        setSymbolState({
          status: "ready",
          symbols: data.symbols,
          disclaimer: data.disclaimer,
          error: null,
        });
        setSelected((current) =>
          current && data.symbols.some((s) => s.symbol === current)
            ? current
            : (data.symbols[0]?.symbol ?? null),
        );
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setSymbolState({
          status: "error",
          symbols: [],
          disclaimer: "",
          error: messageFor(error),
        });
      });

    return () => controller.abort();
  }, [reloadToken]);

  // Load prices + analysis for the selected symbol.
  useEffect(() => {
    if (!selected) {
      setDetail(EMPTY_DETAIL);
      return;
    }

    const controller = new AbortController();
    setDetail(EMPTY_DETAIL);

    Promise.all([
      getPrices(selected, controller.signal),
      getAnalysis(selected, controller.signal),
    ])
      .then(([prices, analysis]) => {
        setDetail({ status: "ready", prices: prices.prices, analysis, error: null });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setDetail({ status: "error", prices: [], analysis: null, error: messageFor(error) });
      });

    return () => controller.abort();
  }, [selected, reloadToken]);

  const retry = useCallback(() => setReloadToken((token) => token + 1), []);

  const derived = useMemo(() => {
    const prices = detail.prices;
    const analysis = detail.analysis;
    if (!analysis || prices.length === 0) return null;

    const last = prices[prices.length - 1];
    const previous = prices.length > 1 ? prices[prices.length - 2].close : null;
    const changePct =
      previous !== null && previous !== 0 ? ((last.close - previous) / previous) * 100 : 0;
    const vsSmaPct = analysis.sma !== 0 ? ((last.close - analysis.sma) / analysis.sma) * 100 : 0;

    return { last, changePct, vsSmaPct };
  }, [detail]);

  const symbolsLoading = symbolState.status === "loading";
  const noSymbols = symbolState.status === "ready" && symbolState.symbols.length === 0;

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="crest" aria-hidden="true">
            <svg viewBox="0 0 32 32" width="28" height="28">
              <path
                d="M4 26 L4 12 L10 18 L16 6 L22 18 L28 12 L28 26 Z"
                fill="none"
                stroke="var(--gold)"
                strokeWidth="2"
                strokeLinejoin="round"
              />
              <circle cx="16" cy="6" r="2.6" fill="var(--gold)" />
            </svg>
          </span>
          <div>
            <p className="brand-name">MarketQuest AI</p>
            <p className="brand-sub">Market simulation sandbox</p>
          </div>
        </div>
        <div className="topbar-right">
          <span className="badge badge-demo">Synthetic demo data</span>
          <StatusBadge />
        </div>
      </header>

      <section className="hero">
        <p className="eyebrow">Quest 01 · Read the market</p>
        <h1>
          Run the market<span className="hero-dot">.</span>
        </h1>
        <p className="tagline">
          Pick a demo company, read its price history, and check the backend&apos;s own
          analysis. Nothing here is real money.
        </p>
      </section>

      <main className="dashboard">
        <section className="panel panel-agent">
          <AgentPanel />
        </section>
        <section className="panel panel-selector">
          <div className="panel-head">
            <h2>Choose a symbol</h2>
            <button type="button" className="btn btn-ghost" onClick={retry}>
              Reload
            </button>
          </div>

          {symbolsLoading && (
            <div className="symbol-grid">
              {[0, 1, 2, 3].map((key) => (
                <div key={key} className="skeleton symbol-card" />
              ))}
            </div>
          )}

          {symbolState.status === "error" && (
            <PanelState
              tone="error"
              title="Could not load the symbol list"
              message={symbolState.error ?? undefined}
              actionLabel="Try again"
              onAction={retry}
            />
          )}

          {noSymbols && (
            <PanelState
              tone="empty"
              title="No symbols in the demo dataset"
              message="The backend returned an empty symbol list. Check that data/sample_prices.csv exists."
              actionLabel="Reload"
              onAction={retry}
            />
          )}

          {symbolState.status === "ready" && !noSymbols && (
            <SymbolSelector
              symbols={symbolState.symbols}
              selected={selected}
              onSelect={setSelected}
            />
          )}
        </section>

        <section className="panel panel-detail">
          <div className="panel-head">
            <h2>
              {selected ? `${selected} · price history` : "Price history"}
            </h2>
            {detail.status === "ready" && (
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={showSma}
                  onChange={(event) => setShowSma(event.target.checked)}
                />
                <span>Moving average</span>
              </label>
            )}
          </div>

          {detail.status === "loading" && (
            <>
              <div className="skeleton skeleton-headline" />
              <div className="skeleton skeleton-chart" />
            </>
          )}

          {detail.status === "error" && (
            <PanelState
              tone="error"
              title={`Could not load ${selected ?? "this symbol"}`}
              message={detail.error ?? undefined}
              actionLabel="Try again"
              onAction={retry}
            />
          )}

          {detail.status === "ready" &&
            detail.prices.length === 0 && (
              <PanelState
                tone="empty"
                title="No price history for this symbol"
                message="The backend returned zero observations."
                actionLabel="Reload"
                onAction={retry}
              />
            )}

          {detail.status === "ready" && detail.prices.length > 0 && detail.analysis && (
            <>
              <div className="headline">
                <div>
                  <p className="headline-label">Latest sample close</p>
                  <p className="headline-price">{formatINR(detail.analysis.latest_close)}</p>
                  <p className="headline-meta">
                    {formatDateLong(detail.analysis.last_date)} ·{" "}
                    {formatCount(detail.analysis.observations)} sessions ·{" "}
                    {detail.analysis.currency}
                  </p>
                </div>
                {derived && (
                  <div className="headline-deltas">
                    <span
                      className={`delta ${derived.changePct >= 0 ? "up" : "down"}`}
                      title="Change from the previous session's close"
                    >
                      {formatSignedPct(derived.changePct)} vs prev
                    </span>
                    <span
                      className={`delta ${derived.vsSmaPct >= 0 ? "up" : "down"}`}
                      title={`Close compared with the ${detail.analysis.sma_window}-session moving average`}
                    >
                      {formatSignedPct(derived.vsSmaPct)} vs SMA
                    </span>
                  </div>
                )}
              </div>

              <PriceChart
                prices={detail.prices}
                smaWindow={detail.analysis.sma_window}
                showSma={showSma}
              />

              <div className="metric-grid">
                <MetricTile
                  label={`${detail.analysis.sma_window}-session moving average`}
                  value={formatINR(detail.analysis.sma)}
                  hint="Mean of the most recent closes, computed by the backend"
                />
                <MetricTile
                  label="Daily volatility"
                  value={formatFractionAsPct(detail.analysis.volatility.daily_volatility)}
                  hint={`Sample std-dev over ${detail.analysis.volatility.window} daily returns`}
                />
                <MetricTile
                  label="Annualised volatility"
                  value={formatFractionAsPct(detail.analysis.volatility.annualized_volatility)}
                  hint={`Scaled by √${detail.analysis.volatility.annualization_factor} trading days`}
                />
                <MetricTile
                  label="Total return"
                  value={formatSignedPct(detail.analysis.total_return_pct)}
                  hint={`${formatDateLong(detail.analysis.first_date)} → ${formatDateLong(detail.analysis.last_date)}`}
                  tone={detail.analysis.total_return_pct >= 0 ? "up" : "down"}
                />
                <MetricTile
                  label="Average volume"
                  value={formatCount(detail.analysis.average_volume)}
                  hint="Mean daily volume across the sample"
                />
                <MetricTile
                  label="Data source"
                  value={detail.analysis.data_source}
                  hint="Generated locally — not real market prices"
                />
              </div>
            </>
          )}
        </section>
      </main>

      <footer className="footer">
        <p>
          <strong>Synthetic demo data.</strong> Every price on this page comes from a locally
          generated sample file ({symbolState.disclaimer || "synthetic demo data"}). It is not
          real market data, it does not represent any real company, and nothing here is
          investment advice.
        </p>
        <p className="footer-meta">
          MarketQuest AI · Part 2 market dashboard · read-only, no trading, no external APIs.
        </p>
      </footer>
    </div>
  );
}
