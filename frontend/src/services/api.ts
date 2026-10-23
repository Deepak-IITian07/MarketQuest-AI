import type {
  AgentDecisionResponse,
  AgentRequest,
  HealthResponse,
} from "../types/agent";
import type {
  AnalysisResponse,
  PriceHistoryResponse,
  SymbolListResponse,
} from "../types/market";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

/** An HTTP or transport failure, with the backend's own message when it gave one. */
export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, init);
  } catch (cause) {
    // An aborted request is a navigation, not a failure - let it through.
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ApiError(
      `Could not reach the backend at ${BASE_URL}. Start it with "uvicorn main:app --reload" in the backend folder.`,
      0,
    );
  }

  if (!res.ok) {
    throw new ApiError(`API ${res.status}: ${await readDetail(res)}`, res.status);
  }
  return res.json() as Promise<T>;
}

/** Prefer the backend's `detail` string; fall back to the raw status text. */
async function readDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body?.detail === "string") return body.detail;
    if (body?.detail) return JSON.stringify(body.detail);
  } catch {
    // Not JSON - keep the status text below.
  }
  return res.statusText || "Request failed";
}

export const getHealth = () => request<HealthResponse>("/health");

/** Every symbol in the sample dataset, with its most recent sample close. */
export const getSymbols = (signal?: AbortSignal) =>
  request<SymbolListResponse>("/market/symbols", { signal });

/** Full sample price history for one symbol, oldest first. */
export const getPrices = (symbol: string, signal?: AbortSignal) =>
  request<PriceHistoryResponse>(`/market/prices/${encodeURIComponent(symbol)}`, { signal });

/** SMA, volatility and total return for one symbol. */
export const getAnalysis = (symbol: string, signal?: AbortSignal) =>
  request<AnalysisResponse>(`/market/analysis/${encodeURIComponent(symbol)}`, { signal });

/**
 * Ask the Decider which market tool answers the question, run that tool, and
 * return the decision, the market data and (if Bedrock is available) an
 * explanation of the numbers.
 *
 * The dashboard does not call this yet -- there is no chat interface -- but
 * the endpoint exists and the shapes below mirror the backend exactly.
 */
export const decide = (body: AgentRequest) =>
  request<AgentDecisionResponse>("/agent/decide", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
