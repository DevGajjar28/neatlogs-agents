"""System status, health, estimate."""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import APIRouter

from app.api.schemas import EstimateIn, EstimateOut, HealthOut, SystemStatusOut
from app.config import get_settings
from app.infra.budget import ACCOUNT_FILE, estimate_campaign
from app.infra.db import connect, init_db
from app.mail.policy import get_setting, max_send_mode_allowed

router = APIRouter(tags=["system"])

_credits_cache: tuple[float, dict] | None = None


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    return HealthOut(ok=True)


@router.get("/system/status", response_model=SystemStatusOut)
def system_status() -> SystemStatusOut:
    settings = get_settings()
    crust: dict = {"status": "unknown", "hint": "Run python cli.py doctor-crustdata"}
    if ACCOUNT_FILE.exists():
        try:
            data = json.loads(ACCOUNT_FILE.read_text(encoding="utf-8"))
            crust = {
                "status": "ok",
                "saved_at": data.get("saved_at"),
                "credits": (data.get("credits") or {}).get("account", {}).get("credits"),
            }
        except Exception as exc:
            crust = {"status": "error", "detail": str(exc)}
    global _credits_cache
    now = time.monotonic()
    if _credits_cache and now - _credits_cache[0] < 60:
        crust["live_credits"] = _credits_cache[1]
    elif settings.crustdata_api_key.strip() and settings.data_mode == "live":
        try:
            from app.tools.crustdata import CrustdataClient

            live = CrustdataClient().account_credits()
            _credits_cache = (now, live if isinstance(live, dict) else {"raw": live})
            crust["live_credits"] = _credits_cache[1]
            crust["status"] = "ok"
        except Exception as exc:
            crust["live_error"] = str(exc)

    init_db(settings.db_path)
    conn = connect(settings.db_path)
    try:
        paused = bool(get_setting(conn, "sending_paused", False))
        mail_count = conn.execute("SELECT COUNT(*) AS n FROM mail_accounts").fetchone()["n"]
        mail_err = conn.execute(
            "SELECT COUNT(*) AS n FROM mail_accounts WHERE status = 'error'"
        ).fetchone()["n"]
    finally:
        conn.close()

    return SystemStatusOut(
        crustdata=crust,
        data_mode=settings.data_mode,
        demo_mode=settings.demo_mode,
        max_credits=settings.max_credits,
        llm={
            "strong": settings.llm_model_strong,
            "fast": settings.llm_model_fast,
            "provider": settings.llm_provider,
        },
        neatlogs={
            "configured": bool(settings.neatlogs_api_key.strip()),
            "traces_url": settings.neatlogs_traces_url or None,
            "endpoint": settings.neatlogs_endpoint,
        },
        max_send_mode=max_send_mode_allowed(),
        sending_paused=paused,
        mail_account_count=int(mail_count or 0),
        mail_account_error=bool(mail_err),
    )


@router.post("/estimate", response_model=EstimateOut)
def estimate(body: EstimateIn) -> EstimateOut:
    out = estimate_campaign(body.n, body.mode)
    return EstimateOut(total=float(out["total"]), by_step=list(out["by_step"]))
