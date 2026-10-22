"""Turn a market question into a Decider choice, then run that choice.

The flow is deliberately narrow:

1. Build the state the model reads (the dataset context and the question).
2. Ask the Decider which tool to use.
3. Check the answer against the allowlist. An answer that is not on the list
   is never executed.
4. Run the chosen tool through the existing market services.

Every step can fail, and each failure has its own reason. Nothing here ever
invents a tool choice, and a failed decision is reported as a failed decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agent import tools
from app.agent.decider import DeciderChoice, DeciderClient, DeciderError
from app.agent.tools import MarketTool
from app.services.analysis import AnalysisError, InsufficientDataError, InvalidWindowError
from app.services.market_data import DataValidationError, SymbolNotFoundError

#: The key the tool question is asked and answered under.
TOOL_QUESTION_NAME = "next_tool"

#: What the model is actually being asked.
TOOL_INSTRUCTIONS = (
    "Which single tool should the agent call next to answer the user's question?"
)


class AgentError(Exception):
    """A problem that stops the agent flow.

    Attributes:
        code: A stable machine-readable reason.
        status_code: The HTTP status this failure maps to.
        decision: The Decider's answer, when there was one. A failure after the
            model has decided still reports the decision it made.
    """

    code = "agent_error"
    status_code = 500

    def __init__(
        self,
        message: str,
        *,
        decision: DeciderChoice | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.decision = decision
        if status_code is not None:
            self.status_code = status_code


class InvalidDecisionError(AgentError):
    """The Decider's answer was not a tool this project can run."""

    code = "invalid_decision"
    status_code = 502


class MissingSymbolError(AgentError):
    """The chosen tool needs a symbol, and none was supplied."""

    code = "missing_symbol"
    status_code = 400


class ToolExecutionError(AgentError):
    """The chosen tool ran but the market data could not be produced."""

    code = "tool_execution_failed"
    status_code = 500


@dataclass(frozen=True, slots=True)
class AgentOutcome:
    """A completed decision, and what running it produced."""

    choice: DeciderChoice
    tool: MarketTool
    result: Any | None
    executed: bool
    note: str | None = None


def build_state(
    question: str,
    symbol: str | None,
    available_symbols: list[str],
) -> str:
    """Build the context the Decider reads before the question.

    The stable context comes first and the question last on purpose: the
    service caches the shared prefix of the prompt, so a stable leading block
    is what makes the second call of a session cheaper than the first.
    """
    lines = [
        "MarketQuest AI demo market dataset.",
        f"Available symbols: {', '.join(available_symbols) if available_symbols else 'none'}.",
        (
            "The prices are synthetic demo data generated locally for development; "
            "they are not real market quotes and no real trading is involved."
        ),
        f"User question: {question}",
    ]
    if symbol:
        lines.append(f"Symbol in focus: {symbol}")
    else:
        lines.append("The user has not selected a specific symbol.")
    return "\n".join(lines)


def run_decision_flow(
    *,
    client: DeciderClient,
    question: str,
    symbol: str | None,
    available_symbols: list[str],
    model: str = "",
) -> AgentOutcome:
    """Ask the Decider which tool to run, then run it.

    Raises:
        DeciderError: The service could not be reached, timed out, or answered
            with something that was not a choice.
        InvalidDecisionError: The chosen name is not an allowlisted tool.
        MissingSymbolError: The chosen tool needs a symbol and none was given.
        ToolExecutionError: The chosen tool ran but the market data failed.
    """
    state = build_state(question, symbol, available_symbols)

    try:
        choice = client.decide(
            state=state,
            instructions=TOOL_INSTRUCTIONS,
            options=tools.TOOL_DESCRIPTIONS,
            question_name=TOOL_QUESTION_NAME,
            model=model,
        )
    except DeciderError:
        # The API layer maps these to a status code and an explicit reason.
        raise

    try:
        tool = tools.find_tool(choice.choice)
    except tools.UnknownToolError as exc:
        raise InvalidDecisionError(str(exc), decision=choice) from exc

    if tool.name == tools.NO_ACTION:
        return AgentOutcome(
            choice=choice,
            tool=tool,
            result=None,
            executed=False,
            note=(
                "The Decider decided that none of the available tools can answer "
                "the question, so no market data was fetched."
            ),
        )

    if tool.needs_symbol and not symbol:
        raise MissingSymbolError(
            f"The Decider chose '{tool.name}', which needs a symbol, "
            "but no symbol was supplied.",
            decision=choice,
        )

    if tool.run is None:  # pragma: no cover - the allowlist has no such tool
        raise InvalidDecisionError(
            f"The tool '{tool.name}' has no implementation.", decision=choice
        )

    try:
        result = tool.run(symbol)
    except SymbolNotFoundError as exc:
        raise ToolExecutionError(
            str(exc), decision=choice, status_code=404
        ) from exc
    except DataValidationError as exc:
        raise ToolExecutionError(
            f"Sample price data could not be loaded: {exc}",
            decision=choice,
            status_code=500,
        ) from exc
    except (InvalidWindowError, InsufficientDataError, AnalysisError) as exc:
        raise ToolExecutionError(str(exc), decision=choice, status_code=400) from exc

    return AgentOutcome(choice=choice, tool=tool, result=result, executed=True)
