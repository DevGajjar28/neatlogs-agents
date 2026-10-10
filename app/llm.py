"""Bedrock chat models. Every model is returned with the neatlogs callback attached."""

from __future__ import annotations

import os
from typing import Literal

from dotenv import load_dotenv
from langchain_aws import ChatBedrockConverse

from app.config import clear_settings_cache, get_settings
from app.infra.tracing import callbacks, init_tracing

Kind = Literal["strong", "fast"]


def _prepare_aws_env() -> None:
    """Load .env and drop an empty AWS_PROFILE so boto3 does not look for profile ''."""
    # Do not override existing process env (e.g. DATA_MODE=live from the CLI).
    load_dotenv(override=False)
    profile = os.getenv("AWS_PROFILE")
    if profile is not None and not profile.strip():
        os.environ.pop("AWS_PROFILE", None)


def get_llm(kind: Kind = "strong"):
    """Return ChatBedrockConverse with neatlogs callbacks always attached."""
    _prepare_aws_env()
    clear_settings_cache()
    settings = get_settings()
    if settings.llm_provider != "bedrock":
        raise RuntimeError("LLM_PROVIDER must be bedrock")
    if not settings.aws_region:
        raise RuntimeError("AWS_REGION is required")

    has_profile = bool(settings.aws_profile.strip())
    has_keys = bool(settings.aws_access_key_id.strip() and settings.aws_secret_access_key.strip())
    if not has_profile and not has_keys:
        raise RuntimeError(
            "Set AWS_PROFILE, or both AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY, in .env"
        )

    model_id = settings.llm_model_strong if kind == "strong" else settings.llm_model_fast
    if not model_id:
        env_name = "LLM_MODEL_STRONG" if kind == "strong" else "LLM_MODEL_FAST"
        raise RuntimeError(f"{env_name} is empty")

    init_tracing()
    kwargs: dict = {
        "model_id": model_id,
        "region_name": settings.aws_region,
    }
    if has_keys:
        kwargs["aws_access_key_id"] = settings.aws_access_key_id
        kwargs["aws_secret_access_key"] = settings.aws_secret_access_key
    else:
        kwargs["credentials_profile_name"] = settings.aws_profile

    llm = ChatBedrockConverse(**kwargs)
    configured = llm.with_config({"callbacks": callbacks()})
    return _ChaosLlmProxy(configured)


class _ChaosLlmProxy:
    """Optional chaos: first invoke / structured invoke raises llm_bad_json once."""

    def __init__(self, inner) -> None:
        self._inner = inner

    def invoke(self, *args, **kwargs):
        from app.infra.chaos import get_chaos

        get_chaos().maybe_bad_llm_json()
        return self._inner.invoke(*args, **kwargs)

    def with_structured_output(self, *args, **kwargs):
        structured = self._inner.with_structured_output(*args, **kwargs)
        return _ChaosStructuredProxy(structured)

    def with_config(self, *args, **kwargs):
        return _ChaosLlmProxy(self._inner.with_config(*args, **kwargs))

    def __getattr__(self, name: str):
        return getattr(self._inner, name)


class _ChaosStructuredProxy:
    def __init__(self, inner) -> None:
        self._inner = inner

    def invoke(self, *args, **kwargs):
        from app.infra.chaos import get_chaos

        get_chaos().maybe_bad_llm_json()
        return self._inner.invoke(*args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)
