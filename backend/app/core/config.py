"""Central configuration. Values come from environment variables / backend/.env."""
import ipaddress
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> <repo root>
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_DATA_DIR = REPO_ROOT / "data"

#: The local Strands Decider 2B service. It has no authentication, so it must
#: stay on the loopback interface.
DEFAULT_DECIDER_BASE_URL = "http://127.0.0.1:8100"

#: The exact checkpoint verified in `experiments/decider-spike.md`.
DEFAULT_DECIDER_MODEL = "StrandsAgents/strands-decider-2B-qwen3.5-v1-2610"


class Settings(BaseSettings):
    # `env_ignore_empty` means a blank value in .env falls back to the default
    # instead of overriding it with an empty string. Without it, the empty
    # placeholders in `.env.example` would silently blank out the defaults.
    model_config = SettingsConfigDict(
        env_file=".env", extra="ignore", env_ignore_empty=True
    )

    app_env: str = "development"
    cors_origins: list[str] | str = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # Local sample market dataset. `data_dir` may be overridden with the DATA_DIR
    # environment variable; it is resolved against the repo root by default so the
    # app works no matter which directory uvicorn is started from.
    data_dir: str = str(DEFAULT_DATA_DIR)
    sample_prices_file: str = "sample_prices.csv"

    # Reserved for later parts. Unused in Part 1; no credentials are read or required.
    aws_region: str = ""
    aws_profile: str = ""
    bedrock_model_id: str = ""

    # The local Strands Decider 2B service. It runs in its own Python 3.12
    # environment (see `experiments/decider-spike/`) and is reached over plain
    # HTTP. It has no authentication, so the URL is restricted to the loopback
    # interface -- see `_validate_decider_base_url`.
    decider_base_url: str = DEFAULT_DECIDER_BASE_URL
    decider_timeout_seconds: float = 15.0
    strands_decider_model: str = DEFAULT_DECIDER_MODEL

    @field_validator("cors_origins", mode="after")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @field_validator("decider_base_url")
    @classmethod
    def _validate_decider_base_url(cls, v: str) -> str:
        """Refuse a Decider URL that is not on the loopback interface.

        The Decider service has no authentication: anyone who can reach its port
        can drive the model. Pointing it at a remote host would turn a local
        experiment into an open proxy, so only loopback addresses are accepted.
        """
        parsed = urlparse(v.strip())
        if parsed.scheme not in ("http", "https"):
            raise ValueError(
                f"decider_base_url must be an http(s) URL, got '{v}'."
            )
        host = parsed.hostname
        if not host:
            raise ValueError(f"decider_base_url has no host: '{v}'.")
        if host == "localhost" or _is_loopback_ip(host):
            return v.strip()
        raise ValueError(
            f"decider_base_url must point at a loopback address "
            f"(127.0.0.1, ::1 or localhost), got '{host}'. The Decider service has "
            f"no authentication, so it must not be reachable from the network."
        )

    @field_validator("decider_timeout_seconds")
    @classmethod
    def _validate_decider_timeout(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(
                f"decider_timeout_seconds must be greater than zero, got {v}."
            )
        return v

    @property
    def sample_prices_path(self) -> Path:
        """Absolute path to the sample price CSV."""
        return Path(self.data_dir) / self.sample_prices_file


@lru_cache
def get_settings() -> Settings:
    return Settings()


def _is_loopback_ip(host: str) -> bool:
    """True when `host` is a loopback IP literal such as 127.0.0.1 or ::1."""
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False
