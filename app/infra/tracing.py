"""neatlogs init and LangChain callbacks. See docs/04_TOOLING_SETUP.md §2 step 4."""

from __future__ import annotations

import os

import neatlogs
from dotenv import load_dotenv

_initialized = False


def init_tracing(workflow_name: str = "signalsdr") -> None:
    """Initialize neatlogs once per process. The first call wins the workflow name."""
    global _initialized
    if _initialized:
        return
    load_dotenv()
    api_key = os.environ.get("NEATLOGS_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("NEATLOGS_API_KEY is missing. Set it in .env.")
    neatlogs.init(
        api_key=api_key,
        endpoint=os.environ.get("NEATLOGS_ENDPOINT", "https://ingest.neatlogs.com"),
        workflow_name=workflow_name,
    )
    _initialized = True


def callbacks() -> list:
    # LangChain/LangGraph need this handler; init() alone does not capture them
    return [neatlogs.langchain_handler()]


def finish() -> None:
    neatlogs.flush()
    neatlogs.shutdown()
