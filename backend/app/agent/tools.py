"""The market-analysis tools the Decider is allowed to choose between.

The registry is a fixed tuple of named, read-only operations. The model picks
a *name* from it; it never supplies arguments, a command, a URL or code, and
the name is looked up by exact match. Anything the model returns that is not
in this tuple is rejected -- it is never executed.

Every tool carries a real description. That is not decoration: the spike asked
the same question with bare option names and with described options and got
different answers (`experiments/decider-spike.md`, section 12). The
descriptions are what make the choice well posed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.services import market_queries


@dataclass(frozen=True, slots=True)
class MarketTool:
    """One read-only market operation the Decider may select."""

    name: str
    description: str
    needs_symbol: bool
    #: Which response shape the tool produces, or None when it produces nothing.
    kind: str | None = None
    run: Callable[[str], Any] | None = None


#: The complete allowlist. The order is the order the options are rendered in.
TOOLS: tuple[MarketTool, ...] = (
    MarketTool(
        name="get_symbols",
        description=(
            "List every symbol in the demo dataset with its latest sample close, "
            "its date and how many observations it has. Use this when the user has "
            "not named a symbol, or asks what is available to look at."
        ),
        needs_symbol=False,
        kind="symbols",
        run=lambda symbol: market_queries.build_symbols_response(),
    ),
    MarketTool(
        name="get_prices",
        description=(
            "Return the full daily price history for one symbol: date, open, high, "
            "low, close and volume, oldest first. Use this when the user wants to "
            "see how the price moved over time, or wants the raw history."
        ),
        needs_symbol=True,
        kind="prices",
        run=lambda symbol: market_queries.build_prices_response(symbol),
    ),
    MarketTool(
        name="get_analysis",
        description=(
            "Return an analysis summary for one symbol: the latest close, the "
            "simple moving average, daily and annualised volatility, the total "
            "return and the average volume. Use this when the user asks a question "
            "about volatility, the moving average, the return, or wants a summary "
            "of the symbol."
        ),
        needs_symbol=True,
        kind="analysis",
        run=lambda symbol: market_queries.build_analysis_response(symbol),
    ),
    MarketTool(
        name="get_returns",
        description=(
            "Return the daily percentage returns for one symbol, one entry for each "
            "pair of consecutive closing prices. Use this when the user asks about "
            "day-to-day percentage changes."
        ),
        needs_symbol=True,
        kind="returns",
        run=lambda symbol: market_queries.build_returns_response(symbol),
    ),
    MarketTool(
        name="no_action",
        description=(
            "Take no action, because none of the listed tools can answer what the "
            "user asked for."
        ),
        needs_symbol=False,
        kind=None,
        run=None,
    ),
)

#: Option name -> description, in the order the options are rendered.
TOOL_DESCRIPTIONS: dict[str, str] = {tool.name: tool.description for tool in TOOLS}

#: The tool that means "do nothing".
NO_ACTION = "no_action"


class UnknownToolError(Exception):
    """The Decider chose a name that is not in the allowlist."""


def find_tool(name: str) -> MarketTool:
    """Look a tool up by exact name.

    Raises:
        UnknownToolError: The name is not one of the allowlisted tools.
    """
    for tool in TOOLS:
        if tool.name == name:
            return tool
    raise UnknownToolError(
        f"The Decider chose '{name}', which is not an allowlisted tool. "
        f"Allowed tools: {', '.join(TOOL_DESCRIPTIONS)}."
    )
