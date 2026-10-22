"""Central configuration. Values come from environment variables / backend/.env."""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> <repo root>
BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BACKEND_DIR.parent
DEFAULT_DATA_DIR = REPO_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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
    strands_decider_model: str = ""

    @field_validator("cors_origins", mode="after")
    @classmethod
    def _split_origins(cls, v):
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    @property
    def sample_prices_path(self) -> Path:
        """Absolute path to the sample price CSV."""
        return Path(self.data_dir) / self.sample_prices_file


@lru_cache
def get_settings() -> Settings:
    return Settings()
