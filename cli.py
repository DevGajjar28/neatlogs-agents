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
def doctor_crustdata() -> None:
    """Print enabled Crustdata endpoints, prices, and balance. Phase 2."""
    _pending("doctor-crustdata")


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
