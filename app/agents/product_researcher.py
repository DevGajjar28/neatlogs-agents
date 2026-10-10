"""Product researcher: seller brief and evidence cards from the seller site."""

from __future__ import annotations

import json
import re
from typing import Any
from pydantic import BaseModel, Field

from app.agents.evidence import make_evidence
from app.llm import get_llm
from app.models import SellerBrief
from app.tools import web
from app.tools.crustdata import CrustdataClient, CrustdataError
from app.infra.events import EventBag


class _ExtractedSeller(BaseModel):
    one_liner: str = ""
    products: list[str] = Field(default_factory=list)
    value_props: list[str] = Field(default_factory=list)
    pricing_notes: str | None = None
    named_customers: list[str] = Field(default_factory=list)


def _domain(website: str) -> str:
    return web.domain_of(website)


def product_researcher_node(state: dict[str, Any]) -> dict[str, Any]:
    """v0: fetch site, identify/enrich seller, LLM extract into SellerBrief."""
    inp = state["input"]
    campaign_id = state["campaign_id"]
    company_name = inp["company_name"]
    website = inp["website"]
    description = inp.get("description") or ""
    events = EventBag(state, "product_researcher")
    errors = list(state.get("errors") or [])

    client = CrustdataClient()
    domain = _domain(website)
    evidence = []
    pages = web.fetch_seller_pages(website)
    page_blob = "\n\n".join(f"URL: {p['url']}\n{p['text'][:3000]}" for p in pages)[:14000]

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

    seller_id = None
    try:
        identified = client.company_identify(
            {"domains": [domain]},
            campaign_id=campaign_id,
            step="product.identify",
        )
        # response shapes vary; try common paths
        seller_id = _first_company_id(identified)
        if seller_id:
            enriched = client.company_enrich(
                {
                    "crustdata_company_ids": [seller_id],
                    "fields": [
                        "basic_info",
                        "taxonomy",
                        "headcount",
                        "funding",
                        "locations",
                        "competitors",
                    ],
                },
                campaign_id=campaign_id,
                step="product.enrich",
            )
            company_data = _first_company_data(enriched)
            if company_data:
                name = (company_data.get("basic_info") or {}).get("name") or company_name
                evidence.append(
                    make_evidence(
                        f"Crustdata profile for {name} ({domain})",
                        source_type="crustdata",
                        source_ref=f"crustdata:/company/enrich:basic_info",
                        confidence="high",
                    )
                )
    except CrustdataError as exc:
        errors.append({"step": "product_researcher", "error": str(exc)})
        events.append({"type": "error", "step": "product_researcher", "detail": str(exc)})

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
    except Exception as exc:  # noqa: BLE001 — v0 soft-fail to heuristics
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

    # identify customer names (free)
    if named:
        try:
            cust_ids = client.company_identify(
                {"names": named[:25]},
                campaign_id=campaign_id,
                step="product.customers_identify",
            )
            kept_names = _confident_customer_names(cust_ids, named)
            if kept_names:
                named = kept_names
                events.append(
                    {
                        "type": "product.customers_identified",
                        "count": len(kept_names),
                    }
                )
        except CrustdataError as exc:
            errors.append({"step": "product.customers_identify", "error": str(exc)})

    if not named:
        events.append({"type": "product.no_customers", "detail": "buyer_finder will use low-confidence ICP"})

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
    spent = client.ledger.spent(campaign_id)
    client.close()
    return {
        "seller": brief.model_dump(mode="json"),
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
    rows: list[dict] = []
    if isinstance(payload, list):
        rows = [r for r in payload if isinstance(r, dict)]
    elif isinstance(payload, dict):
        if "matches" in payload:
            rows = [payload]
        else:
            rows = [r for r in (payload.get("companies") or payload.get("results") or []) if isinstance(r, dict)]
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
            label = name or next((o for o in originals if o.lower() in json.dumps(row).lower()), None)
            if label and label not in kept:
                kept.append(str(label))
    if not kept:
        return [n for n in originals if re.search(r"[A-Za-z]", n)][:8]
    return kept[:8]
