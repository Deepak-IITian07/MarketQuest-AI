"""Turn the result of a market tool into a plain-language explanation.

This is the Bedrock half of the agent. The Strands Decider has already chosen
the tool and the backend has already computed the numbers; this module hands
those numbers to Amazon Bedrock and returns the prose that describes them.

Two rules shape everything here:

- **The model explains, it does not compute.** The prompt carries the figures
  the backend already produced, in the units they are meant to be quoted in,
  and the model is told not to derive anything new.
- **The prices are synthetic.** The prompt says so and carries the backend's
  own disclaimer, so an explanation cannot present demo prices as real quotes.

The payload is deliberately bounded. The backend holds the whole price history,
but the model only needs enough of it to describe the series, and a short
prompt is a cheap prompt. The rows that are not sent are named as such, so the
model is never left guessing what it was not shown.
"""

from __future__ import annotations

import json
from typing import Any

from app.schemas.market import (
    DATA_DISCLAIMER,
    DATA_SOURCE,
    AnalysisResponse,
    PriceHistoryResponse,
    ReturnsResponse,
    SymbolListResponse,
)
from app.services.bedrock import (
    BedrockAccessDeniedError,
    BedrockClient,
    BedrockCredentialsError,
    BedrockError,
    BedrockExplanation,
    BedrockModelError,
    BedrockNotInstalledError,
)

#: How many rows of a price or return series to include in the prompt.
MAX_SERIES_ROWS = 8

#: The role and the hard constraints. This is the prompt that keeps Bedrock
#: from doing the Decider's job, and from inventing a number.
SYSTEM_PROMPT = (
    "You are the analyst for MarketQuest AI, a learning simulation of the "
    "Indian stock market that uses virtual money only.\n"
    "\n"
    "You explain market results that the backend has already computed. You "
    "did not fetch the data and you did not calculate the figures, so never "
    "recompute, convert, estimate, round or add a number that is not in the "
    "data you are given.\n"
    "\n"
    "Rules:\n"
    "- Use only the figures in the supplied data, and quote them in the units "
    "the data gives them. Every field ending in _pct is already a percentage.\n"
    "- The prices are SYNTHETIC demo data generated locally for this "
    "simulation. They are not real market quotes, and no real trading is "
    "involved. Say so plainly.\n"
    "- This is a learning simulation. Never recommend buying or selling, never "
    "give a price target, never predict what will happen next, and never "
    "comment on whether the user should act.\n"
    "- If a figure you would need is not in the data, say it is unavailable "
    "rather than guessing.\n"
    "- If only some rows of a series are shown, describe only those rows.\n"
    "- Answer the user's question in plain language, in under 120 words, "
    "leading with the direct answer and then the supporting figures."
)


class ExplanationError(Exception):
    """The explanation could not be produced.

    Attributes:
        status: Whether Bedrock could not be used at all (`unavailable`) or
            was used and failed (`failed`).
    """

    status = "failed"

    def __init__(self, message: str, *, status: str | None = None) -> None:
        super().__init__(message)
        if status is not None:
            self.status = status


class ExplanationUnavailableError(ExplanationError):
    """Bedrock could not be used, so no call was made."""

    status = "unavailable"


def build_payload(*, operation: str, result: Any, question: str) -> dict[str, Any]:
    """Build the bounded data payload the model explains.

    Args:
        operation: The tool that produced the result -- `get_symbols`,
            `get_prices`, `get_analysis` or `get_returns`.
        result: The response model that tool returned.
        question: The user's question, so the model can answer that question
            rather than describe the data in general.

    Raises:
        ExplanationError: The operation is not one that can be explained.
    """
    builders = {
        "get_symbols": _symbols_payload,
        "get_prices": _prices_payload,
        "get_analysis": _analysis_payload,
        "get_returns": _returns_payload,
    }
    builder = builders.get(operation)
    if builder is None:
        raise ExplanationError(
            f"'{operation}' is not an operation whose result can be explained."
        )

    return {
        "operation": operation,
        "question": question,
        "data_source": DATA_SOURCE,
        "data_disclaimer": DATA_DISCLAIMER,
        "units": (
            "Prices are in INR and volume is a share count. Every field ending "
            "in _pct is already a percentage, so 1.25 means 1.25 percent."
        ),
        "data": builder(result),
    }


def explain_result(
    *,
    client: BedrockClient,
    operation: str,
    result: Any,
    question: str,
) -> BedrockExplanation:
    """Ask Bedrock to explain a tool's result.

    Raises:
        ExplanationError: The explanation could not be produced. The message
            says why, and no text is ever returned alongside it.
    """
    payload = build_payload(operation=operation, result=result, question=question)

    try:
        return client.explain(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=json.dumps(payload, indent=2),
        )
    except BedrockError as exc:
        raise _wrap(exc) from exc


def _wrap(exc: BedrockError) -> ExplanationError:
    """Map a Bedrock error onto the two statuses the API reports.

    `unavailable` means Bedrock could not be used at all -- the SDK is missing,
    no credentials resolved, or the model is unknown -- so no request was
    made. `failed` means a request was made and did not produce a usable
    explanation.
    """
    if isinstance(
        exc,
        (BedrockNotInstalledError, BedrockCredentialsError, BedrockModelError),
    ):
        return ExplanationUnavailableError(str(exc), status="unavailable")
    if isinstance(exc, BedrockAccessDeniedError):
        # Access denied is a configuration problem, not a transient failure, so
        # it reads as "unavailable" too. The message names all three causes.
        return ExplanationUnavailableError(str(exc), status="unavailable")
    return ExplanationError(str(exc), status="failed")


def _pct(value: float) -> float:
    """A decimal fraction as a percentage, rounded for display.

    Volatility and the daily returns are stored as decimal fractions, but an
    explanation that says "0.0123" is not an explanation. Converting the unit
    here -- exactly, and once -- means the model only ever quotes numbers that
    are already in the right unit.
    """
    return round(value * 100.0, 4)


def _analysis_payload(result: AnalysisResponse) -> dict[str, Any]:
    """Every figure the analysis endpoint reports, in quotable units."""
    return {
        "symbol": result.symbol,
        "currency": result.currency,
        "observations": result.observations,
        "first_date": result.first_date,
        "last_date": result.last_date,
        "latest_close": result.latest_close,
        "sma": result.sma,
        "sma_window": result.sma_window,
        "daily_volatility_pct": _pct(result.volatility.daily_volatility),
        "annualized_volatility_pct": _pct(result.volatility.annualized_volatility),
        "volatility_window": result.volatility.window,
        "total_return_pct": result.total_return_pct,
        "average_volume": result.average_volume,
    }


def _symbols_payload(result: SymbolListResponse) -> dict[str, Any]:
    """Every symbol with its latest sample close."""
    return {
        "count": result.count,
        "symbols": [
            {
                "symbol": quote.symbol,
                "latest_date": quote.latest_date,
                "latest_close": quote.latest_close,
                "observations": quote.observations,
            }
            for quote in result.symbols
        ],
    }


def _prices_payload(result: PriceHistoryResponse) -> dict[str, Any]:
    """The price history, bounded to the first and last rows."""
    rows = [
        {
            "date": point.date,
            "open": point.open,
            "high": point.high,
            "low": point.low,
            "close": point.close,
            "volume": point.volume,
        }
        for point in result.prices
    ]
    return {
        "symbol": result.symbol,
        "currency": result.currency,
        "observations": result.count,
        "first_date": result.prices[0].date,
        "last_date": result.prices[-1].date,
        "daily_rows_shown": _bounded_rows(rows),
        "rows_note": _rows_note(result.count),
    }


def _returns_payload(result: ReturnsResponse) -> dict[str, Any]:
    """The daily returns, bounded to the first and last rows."""
    rows = [
        {"date": daily.date, "return_pct": _pct(daily.return_pct)}
        for daily in result.returns
    ]
    return {
        "symbol": result.symbol,
        "observations": result.count,
        "first_date": result.returns[0].date,
        "last_date": result.returns[-1].date,
        "daily_rows_shown": _bounded_rows(rows),
        "rows_note": _rows_note(result.count),
    }


def _bounded_rows(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Keep the first and last rows of a series, and drop the middle.

    A short series is kept whole. A longer one is trimmed at both ends, so the
    model can still describe where the series started and where it ended.
    """
    if len(rows) <= 2 * MAX_SERIES_ROWS:
        return {"first": rows, "last": []}
    return {"first": rows[:MAX_SERIES_ROWS], "last": rows[-MAX_SERIES_ROWS:]}


def _rows_note(total: int) -> str:
    """Say which rows the model was given, so it cannot describe the rest."""
    if total <= 2 * MAX_SERIES_ROWS:
        return f"Showing all {total} rows of the series."
    return (
        f"Showing the first {MAX_SERIES_ROWS} and last {MAX_SERIES_ROWS} of "
        f"{total} rows. The rows in between were not provided, so do not "
        "describe them."
    )
