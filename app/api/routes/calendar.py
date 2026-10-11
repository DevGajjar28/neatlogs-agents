"""Google Calendar OAuth connect / disconnect (separate from Gmail)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app.api.schemas import CalendarStatusOut
from app.calendar import oauth as cal_oauth
from app.infra.audit import write_audit
from app.mail.crypto import SecretKeyMissing

router = APIRouter(tags=["calendar"])


@router.get("/calendar/status", response_model=CalendarStatusOut)
def calendar_status() -> CalendarStatusOut:
    st = cal_oauth.get_status()
    return CalendarStatusOut(**st)


@router.get("/calendar/oauth/start")
def calendar_oauth_start() -> dict[str, Any]:
    try:
        url = cal_oauth.start_auth_url()
    except cal_oauth.CalendarNotConfigured as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    return {"auth_url": url}


@router.get("/calendar/oauth/callback")
def calendar_oauth_callback(code: str = "", state: str = "", error: str = "") -> RedirectResponse:
    ui = cal_oauth.ui_settings_url().rstrip("/")
    if error:
        return RedirectResponse(f"{ui}/settings?calendar=error&reason={error}", status_code=302)
    if not code or not state:
        return RedirectResponse(f"{ui}/settings?calendar=error&reason=missing_code", status_code=302)
    try:
        cal_oauth.complete_oauth(code=code, state=state)
    except SecretKeyMissing:
        return RedirectResponse(
            f"{ui}/settings?calendar=error&reason=secret_key",
            status_code=302,
        )
    except ValueError:
        return RedirectResponse(f"{ui}/settings?calendar=error&reason=state", status_code=302)
    except Exception:  # noqa: BLE001
        return RedirectResponse(f"{ui}/settings?calendar=error&reason=token", status_code=302)
    write_audit(actor="api", action="calendar_oauth_connect", target="primary", details={})
    return RedirectResponse(f"{ui}/settings?calendar=connected", status_code=302)


@router.post("/calendar/disconnect", response_model=CalendarStatusOut)
def calendar_disconnect() -> CalendarStatusOut:
    cal_oauth.disconnect()
    write_audit(actor="api", action="calendar_oauth_disconnect", target="primary", details={})
    return CalendarStatusOut(**cal_oauth.get_status())
