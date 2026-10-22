import type { SymbolQuote } from "../types/market";
import { formatINR } from "../utils/format";

type Props = {
  symbols: SymbolQuote[];
  selected: string | null;
  onSelect: (symbol: string) => void;
  disabled?: boolean;
};

export default function SymbolSelector({ symbols, selected, onSelect, disabled }: Props) {
  return (
    <div className="symbol-grid" role="group" aria-label="Choose a demo symbol">
      {symbols.map((quote) => {
        const active = quote.symbol === selected;
        return (
          <button
            key={quote.symbol}
            type="button"
            className={`symbol-card${active ? " is-active" : ""}`}
            aria-pressed={active}
            disabled={disabled}
            onClick={() => onSelect(quote.symbol)}
          >
            <span className="symbol-name">{quote.symbol}</span>
            <span className="symbol-price">{formatINR(quote.latest_close)}</span>
            <span className="symbol-meta">
              {quote.observations} sessions · {quote.latest_date}
            </span>
            <span className="symbol-tag">DEMO</span>
          </button>
        );
      })}
    </div>
  );
}
