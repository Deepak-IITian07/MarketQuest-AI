"""Tests for the Decider-backed agent endpoint.

The HTTP boundary is mocked with `httpx.MockTransport`, so the real client
code -- the request body, the response parsing and the error mapping -- is
exercised without loading the model or running any inference. The tests that
need the genuine model live in `experiments/decider-spike.md`.
"""

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.agent.decider import DeciderClient
from app.api.agent import get_decider_client
from app.core.config import Settings
from main import app

client = TestClient(app)

QUESTION = "Tell me how volatile DEMOTECH has been."


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


@pytest.fixture()
def decider():
    """Install a mocked Decider in place of the real one."""
    mock = DeciderMock()
    transport = httpx.MockTransport(mock.handler)
    mocked_client = DeciderClient(
        base_url="http://127.0.0.1:8100",
        timeout=5.0,
        client=httpx.Client(transport=transport, timeout=5.0),
    )
    app.dependency_overrides[get_decider_client] = lambda: mocked_client
    yield mock
    app.dependency_overrides.clear()


# --- a successful decision -------------------------------------------------


def test_decide_runs_the_tool_the_decider_chosen(decider):
    decider.reply(decider_body("get_analysis"))

    response = client.post("/agent/decide", json={"question": QUESTION, "symbol": "DEMOTECH"})

    assert response.status_code == 200
    body = response.json()

    assert body["decision_made"] is True
    assert body["executed"] is True
    assert body["tool"] == "get_analysis"
    assert body["symbol"] == "DEMOTECH"
    assert body["data_source"] == "synthetic_demo"
    assert "Not real market data" in body["disclaimer"]

    assert body["result"]["kind"] == "analysis"
    data = body["result"]["data"]
    assert data["symbol"] == "DEMOTECH"
    assert data["observations"] == 30
    assert data["sma"] > 0
    assert data["volatility"]["annualization_factor"] == 252


def test_decide_runs_get_prices_when_that_is_the_choice(decider):
    decider.reply(decider_body("get_prices", confidence=0.31))

    response = client.post("/agent/decide", json={"question": "Show me DEMOTECH", "symbol": "DEMOTECH"})

    assert response.status_code == 200
    body = response.json()

    assert body["tool"] == "get_prices"
    assert body["result"]["kind"] == "prices"
    assert body["result"]["data"]["count"] == 30
    assert body["result"]["data"]["prices"][0]["date"] == "2026-09-07"


def test_decide_runs_get_symbols_when_that_is_the_choice(decider):
    decider.reply(decider_body("get_symbols"))

    response = client.post("/agent/decide", json={"question": "What is available to look at?"})

    assert response.status_code == 200
    body = response.json()

    assert body["tool"] == "get_symbols"
    assert body["result"]["kind"] == "symbols"
    assert body["result"]["data"]["count"] == 4


def test_decide_reports_the_model_probabilities_and_confidence(decider):
    decider.reply(decider_body("get_analysis"))

    response = client.post("/agent/decide", json={"question": QUESTION, "symbol": "DEMOTECH"})

    decision = response.json()["decision"]
    assert decision["question_name"] == "next_tool"
    assert decision["tool"] == "get_analysis"
    assert decision["confidence"] == pytest.approx(0.6057)
    assert decision["probabilities"]["get_analysis"] == pytest.approx(0.6846)
    assert decision["probabilities"]["get_prices"] == pytest.approx(0.2234)
    assert decision["latency_ms"] == pytest.approx(5826.81)
    assert decision["input_tokens"] == 196
    assert decision["output_tokens"] == 1


def test_decide_sends_the_question_and_a_description_for_every_option(decider):
    decider.reply(decider_body("get_analysis"))

    client.post("/agent/decide", json={"question": QUESTION, "symbol": "DEMOTECH"})

    body = decider.request_body()
    assert body["questions"]["next_tool"]["type"] == "choice"
    assert "Tell me how volatile DEMOTECH has been." in body["state"]
    assert body["model"] == "StrandsAgents/strands-decider-2B-qwen3.5-v1-2610"

    criteria = body["questions"]["next_tool"]["criteria"]
    assert set(criteria) == {
        "get_symbols",
        "get_prices",
        "get_analysis",
        "get_returns",
        "no_action",
    }
    # The spike showed the descriptions are what make the choice well posed.
    for name, description in criteria.items():
        assert description.strip()
        assert len(description) > len(name)


def test_decide_accepts_a_no_action_choice_without_inventing_data(decider):
    decider.reply(decider_body("no_action"))

    response = client.post("/agent/decide", json={"question": "What is the weather?"})

    assert response.status_code == 200
    body = response.json()

    assert body["decision_made"] is True
    assert body["tool"] == "no_action"
    assert body["executed"] is False
    assert body["result"] is None
    assert body["note"]


# --- failures --------------------------------------------------------------


def test_decide_rejects_a_choice_outside_the_allowlist(decider):
    decider.reply(decider_body("rm_-rf"))

    response = client.post("/agent/decide", json={"question": QUESTION, "symbol": "DEMOTECH"})

    assert response.status_code == 502
    body = response.json()
    assert body["decision_made"] is False
    assert body["error"] == "invalid_decision"
    assert "not an allowlisted tool" in body["message"]
    assert body["result"] is None if "result" in body else True


def test_decide_reports_a_timeout(decider):
    decider.raises = httpx.ReadTimeout("timed out")

    response = client.post("/agent/decide", json={"question": QUESTION, "symbol": "DEMOTECH"})

    assert response.status_code == 503
    body = response.json()
    assert body["decision_made"] is False
    assert body["error"] == "decider_timeout"
    assert "did not make a usable decision" in body["message"]


def test_decide_reports_the_service_as_unavailable(decider):
    decider.raises = httpx.ConnectError("connection refused")

    response = client.post("/agent/decide", json={"question": QUESTION, "symbol": "DEMOTECH"})

    assert response.status_code == 503
    body = response.json()
    assert body["decision_made"] is False
    assert body["error"] == "decider_unavailable"
    assert "did not make a usable decision" in body["message"]


def test_decide_reports_a_malformed_decider_answer(decider):
    decider.reply({"model": "x", "answers": {}, "usage": {}})

    response = client.post("/agent/decide", json={"question": QUESTION, "symbol": "DEMOTECH"})

    assert response.status_code == 502
    body = response.json()
    assert body["error"] == "invalid_response"
    assert body["decision_made"] is False


def test_decide_reports_an_answer_that_is_not_a_choice(decider):
    decider.reply(decider_body("get_analysis", type="noul"))

    response = client.post("/agent/decide", json={"question": QUESTION, "symbol": "DEMOTECH"})

    assert response.status_code == 502
    assert response.json()["error"] == "invalid_response"


def test_decide_reports_a_non_json_answer(decider):
    decider.response = httpx.Response(200, text="not json at all")

    response = client.post("/agent/decide", json={"question": QUESTION, "symbol": "DEMOTECH"})

    assert response.status_code == 502
    assert response.json()["error"] == "invalid_response"


def test_decide_returns_400_when_the_chosen_tool_needs_a_symbol_and_none_was_given(decider):
    decider.reply(decider_body("get_analysis"))

    response = client.post("/agent/decide", json={"question": QUESTION})

    assert response.status_code == 400
    body = response.json()
    assert body["error"] == "missing_symbol"
    assert body["decision_made"] is False
    # The model did choose something; that choice is still reported.
    assert body["decision"]["tool"] == "get_analysis"


# --- input validation ------------------------------------------------------


def test_decide_rejects_an_empty_question(decider):
    response = client.post("/agent/decide", json={"question": "", "symbol": "DEMOTECH"})

    assert response.status_code == 422
    assert decider.requests == []


def test_decide_rejects_an_unknown_symbol_before_asking_the_model(decider):
    response = client.post("/agent/decide", json={"question": QUESTION, "symbol": "NOTLISTED"})

    assert response.status_code == 404
    assert "NOTLISTED" in response.json()["detail"]
    # The model was never asked, so no time was spent on a doomed request.
    assert decider.requests == []


def test_decide_normalises_the_symbol(decider):
    decider.reply(decider_body("get_analysis"))

    response = client.post("/agent/decide", json={"question": QUESTION, "symbol": "  demotech "})

    assert response.status_code == 200
    assert response.json()["symbol"] == "DEMOTECH"


# --- the status endpoint ---------------------------------------------------


def test_agent_status_reports_a_reachable_decider(decider):
    decider.response = httpx.Response(
        200,
        json={
            "status": "ok",
            "model": "strands-decider-2B-qwen3.5-v1-2610",
            "checkpoint": "StrandsAgents/strands-decider-2B-qwen3.5-v1-2610",
            "base_model": "Qwen/Qwen3.5-2B-Base",
            "num_slots": 24,
            "max_length": 4096,
            "device": "cpu",
        },
    )

    response = client.get("/agent/status")

    assert response.status_code == 200
    body = response.json()
    assert body["decider_reachable"] is True
    assert body["base_model"] == "Qwen/Qwen3.5-2B-Base"
    assert body["device"] == "cpu"
    assert body["num_slots"] == 24


def test_agent_status_reports_an_unreachable_decider(decider):
    decider.raises = httpx.ConnectError("connection refused")

    response = client.get("/agent/status")

    assert response.status_code == 503
    body = response.json()
    assert body["decider_reachable"] is False
    assert "not reachable" in body["note"]


# --- configuration safety --------------------------------------------------


def test_decider_base_url_must_be_a_loopback_address():
    with pytest.raises(ValidationError):
        Settings(decider_base_url="http://decider.example.com:8100")


def test_decider_base_url_accepts_loopback_addresses():
    for url in ("http://127.0.0.1:8100", "http://localhost:8100", "http://[::1]:8100"):
        assert Settings(decider_base_url=url).decider_base_url == url


def test_decider_timeout_must_be_positive():
    with pytest.raises(ValidationError):
        Settings(decider_timeout_seconds=0)
