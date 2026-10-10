"""neatlogs init and LangChain callbacks. No LLM or tool call bypasses this."""

from __future__ import annotations

import os

import neatlogs


def init_tracing(workflow_name: str = "signalsdr") -> None:
    api_key = os.environ.get("NEATLOGS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("NEATLOGS_API_KEY is missing. Set it in .env.")
    neatlogs.init(api_key=api_key, workflow_name=workflow_name)


def callbacks() -> list:
    # LangChain/LangGraph need this handler; init() alone does not capture them.
    return [neatlogs.langchain_handler()]


def run_config(campaign_id: str) -> dict:
    return {
        "callbacks": callbacks(),
        "configurable": {"thread_id": campaign_id},
        "metadata": {"campaign_id": campaign_id},
    }


def finish() -> None:
    neatlogs.flush()
    neatlogs.shutdown()
