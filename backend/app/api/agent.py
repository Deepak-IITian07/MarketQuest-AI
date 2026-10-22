"""The agent endpoint: let the Decider choose which market tool to run.

The Decider picks a tool. This module then runs that tool, and nothing else:
the chosen name is looked up in a fixed allowlist and the market data comes
from the same services the plain `/market` endpoints use.

If the model cannot be reached, times out, or names something that is not on
the allowlist, the request fails with an explicit reason. No tool choice is
ever invented, and no result is ever fabricated.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.agent import runner, tools
from app.agent.decider import (
    DeciderChoice,
    DeciderClient,
    DeciderError,
    DeciderResponseError,
    DeciderTimeoutError,
    DeciderUnavailableError,
)
from app.agent.runner import AgentError
from app.core.config import get_settings
from app.schemas.agent import (
    AgentDecisionError,
    AgentDecisionResponse,
    AgentRequest,
    AgentStatusResponse,
    AnalysisResult,
    DecisionMetadata,
    PricesResult,
    ReturnsResult,
    SymbolsResult,
)
from app.schemas.market import DATA_DISCLAIMER, DATA_SOURCE
from app.services import market_data
from app.services.market_data import DataValidationError

router = APIRouter(prefix="/agent", tags=["agent"])

#: Which wrapper carries the result of each tool.
_RESULT_WRAPPERS = {
    "symbols": SymbolsResult,
    "prices": PricesResult,
    "analysis": AnalysisResult,
    "returns": ReturnsResult,
}

_DECISION_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"model": AgentDecisionError, "description": "The chosen tool could not be run."},
    502: {
        "model": AgentDecisionError,
        "description": "The Decider answered with something that was not a usable decision.",
    },
    503: {
        "model": AgentDecisionError,
        "description": "The Decider service was unavailable or timed out.",
    },
}


@lru_cache(maxsize=1)
def get_decider_client() -> DeciderClient:
    """The shared client for the local Decider service."""
    settings = get_settings()
    return DeciderClient(
        base_url=settings.decider_base_url,
        timeout=settings.decider_timeout_seconds,
    )


def _normalise_symbol(raw: str | None) -> str | None:
    if raw is None:
        return None
    cleaned = raw.strip()
    if not cleaned:
        return None
    return market_data.normalize_symbol(cleaned)


def _decision_metadata(choice: DeciderChoice | None) -> DecisionMetadata | None:
    if choice is None:
        return None
    return DecisionMetadata(
        question_name=choice.question_name,
        tool=choice.choice,
        confidence=choice.confidence,
        probabilities=choice.probabilities,
        model=choice.model,
        latency_ms=choice.latency_ms,
        input_tokens=choice.input_tokens,
        output_tokens=choice.output_tokens,
    )


def _failure(
    *,
    status_code: int,
    error: str,
    message: str,
    question: str,
    symbol: str | None,
    decision: DeciderChoice | None = None,
) -> JSONResponse:
    """Build the failure body.

    `decision_made` is False here: the response carries no result of a
    model-made decision. When the model *did* choose a valid tool and the
    flow then failed, `decision` still carries that choice, so the caller can
    see what the model wanted.
    """
    body = AgentDecisionError(
        decision_made=False,
        error=error,
        message=message,
        question=question,
        symbol=symbol,
        decision=_decision_metadata(decision),
    )
    return JSONResponse(status_code=status_code, content=body.model_dump())


@router.post(
    "/decide",
    response_model=AgentDecisionResponse,
    responses=_DECISION_ERROR_RESPONSES,
    summary="Let the Decider choose which market tool answers a question.",
)
def decide(
    request: AgentRequest,
    client: DeciderClient = Depends(get_decider_client),
):
    """Ask the Decider which tool to run, then run that tool.

    The tool is chosen by the model; it is executed only if it is on the
    allowlist. The response carries the model's own probabilities and
    confidence, so the decision can be audited rather than taken on trust.
    """
    settings = get_settings()
    symbol = _normalise_symbol(request.symbol)

    try:
        available_symbols = market_data.get_symbols()
    except DataValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sample price data could not be loaded: {exc}",
        ) from exc

    if symbol is not None and symbol not in available_symbols:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Unknown symbol '{symbol}'. "
                f"Available symbols: {', '.join(available_symbols)}."
            ),
        )

    try:
        outcome = runner.run_decision_flow(
            client=client,
            question=request.question,
            symbol=symbol,
            available_symbols=available_symbols,
            model=settings.strands_decider_model,
        )
    except DeciderTimeoutError as exc:
        return _failure(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error="decider_timeout",
            message=f"The Decider model did not make a usable decision. {exc}",
            question=request.question,
            symbol=symbol,
        )
    except DeciderUnavailableError as exc:
        return _failure(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error="decider_unavailable",
            message=f"The Decider model did not make a usable decision. {exc}",
            question=request.question,
            symbol=symbol,
        )
    except DeciderResponseError as exc:
        return _failure(
            status_code=status.HTTP_502_BAD_GATEWAY,
            error="invalid_response",
            message=f"The Decider model did not make a usable decision. {exc}",
            question=request.question,
            symbol=symbol,
        )
    except AgentError as exc:
        return _failure(
            status_code=exc.status_code,
            error=exc.code,
            message=str(exc),
            question=request.question,
            symbol=symbol,
            decision=exc.decision,
        )

    result = None
    if outcome.result is not None and outcome.tool.kind is not None:
        wrapper = _RESULT_WRAPPERS[outcome.tool.kind]
        result = wrapper(data=outcome.result)

    return AgentDecisionResponse(
        decision_made=True,
        question=request.question,
        symbol=symbol,
        tool=outcome.tool.name,
        executed=outcome.executed,
        decision=_decision_metadata(outcome.choice),
        result=result,
        data_source=DATA_SOURCE,
        disclaimer=DATA_DISCLAIMER,
        note=outcome.note,
    )


@router.get(
    "/status",
    response_model=AgentStatusResponse,
    summary="Whether the local Decider service is reachable.",
)
def agent_status(
    client: DeciderClient = Depends(get_decider_client),
):
    """Report whether the Decider service is up, and what it is serving.

    This is the pre-flight check to run before a demo: the Decider needs
    about 28 seconds to start once its weights are on disk.
    """
    settings = get_settings()
    try:
        health = client.health()
    except DeciderError as exc:
        body = AgentStatusResponse(
            decider_reachable=False,
            service_url=settings.decider_base_url,
            timeout_seconds=settings.decider_timeout_seconds,
            note=(
                f"The Decider service is not reachable: {exc} "
                "Start it with 'strands-decider serve' on 127.0.0.1:8100."
            ),
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content=body.model_dump()
        )

    body = AgentStatusResponse(
        decider_reachable=True,
        service_url=settings.decider_base_url,
        timeout_seconds=settings.decider_timeout_seconds,
        model=_optional_str(health.get("model")),
        checkpoint=_optional_str(health.get("checkpoint")),
        base_model=_optional_str(health.get("base_model")),
        device=_optional_str(health.get("device")),
        num_slots=health.get("num_slots") if isinstance(health.get("num_slots"), int) else None,
        max_length=health.get("max_length") if isinstance(health.get("max_length"), int) else None,
        note=(
            "The Decider service is up. A decision takes about 3.7 to 5.8 seconds "
            "on CPU, so the caller should show a waiting state."
        ),
    )
    return body


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None
