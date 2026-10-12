"""Product researcher: seller brief from the seller website + LLM (no Crustdata)."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from app.agents.evidence import make_evidence
from app.infra.events import EventBag
from app.llm import get_llm
from app.models import SellerBrief
from app.tools import web


class _ExtractedSeller(BaseModel):
    one_liner: str = ""
    products: list[str] = Field(default_factory=list)
    value_props: list[str] = Field(default_factory=list)
    pricing_notes: str | None = None
    named_customers: list[str] = Field(default_factory=list)


def _domain(website: str) -> str:
    return web.domain_of(website)


def product_researcher_node(state: dict[str, Any]) -> dict[str, Any]:
    """Fetch seller site + LLM extract into SellerBrief. Crustdata is not used here."""
    inp = state["input"]
    campaign_id = state["campaign_id"]
    company_name = inp["company_name"]
    website = inp["website"]
    description = inp.get("description") or ""
    events = EventBag(state, "product_researcher")
    errors = list(state.get("errors") or [])

    domain = _domain(website)
    evidence = []
    pages = web.fetch_seller_pages(website)
    page_blob = "\n\n".join(f"URL: {p['url']}\n{p['text'][:3000]}" for p in pages)[:14000]

    events.append(
        {
            "type": "fallback.seller_crustdata_skipped",
            "detail": "product research uses website fetch + LLM only",
            "domain": domain,
        }
    )

    for page in pages:
        for snippet in page.get("quarantined") or []:
            events.append(
                {
                    "type": "security.injection_quarantined",
                    "url": page.get("url"),
                    "snippet": str(snippet)[:200],
                }
            )

    for page in pages[:3]:
        snippet = page["text"][:160]
        if snippet:
            evidence.append(
                make_evidence(
                    snippet,
                    source_type="web",
                    source_ref=page["url"],
                    confidence="medium",
                )
            )

    heuristic_customers = web.heuristic_named_customers(pages)
    llm = get_llm("fast")
    prompt = (
        "Extract seller facts from the page text. Named customers must appear in the text; "
        "never invent customers. Return JSON matching the schema.\n"
        f"Company: {company_name}\nWebsite: {website}\nDescription: {description}\n\n"
        f"Heuristic customer candidates: {heuristic_customers}\n\n"
        f"PAGE TEXT:\n{page_blob or '(no pages fetched)'}"
    )
    try:
        structured = llm.with_structured_output(_ExtractedSeller)
        extracted = structured.invoke(prompt)
        if not isinstance(extracted, _ExtractedSeller):
            extracted = _ExtractedSeller.model_validate(extracted)
    except Exception as exc:  # noqa: BLE001 — soft-fail to heuristics
        errors.append({"step": "product_researcher.llm", "error": str(exc)})
        if "llm_bad_json" in str(exc):
            events.append({"type": "recovery.llm_bad_json", "step": "product_researcher"})
        extracted = _ExtractedSeller(
            one_liner=description or f"{company_name} product",
            products=[company_name],
            value_props=[description] if description else [],
            named_customers=heuristic_customers[:8],
        )

    named = []
    for name in extracted.named_customers:
        clean = name.strip()
        if clean and clean.lower() not in {company_name.lower(), domain} and clean not in named:
            named.append(clean)

    if not named:
        events.append(
            {"type": "product.no_customers", "detail": "buyer_finder will use low-confidence ICP"}
        )

    for name in named[:8]:
        evidence.append(
            make_evidence(
                f"Named customer on seller site: {name}",
                source_type="web",
                source_ref=pages[0]["url"] if pages else website,
                confidence="medium",
            )
        )

    brief = SellerBrief(
        company_name=company_name,
        domain=domain,
        one_liner=extracted.one_liner or description or company_name,
        products=extracted.products or [company_name],
        value_props=extracted.value_props or [],
        pricing_notes=extracted.pricing_notes,
        named_customers=named,
        evidence=evidence,
    )
    spent = float((state.get("budget") or {}).get("credits_spent") or 0)
    return {
        "seller": brief.model_dump(mode="json"),
        "extras": dict(state.get("extras") or {}),
        "events": events,
        "errors": errors,
        "budget": {"credits_spent": spent},
    }


def _first_company_id(payload: Any) -> int | str | None:
    data = _first_company_data(payload)
    if data:
        return data.get("crustdata_company_id") or (data.get("basic_info") or {}).get(
            "crustdata_company_id"
        )
    return None


def _first_company_data(payload: Any) -> dict | None:
    """Shared helper for buyer_finder / identify response shapes."""
    rows: list[dict] = []
    if isinstance(payload, list):
        rows = [r for r in payload if isinstance(r, dict)]
    elif isinstance(payload, dict):
        if "matches" in payload:
            rows = [payload]
        else:
            rows = [
                r
                for r in (payload.get("companies") or payload.get("results") or [])
                if isinstance(r, dict)
            ]
    for item in rows:
        matches = item.get("matches") or []
        if matches and isinstance(matches[0], dict):
            return matches[0].get("company_data") or matches[0]
        if "company_data" in item:
            return item["company_data"]
        if "basic_info" in item or "crustdata_company_id" in item:
            return item
    return None


def _confident_customer_names(payload: Any, originals: list[str]) -> list[str]:
    """Keep identify matches with confidence >= 0.9 when available."""
    kept: list[str] = []
    rows: list[dict] = []
    if isinstance(payload, list):
        rows = [r for r in payload if isinstance(r, dict)]
    elif isinstance(payload, dict):
        rows = [payload] if "matches" in payload else []

    for row in rows:
        matches = row.get("matches") or []
        for match in matches:
            if not isinstance(match, dict):
                continue
            conf = match.get("confidence_score") or match.get("confidence")
            if conf is not None and float(conf) < 0.9:
                continue
            data = match.get("company_data") or match
            basic = data.get("basic_info") or {}
            name = basic.get("name") or data.get("name")
            domain = basic.get("primary_domain") or data.get("primary_domain")
            if not domain and not name:
                continue
            label = name or next(
                (o for o in originals if o.lower() in json.dumps(row).lower()), None
            )
            if label and label not in kept:
                kept.append(str(label))
    if not kept:
        return [n for n in originals if re.search(r"[A-Za-z]", n)][:8]
    return kept[:8]
