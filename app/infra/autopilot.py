"""Campaign Autopilot helpers (default-on; user stops via sending_paused)."""

from __future__ import annotations

from typing import Any


def autopilot_enabled(
    *,
    options: dict[str, Any] | None = None,
    inp: dict[str, Any] | None = None,
) -> bool:
    """Autopilot is on unless explicitly disabled on campaign input or options."""
    if inp is not None and inp.get("autopilot") is False:
        return False
    if options is not None and options.get("autopilot") is False:
        return False
    return True


def state_autopilot_enabled(state: dict[str, Any]) -> bool:
    inp = state.get("input") or {}
    extras = state.get("extras") or {}
    opts = extras.get("campaign_options") or {}
    return autopilot_enabled(options=opts if isinstance(opts, dict) else None, inp=inp)


def campaign_autopilot_from_db_options(options_json: dict[str, Any] | None) -> bool:
    return autopilot_enabled(options=options_json or {})
