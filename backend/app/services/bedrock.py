"""A small client for Amazon Bedrock's Converse API.

Bedrock is the *explanation* half of the agent. The Strands Decider chooses
which market tool runs, the backend computes the numbers, and this client turns
those numbers into prose. The model never selects a tool and never produces a
number -- it is given the computed result and asked to describe it.

The wire contract was read from the AWS Converse API reference, not guessed:

    client.converse(
        modelId="global.anthropic.claude-haiku-5-5",
        messages=[{"role": "user", "content": [{"text": "..."}]}],
        system=[{"text": "..."}],
        inferenceConfig={"maxTokens": 600, "temperature": 0.2},
    )

    -> 200
    {
      "output": {"message": {"role": "assistant", "content": [{"text": "..."}]}},
      "stopReason": "end_turn",
      "usage": {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
      "metrics": {"latencyMs": 0}
    }

**Credentials are never read, printed or logged here.** `boto3` resolves them
from the ambient chain (environment, shared profile, SSO token cache); this
module only ever names a *profile*. The error messages below are written by
hand for that reason: they name the likely cause without echoing whatever the
AWS SDK put in the exception.

`boto3` is imported lazily, so the backend still starts (and the Decider half
still works) in an environment where the SDK is not installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: Claude Haiku 5.5 is the model the research picked for a short, factual
#: "explain these numbers" turn. In `ap-south-1` it is available through the
#: **Global** cross-region inference profile only, so the id carries the
#: `global.` prefix.
DEFAULT_MODEL_ID = "global.anthropic.claude-haiku-5-5"

#: The natural region for an India-focused project.
DEFAULT_REGION = "ap-south-1"

#: An explanation is a few hundred tokens, not a long-form answer.
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_TOKENS = 600
DEFAULT_TEMPERATURE = 0.2

#: AWS error codes, and SDK exception class names, grouped by what they mean.
#: Matching on the class name keeps this module importable without botocore.
_CREDENTIAL_ERROR_NAMES = frozenset(
    {
        "NoCredentialsError",
        "PartialCredentialsError",
        "CredentialRetrievalError",
        "TokenRetrievalError",
        "ProfileNotFound",
    }
)
_CREDENTIAL_ERROR_CODES = frozenset({"ExpiredTokenException", "InvalidClientTokenId"})

_ACCESS_DENIED_CODES = frozenset(
    {"AccessDeniedException", "UnauthorizedException", "ForbiddenException"}
)

_MODEL_ERROR_CODES = frozenset({"ResourceNotFoundException"})

_THROTTLING_CODES = frozenset({"ThrottlingException", "TooManyRequestsException", "ModelNotReadyException"})

_TIMEOUT_ERROR_NAMES = frozenset(
    {"ReadTimeoutError", "ConnectTimeoutError", "ConnectionTimeoutError"}
)
_TIMEOUT_CODES = frozenset({"ModelTimeoutException"})

_UNAVAILABLE_ERROR_NAMES = frozenset(
    {"EndpointConnectionError", "ConnectionClosedError", "HTTPClientError"}
)
_UNAVAILABLE_CODES = frozenset({"ServiceUnavailableException", "InternalServerException"})


class BedrockError(Exception):
    """Base class for every Bedrock problem."""


class BedrockNotInstalledError(BedrockError):
    """`boto3` is not installed in this environment."""


class BedrockCredentialsError(BedrockError):
    """No AWS credentials could be resolved."""


class BedrockAccessDeniedError(BedrockError):
    """Bedrock refused the call."""


class BedrockModelError(BedrockError):
    """The model or inference profile is not available in this region."""


class BedrockThrottledError(BedrockError):
    """The account's Bedrock quota is exhausted."""


class BedrockTimeoutError(BedrockError):
    """The call did not finish in time."""


class BedrockUnavailableError(BedrockError):
    """Bedrock could not be reached."""


class BedrockResponseError(BedrockError):
    """Bedrock answered, but not in the documented shape."""


@dataclass(frozen=True, slots=True)
class BedrockExplanation:
    """One explanation, and what the Bedrock call reported about itself."""

    text: str
    model_id: str
    region: str
    stop_reason: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: float | None = None


class BedrockClient:
    """A thin, synchronous client for Bedrock's Converse API.

    Args:
        region: The AWS region to call, e.g. `ap-south-1`.
        model_id: The model or inference profile to call. Must be the id AWS
            documents for the region -- a cross-region profile id, not the bare
            base model id.
        profile: An AWS profile or SSO profile name. Empty means "use the
            ambient credential chain". A profile *name* is not a credential.
        timeout: Seconds to wait for the call.
        max_tokens: Upper bound on the generated explanation.
        temperature: Sampling temperature. Low, because this is a factual
            summarisation task rather than creative writing.
        client: An existing `bedrock-runtime` client to use. Tests pass a fake
            one; production code lets the client create its own.
    """

    def __init__(
        self,
        *,
        region: str = DEFAULT_REGION,
        model_id: str = DEFAULT_MODEL_ID,
        profile: str = "",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
        client: Any | None = None,
    ) -> None:
        self.region = region
        self.model_id = model_id
        self.profile = profile or ""
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature
        self._client = client

    def explain(self, *, system_prompt: str, user_prompt: str) -> BedrockExplanation:
        """Ask the model to explain the supplied data.

        Args:
            system_prompt: The role and the hard constraints (use only the
                given numbers, this is synthetic data, no advice, no
                predictions).
            user_prompt: The data to explain, as text.

        Raises:
            BedrockError: A subclass describing what went wrong.
        """
        request: dict[str, Any] = {
            "modelId": self.model_id,
            "messages": [{"role": "user", "content": [{"text": user_prompt}]}],
            "system": [{"text": system_prompt}],
            "inferenceConfig": {
                "maxTokens": self.max_tokens,
                "temperature": self.temperature,
            },
        }

        try:
            response = self._runtime().converse(**request)
        except Exception as exc:
            # Every AWS failure is mapped to one of the typed errors above, so
            # an SDK exception never reaches the API layer with its own text.
            raise _map_error(exc, model_id=self.model_id, profile=self.profile) from exc

        return self._parse(response)

    def credentials_available(self) -> bool | None:
        """Whether AWS credentials can be resolved right now.

        Returns:
            True or False when the answer is known, None when it cannot be
            determined. The credential value itself is never returned, read
            into the response, or logged -- only whether one was found.
        """
        try:
            import boto3

            session = (
                boto3.Session(profile_name=self.profile)
                if self.profile
                else boto3.Session()
            )
            return session.get_credentials() is not None
        except Exception:
            return None

    def _runtime(self) -> Any:
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _build_client(self) -> Any:
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise BedrockNotInstalledError(
                "boto3 is not installed in the backend environment. "
                "Run 'pip install -r requirements.txt' from backend/."
            ) from exc

        config = Config(
            connect_timeout=self.timeout,
            read_timeout=self.timeout,
            retries={"max_attempts": 2, "mode": "standard"},
        )
        try:
            session = (
                boto3.Session(profile_name=self.profile)
                if self.profile
                else boto3.Session()
            )
            return session.client(
                "bedrock-runtime", region_name=self.region, config=config
            )
        except Exception as exc:
            raise _map_error(exc, model_id=self.model_id, profile=self.profile) from exc

    def _parse(self, response: Any) -> BedrockExplanation:
        """Read the generated text out of a Converse response.

        Every failure here means no usable explanation came back, so it is
        raised rather than papered over with a placeholder.
        """
        if not isinstance(response, dict):
            raise BedrockResponseError("The Bedrock response was not a JSON object.")

        output = response.get("output")
        message = output.get("message") if isinstance(output, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list) or not content:
            raise BedrockResponseError(
                "The Bedrock response carried no message content."
            )

        text: str | None = None
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                text = block["text"]
                break
        if text is None or not text.strip():
            raise BedrockResponseError(
                "The Bedrock response contained no text to show."
            )

        usage = response.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        metrics = response.get("metrics")
        metrics = metrics if isinstance(metrics, dict) else {}

        return BedrockExplanation(
            text=text.strip(),
            model_id=self.model_id,
            region=self.region,
            stop_reason=_optional_str(response.get("stopReason")),
            input_tokens=_optional_int(usage.get("inputTokens")),
            output_tokens=_optional_int(usage.get("outputTokens")),
            latency_ms=_optional_float(metrics.get("latencyMs")),
        )


def _error_code(exc: Exception) -> str:
    """The AWS error code, if the exception carries one."""
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return ""
    error = response.get("Error")
    if not isinstance(error, dict):
        return ""
    code = error.get("Code")
    return code if isinstance(code, str) else ""


def _map_error(
    exc: Exception, *, model_id: str, profile: str
) -> BedrockError:
    """Turn an AWS exception into one of this module's typed errors.

    The messages are written by hand rather than taken from the exception, so
    that whatever the SDK put in the message (request ids, internal details)
    is not echoed back to the caller.
    """
    if isinstance(exc, BedrockError):
        # Already mapped -- for example a failure raised while the client was
        # being built. Mapping it again would flatten it to the generic error.
        return exc

    name = type(exc).__name__
    code = _error_code(exc)

    if name in _CREDENTIAL_ERROR_NAMES or code in _CREDENTIAL_ERROR_CODES:
        if name == "ProfileNotFound":
            return BedrockCredentialsError(
                f"AWS profile '{profile}' was not found. Check the AWS_PROFILE "
                "setting, or run 'aws sso login --profile <name>' if it is an "
                "IAM Identity Center profile."
            )
        return BedrockCredentialsError(
            "No AWS credentials were found. Configure an AWS profile, or sign "
            "in with IAM Identity Center, and try again."
        )

    if code in _ACCESS_DENIED_CODES:
        return BedrockAccessDeniedError(
            "Bedrock denied the call. Check that the profile's role allows "
            "bedrock:Converse, that the Anthropic first-time-use form has been "
            "submitted for the account, and that the model is enabled in this "
            "region."
        )

    if code in _MODEL_ERROR_CODES:
        return BedrockModelError(
            f"Bedrock does not know the model or inference profile '{model_id}' "
            f"in this region. Check the model id and the region."
        )

    if name in _TIMEOUT_ERROR_NAMES or code in _TIMEOUT_CODES:
        return BedrockTimeoutError(
            "The Bedrock call did not finish in time. It may be a cold model, "
            "or the account may be throttled. Try again."
        )

    if code in _THROTTLING_CODES:
        return BedrockThrottledError(
            "Bedrock is throttling this account, or the model is not ready. "
            "Wait a moment and try again."
        )

    if name in _UNAVAILABLE_ERROR_NAMES or code in _UNAVAILABLE_CODES:
        return BedrockUnavailableError(
            "Amazon Bedrock could not be reached. Check the network and the "
            "region, then try again."
        )

    return BedrockError(
        f"The Bedrock call failed ({name}). The reason was not recognised, so "
        "no explanation was generated."
    )


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)
