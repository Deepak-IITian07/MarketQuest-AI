"""A small HTTP client for the local Strands Decider 2B service.

The Decider runs in its own Python 3.12 environment under
`experiments/decider-spike/` and owns the model weights. The backend never
imports it -- it talks to it over plain HTTP on the loopback interface, so
`torch` and `transformers` never enter the backend environment.

The wire contract below was read from the installed package
(`strands_decider/schema.py` and `strands_decider/server.py`), not guessed:

    POST /v1/systemone
    {
      "state": "<text>",
      "questions": {
        "<name>": {
          "type": "choice",
          "instructions": "<text>",
          "criteria": {"<option>": "<description>"}
        }
      },
      "model": "<model id>",
      "images": []
    }

    -> 200
    {
      "model": "...",
      "answers": {
        "<name>": {
          "type": "choice",
          "choice": "<option name>",
          "probabilities": {"<option>": 0.0, ...},
          "confidence": 0.0
        }
      },
      "usage": {"input_tokens": 0, "output_tokens": 0},
      "latency_ms": 0.0
    }

`latency_ms` is added by the server around the forward pass; it is not part of
the `SystemOneResponse` model. The request's `model` field is not used by the
engine -- the served checkpoint decides the answer -- but it is sent because it
is part of the documented request shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

#: Where the Decider service listens by default.
DEFAULT_BASE_URL = "http://127.0.0.1:8100"

#: A decision takes 3.7-5.8 s on CPU, so the default leaves comfortable headroom.
DEFAULT_TIMEOUT_SECONDS = 15.0

SYSTEMONE_PATH = "/v1/systemone"
HEALTH_PATH = "/health"


class DeciderError(Exception):
    """Base class for every Decider problem."""


class DeciderUnavailableError(DeciderError):
    """The Decider service could not be reached."""


class DeciderTimeoutError(DeciderUnavailableError):
    """The Decider service did not answer within the configured timeout."""


class DeciderResponseError(DeciderError):
    """The Decider answered, but not in the documented shape."""


@dataclass(frozen=True, slots=True)
class DeciderChoice:
    """One `choice` answer, as the Decider reported it."""

    question_name: str
    choice: str
    probabilities: dict[str, float]
    confidence: float
    model: str
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None


class DeciderClient:
    """A thin, synchronous client for the local Decider service.

    Args:
        base_url: Root URL of the service. Must be a loopback address; the
            service has no authentication, so it must not be exposed.
        timeout: Seconds to wait for a decision before giving up.
        client: An existing `httpx.Client` to use. Tests pass one backed by a
            `httpx.MockTransport`; production code lets the client create its own.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = client if client is not None else httpx.Client()

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()

    def health(self) -> dict[str, Any]:
        """Return the service's `/health` payload.

        Raises:
            DeciderUnavailableError: The service could not be reached.
            DeciderTimeoutError: The service did not answer in time.
            DeciderResponseError: The service answered with an unexpected body.
        """
        body = self._get(HEALTH_PATH)
        if not isinstance(body, dict):
            raise DeciderResponseError("The Decider health response was not a JSON object.")
        return body

    def decide(
        self,
        *,
        state: str,
        instructions: str,
        options: dict[str, str],
        question_name: str = "next_tool",
        model: str = "",
    ) -> DeciderChoice:
        """Ask the Decider to pick one of `options`.

        Args:
            state: The context the decision is made in. The model reads this
                before the question.
            instructions: What the question is asking for.
            options: Option name -> description. The descriptions are not
                decoration: the spike showed the model chooses differently when
                the options are bare names, so every option needs a real one.
            question_name: The key this question is asked and answered under.
            model: The model id to report in the request.

        Raises:
            DeciderUnavailableError: The service could not be reached.
            DeciderTimeoutError: The service did not answer in time.
            DeciderResponseError: The answer was not in the documented shape.
        """
        if len(options) < 2:
            raise ValueError("A choice question needs at least two options.")

        payload: dict[str, Any] = {
            "state": state,
            "questions": {
                question_name: {
                    "type": "choice",
                    "instructions": instructions,
                    "criteria": dict(options),
                }
            },
            "model": model,
            "images": [],
        }

        try:
            response = self._client.post(
                f"{self.base_url}{SYSTEMONE_PATH}",
                json=payload,
                timeout=self.timeout,
            )
        except httpx.TimeoutException as exc:
            raise DeciderTimeoutError(
                f"The Decider service did not answer within {self.timeout:g} seconds."
            ) from exc
        except httpx.HTTPError as exc:
            raise DeciderUnavailableError(
                f"The Decider service at {self.base_url} could not be reached: {exc}"
            ) from exc

        if response.status_code != 200:
            raise DeciderResponseError(
                f"The Decider service returned HTTP {response.status_code}: "
                f"{_snippet(response.text)}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise DeciderResponseError(
                f"The Decider service did not return JSON: {_snippet(response.text)}"
            ) from exc

        return _parse_choice(body, question_name)

    def _get(self, path: str) -> Any:
        try:
            response = self._client.get(
                f"{self.base_url}{path}", timeout=self.timeout
            )
        except httpx.TimeoutException as exc:
            raise DeciderTimeoutError(
                f"The Decider service did not answer within {self.timeout:g} seconds."
            ) from exc
        except httpx.HTTPError as exc:
            raise DeciderUnavailableError(
                f"The Decider service at {self.base_url} could not be reached: {exc}"
            ) from exc

        if response.status_code != 200:
            raise DeciderResponseError(
                f"The Decider service returned HTTP {response.status_code}: "
                f"{_snippet(response.text)}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise DeciderResponseError(
                f"The Decider service did not return JSON: {_snippet(response.text)}"
            ) from exc


def _snippet(text: str, limit: int = 200) -> str:
    """A short, safe excerpt of a response body for error messages."""
    collapsed = " ".join((text or "").split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[:limit] + "..."


def _parse_choice(body: Any, question_name: str) -> DeciderChoice:
    """Read a `choice` answer out of a `SystemOneResponse` body.

    Every failure here means the model did not produce a usable decision, so
    it is raised as `DeciderResponseError` rather than being papered over.
    """
    if not isinstance(body, dict):
        raise DeciderResponseError("The Decider response was not a JSON object.")

    answers = body.get("answers")
    if not isinstance(answers, dict) or question_name not in answers:
        raise DeciderResponseError(
            f"The Decider response has no answer for the question '{question_name}'."
        )

    answer = answers[question_name]
    if not isinstance(answer, dict):
        raise DeciderResponseError("The Decider answer was not a JSON object.")

    answer_type = answer.get("type")
    if answer_type != "choice":
        raise DeciderResponseError(
            f"The Decider answered with type '{answer_type}', expected 'choice'."
        )

    choice = answer.get("choice")
    if not isinstance(choice, str) or not choice:
        raise DeciderResponseError("The Decider answer did not contain a choice.")

    raw_probabilities = answer.get("probabilities")
    if not isinstance(raw_probabilities, dict) or not raw_probabilities:
        raise DeciderResponseError(
            "The Decider answer did not contain any probabilities."
        )
    try:
        probabilities = {str(key): float(value) for key, value in raw_probabilities.items()}
    except (TypeError, ValueError) as exc:
        raise DeciderResponseError(
            "The Decider probabilities were not numbers."
        ) from exc

    confidence = answer.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise DeciderResponseError(
            "The Decider answer did not contain a confidence value."
        )

    usage = body.get("usage")
    usage = usage if isinstance(usage, dict) else {}

    latency_ms = body.get("latency_ms")
    if isinstance(latency_ms, bool) or not isinstance(latency_ms, (int, float)):
        latency_ms = None

    model = body.get("model")
    if not isinstance(model, str):
        model = ""

    return DeciderChoice(
        question_name=question_name,
        choice=choice,
        probabilities=probabilities,
        confidence=float(confidence),
        model=model,
        latency_ms=float(latency_ms) if latency_ms is not None else None,
        input_tokens=_optional_int(usage.get("input_tokens")),
        output_tokens=_optional_int(usage.get("output_tokens")),
    )


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value
