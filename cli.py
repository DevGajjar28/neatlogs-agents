"""SignalSDR command line. Agent commands are stubs until later phases."""

from __future__ import annotations

import typer

app = typer.Typer(add_completion=False, no_args_is_help=True, help="SignalSDR outbound campaigns")


def _pending(name: str) -> None:
    typer.echo(f"{name} is not implemented yet")
    raise typer.Exit(code=1)


@app.command()
def run(
    company_name: str = typer.Option(..., help="Seller company name"),
    website: str = typer.Option(..., help="Seller website"),
    description: str = typer.Option("", help="Optional one-line description"),
    n: int = typer.Option(10, min=1, help="How many leads to keep"),
) -> None:
    """Start a campaign."""
    _ = (company_name, website, description, n)
    _pending("run")


@app.command()
def resume(campaign_id: str = typer.Argument(..., help="Campaign to resume")) -> None:
    """Resume a campaign from the last checkpoint."""
    _ = campaign_id
    _pending("resume")


@app.command()
def approve(campaign_id: str = typer.Argument(..., help="Campaign waiting for approval")) -> None:
    """Approve an ICP or a queued email."""
    _ = campaign_id
    _pending("approve")


@app.command()
def report(campaign_id: str = typer.Argument(..., help="Campaign to report")) -> None:
    """Write a run report for a campaign."""
    _ = campaign_id
    _pending("report")


@app.command("simulate-reply")
def simulate_reply(lead_id: str = typer.Argument(..., help="Lead that replied")) -> None:
    """Insert a demo reply so follow-ups stop."""
    _ = lead_id
    _pending("simulate-reply")


@app.command()
def purge(campaign_id: str = typer.Argument(..., help="Campaign data to delete")) -> None:
    """Delete cache, leads, drafts, and schedule rows for one campaign."""
    _ = campaign_id
    _pending("purge")


@app.command("doctor-crustdata")
def doctor_crustdata(
    sample_search: bool = typer.Option(
        False,
        "--sample-search",
        help="Make one small live company/search (limit 5) and save a fixture",
    ),
    chaos: str = typer.Option("", help="Comma-separated chaos flags"),
) -> None:
    """Print enabled Crustdata endpoints, prices, and balance (08 §6)."""
    from pathlib import Path

    from app.config import clear_settings_cache, get_settings
    from app.infra.budget import ACCOUNT_FILE
    from app.infra.chaos import set_chaos
    from app.infra.tracing import finish, init_tracing
    from app.tools.crustdata import CrustdataClient, save_account_snapshot

    clear_settings_cache()
    settings = get_settings()
    if not settings.crustdata_api_key.strip():
        typer.echo("CRUSTDATA_API_KEY is missing in .env", err=True)
        raise typer.Exit(code=1)

    if chaos:
        set_chaos(chaos)

    init_tracing("doctor-crustdata")
    client = CrustdataClient()
    try:
        endpoints = client.account_endpoints()
        credits = client.account_credits()
        path = save_account_snapshot(endpoints, credits)
        client.reload_prices()

        endpoint_list = []
        if isinstance(endpoints, dict):
            endpoint_list = endpoints.get("endpoints") or []
        elif isinstance(endpoints, list):
            endpoint_list = endpoints

        wanted = {
            "/company/identify",
            "/company/search",
            "/company/search/autocomplete",
            "/company/enrich",
            "/person/search",
            "/person/search/autocomplete",
            "/person/enrich",
            "/person/professional_network/search/live",
            "/person/contact/enrich",
            "/web/search/live",
            "/web/enrich/live",
            "/account/endpoints",
            "/account/credits",
            "/account/usage/events",
        }

        typer.echo(f"Saved account snapshot -> {path}")
        typer.echo("path\tstatus\trpm\tbase_credits")
        by_path = {}
        for item in endpoint_list:
            if not isinstance(item, dict):
                continue
            p = item.get("path")
            if p in wanted or p in {
                "/company/identify",
                "/company/search",
                "/company/enrich",
                "/person/search",
                "/person/enrich",
                "/web/search/live",
                "/web/enrich/live",
            }:
                by_path[p] = item
                typer.echo(
                    f"{p}\t{item.get('status')}\t{item.get('effective_rate_limit_rpm')}\t{item.get('base_credits')}"
                )

        # credits payload shapes vary; print compactly
        typer.echo(f"credits_payload={credits}")

        balance = None
        if isinstance(credits, dict):
            account = credits.get("account")
            if isinstance(account, dict) and isinstance(account.get("credits"), (int, float)):
                balance = float(account["credits"])
            if balance is None:
                for key in ("remaining_credits", "credits_remaining", "balance", "credits"):
                    if key in credits and isinstance(credits[key], (int, float)):
                        balance = float(credits[key])
                        break

        if balance is not None:
            typer.echo(f"balance={balance}")
            if balance < settings.max_credits:
                typer.echo(
                    f"WARNING: balance {balance} < MAX_CREDITS {settings.max_credits}; "
                    "keep live runs small or lower MAX_CREDITS"
                )

        person_enrich = by_path.get("/person/enrich") or {}
        enabled_fields = person_enrich.get("enabled_fields") or person_enrich.get("fields") or []
        live_people = by_path.get("/person/professional_network/search/live") or {}
        contact_enrich = by_path.get("/person/contact/enrich") or {}

        typer.echo("fallbacks:")
        typer.echo(
            f"  live_people_search={live_people.get('status', 'missing')} "
            f"(only use if enabled)"
        )
        typer.echo(f"  person_contact_enrich={contact_enrich.get('status', 'missing')}")
        typer.echo(
            f"  contact.business_emails_on_person_enrich="
            f"{'yes' if 'contact.business_emails' in str(enabled_fields) else 'check_snapshot'}"
        )
        typer.echo(f"  DATA_MODE={settings.data_mode} MAX_CREDITS={settings.max_credits}")

        if sample_search:
            if settings.data_mode != "live":
                typer.echo("Set DATA_MODE=live in .env for --sample-search", err=True)
                raise typer.Exit(code=1)
            body = {
                "filters": {
                    "op": "and",
                    "conditions": [
                        {"field": "locations.country", "type": "=", "value": "United States"},
                    ],
                },
                "fields": [
                    "crustdata_company_id",
                    "basic_info.name",
                    "basic_info.primary_domain",
                    "basic_info.employee_count_range",
                    "locations.country",
                ],
                "limit": 5,
            }
            result = client.company_search(body, campaign_id="doctor-sample", step="sample_search")
            fixtures = Path("fixtures")
            fixtures.mkdir(exist_ok=True)
            out = fixtures / "company_search_limit5.json"
            out.write_text(__import__("json").dumps(result, indent=2, default=str), encoding="utf-8")
            spent = client.ledger.spent("doctor-sample")
            typer.echo(f"sample_search saved -> {out} ledger_credits={spent}")
            # second call should be cache hit
            client.company_search(body, campaign_id="doctor-sample", step="sample_search_repeat")
            spent2 = client.ledger.spent("doctor-sample")
            typer.echo(f"repeat_search ledger_credits={spent2} (should match if cache hit added 0)")
    finally:
        client.close()
        finish()


@app.command("llm-smoke")
def llm_smoke() -> None:
    """Send one tiny Bedrock call through app/llm.py, then flush neatlogs."""
    from app.infra.tracing import finish, init_tracing
    from app.llm import get_llm

    init_tracing("llm-smoke")
    try:
        model = get_llm("fast")
        result = model.invoke("Reply with the single word ok.")
        text = getattr(result, "content", result)
        typer.echo(text)
    finally:
        finish()


if __name__ == "__main__":
    app()
