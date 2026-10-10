"""Read-only checkpoint accessors with a short TTL cache."""

from __future__ import annotations

import time
from typing import Any

from app.campaign_runner import interrupt_from_state, run_config
from app.graph import build_graph, open_checkpointer

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_TTL = 2.0


def get_values(campaign_id: str) -> dict[str, Any]:
    now = time.monotonic()
    hit = _CACHE.get(campaign_id)
    if hit and now - hit[0] < _TTL:
        return hit[1]
    conn, checkpointer = open_checkpointer()
    try:
        graph = build_graph(checkpointer)
        snap = graph.get_state(run_config(campaign_id))
        values = dict(snap.values or {})
        values["__interrupt_payload__"] = interrupt_from_state(snap)
    finally:
        conn.close()
    _CACHE[campaign_id] = (now, values)
    return values


def invalidate(campaign_id: str) -> None:
    _CACHE.pop(campaign_id, None)


def seller(campaign_id: str) -> dict | None:
    return get_values(campaign_id).get("seller")


def icp(campaign_id: str) -> dict | None:
    values = get_values(campaign_id)
    payload = values.get("__interrupt_payload__") or {}
    if isinstance(payload, dict) and payload.get("type") == "icp_approval":
        return payload.get("icp") or values.get("icp")
    return values.get("icp")


def companies(campaign_id: str) -> list:
    return list(get_values(campaign_id).get("companies") or [])


def contacts(campaign_id: str) -> list:
    return list(get_values(campaign_id).get("contacts") or [])


def drafts(campaign_id: str) -> dict:
    return dict(get_values(campaign_id).get("drafts") or {})


def verifier(campaign_id: str) -> dict:
    return dict(get_values(campaign_id).get("verifier") or {})


def accounts(campaign_id: str) -> dict:
    return dict(get_values(campaign_id).get("accounts") or {})


def pending_interrupt(campaign_id: str) -> dict | None:
    payload = get_values(campaign_id).get("__interrupt_payload__")
    return payload if isinstance(payload, dict) else None
