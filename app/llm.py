"""Bedrock chat models. Every model is returned with the neatlogs callback attached."""

from __future__ import annotations

from typing import Literal

from langchain_aws import ChatBedrockConverse

from app.config import get_settings
from app.infra.tracing import callbacks, init_tracing

Tier = Literal["strong", "fast"]


def get_llm(tier: Tier = "strong"):
    settings = get_settings()
    if settings.llm_provider != "bedrock":
        raise RuntimeError("LLM_PROVIDER must be bedrock")
    if not settings.aws_profile or not settings.aws_region:
        raise RuntimeError("AWS_PROFILE and AWS_REGION are required")

    model_id = settings.llm_model_strong if tier == "strong" else settings.llm_model_fast
    if not model_id:
        env_name = "LLM_MODEL_STRONG" if tier == "strong" else "LLM_MODEL_FAST"
        raise RuntimeError(f"{env_name} is empty")

    init_tracing()
    llm = ChatBedrockConverse(
        model_id=model_id,
        region_name=settings.aws_region,
        credentials_profile_name=settings.aws_profile,
    )
    return llm.with_config({"callbacks": callbacks()})
