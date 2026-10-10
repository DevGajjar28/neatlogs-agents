"""Run metrics from checkpoint state, ledger, and mail tables."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.infra.budget import BudgetLedger
from app.infra.db import connect, init_db
from app.infra.redact import redact_text

# Metrics where a lower value is better for compare().
_LOWER_IS_BETTER = frozenset(
    {
        "credits_spent",
        "wall_clock_seconds",
        "companies_dropped",
        "verifier_redraft",
        "verifier_downgrade",
        "verifier_drop",
        "followups_cancelled",
        "cost_per_qualified_lead",
        "errors",
    }
)


def load_campaign_state(campaign_id: str, *, db_path: str | Path | None = None) -> dict[str, Any]:
    from app.graph import build_graph, open_checkpointer

    path = str(db_path) if db_path else None
    conn, checkpointer = open_checkpointer(path)
    try:
        graph = build_graph(checkpointer)
        snap = graph.get_state(
            {
                "configurable": {"thread_id": campaign_id},
                "metadata": {"campaign_id": campaign_id},
            }
        )
        return dict(snap.values or {})
    finally:
        conn.close()


def compute_metrics(
    campaign_id: str,
    *,
    state: dict[str, Any] | None = None,
    wall_seconds: float | None = None,
    db_path: str | Path | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    path = Path(db_path or settings.db_path)
    init_db(path)
    state = state if state is not None else load_campaign_state(campaign_id, db_path=path)

    ledger = BudgetLedger(path)
    credits_spent = ledger.spent(campaign_id)
    by_step, cache_hits, cache_total = _ledger_breakdown(path, campaign_id)
    cache_hit_rate = (cache_hits / cache_total) if cache_total else 0.0

    companies = state.get("companies") or []
    kept = [c for c in companies if isinstance(c, dict) and c.get("status") == "kept"]
    dropped = [c for c in companies if isinstance(c, dict) and c.get("status") == "dropped"]
    contacts = state.get("contacts") or []
    events = state.get("events") or []

    fallback_counts = _count_prefix(events, "fallback.contact_step_")
    verifier = {
        "pass": _count_type(events, "verify.pass"),
        "redraft": _count_type(events, "verify.redraft"),
        "downgrade": _count_type(events, "verify.downgrade"),
        "drop": _count_type(events, "verify.drop"),
    }
    recoveries = _count_recoveries(events)

    mail = _mail_stats(path, campaign_id)
    qualified = max(1, len(contacts)) if contacts else 0
    cost_per_ql = (credits_spent / len(contacts)) if contacts else None

    wall = wall_seconds
    if wall is None:
        wall = _estimate_wall(path, campaign_id)

    reconciled, reconcile_note = _try_reconcile(campaign_id)

    return {
        "campaign_id": campaign_id,
        "seller": (state.get("input") or {}).get("company_name"),
        "n": (state.get("input") or {}).get("n"),
        "data_mode": (state.get("input") or {}).get("mode"),
        "credits_spent": credits_spent,
        "credits_by_step": by_step,
        "cache_hit_rate": cache_hit_rate,
        "cache_hits": cache_hits,
        "cache_total": cache_total,
        "tokens": None,
        "llm_cost": None,
        "tokens_note": "unavailable locally; read neatlogs dashboard for the campaign",
        "wall_clock_seconds": wall,
        "companies_found": len(companies),
        "companies_kept": len(kept),
        "companies_dropped": len(dropped),
        "contacts_found": len(contacts),
        "contacts_by_fallback_step": fallback_counts,
        "verifier_pass": verifier["pass"],
        "verifier_redraft": verifier["redraft"],
        "verifier_downgrade": verifier["downgrade"],
        "verifier_drop": verifier["drop"],
        "emails_sent": mail["emails_sent"],
        "followups_sent": mail["followups_sent"],
        "followups_cancelled": mail["followups_cancelled"],
        "recoveries_by_type": recoveries,
        "cost_per_qualified_lead": cost_per_ql,
        "qualified_leads": len(contacts),
        "errors": len(state.get("errors") or []),
        "events": len(events),
        "halt_reason": state.get("halt_reason"),
        "reconciled": reconciled,
        "reconcile_note": reconcile_note,
        "events_sample": events[:40],
    }


def compare(baseline_id: str, campaign_id: str, *, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    base = compute_metrics(baseline_id, db_path=db_path)
    cur = compute_metrics(campaign_id, db_path=db_path)
    keys = [
        "credits_spent",
        "cache_hit_rate",
        "wall_clock_seconds",
        "companies_found",
        "companies_kept",
        "companies_dropped",
        "contacts_found",
        "verifier_pass",
        "verifier_redraft",
        "verifier_downgrade",
        "verifier_drop",
        "emails_sent",
        "followups_sent",
        "followups_cancelled",
        "cost_per_qualified_lead",
        "errors",
    ]
    rows: list[dict[str, Any]] = []
    for key in keys:
        b = base.get(key)
        c = cur.get(key)
        change = None
        better = None
        if isinstance(b, (int, float)) and isinstance(c, (int, float)):
            change = c - b
            if key in _LOWER_IS_BETTER:
                better = c < b
            else:
                better = c > b
            if c == b:
                better = None
        rows.append(
            {
                "metric": key,
                "baseline": b,
                "current": c,
                "change": change,
                "better": better,
            }
        )
    return rows


def write_report(
    campaign_id: str,
    baseline_id: str | None = None,
    *,
    path: Path | None = None,
    state: dict[str, Any] | None = None,
    wall_seconds: float | None = None,
    db_path: str | Path | None = None,
) -> Path:
    metrics = compute_metrics(
        campaign_id, state=state, wall_seconds=wall_seconds, db_path=db_path
    )
    out = path or Path("reports") / f"{campaign_id}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = _render_metrics_md(metrics)
    if baseline_id:
        rows = compare(baseline_id, campaign_id, db_path=db_path)
        lines.extend(["", "## Comparison", "", f"- baseline: `{baseline_id}`", ""])
        lines.append("| metric | baseline | current | change | better |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in rows:
            lines.append(
                f"| {row['metric']} | {row['baseline']} | {row['current']} | "
                f"{row['change']} | {row['better']} |"
            )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    json_path = out.with_suffix(".json")
    json_path.write_text(json.dumps(metrics, indent=2, default=str), encoding="utf-8")
    return out


def write_comparison(
    baseline_id: str,
    campaign_id: str,
    *,
    path: Path | None = None,
    db_path: str | Path | None = None,
) -> Path:
    rows = compare(baseline_id, campaign_id, db_path=db_path)
    out = path or Path("reports") / "comparison.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# SignalSDR comparison",
        "",
        f"- baseline: `{baseline_id}`",
        f"- current: `{campaign_id}`",
        f"- generated_at: {datetime.now(timezone.utc).isoformat()}",
        "",
        "| metric | baseline | current | change | better |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| {row['metric']} | {row['baseline']} | {row['current']} | "
            f"{row['change']} | {row['better']} |"
        )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def write_v0_report(
    state: dict[str, Any],
    *,
    wall_seconds: float,
    path: Path | None = None,
) -> Path:
    """Thin wrapper kept for existing CLI callers."""
    campaign_id = state["campaign_id"]
    out = path or Path("reports") / "v0.md"
    return write_report(
        campaign_id,
        path=out,
        state=state,
        wall_seconds=wall_seconds,
    )


def _render_metrics_md(m: dict[str, Any]) -> list[str]:
    sample = redact_text(json.dumps(m.get("events_sample") or [], indent=2, default=str))
    return [
        f"# SignalSDR run report - `{m['campaign_id']}`",
        "",
        f"- generated_at: {datetime.now(timezone.utc).isoformat()}",
        f"- seller: {m.get('seller')}",
        f"- n: {m.get('n')}",
        f"- data_mode: {m.get('data_mode')}",
        f"- wall_clock_seconds: {m.get('wall_clock_seconds')}",
        f"- crustdata_credits_spent: {m.get('credits_spent')}",
        f"- cache_hit_rate: {m.get('cache_hit_rate'):.2%}"
        if isinstance(m.get("cache_hit_rate"), float)
        else f"- cache_hit_rate: {m.get('cache_hit_rate')}",
        f"- companies_found/kept/dropped: {m.get('companies_found')}/"
        f"{m.get('companies_kept')}/{m.get('companies_dropped')}",
        f"- contacts_found: {m.get('contacts_found')}",
        f"- contacts_by_fallback_step: {m.get('contacts_by_fallback_step')}",
        f"- verifier pass/redraft/downgrade/drop: {m.get('verifier_pass')}/"
        f"{m.get('verifier_redraft')}/{m.get('verifier_downgrade')}/{m.get('verifier_drop')}",
        f"- emails_sent: {m.get('emails_sent')}",
        f"- followups_sent/cancelled: {m.get('followups_sent')}/{m.get('followups_cancelled')}",
        f"- recoveries_by_type: {m.get('recoveries_by_type')}",
        f"- cost_per_qualified_lead: {m.get('cost_per_qualified_lead')}",
        f"- tokens/llm_cost: {m.get('tokens')}/{m.get('llm_cost')} ({m.get('tokens_note')})",
        f"- reconciled: {m.get('reconciled')} — {m.get('reconcile_note')}",
        f"- halt_reason: {m.get('halt_reason')}",
        f"- errors: {m.get('errors')}",
        "",
        "## Credits by step",
        "",
        "```json",
        json.dumps(m.get("credits_by_step") or {}, indent=2, default=str),
        "```",
        "",
        "## Events (truncated, redacted)",
        "",
        "```json",
        sample,
        "```",
    ]


def _ledger_breakdown(path: Path, campaign_id: str) -> tuple[dict[str, float], int, int]:
    conn = connect(path)
    try:
        rows = conn.execute(
            """
            SELECT step, SUM(credits) AS credits, SUM(cache_hit) AS hits, COUNT(*) AS n
            FROM budget_ledger WHERE campaign_id = ?
            GROUP BY step
            """,
            (campaign_id,),
        ).fetchall()
    finally:
        conn.close()
    by_step: dict[str, float] = {}
    hits = 0
    total = 0
    for row in rows:
        step = str(row["step"]).split("|rid=")[0]
        by_step[step] = by_step.get(step, 0.0) + float(row["credits"] or 0)
        hits += int(row["hits"] or 0)
        total += int(row["n"] or 0)
    return by_step, hits, total


def _mail_stats(path: Path, campaign_id: str) -> dict[str, int]:
    conn = connect(path)
    try:
        lead_ids = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM leads WHERE campaign_id = ?",
                (campaign_id,),
            ).fetchall()
        ]
        if not lead_ids:
            return {"emails_sent": 0, "followups_sent": 0, "followups_cancelled": 0}
        placeholders = ",".join("?" * len(lead_ids))
        sent = conn.execute(
            f"SELECT COUNT(*) AS n FROM emails WHERE lead_id IN ({placeholders}) AND status = 'sent'",
            lead_ids,
        ).fetchone()["n"]
        follow_sent = conn.execute(
            f"""
            SELECT COUNT(*) AS n FROM emails
            WHERE lead_id IN ({placeholders}) AND status = 'sent' AND step > 1
            """,
            lead_ids,
        ).fetchone()["n"]
        cancelled = conn.execute(
            f"""
            SELECT COUNT(*) AS n FROM scheduled_jobs
            WHERE lead_id IN ({placeholders}) AND status = 'cancelled'
            """,
            lead_ids,
        ).fetchone()["n"]
    finally:
        conn.close()
    return {
        "emails_sent": int(sent or 0),
        "followups_sent": int(follow_sent or 0),
        "followups_cancelled": int(cancelled or 0),
    }


def _estimate_wall(path: Path, campaign_id: str) -> float | None:
    conn = connect(path)
    try:
        row = conn.execute(
            "SELECT created_at FROM campaigns WHERE id = ?",
            (campaign_id,),
        ).fetchone()
        if not row:
            return None
        start = datetime.fromisoformat(row["created_at"])
        end_row = conn.execute(
            "SELECT MAX(ts) AS ts FROM budget_ledger WHERE campaign_id = ?",
            (campaign_id,),
        ).fetchone()
        if end_row and end_row["ts"]:
            end = datetime.fromisoformat(end_row["ts"])
            return max(0.0, (end - start).total_seconds())
    except Exception:
        return None
    finally:
        conn.close()
    return None


def _try_reconcile(campaign_id: str) -> tuple[bool | None, str]:
    """Best-effort Crustdata usage reconciliation; honest if unavailable."""
    settings = get_settings()
    if settings.data_mode == "replay":
        return None, "not reconciled (DATA_MODE=replay; usage/events skipped)"
    if not settings.crustdata_api_key.strip():
        return None, "not reconciled (no CRUSTDATA_API_KEY)"
    try:
        from app.tools.crustdata import CrustdataClient

        client = CrustdataClient()
        client.usage_events(campaign_id=campaign_id)
        return None, "not reconciled (usage/events fetched; X-Request-Id join not automated yet)"
    except Exception as exc:
        return None, f"not reconciled ({exc})"


def _count_type(events: list, type_name: str) -> int:
    return sum(1 for e in events if isinstance(e, dict) and e.get("type") == type_name)


def _count_prefix(events: list, prefix: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in events:
        if not isinstance(e, dict):
            continue
        t = str(e.get("type") or "")
        if t.startswith(prefix):
            out[t] = out.get(t, 0) + 1
    return out


def _count_recoveries(events: list) -> dict[str, int]:
    out: dict[str, int] = {}
    for e in events:
        if not isinstance(e, dict):
            continue
        t = str(e.get("type") or "")
        if t.startswith("recovery."):
            out[t] = out.get(t, 0) + 1
    return out
