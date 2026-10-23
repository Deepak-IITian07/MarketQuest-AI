"""Shared fixtures.

The Bedrock fixture is **autouse**: every test in the suite gets a fake
`bedrock-runtime` client, so no test can reach AWS, no test needs a credential,
and no test can incur a charge. The real `BedrockClient` sits in front of the
fake, so request building, response parsing and the AWS error mapping all run
for real.
"""

from __future__ import annotations

import httpx
import pytest

from app.agent.decider import DeciderClient
from app.api.agent import get_bedrock_client, get_decider_client
from app.services.bedrock import BedrockClient
from main import app
from tests.helpers import DeciderMock, FakeBedrockRuntime, converse_response

#: The model and region the tests pretend to call. They are the real default
#: values, so the tests exercise the same shape a live call would.
TEST_MODEL_ID = "global.anthropic.claude-haiku-5-5"
TEST_REGION = "ap-south-1"


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
    app.dependency_overrides.pop(get_decider_client, None)


@pytest.fixture(autouse=True)
def bedrock_runtime():
    """Install a fake Bedrock runtime for every test."""
    runtime = FakeBedrockRuntime(response=converse_response())
    client = BedrockClient(
        region=TEST_REGION, model_id=TEST_MODEL_ID, client=runtime
    )
    app.dependency_overrides[get_bedrock_client] = lambda: client
    yield runtime
    app.dependency_overrides.pop(get_bedrock_client, None)
