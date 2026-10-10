"""Buyer finder: propose ICP, human gate, then lookalike company search."""

from __future__ import annotations

from collections import Counter
from typing import Any

from langgraph.types import interrupt
from pydantic import BaseModel, Field

from app.agents.evidence import make_evidence
from app.agents.planner import set_plan_phase
from app.llm import get_llm
from app.models import BuyerRole, Company, ICPProposal, SellerBrief
from app.tools.crustdata import CrustdataClient, CrustdataError


class _IcpDraft(BaseModel):
    industries: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    employee_count_ranges: list[str] = Field(default_factory=list)
    funding_stages: list[str] = Field(default_factory=list)
    economic_buyer_titles: list[str] = Field(default_factory=list)
    champion_titles: list[str] = Field(default_factory=list)
    rationale: str = ""


def buyer_propose_icp_node(state: dict[str, Any]) -> dict[str, Any]:
    """Enrich named customers, derive ICP, validate autocomplete. Does not search yet."""
    campaign_id = state["campaign_id"]
    seller = SellerBrief.model_validate(state["seller"])
    events = list(state.get("events") or [])
    errors = list(state.get("errors") or [])
    client = CrustdataClient()

    customer_ids: list[int] = []
    if seller.named_customers:
        try:
            identified = client.company_identify(
                {"names": seller.named_customers[:25]},
                campaign_id=campaign_id,
                step="buyer.customers_identify",
            )
            customer_ids = _collect_ids(identified)
        except CrustdataError as exc:
            errors.append({"step": "buyer.customers_identify", "error": str(exc)})

    customer_profiles: list[dict] = []
    if customer_ids:
        try:
            enriched = client.company_enrich(
                {
                    "crustdata_company_ids": customer_ids[:25],
                    "fields": ["basic_info", "taxonomy", "headcount", "locations", "funding"],
                },
                campaign_id=campaign_id,
                step="buyer.customers_enrich",
            )
            customer_profiles = _collect_company_data(enriched)
        except CrustdataError as exc:
            errors.append({"step": "buyer.customers_enrich", "error": str(exc)})

    industries = _top_values(customer_profiles, _industry) or ["Software Development"]
    countries = _top_values(customer_profiles, _country) or ["United States"]
    ranges = _top_values(customer_profiles, _employee_range) or ["51-200", "201-500"]

    llm = get_llm("strong")
    prompt = (
        "Propose buyer roles and a short rationale only. Do NOT invent new industries/countries/"
        "size bands; those are fixed from customer evidence.\n"
        f"Seller: {seller.company_name} — {seller.one_liner}\n"
        f"Products: {seller.products}\nValue props: {seller.value_props}\n"
        f"Named customers: {seller.named_customers}\n"
        f"Fixed industries: {industries}\nFixed countries: {countries}\nFixed size bands: {ranges}\n"
    )
    try:
        draft = llm.with_structured_output(_IcpDraft).invoke(prompt)
        if not isinstance(draft, _IcpDraft):
            draft = _IcpDraft.model_validate(draft)
    except Exception as exc:  # noqa: BLE001
        errors.append({"step": "buyer.icp_llm", "error": str(exc)})
        if "llm_bad_json" in str(exc):
            events.append({"type": "recovery.llm_bad_json", "step": "buyer_propose_icp"})
        draft = _IcpDraft(
            economic_buyer_titles=["VP Engineering", "CTO", "Head of Product"],
            champion_titles=["Engineering Manager", "Product Manager"],
            rationale="Fallback roles because structured LLM output failed.",
        )

    industries = _validate_autocomplete(client, "basic_info.industries", industries, campaign_id)
    countries = _validate_autocomplete(client, "locations.country", countries, campaign_id)
    ranges = _validate_autocomplete(
        client,
        "basic_info.employee_count_range",
        ranges,
        campaign_id,
    )

    # Acceptance helper: force a thin ICP so planner must emit replan.widen_icp.
    if (state.get("input") or {}).get("narrow_icp"):
        industries = industries[:1] or ["Computer Games"]
        countries = countries[:1] or ["Iceland"]
        ranges = ranges[:1] or ["10001+"]
        events.append(
            {
                "type": "buyer.narrow_icp",
                "industries": industries,
                "countries": countries,
                "employee_count_ranges": ranges,
            }
        )

    low_conf = len(seller.named_customers) < 3
    evidence = list(seller.evidence[:5])
    if low_conf:
        evidence.append(
            make_evidence(
                "ICP confidence low: fewer than 3 named customers on seller site",
                source_type="user_input",
                source_ref="seller_brief",
                confidence="low",
            )
        )

    roles = [
        BuyerRole(
            title_variants=draft.economic_buyer_titles
            or ["VP Engineering", "CTO", "Chief Technology Officer"],
            kind="economic_buyer",
            why="Owns tooling budget and platform outcomes",
        ),
        BuyerRole(
            title_variants=draft.champion_titles or ["Engineering Manager", "Product Manager"],
            kind="champion",
            why="Feels day-to-day product analytics / engineering pain",
        ),
    ]

    icp = ICPProposal(
        industries=industries or ["Software Development"],
        headcount_min=None,
        headcount_max=None,
        countries=countries or ["United States"],
        employee_count_ranges=ranges or ["51-200", "201-500"],
        funding_stages=draft.funding_stages or [],
        roles=roles,
        rationale=draft.rationale or "ICP derived from named customer enrich",
        evidence=evidence,
        approved=False,
        edited_by_user=False,
    )

    exclude = [seller.domain] + _customer_domains(customer_profiles)
    extras = dict(state.get("extras") or {})
    extras["exclude_domains"] = exclude
    extras["customer_domains"] = _customer_domains(customer_profiles)

    events.append(
        {
            "type": "buyer.icp_proposed",
            "industries": icp.industries,
            "countries": icp.countries,
            "employee_count_ranges": icp.employee_count_ranges,
            "low_confidence_icp": low_conf,
            "customer_profiles": len(customer_profiles),
        }
    )
    spent = client.ledger.spent(campaign_id)
    client.close()
    return {
        "icp": icp.model_dump(mode="json"),
        "extras": extras,
        "events": events,
        "errors": errors,
        "budget": {"credits_spent": spent},
        "plan": set_plan_phase(state, "after_icp_proposed"),
    }


def icp_gate_node(state: dict[str, Any]) -> dict[str, Any]:
    """Human gate 1: interrupt with ICP, roles, and customer evidence; resume approves/edits."""
    icp_raw = dict(state.get("icp") or {})
    events = list(state.get("events") or [])
    payload = {
        "type": "icp_approval",
        "campaign_id": state.get("campaign_id"),
        "icp": icp_raw,
        "roles": icp_raw.get("roles") or [],
        "evidence": icp_raw.get("evidence") or [],
        "message": "Approve or edit the ICP before paid company search.",
    }
    decision = interrupt(payload)
    if not isinstance(decision, dict):
        decision = {"approved": bool(decision)}

    approved = bool(decision.get("approved", True))
    edited = decision.get("icp")
    if isinstance(edited, dict):
        merged = {**icp_raw, **edited}
        icp = ICPProposal.model_validate(merged)
        icp.edited_by_user = True
    else:
        icp = ICPProposal.model_validate(icp_raw)

    icp.approved = approved
    if not approved:
        events.append({"type": "icp.rejected", "by": "human"})
        return {
            "icp": icp.model_dump(mode="json"),
            "events": events,
            "halt_reason": "icp_rejected",
            "plan": set_plan_phase(state, "done"),
        }

    events.append(
        {
            "type": "icp.approved",
            "edited_by_user": icp.edited_by_user,
            "industries": icp.industries,
            "countries": icp.countries,
        }
    )
    return {
        "icp": icp.model_dump(mode="json"),
        "events": events,
        "plan": set_plan_phase(state, "after_icp_approved"),
    }


def buyer_search_node(state: dict[str, Any]) -> dict[str, Any]:
    """Search lookalikes with approved ICP; overfetch 3xN; score; keep top N."""
    campaign_id = state["campaign_id"]
    n = int(state["input"].get("n") or 10)
    seller = SellerBrief.model_validate(state["seller"])
    icp = ICPProposal.model_validate(state["icp"])
    events = list(state.get("events") or [])
    errors = list(state.get("errors") or [])
    extras = state.get("extras") or {}
    exclude = list(extras.get("exclude_domains") or [seller.domain])
    customer_domains = list(extras.get("customer_domains") or [])

    client = CrustdataClient()
    stable_query = (
        (state.get("input") or {}).get("description")
        or seller.one_liner
        or seller.company_name
    )
    ranges = list(icp.employee_count_ranges or [])
    companies = _search_companies(
        client,
        icp=icp,
        ranges=ranges,
        exclude_domains=exclude,
        customer_domains=customer_domains,
        value_prop=stable_query,
        n=n,
        campaign_id=campaign_id,
        events=events,
        errors=errors,
    )

    companies = sorted(companies, key=lambda c: c.fit_score, reverse=True)
    kept: list[Company] = []
    buffer: list[Company] = []
    for idx, company in enumerate(companies):
        if idx < n:
            company.status = "kept"
            kept.append(company)
        else:
            company.status = "dropped"
            company.drop_reason = "below_top_n"
            buffer.append(company)

    # Keep overfetch buffer (up to 2xN extra) so planner can replace no_contact drops.
    pool = kept + buffer[: max(n * 2, n)]
    events.append(
        {
            "type": "buyer.kept",
            "count": len(kept),
            "pool": len(pool),
            "buffer": len(buffer[: max(n * 2, n)]),
            "n": n,
        }
    )
    spent = client.ledger.spent(campaign_id)
    client.close()
    return {
        "companies": [c.model_dump(mode="json") for c in pool],
        "events": events,
        "errors": errors,
        "budget": {"credits_spent": spent},
        "plan": set_plan_phase(state, "after_search"),
    }


# Backward-compatible name used by older imports / docs.
def buyer_finder_node(state: dict[str, Any]) -> dict[str, Any]:
    """Legacy single-shot path (propose + auto-approve + search). Prefer split nodes."""
    proposed = buyer_propose_icp_node(state)
    merged = {**state, **proposed}
    icp = dict(proposed.get("icp") or {})
    icp["approved"] = True
    merged["icp"] = icp
    searched = buyer_search_node(merged)
    return {
        **proposed,
        **searched,
        "icp": icp,
        "plan": set_plan_phase(merged, "after_search"),
    }


def _validate_autocomplete(
    client: CrustdataClient,
    field: str,
    values: list[str],
    campaign_id: str,
) -> list[str]:
    out: list[str] = []
    for value in values[:5]:
        try:
            result = client.company_autocomplete(
                {"field": field, "query": value, "limit": 5},
                campaign_id=campaign_id,
                step="buyer.autocomplete",
            )
            suggestions = _autocomplete_values(result)
            if suggestions:
                out.append(suggestions[0])
            else:
                out.append(value)
        except CrustdataError:
            out.append(value)
    seen: set[str] = set()
    unique: list[str] = []
    for item in out:
        if item not in seen:
            seen.add(item)
            unique.append(item)
    return unique


def _search_companies(
    client: CrustdataClient,
    *,
    icp: ICPProposal,
    ranges: list[str],
    exclude_domains: list[str],
    customer_domains: list[str],
    value_prop: str,
    n: int,
    campaign_id: str,
    events: list[dict],
    errors: list[dict],
) -> list[Company]:
    hard: list[dict] = []
    if icp.industries:
        hard.append({"field": "basic_info.industries", "type": "in", "value": icp.industries[:5]})
    if icp.countries:
        hard.append({"field": "locations.country", "type": "in", "value": icp.countries[:5]})
    if ranges:
        hard.append({"field": "basic_info.employee_count_range", "type": "in", "value": ranges[:5]})
    if exclude_domains:
        hard.append(
            {
                "field": "basic_info.primary_domain",
                "type": "not_in",
                "value": exclude_domains[:50],
            }
        )

    fields = [
        "crustdata_company_id",
        "basic_info.name",
        "basic_info.primary_domain",
        "basic_info.employee_count_range",
        "locations.country",
    ]
    limit = max(n * 3, n)
    rows: list[dict] = []
    strategy_used = "none"

    # Strategy A: companies that list our customers as competitors.
    if customer_domains:
        body_a = {
            "filters": {
                "op": "and",
                "conditions": hard
                + [
                    {
                        "field": "competitors.websites",
                        "type": "in",
                        "value": customer_domains[:10],
                    }
                ],
            },
            "fields": fields,
            "limit": min(limit, 100),
            "sorts": [{"field": "basic_info.name", "order": "asc"}],
        }
        try:
            result = client.company_search(body_a, campaign_id=campaign_id, step="buyer.search_lookalike")
            rows = _company_rows(result)
            strategy_used = "competitors"
            events.append({"type": "buyer.search", "strategy": strategy_used, "count": len(rows)})
        except CrustdataError as exc:
            errors.append({"step": "buyer.search_lookalike", "error": str(exc)})

    # Strategy B: ranked hybrid search with the same hard filters.
    if len(rows) < n:
        body_b = {
            "filters": {"op": "and", "conditions": hard} if hard else None,
            "search": {"query": value_prop or "B2B software analytics", "mode": "hybrid"},
            "fields": fields,
            "limit": min(limit, 100),
        }
        body_b = {k: v for k, v in body_b.items() if v is not None}
        try:
            result = client.company_search(body_b, campaign_id=campaign_id, step="buyer.search")
            rows = _company_rows(result)
            strategy_used = "ranked"
            events.append({"type": "buyer.search", "strategy": strategy_used, "count": len(rows)})
        except CrustdataError as exc:
            errors.append({"step": "buyer.search", "error": str(exc)})

    if len(rows) < n and hard:
        try:
            result = client.company_search(
                {
                    "filters": {"op": "and", "conditions": hard},
                    "fields": fields,
                    "limit": min(limit, 100),
                    "sorts": [{"field": "basic_info.name", "order": "asc"}],
                },
                campaign_id=campaign_id,
                step="buyer.search_filters",
            )
            rows = _company_rows(result)
            strategy_used = "filters"
            events.append({"type": "buyer.search", "strategy": strategy_used, "count": len(rows)})
        except CrustdataError as exc:
            errors.append({"step": "buyer.search_filters", "error": str(exc)})

    companies: list[Company] = []
    for row in rows:
        basic = row.get("basic_info") or {}
        cid = str(row.get("crustdata_company_id") or basic.get("primary_domain") or basic.get("name"))
        industry = None
        inds = basic.get("industries") or row.get("industries")
        if isinstance(inds, list) and inds:
            industry = str(inds[0])
        country = None
        locs = row.get("locations") or {}
        if isinstance(locs, dict):
            country = locs.get("country")
        elif isinstance(locs, list) and locs:
            country = locs[0].get("country") if isinstance(locs[0], dict) else None
        size = basic.get("employee_count_range")
        score = 0.0
        reasons = []
        if industry and industry in icp.industries:
            score += 0.35
            reasons.append("industry_match")
        if country and country in icp.countries:
            score += 0.25
            reasons.append("country_match")
        if size and size in ranges:
            score += 0.25
            reasons.append("size_match")
        if strategy_used == "competitors":
            score += 0.15
            reasons.append("lookalike_competitors")
        elif strategy_used == "ranked":
            score += 0.1
            reasons.append("lookalike_ranked")
        companies.append(
            Company(
                id=cid,
                name=str(basic.get("name") or cid),
                domain=str(basic.get("primary_domain") or ""),
                industry=industry,
                headcount=None,
                country=country if isinstance(country, str) else None,
                fit_score=min(score, 1.0),
                fit_reasons=reasons,
                status="candidate",
            )
        )
    return companies


def _autocomplete_values(payload: Any) -> list[str]:
    if isinstance(payload, list):
        out = []
        for item in payload:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                out.append(str(item.get("value") or item.get("name") or item.get("label") or ""))
        return [x for x in out if x]
    if isinstance(payload, dict):
        for key in ("results", "suggestions", "values", "data"):
            if key in payload:
                return _autocomplete_values(payload[key])
    return []


def _collect_ids(payload: Any) -> list[int]:
    ids: list[int] = []
    for data in _collect_company_data(payload):
        cid = data.get("crustdata_company_id") or (data.get("basic_info") or {}).get(
            "crustdata_company_id"
        )
        if cid is None:
            continue
        try:
            ids.append(int(cid))
        except (TypeError, ValueError):
            continue
    return ids[:25]


def _collect_company_data(payload: Any) -> list[dict]:
    out: list[dict] = []
    rows: list[dict] = []
    if isinstance(payload, list):
        rows = [r for r in payload if isinstance(r, dict)]
    elif isinstance(payload, dict):
        rows = [payload] if "matches" in payload else [
            r for r in (payload.get("companies") or payload.get("results") or []) if isinstance(r, dict)
        ]
    for item in rows:
        matches = item.get("matches") or []
        if matches and isinstance(matches[0], dict):
            out.append(matches[0].get("company_data") or matches[0])
        elif "basic_info" in item or "crustdata_company_id" in item:
            out.append(item)
    return out


def _company_rows(payload: Any) -> list[dict]:
    if isinstance(payload, dict):
        rows = payload.get("companies") or payload.get("results") or []
        return [r for r in rows if isinstance(r, dict)]
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    return []


def _industry(data: dict) -> str | None:
    tax = data.get("taxonomy") or {}
    basic = data.get("basic_info") or {}
    inds = basic.get("industries") or tax.get("professional_network_industries") or []
    if isinstance(inds, list) and inds:
        return str(inds[0])
    return None


def _country(data: dict) -> str | None:
    locs = data.get("locations") or {}
    if isinstance(locs, dict) and locs.get("country"):
        return str(locs["country"])
    if isinstance(locs, list) and locs and isinstance(locs[0], dict):
        return locs[0].get("country")
    return None


def _employee_range(data: dict) -> str | None:
    basic = data.get("basic_info") or {}
    return basic.get("employee_count_range")


def _top_values(profiles: list[dict], getter, k: int = 3) -> list[str]:
    counter: Counter[str] = Counter()
    for profile in profiles:
        value = getter(profile)
        if value:
            counter[str(value)] += 1
    return [name for name, _ in counter.most_common(k)]


def _customer_domains(profiles: list[dict]) -> list[str]:
    out = []
    for profile in profiles:
        basic = profile.get("basic_info") or {}
        domain = basic.get("primary_domain")
        if domain:
            out.append(str(domain))
    return out
