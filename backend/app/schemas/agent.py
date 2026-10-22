"""Request and response models for the Decider-backed agent endpoint."""

from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

from app.schemas.market import (
    DATA_DISCLAIMER,
    DATA_SOURCE,
    AnalysisResponse,
    PriceHistoryResponse,
    ReturnsResponse,
    SymbolListResponse,
)


class AgentRequest(BaseModel):
    """A market question, and optionally the symbol it is about."""

    question: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="The user's question, in their own words.",
    )
    symbol: str | None = Field(
        default=None,
        max_length=32,
        description="The symbol the question is about, if it is already known.",
    )


class DecisionMetadata(BaseModel):
    """What the Decider reported about the choice it made."""

    question_name: str
    tool: str
    confidence: float = Field(
        ..., description="The model's own confidence in the choice, from 0 to 1."
    )
    probabilities: dict[str, float] = Field(
        ..., description="The probability the model gave to every option offered."
    )
    model: str = Field(..., description="The model id the service reported.")
    latency_ms: float | None = Field(
        default=None, description="How long the forward pass took, in milliseconds."
    )
    input_tokens: int | None = None
    output_tokens: int | None = None


class SymbolsResult(BaseModel):
    """The result of the `get_symbols` tool."""

    kind: Literal["symbols"] = "symbols"
    data: SymbolListResponse


class PricesResult(BaseModel):
    """The result of the `get_prices` tool."""

    kind: Literal["prices"] = "prices"
    data: PriceHistoryResponse


class AnalysisResult(BaseModel):
    """The result of the `get_analysis` tool."""

    kind: Literal["analysis"] = "analysis"
    data: AnalysisResponse


class ReturnsResult(BaseModel):
    """The result of the `get_returns` tool."""

    kind: Literal["returns"] = "returns"
    data: ReturnsResponse


#: The result of whichever tool the Decider chose.
ToolResult = Annotated[
    Union[SymbolsResult, PricesResult, AnalysisResult, ReturnsResult],
    Field(discriminator="kind"),
]


class AgentDecisionResponse(BaseModel):
    """A completed decision, and the market data it produced."""

    decision_made: bool = Field(
        ...,
        description="True only when the Decider itself made a usable choice.",
    )
    question: str
    symbol: str | None = None
    tool: str | None = Field(default=None, description="The tool the Decider chose.")
    executed: bool = Field(
        default=False, description="Whether that tool was actually run."
    )
    decision: DecisionMetadata | None = None
    result: ToolResult | None = None
    data_source: str = DATA_SOURCE
    disclaimer: str = DATA_DISCLAIMER
    note: str | None = None


class AgentDecisionError(BaseModel):
    """A failed decision.

    `decision_made` is False because the response carries no result of a
    model-made decision. When the model *did* choose a valid tool and the
    flow then failed -- because no symbol was supplied, or the market data
    could not be produced -- `decision` still carries that choice, so the
    caller can see what the model wanted. When the model itself failed, the
    message says in words that it did not make a usable decision.
    """

    decision_made: bool = False
    error: str = Field(..., description="A stable machine-readable reason.")
    message: str
    question: str
    symbol: str | None = None
    decision: DecisionMetadata | None = None


class AgentStatusResponse(BaseModel):
    """Whether the Decider service is up, and what it is serving."""

    decider_reachable: bool
    service_url: str
    timeout_seconds: float
    model: str | None = None
    checkpoint: str | None = None
    base_model: str | None = None
    device: str | None = None
    num_slots: int | None = None
    max_length: int | None = None
    note: str
