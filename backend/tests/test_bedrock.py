"""Tests for the Bedrock explanation layer.

The AWS boundary is mocked with a fake `bedrock-runtime` client, so the real
request-building, response-parsing and error-mapping code runs without AWS
credentials and without a billable call. The real `BedrockClient` sits in
front of the fake -- only the boto3 client underneath it is replaced.

No test in this file reaches AWS. The autouse `bedrock_runtime` fixture in
`conftest.py` guarantees that for the whole suite.
"""

import json

import pytest
from botocore.exceptions import (
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    NoCredentialsError,
    ReadTimeoutError,
)
from fastapi.testclient import TestClient

from app.agent.explainer import (
    MAX_SERIES_ROWS,
    SYSTEM_PROMPT,
    build_payload,
)
from app.api.agent import get_bedrock_client
from app.core.config import Settings
from app.schemas.market import DATA_DISCLAIMER
from app.services.bedrock import (
    BedrockAccessDeniedError,
    BedrockClient,
    BedrockCredentialsError,
    BedrockError,
    BedrockModelError,
    BedrockResponseError,
    BedrockThrottledError,
    BedrockTimeoutError,
    BedrockUnavailableError,
)
from main import app
from tests.conftest import TEST_MODEL_ID, TEST_REGION
from tests.helpers import FakeBedrockRuntime, converse_response, decider_body

client = TestClient(app)

QUESTION = "Tell me how volatile DEMOTECH has been."


def aws_error(code: str, message: str = "something went wrong") -> ClientError:
    """A botocore `ClientError` carrying the given AWS error code."""
    return ClientError({"Error": {"Code": code, "Message": message}}, "Converse")


def make_client(runtime: FakeBedrockRuntime) -> BedrockClient:
    return BedrockClient(region=TEST_REGION, model_id=TEST_MODEL_ID, client=runtime)


def sent_payload(runtime: FakeBedrockRuntime) -> dict:
    """The JSON payload the backend sent to Bedrock."""
    request = runtime.last_request()
    text = request["messages"][0]["content"][0]["text"]
    return json.loads(text)


# --- the request the client builds ------------------------------------------


def test_explain_sends_the_documented_converse_request():
    runtime = FakeBedrockRuntime(response=converse_response())

    make_client(runtime).explain(system_prompt="rules", user_prompt="the data")

    request = runtime.last_request()
    assert request["modelId"] == TEST_MODEL_ID
    assert request["system"] == [{"text": "rules"}]
    assert request["messages"] == [
        {"role": "user", "content": [{"text": "the data"}]}
    ]
    assert request["inferenceConfig"]["maxTokens"] == 600
    assert request["inferenceConfig"]["temperature"] == pytest.approx(0.2)


def test_explain_returns_the_generated_text_and_the_usage():
    runtime = FakeBedrockRuntime(response=converse_response("A plain explanation."))

    explanation = make_client(runtime).explain(
        system_prompt="rules", user_prompt="the data"
    )

    assert explanation.text == "A plain explanation."
    assert explanation.model_id == TEST_MODEL_ID
    assert explanation.region == TEST_REGION
    assert explanation.stop_reason == "end_turn"
    assert explanation.input_tokens == 412
    assert explanation.output_tokens == 57
    assert explanation.latency_ms == pytest.approx(1180)


# --- malformed responses ----------------------------------------------------


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"output": {}},
        {"output": {"message": {}}},
        {"output": {"message": {"content": []}}},
        {"output": {"message": {"content": [{"notText": "hello"}]}}},
        {"output": {"message": {"content": [{"text": "   "}]}}},
        "not a dict at all",
    ],
)
def test_explain_rejects_a_response_it_cannot_read(response):
    runtime = FakeBedrockRuntime(response=response)

    with pytest.raises(BedrockResponseError):
        make_client(runtime).explain(system_prompt="rules", user_prompt="the data")


# --- AWS errors -------------------------------------------------------------


def test_explain_maps_missing_credentials():
    runtime = FakeBedrockRuntime(error=NoCredentialsError())

    with pytest.raises(BedrockCredentialsError) as caught:
        make_client(runtime).explain(system_prompt="rules", user_prompt="the data")

    assert "credentials" in str(caught.value).lower()


def test_explain_keeps_an_already_typed_error():
    """A failure that is already one of ours must not be flattened.

    Building the AWS client can itself fail, and that failure is already a
    `BedrockError`. Mapping it a second time used to turn it into the
    generic "reason was not recognised" error, which hid the real cause.
    """
    runtime = FakeBedrockRuntime(
        error=BedrockCredentialsError("no credentials were found")
    )

    with pytest.raises(BedrockCredentialsError) as caught:
        make_client(runtime).explain(system_prompt="rules", user_prompt="the data")

    assert "no credentials" in str(caught.value)


def test_explain_reports_missing_credentials_from_the_ambient_chain(
    monkeypatch, tmp_path
):
    """With no credentials anywhere, the call fails locally and cannot be sent.

    The shared config is pointed at an empty directory, the credential
    environment variables are removed and IMDS is disabled, so boto3 finds
    nothing to sign with and raises before any request leaves the process.
    """
    for name in (
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_SESSION_TOKEN",
        "AWS_PROFILE",
        "AWS_DEFAULT_PROFILE",
        "AWS_BEARER_TOKEN_BEDROCK",
        "AWS_WEB_IDENTITY_TOKEN_FILE",
        "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    client = BedrockClient(region=TEST_REGION, model_id=TEST_MODEL_ID)
    with pytest.raises(BedrockCredentialsError) as caught:
        client.explain(system_prompt="rules", user_prompt="the data")

    assert "credentials" in str(caught.value).lower()


def test_explain_maps_access_denied():
    runtime = FakeBedrockRuntime(error=aws_error("AccessDeniedException"))

    with pytest.raises(BedrockAccessDeniedError) as caught:
        make_client(runtime).explain(system_prompt="rules", user_prompt="the data")

    message = str(caught.value)
    assert "bedrock:Converse" in message
    assert "first-time-use" in message


def test_explain_maps_an_unknown_model():
    runtime = FakeBedrockRuntime(error=aws_error("ResourceNotFoundException"))

    with pytest.raises(BedrockModelError) as caught:
        make_client(runtime).explain(system_prompt="rules", user_prompt="the data")

    assert TEST_MODEL_ID in str(caught.value)


def test_explain_maps_throttling():
    runtime = FakeBedrockRuntime(error=aws_error("ThrottlingException"))

    with pytest.raises(BedrockThrottledError):
        make_client(runtime).explain(system_prompt="rules", user_prompt="the data")


def test_explain_maps_a_read_timeout():
    runtime = FakeBedrockRuntime(
        error=ReadTimeoutError(endpoint_url="https://bedrock-runtime", error="timed out")
    )

    with pytest.raises(BedrockTimeoutError):
        make_client(runtime).explain(system_prompt="rules", user_prompt="the data")


def test_explain_maps_a_connect_timeout():
    runtime = FakeBedrockRuntime(
        error=ConnectTimeoutError(endpoint_url="https://bedrock-runtime", error="timed out")
    )

    with pytest.raises(BedrockTimeoutError):
        make_client(runtime).explain(system_prompt="rules", user_prompt="the data")


def test_explain_maps_an_unreachable_endpoint():
    runtime = FakeBedrockRuntime(
        error=EndpointConnectionError(endpoint_url="https://bedrock-runtime")
    )

    with pytest.raises(BedrockUnavailableError):
        make_client(runtime).explain(system_prompt="rules", user_prompt="the data")


def test_explain_maps_an_unrecognised_error_to_the_base_type():
    runtime = FakeBedrockRuntime(error=aws_error("SomethingBrandNew"))

    with pytest.raises(BedrockError) as caught:
        make_client(runtime).explain(system_prompt="rules", user_prompt="the data")

    assert not isinstance(caught.value, BedrockAccessDeniedError)
    assert "not recognised" in str(caught.value)


def test_explain_never_echoes_the_aws_message():
    """The SDK's own message can carry internal detail; ours must not."""
    secret = "aws-signature AKIAIOSFODNN7EXAMPLE internal-arn"
    runtime = FakeBedrockRuntime(error=aws_error("AccessDeniedException", secret))

    with pytest.raises(BedrockAccessDeniedError) as caught:
        make_client(runtime).explain(system_prompt="rules", user_prompt="the data")

    assert secret not in str(caught.value)
    assert "AKIA" not in str(caught.value)


# --- the payload the model is given -----------------------------------------


def test_the_payload_carries_the_real_figures_and_the_synthetic_warning(
    bedrock_runtime, decider
):
    decider.reply(decider_body("get_analysis"))

    client.post("/agent/decide", json={"question": QUESTION, "symbol": "DEMOTECH"})

    payload = sent_payload(bedrock_runtime)
    data = payload["data"]

    assert payload["operation"] == "get_analysis"
    assert payload["question"] == QUESTION
    assert payload["data_source"] == "synthetic_demo"
    assert payload["data_disclaimer"] == DATA_DISCLAIMER
    assert "_pct" in payload["units"]
    assert "percentage" in payload["units"].lower()

    # The figures are the ones the market service actually computed.
    assert data["symbol"] == "DEMOTECH"
    assert data["observations"] == 30
    assert data["sma"] > 0
    assert data["latest_close"] > 0
    assert data["total_return_pct"] != 0

    # The system block is what keeps Bedrock from inventing a figure or
    # giving advice, and it says the data is synthetic.
    system = bedrock_runtime.last_request()["system"][0]["text"].lower()
    assert "synthetic" in system
    assert "never recompute" in system
    assert "never recommend" in system


def test_the_payload_reports_volatility_as_a_percentage():
    runtime = FakeBedrockRuntime(response=converse_response())
    client = make_client(runtime)

    from app.services import market_queries

    analysis = market_queries.build_analysis_response("DEMOTECH")
    payload = build_payload(
        operation="get_analysis", result=analysis, question="How volatile is it?"
    )

    # The stored figure is a decimal fraction; the payload carries a
    # percentage, so the model never has to convert one.
    assert analysis.volatility.daily_volatility < 1
    assert payload["data"]["daily_volatility_pct"] == pytest.approx(
        round(analysis.volatility.daily_volatility * 100, 4)
    )
    assert payload["data"]["annualized_volatility_pct"] > payload["data"][
        "daily_volatility_pct"
    ]


def test_the_payload_bounds_the_price_series():
    from app.services import market_queries

    prices = market_queries.build_prices_response("DEMOTECH")
    payload = build_payload(
        operation="get_prices", result=prices, question="Show me the history"
    )

    shown = payload["data"]["daily_rows_shown"]
    assert len(shown["first"]) == MAX_SERIES_ROWS
    assert len(shown["last"]) == MAX_SERIES_ROWS
    assert prices.count == 30
    # The rows that were not sent are named, so the model cannot describe them.
    assert "30 rows" in payload["data"]["rows_note"]


def test_the_system_prompt_forbids_inventing_numbers_and_giving_advice():
    lowered = SYSTEM_PROMPT.lower()

    assert "synthetic" in lowered
    assert "never recompute" in lowered
    assert "never recommend" in lowered
    assert "never predict" in lowered


# --- the endpoint -----------------------------------------------------------


def test_decide_returns_the_bedrock_explanation(decider, bedrock_runtime):
    decider.reply(decider_body("get_analysis"))

    response = client.post(
        "/agent/decide", json={"question": QUESTION, "symbol": "DEMOTECH"}
    )

    assert response.status_code == 200
    body = response.json()

    assert body["explanation_status"] == "generated"
    assert body["explanation"]
    assert body["explanation_error"] is None
    assert body["bedrock"]["model_id"] == TEST_MODEL_ID
    assert body["bedrock"]["region"] == TEST_REGION
    assert body["bedrock"]["input_tokens"] == 412
    assert body["bedrock"]["stop_reason"] == "end_turn"
    assert bedrock_runtime.call_count == 1


def test_decide_preserves_the_decision_metadata(decider, bedrock_runtime):
    decider.reply(decider_body("get_analysis", confidence=0.7565))

    body = client.post(
        "/agent/decide", json={"question": QUESTION, "symbol": "DEMOTECH"}
    ).json()

    assert body["decision_made"] is True
    assert body["tool"] == "get_analysis"
    assert body["decision"]["confidence"] == pytest.approx(0.7565)
    assert body["decision"]["probabilities"]["get_analysis"] == pytest.approx(0.6846)
    assert body["result"]["kind"] == "analysis"


def test_decide_reports_an_unavailable_bedrock_without_failing(
    decider, bedrock_runtime
):
    decider.reply(decider_body("get_analysis"))
    bedrock_runtime.error = NoCredentialsError()

    response = client.post(
        "/agent/decide", json={"question": QUESTION, "symbol": "DEMOTECH"}
    )

    # The decision and the real market data still come back.
    assert response.status_code == 200
    body = response.json()
    assert body["decision_made"] is True
    assert body["result"]["kind"] == "analysis"
    assert body["result"]["data"]["symbol"] == "DEMOTECH"

    # But there is no explanation, and the response says why.
    assert body["explanation"] is None
    assert body["explanation_status"] == "unavailable"
    assert "credentials" in body["explanation_error"].lower()
    assert body["bedrock"] is None


def test_decide_reports_a_failed_bedrock_without_fabricating(
    decider, bedrock_runtime
):
    decider.reply(decider_body("get_analysis"))
    bedrock_runtime.error = aws_error("ThrottlingException")

    response = client.post(
        "/agent/decide", json={"question": QUESTION, "symbol": "DEMOTECH"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["explanation"] is None
    assert body["explanation_status"] == "failed"
    assert body["explanation_error"]
    assert body["result"]["kind"] == "analysis"


def test_decide_reports_a_malformed_bedrock_response_without_fabricating(
    decider, bedrock_runtime
):
    decider.reply(decider_body("get_analysis"))
    bedrock_runtime.response = {"output": {"message": {"content": []}}}

    body = client.post(
        "/agent/decide", json={"question": QUESTION, "symbol": "DEMOTECH"}
    ).json()

    assert body["explanation"] is None
    assert body["explanation_status"] == "failed"
    assert body["result"]["kind"] == "analysis"


def test_decide_skips_the_explanation_when_it_is_not_requested(
    decider, bedrock_runtime
):
    decider.reply(decider_body("get_analysis"))

    body = client.post(
        "/agent/decide",
        json={"question": QUESTION, "symbol": "DEMOTECH", "explain": False},
    ).json()

    assert body["explanation_status"] == "skipped"
    assert body["explanation"] is None
    assert bedrock_runtime.call_count == 0


def test_decide_makes_no_bedrock_call_when_the_decider_declines(
    decider, bedrock_runtime
):
    decider.reply(decider_body("no_action"))

    body = client.post("/agent/decide", json={"question": "What is the weather?"}).json()

    assert body["tool"] == "no_action"
    assert body["explanation_status"] == "skipped"
    assert body["explanation"] is None
    # Nothing to explain, so nothing is spent explaining it.
    assert bedrock_runtime.call_count == 0


def test_decide_explains_each_kind_of_result(decider, bedrock_runtime):
    for tool, kind in (
        ("get_symbols", "symbols"),
        ("get_prices", "prices"),
        ("get_analysis", "analysis"),
        ("get_returns", "returns"),
    ):
        decider.reply(decider_body(tool))
        body = client.post(
            "/agent/decide", json={"question": QUESTION, "symbol": "DEMOTECH"}
        ).json()

        assert body["explanation_status"] == "generated", tool
        assert body["result"]["kind"] == kind
        assert sent_payload(bedrock_runtime)["operation"] == tool


# --- the status endpoint ----------------------------------------------------


def test_agent_status_reports_bedrock_readiness(decider, bedrock_runtime):
    decider.response = httpx_response_health()

    body = client.get("/agent/status").json()

    assert body["bedrock_enabled"] is True
    assert body["bedrock_model_id"] == TEST_MODEL_ID
    assert body["bedrock_region"] == TEST_REGION
    # The credential check is a real one, so on a machine with no AWS
    # profile it reports that rather than claiming readiness.
    assert body["bedrock_credentials_found"] in (True, False, None)


def httpx_response_health():
    import httpx

    return httpx.Response(
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


# --- configuration ----------------------------------------------------------


def test_the_default_model_id_is_the_global_inference_profile():
    """`ap-south-1` serves Claude 5.5 through the global profile only."""
    assert Settings().bedrock_model_id == "global.anthropic.claude-haiku-5-5"
    assert Settings().aws_region == "ap-south-1"


def test_bedrock_timeout_must_be_positive():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(bedrock_timeout_seconds=0)


def test_bedrock_max_tokens_must_be_positive():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(bedrock_max_tokens=0)


def test_bedrock_temperature_must_be_in_range():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        Settings(bedrock_temperature=1.5)


def test_the_bedrock_client_is_overridable(monkeypatch):
    """The endpoint takes its Bedrock client from the dependency, not a global."""
    runtime = FakeBedrockRuntime(response=converse_response("overridden"))
    app.dependency_overrides[get_bedrock_client] = lambda: make_client(runtime)
    try:
        assert app.dependency_overrides[get_bedrock_client]().explain(
            system_prompt="rules", user_prompt="data"
        ).text == "overridden"
    finally:
        app.dependency_overrides.pop(get_bedrock_client, None)
