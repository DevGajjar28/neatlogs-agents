"""Minimal FastAPI page for ICP (human gate 1) approval."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from langgraph.types import Command

from app.config import get_settings
from app.graph import build_graph, open_checkpointer
from app.infra.tracing import callbacks, finish, init_tracing

app = FastAPI(title="SignalSDR Approval")
_TEMPLATES = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


def _thread_config(campaign_id: str) -> dict[str, Any]:
    return {
        "callbacks": callbacks(),
        "configurable": {"thread_id": campaign_id},
        "metadata": {"campaign_id": campaign_id},
    }


def _interrupt_payload(snapshot) -> dict[str, Any] | None:
    for task in snapshot.tasks or ():
        for item in getattr(task, "interrupts", ()) or ():
            value = getattr(item, "value", None)
            if isinstance(value, dict):
                return value
    values = snapshot.values or {}
    interrupts = values.get("__interrupt__") or []
    if interrupts:
        first = interrupts[0]
        value = getattr(first, "value", first)
        if isinstance(value, dict):
            return value
    return None


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return (
        "<html><body><h1>SignalSDR</h1>"
        "<p>Open <code>/campaigns/&lt;campaign_id&gt;/icp</code> for ICP approval.</p>"
        "</body></html>"
    )


@app.get("/campaigns/{campaign_id}/icp", response_class=HTMLResponse)
def icp_page(request: Request, campaign_id: str) -> HTMLResponse:
    conn, checkpointer = open_checkpointer()
    try:
        graph = build_graph(checkpointer)
        snap = graph.get_state(_thread_config(campaign_id))
        payload = _interrupt_payload(snap) or {}
        icp = payload.get("icp") or (snap.values or {}).get("icp") or {}
        if not icp:
            raise HTTPException(status_code=404, detail="No ICP waiting for this campaign")
        return _TEMPLATES.TemplateResponse(
            "icp.html",
            {
                "request": request,
                "campaign_id": campaign_id,
                "icp": icp,
                "roles": icp.get("roles") or [],
                "evidence": icp.get("evidence") or [],
                "waiting": bool(payload),
                "icp_json": json.dumps(icp, indent=2),
            },
        )
    finally:
        conn.close()


@app.post("/campaigns/{campaign_id}/icp/approve")
def icp_approve(
    campaign_id: str,
    industries: str = Form(""),
    countries: str = Form(""),
    employee_count_ranges: str = Form(""),
) -> RedirectResponse:
    conn, checkpointer = open_checkpointer()
    init_tracing("outbound-approve-ui")
    try:
        graph = build_graph(checkpointer)
        config = _thread_config(campaign_id)
        snap = graph.get_state(config)
        payload = _interrupt_payload(snap)
        if not payload:
            raise HTTPException(status_code=409, detail="Campaign is not waiting on ICP approval")
        base = dict(payload.get("icp") or {})
        if industries.strip():
            base["industries"] = [x.strip() for x in industries.split(",") if x.strip()]
        if countries.strip():
            base["countries"] = [x.strip() for x in countries.split(",") if x.strip()]
        if employee_count_ranges.strip():
            base["employee_count_ranges"] = [
                x.strip() for x in employee_count_ranges.split(",") if x.strip()
            ]
        graph.invoke(
            Command(resume={"approved": True, "icp": base}),
            config=config,
        )
        return RedirectResponse(url=f"/campaigns/{campaign_id}/icp?done=1", status_code=303)
    finally:
        conn.close()
        finish()


def main() -> None:
    import uvicorn

    settings = get_settings()
    uvicorn.run("app.ui.app:app", host="127.0.0.1", port=8080, reload=False)
    _ = settings


if __name__ == "__main__":
    main()
