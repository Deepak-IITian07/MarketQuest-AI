"""Test doubles shared by the agent test modules.

Nothing here reaches AWS or the Decider's model. The HTTP boundary is mocked
with `httpx.MockTransport` and the AWS boundary with a fake `bedrock-runtime`
client, so the real request-building, response-parsing and error-mapping code
runs without credentials and without a billable call.
"""

from __future__ import annotations

import json

import httpx


def decider_body(choice: str = "get_analysis", **answer_overrides) -> dict:
    """A `SystemOneResponse` body in the shape the service actually returns."""
    answer = {
        "type": "choice",
        "choice": choice,
        "probabilities": {
            "get_symbols": 0.003,
            "get_prices": 0.2234,
            "get_analysis": 0.6846,
            "get_returns": 0.085,
            "no_action": 0.004,
        },
        "confidence": 0.6057,
    }
    answer.update(answer_overrides)
    return {
        "model": "strands-decider-2B-qwen3.5-v1-2610",
        "answers": {"next_tool": answer},
        "usage": {"input_tokens": 196, "output_tokens": 1},
        "latency_ms": 5826.81,
    }


class DeciderMock:
    """Records the requests the backend made and replays a canned answer."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.response: httpx.Response | None = None
        self.raises: Exception | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raises is not None:
            raise self.raises
        assert self.response is not None
        return self.response

    def reply(self, body: dict) -> None:
        self.response = httpx.Response(200, json=body)

    def request_body(self, index: int = 0) -> dict:
        return json.loads(self.requests[index].content)


DEFAULT_EXPLANATION = (
    "DEMOTECH is a synthetic demo symbol, so these are not real quotes. Over "
    "the 30 sample sessions it rose 4.12% in total, and its daily volatility "
    "was 1.35%, which annualises to about 21.4%."
)


def converse_response(text: str = DEFAULT_EXPLANATION, **overrides) -> dict:
    """A Converse response in the shape the API actually returns."""
    body = {
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": text}],
            }
        },
        "stopReason": "end_turn",
        "usage": {"inputTokens": 412, "outputTokens": 57, "totalTokens": 469},
        "metrics": {"latencyMs": 1180},
    }
    body.update(overrides)
    return body


class FakeBedrockRuntime:
    """Stands in for the boto3 `bedrock-runtime` client.

    It records every `converse` call, so a test can assert on the request the
    backend actually built, and it can be told to fail with any exception.
    """

    def __init__(
        self, response: dict | None = None, error: Exception | None = None
    ) -> None:
        self.requests: list[dict] = []
        self.response = response
        self.error = error

    def converse(self, **kwargs):
        self.requests.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response

    @property
    def call_count(self) -> int:
        return len(self.requests)

    def last_request(self) -> dict:
        assert self.requests, "No Bedrock call was made."
        return self.requests[-1]
