import { useMemo, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import type { PricePoint } from "../types/market";
import { formatCount, formatDate, formatINR, formatINRCompact } from "../utils/format";

type Props = {
  prices: PricePoint[];
  /** Window for the moving-average overlay; matches the backend's `sma_window`. */
  smaWindow: number;
  showSma: boolean;
};

const W = 960;
const H = 320;
const PAD = { top: 16, right: 20, bottom: 38, left: 72 };
const INNER_W = W - PAD.left - PAD.right;
const INNER_H = H - PAD.top - PAD.bottom;

type Geometry = {
  x: (index: number) => number;
  y: (value: number) => number;
  linePath: string;
  areaPath: string;
  smaPath: string;
  gridLines: { value: number; y: number }[];
  xTicks: { index: number; label: string }[];
  min: number;
  max: number;
  count: number;
};

function buildGeometry(prices: PricePoint[], smaWindow: number, showSma: boolean): Geometry {
  const closes = prices.map((p) => p.close);
  const n = closes.length;

  const rawMin = Math.min(...closes);
  const rawMax = Math.max(...closes);
  const spread = rawMax - rawMin;
  const pad = spread > 0 ? spread * 0.14 : Math.max(Math.abs(rawMax) * 0.05, 1);
  const min = rawMin - pad;
  const max = rawMax + pad;

  const x = (index: number) =>
    PAD.left + (n === 1 ? INNER_W / 2 : (index / (n - 1)) * INNER_W);
  const y = (value: number) =>
    PAD.top + (1 - (value - min) / (max - min)) * INNER_H;

  const points = closes.map((close, index) => `${x(index).toFixed(2)},${y(close).toFixed(2)}`);
  const linePath = `M ${points.join(" L ")}`;
  const baseline = (PAD.top + INNER_H).toFixed(2);
  const areaPath = `${linePath} L ${x(n - 1).toFixed(2)},${baseline} L ${x(0).toFixed(2)},${baseline} Z`;

  let smaPath = "";
  if (showSma && smaWindow >= 1 && n >= smaWindow) {
    const rolling: string[] = [];
    let running = 0;
    for (let i = 0; i < n; i += 1) {
      running += closes[i];
      if (i >= smaWindow) running -= closes[i - smaWindow];
      if (i >= smaWindow - 1) {
        rolling.push(`${x(i).toFixed(2)},${y(running / smaWindow).toFixed(2)}`);
      }
    }
    smaPath = `M ${rolling.join(" L ")}`;
  }

  const gridLines = Array.from({ length: 5 }, (_, i) => {
    const value = max - (i / 4) * (max - min);
    return { value, y: y(value) };
  });

  const tickIndexes = [...new Set([0, Math.round((n - 1) / 3), Math.round(((n - 1) * 2) / 3), n - 1])]
    .filter((i) => i >= 0 && i < n)
    .sort((a, b) => a - b);
  const xTicks = tickIndexes.map((index) => ({
    index,
    label: formatDate(prices[index].date),
  }));

  return { x, y, linePath, areaPath, smaPath, gridLines, xTicks, min, max, count: n };
}

export default function PriceChart({ prices, smaWindow, showSma }: Props) {
  const [hover, setHover] = useState<number | null>(null);
  const geometry = useMemo(
    () => buildGeometry(prices, smaWindow, showSma),
    [prices, smaWindow, showSma],
  );

  if (prices.length === 0) return null;

  const handleMove = (event: ReactPointerEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    if (rect.width === 0) return;
    const viewX = ((event.clientX - rect.left) / rect.width) * W;
    const ratio = (viewX - PAD.left) / INNER_W;
    const index = Math.round(ratio * (geometry.count - 1));
    setHover(Math.min(Math.max(index, 0), geometry.count - 1));
  };

  const hovered = hover === null ? null : prices[hover];
  const hoveredClose = hovered ? hovered.close : 0;
  const previousClose = hover !== null && hover > 0 ? prices[hover - 1].close : null;
  const changePct =
    previousClose && previousClose !== 0
      ? ((hoveredClose - previousClose) / previousClose) * 100
      : null;

  const last = prices[prices.length - 1];
  const lastChangePct =
    prices.length > 1 && prices[0].close !== 0
      ? ((last.close - prices[prices.length - 2].close) / prices[prices.length - 2].close) * 100
      : 0;

  return (
    <div className="chart-wrap">
      <svg
        className="chart"
        viewBox={`0 0 ${W} ${H}`}
        style={{ aspectRatio: `${W} / ${H}` }}
        role="img"
        aria-label={`Closing price history for ${prices.length} synthetic demo observations`}
        onPointerMove={handleMove}
        onPointerLeave={() => setHover(null)}
      >
        <defs>
          <linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--gold)" stopOpacity="0.38" />
            <stop offset="100%" stopColor="var(--gold)" stopOpacity="0" />
          </linearGradient>
        </defs>

        {geometry.gridLines.map((line) => (
          <g key={line.y}>
            <line
              className="chart-grid"
              x1={PAD.left}
              x2={W - PAD.right}
              y1={line.y}
              y2={line.y}
            />
            <text className="chart-axis-label" x={PAD.left - 10} y={line.y + 4} textAnchor="end">
              {formatINRCompact(line.value)}
            </text>
          </g>
        ))}

        <path className="chart-area" d={geometry.areaPath} fill="url(#areaFill)" />
        <path className="chart-line" d={geometry.linePath} />
        {geometry.smaPath && <path className="chart-sma" d={geometry.smaPath} />}

        {geometry.xTicks.map((tick) => (
          <text
            key={tick.index}
            className="chart-axis-label"
            x={geometry.x(tick.index)}
            y={H - 12}
            textAnchor={
              tick.index === 0 ? "start" : tick.index === geometry.count - 1 ? "end" : "middle"
            }
          >
            {tick.label}
          </text>
        ))}

        {hover !== null && hovered && (
          <g>
            <line
              className="chart-crosshair"
              x1={geometry.x(hover)}
              x2={geometry.x(hover)}
              y1={PAD.top}
              y2={PAD.top + INNER_H}
            />
            <circle
              className="chart-point"
              cx={geometry.x(hover)}
              cy={geometry.y(hovered.close)}
              r={5}
            />
          </g>
        )}

        <circle
          className="chart-point chart-point-last"
          cx={geometry.x(geometry.count - 1)}
          cy={geometry.y(last.close)}
          r={4}
        />
      </svg>

      {hovered && (
        <div
          className="chart-tooltip"
          style={{
            left: `${(geometry.x(hover as number) / W) * 100}%`,
            top: `${(geometry.y(hoveredClose) / H) * 100}%`,
          }}
        >
          <strong>{hovered.date}</strong>
          <span>{formatINR(hovered.close)}</span>
          {changePct !== null && (
            <span className={changePct >= 0 ? "up" : "down"}>
              {changePct >= 0 ? "+" : ""}
              {changePct.toFixed(2)}% vs prev
            </span>
          )}
          <span className="muted">Vol {formatCount(hovered.volume)}</span>
        </div>
      )}

      <div className="chart-legend">
        <span className="legend-item">
          <i className="swatch swatch-close" /> Close
        </span>
        {showSma && (
          <span className="legend-item">
            <i className="swatch swatch-sma" /> {smaWindow}-session moving average
          </span>
        )}
        <span className="legend-item muted">
          Last change {lastChangePct >= 0 ? "+" : ""}
          {lastChangePct.toFixed(2)}% · synthetic demo prices
        </span>
      </div>
    </div>
  );
}
