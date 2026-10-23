"""The agent endpoint: let the Decider choose which market tool to run.

The Decider picks a tool. This module then runs that tool, and nothing else:
the chosen name is looked up in a fixed allowlist and the market data comes
from the same services the plain `/market` endpoints use.

If the model cannot be reached, times out, or names something that is not on
the allowlist, the request fails with an explicit reason. No tool choice is
ever invented, and no result is ever fabricated.

Once the tool has run, Amazon Bedrock explains the numbers it produced. That
is the whole of Bedrock's job: it never picks the tool and never supplies a
figure. A Bedrock failure is reported in the response body with its own
status, and the request still succeeds with the real market data -- because
the data is real whether or not the explanation could be written.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.agent import explainer, runner, tools
from app.agent.decider import (
    DeciderChoice,
    DeciderClient,
    DeciderError,
    DeciderResponseError,
    DeciderTimeoutError,
    DeciderUnavailableError,
)
from app.agent.explainer import ExplanationError
from app.agent.runner import AgentError
from app.core.config import get_settings
from app.schemas.agent import (
    AgentDecisionError,
    AgentDecisionResponse,
    AgentRequest,
    AgentStatusResponse,
    AnalysisResult,
    BedrockMetadata,
    DecisionMetadata,
    PricesResult,
    ReturnsResult,
    SymbolsResult,
)
from app.schemas.market import DATA_DISCLAIMER, DATA_SOURCE
from app.services import market_data
from app.services.bedrock import BedrockClient
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


@lru_cache(maxsize=1)
def get_bedrock_client() -> BedrockClient:
    """The shared client for Amazon Bedrock.

    The AWS credentials are not resolved here. `boto3` resolves them from the
    ambient chain when a call is actually made, so this only names a profile.
    """
    settings = get_settings()
    return BedrockClient(
        region=settings.aws_region,
        model_id=settings.bedrock_model_id,
        profile=settings.aws_profile,
        timeout=settings.bedrock_timeout_seconds,
        max_tokens=settings.bedrock_max_tokens,
        temperature=settings.bedrock_temperature,
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
    bedrock_client: BedrockClient = Depends(get_bedrock_client),
):
    """Ask the Decider which tool to run, then run that tool, then explain it.

    The tool is chosen by the model; it is executed only if it is on the
    allowlist. The response carries the model's own probabilities and
    confidence, so the decision can be audited rather than taken on trust.

    Amazon Bedrock then explains the numbers the tool produced. Bedrock never
    chooses the tool and never supplies a number. If the explanation cannot be
    generated, the response says so and carries no explanation text.
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

    explanation_text, explanation_status, explanation_error, bedrock = _explain(
        bedrock_client=bedrock_client,
        requested=request.explain,
        enabled=settings.bedrock_enabled,
        operation=outcome.tool.name,
        result=outcome.result,
        question=request.question,
    )

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
        explanation=explanation_text,
        explanation_status=explanation_status,
        explanation_error=explanation_error,
        bedrock=bedrock,
    )


def _explain(
    *,
    bedrock_client: BedrockClient,
    requested: bool,
    enabled: bool,
    operation: str,
    result: Any,
    question: str,
) -> tuple[str | None, str, str | None, BedrockMetadata | None]:
    """Ask Bedrock to explain the result, and report honestly what happened.

    A Bedrock failure never produces a fabricated explanation and never fails
    the request: the decision and the market data are real whatever the
    explanation layer does, so the explanation is reported separately, with a
    status that says exactly what happened.
    """
    if not enabled:
        return None, "disabled", "The Bedrock explanation layer is turned off.", None
    if not requested:
        return None, "skipped", None, None
    if operation == tools.NO_ACTION or result is None:
        # `no_action` -- there is no market data to explain, so no call is
        # made and nothing is charged for one.
        return None, "skipped", None, None

    try:
        explanation = explainer.explain_result(
            client=bedrock_client,
            operation=operation,
            result=result,
            question=question,
        )
    except ExplanationError as exc:
        return None, exc.status, str(exc), None

    return (
        explanation.text,
        "generated",
        None,
        BedrockMetadata(
            model_id=explanation.model_id,
            region=explanation.region,
            stop_reason=explanation.stop_reason,
            input_tokens=explanation.input_tokens,
            output_tokens=explanation.output_tokens,
            latency_ms=explanation.latency_ms,
        ),
    )


@router.get(
    "/status",
    response_model=AgentStatusResponse,
    summary="Whether the local Decider service is reachable, and Bedrock readiness.",
)
def agent_status(
    client: DeciderClient = Depends(get_decider_client),
    bedrock_client: BedrockClient = Depends(get_bedrock_client),
):
    """Report whether the Decider service is up, and what it is serving.

    This is the pre-flight check to run before a demo: the Decider needs
    about 28 seconds to start once its weights are on disk.

    It also reports whether the Bedrock explanation layer is configured and
    whether AWS credentials could be resolved. The credential value is never
    read into the response -- only whether one was found.
    """
    settings = get_settings()
    bedrock_enabled = settings.bedrock_enabled
    bedrock_credentials = (
        bedrock_client.credentials_available() if bedrock_enabled else None
    )
    bedrock_note = _bedrock_note(bedrock_enabled, bedrock_credentials, settings)

    try:
        health = client.health()
    except DeciderError as exc:
        body = AgentStatusResponse(
            decider_reachable=False,
            service_url=settings.decider_base_url,
            timeout_seconds=settings.decider_timeout_seconds,
            bedrock_enabled=bedrock_enabled,
            bedrock_model_id=settings.bedrock_model_id,
            bedrock_region=settings.aws_region,
            bedrock_profile=settings.aws_profile or None,
            bedrock_credentials_found=bedrock_credentials,
            note=(
                f"The Decider service is not reachable: {exc} "
                "Start it with 'strands-decider serve' on 127.0.0.1:8100. "
                + bedrock_note
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
        bedrock_enabled=bedrock_enabled,
        bedrock_model_id=settings.bedrock_model_id,
        bedrock_region=settings.aws_region,
        bedrock_profile=settings.aws_profile or None,
        bedrock_credentials_found=bedrock_credentials,
        note=(
            "The Decider service is up. A decision takes about 3.7 to 5.8 seconds "
            "on CPU, so the caller should show a waiting state. " + bedrock_note
        ),
    )
    return body


def _bedrock_note(
    enabled: bool, credentials_found: bool | None, settings
) -> str:
    """One sentence about the Bedrock layer, for the status note."""
    if not enabled:
        return "The Bedrock explanation layer is turned off."
    if credentials_found is True:
        return (
            f"AWS credentials were found, so Bedrock will call "
            f"{settings.bedrock_model_id} in {settings.aws_region}."
        )
    if credentials_found is False:
        return (
            "No AWS credentials were found, so Bedrock cannot be called. "
            "Configure an AWS profile or sign in with IAM Identity Center."
        )
    return (
        "The AWS credentials could not be determined, so Bedrock may not be "
        "callable. Check the AWS_PROFILE setting."
    )


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None
