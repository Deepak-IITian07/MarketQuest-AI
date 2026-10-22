"""Central configuration. Values come from environment variables / backend/.env."""
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    cors_origins: list[str] | str = ["http://localhost:5173", "http://127.0.0.1:5173"]

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
