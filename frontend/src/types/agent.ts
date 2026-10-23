// Request and response shapes for the agent endpoint.
// These mirror backend/app/schemas/agent.py exactly.

import type {
  AnalysisResponse,
  PriceHistoryResponse,
  SymbolListResponse,
} from "./market";

export interface HealthResponse {
  status: string;
  service: string;
  environment: string;
}

export interface AgentRequest {
  question: string;
  symbol?: string;
  // Set to false to run the chosen tool without asking Bedrock to explain it.
  explain?: boolean;
}

export interface DecisionMetadata {
  question_name: string;
  tool: string;
  confidence: number; // the model's own confidence, from 0 to 1
  probabilities: Record<string, number>;
  model: string;
  latency_ms?: number | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
}

export interface SymbolsResult {
  kind: "symbols";
  data: SymbolListResponse;
}

export interface PricesResult {
  kind: "prices";
  data: PriceHistoryResponse;
}

export interface AnalysisResult {
  kind: "analysis";
  data: AnalysisResponse;
}

export interface ReturnsResult {
  kind: "returns";
  data: unknown; // the /market/returns shape, not yet mirrored here
}

export type ToolResult =
  | SymbolsResult
  | PricesResult
  | AnalysisResult
  | ReturnsResult;

export interface BedrockMetadata {
  model_id: string;
  region: string;
  stop_reason?: string | null;
  input_tokens?: number | null;
  output_tokens?: number | null;
  latency_ms?: number | null;
}

/**
 * Why the explanation is or is not there.
 * - generated:  Bedrock produced the text
 * - skipped:    not requested, or there was nothing to explain (no Bedrock call)
 * - disabled:   the explanation layer is turned off in the configuration
 * - unavailable: Bedrock could not be used, so no call was made
 * - failed:     a call was made and did not produce an explanation
 */
export type ExplanationStatus =
  | "generated"
  | "skipped"
  | "disabled"
  | "unavailable"
  | "failed";

export interface AgentDecisionResponse {
  decision_made: boolean;
  question: string;
  symbol?: string | null;
  tool?: string | null;
  executed: boolean;
  decision?: DecisionMetadata | null;
  result?: ToolResult | null;
  data_source: string;
  disclaimer: string;
  note?: string | null;
  // Present only when explanation_status is "generated".
  explanation?: string | null;
  explanation_status: ExplanationStatus;
  explanation_error?: string | null;
  // Present only on a successful Bedrock call.
  bedrock?: BedrockMetadata | null;
}

export interface AgentDecisionError {
  decision_made: false;
  error: string; // a stable machine-readable reason
  message: string;
  question: string;
  symbol?: string | null;
  decision?: DecisionMetadata | null;
}

export interface AgentStatusResponse {
  decider_reachable: boolean;
  service_url: string;
  timeout_seconds: number;
  model?: string | null;
  checkpoint?: string | null;
  base_model?: string | null;
  device?: string | null;
  num_slots?: number | null;
  max_length?: number | null;
  bedrock_enabled: boolean;
  bedrock_model_id?: string | null;
  bedrock_region?: string | null;
  // The AWS *profile* name, not a credential.
  bedrock_profile?: string | null;
  // null when it could not be determined.
  bedrock_credentials_found?: boolean | null;
  note: string;
}
