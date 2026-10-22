// Types for FUTURE agent requests. Planned, not implemented in Part 1.
// Shapes are provisional and will be aligned with the verified Strands Decider 2B interface.

export interface HealthResponse {
  status: string;
  service: string;
  environment: string;
}

export interface AgentAnalysisRequest {
  symbol: string; // e.g. "RELIANCE"
  question?: string;
}

export interface AgentAnalysisResponse {
  selectedTool: string | null; // null = valid "no action" decision
  explanation: string;
}
