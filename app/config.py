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
    hunter_api_key: str = ""
    hunter_base_url: str = "https://api.hunter.io/v2"

    llm_provider: Literal["bedrock"] = "bedrock"
    aws_profile: str = ""
    aws_region: str = ""
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    llm_model_strong: str = ""
    llm_model_fast: str = ""

    data_mode: Literal["replay", "live"] = "replay"
    demo_mode: bool = True
    allow_live_sends: bool = False
    max_credits: int = 400

    smtp_host: str = "localhost"
    smtp_port: int = 1025
    from_email: str = "demo@signalsdr.local"

    signalsdr_secret_key: str = ""
    imap_poll_seconds: int = 60

    db_path: str = "signalsdr.db"

    # Separate Google Calendar OAuth (test account). Never the Gmail app password.
    google_calendar_client_id: str = ""
    google_calendar_client_secret: str = ""
    google_calendar_redirect_uri: str = "http://127.0.0.1:8000/api/calendar/oauth/callback"
    google_calendar_notify_attendees: bool = False
    ui_base_url: str = "http://localhost:3000"

    # Deploy: bind 0.0.0.0 on EC2; keep 127.0.0.1 for local.
    api_host: str = "127.0.0.1"
    # Comma-separated browser origins (local + Vercel). Empty → localhost:3000 only.
    cors_origins: str = "http://localhost:3000"


def cors_origin_list(settings: Settings | None = None) -> list[str]:
    s = settings or get_settings()
    raw = (s.cors_origins or "").strip()
    if not raw:
        return ["http://localhost:3000"]
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    return origins or ["http://localhost:3000"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()
