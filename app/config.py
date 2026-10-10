"""Settings loaded from the environment and an optional .env file."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    neatlogs_api_key: str = ""
    neatlogs_endpoint: str = "https://ingest.neatlogs.com"
    neatlogs_traces_url: str = ""
    crustdata_api_key: str = ""
    crustdata_api_version: str = "2025-11-01"
    crustdata_base_url: str = "https://api.crustdata.com"

    llm_provider: Literal["bedrock"] = "bedrock"
    aws_profile: str = ""
    aws_region: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    llm_model_strong: str = ""
    llm_model_fast: str = ""

    data_mode: Literal["replay", "live"] = "replay"
    demo_mode: bool = True
    max_credits: int = 400

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    from_email: str = "demo@signalsdr.local"

    db_path: str = "signalsdr.db"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
