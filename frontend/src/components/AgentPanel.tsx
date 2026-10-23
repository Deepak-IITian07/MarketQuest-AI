import { useEffect, useState, useCallback } from "react";
import { decide, getSymbols, ApiError } from "../services/api";
import type { AgentDecisionResponse, AgentRequest } from "../types/agent";
import type { SymbolQuote } from "../types/market";
import { formatINR, formatFractionAsPct, formatDateLong, formatCount } from "../utils/format";

export default function AgentPanel() {
  const [question, setQuestion] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<AgentDecisionResponse | null>(null);
  const [symbolOptions, setSymbolOptions] = useState<SymbolQuote[]>([]);

  // Load symbol list once for symbol extraction.
  useEffect(() => {
    getSymbols()
      .then((list) => {
        setSymbolOptions(list?.symbols ?? []);
      })
      .catch(() => {
        setSymbolOptions([]);
      });
  }, []);

  const extractSymbol = useCallback((): string | undefined => {
    if (!symbolOptions.length) return undefined;
    const q = question;
    for (const sym of symbolOptions) {
      const re = new RegExp(`\\b${sym.symbol}\\b`, "i");
      if (re.test(q)) {
        return sym.symbol;
      }
    }
    return undefined;
  }, [question, symbolOptions]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setResponse(null);
    setLoading(true);
    try {
      const found = extractSymbol();
      const body: AgentRequest = { question, explain: true };
      if (found) body.symbol = found;
      const res = await decide(body);
      setResponse(res as AgentDecisionResponse);
    } catch (err) {
      if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError(String(err));
      }
    } finally {
      setLoading(false);
    }
  };

  const renderResult = (result: any) => {
    if (!result) return null;
    const { kind, data } = result;
    switch (kind) {
      case "analysis": {
        const d = data as any;
        return (
          <ul>
            <li>Symbol: {d.symbol}</li>
            <li>Latest close: {formatINR(d.latest_close)}</li>
            <li>Moving average ({d.sma_window}): {formatINR(d.sma)}</li>
            <li>Volatility: {formatFractionAsPct(d.volatility.daily_volatility)}</li>
            <li>Total return: {formatFractionAsPct(d.total_return_pct)}</li>
            <li>Average volume: {formatCount(Math.round(d.average_volume))}</li>
          </ul>
        );
      }
      case "prices": {
        const d = data as any;
        return <p>Found {d.count} price points for {d.symbol}.</p>;
      }
      case "symbols": {
        const d = data as any;
        return <p>Found {d.count} symbols.</p>;
      }
      case "returns": {
        const d = data as any;
        return <p>Found {d.count} return entries.</p>;
      }
      default:
        return <pre>{JSON.stringify(data, null, 2)}</pre>;
    }
  };

  return (
    <div className="agent-panel" style={{ marginBottom: "1rem" }}>
      <h2>Agent Query</h2>
      <form onSubmit={handleSubmit}>
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
          style={{ width: "100%", fontFamily: "inherit" }}
          placeholder="Enter a market question…"
          required
        />
        <div style={{ marginTop: "0.5rem" }}>
          <button type="submit" disabled={loading || !question.trim()}>
            Send
          </button>
        </div>
      </form>
      {loading && <p>Loading…</p>}
      {error && <p style={{ color: "red" }}>{error}</p>}
      {response && (
        <div style={{ marginTop: "1rem" }}>
          <h3>Query: <strong>{response.question}</strong></h3>
          <p>Selected tool: {response.tool ?? "none"}</p>
          <p>Execution status: {response.executed ? "Success" : "None"}</p>
          {response.result && (
            <div>
              <h4>Result ({response.result.kind})</h4>
              {renderResult(response.result)}
            </div>
          )}
          <p>
            Disclaimer: <em>{response.disclaimer}</em>
          </p>
          <p>Bedrock explanation status: {response.explanation_status}</p>
          {response.explanation && (
            <div>
              <h4>Bedrock explanation</h4>
              <pre>{response.explanation}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
