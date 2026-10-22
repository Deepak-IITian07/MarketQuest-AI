import type { AgentAnalysisRequest, AgentAnalysisResponse, HealthResponse } from "../types/agent";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, init);
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json() as Promise<T>;
}

export const getHealth = () => request<HealthResponse>("/health");

// PLANNED (Part 2+): the backend endpoint does not exist yet.
export const analyzeStock = (body: AgentAnalysisRequest) =>
  request<AgentAnalysisResponse>("/agent/analyze", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
