"""Buyer finder: propose ICP, human gate, then lookalike company search."""

from __future__ import annotations

from collections import Counter
from typing import Any

from pydantic import BaseModel, Field

from app.agents.evidence import make_evidence
from app.agents.planner import set_plan_phase
from app.llm import get_llm
from app.models import BuyerRole, Company, ICPProposal, SellerBrief
from app.tools.crustdata import CrustdataClient, CrustdataError, client_for_campaign
from app.infra.events import EventBag

_DEFAULT_BUYER_TITLES = [
    "CTO",
    "VP Engineering",
    "VP of Engineering",
    "VP Infrastructure",
    "Head of Platform",
    "Head of Infrastructure",
    "Chief Technology Officer",
]


class _IcpDraft(BaseModel):
    industries: list[str] = Field(default_factory=list)
    countries: list[str] = Field(default_factory=list)
    employee_count_ranges: list[str] = Field(default_factory=list)
    funding_stages: list[str] = Field(default_factory=list)
    economic_buyer_titles: list[str] = Field(default_factory=list)
    champion_titles: list[str] = Field(default_factory=list)
    rationale: str = ""
    buyer_why: str = ""
    champion_why: str = ""


def buyer_propose_icp_node(state: dict[str, Any]) -> dict[str, Any]:
    """Enrich named customers, derive ICP, validate autocomplete. Does not search yet."""
    campaign_id = state["campaign_id"]
    seller = SellerBrief.model_validate(state["seller"])
    events = EventBag(state, "buyer_finder")
    errors = list(state.get("errors") or [])
    client = client_for_campaign(state)

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
            events.append(
                {
                    "type": "buyer.data_error",
                    "step": "buyer.customers_identify",
                    "detail": str(exc)[:200],
                }
            )

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
            events.append(
                {
                    "type": "buyer.data_error",
                    "step": "buyer.customers_enrich",
                    "detail": str(exc)[:200],
                }
            )

    industries = _top_values(customer_profiles, _industry)
    countries = _top_values(customer_profiles, _country)
    ranges = _top_values(customer_profiles, _employee_range)

    # Seller profile when customer enrich is empty
    seller_profile = (state.get("extras") or {}).get("seller_profile") or {}
    if not industries and seller_profile:
        industries = [_industry(seller_profile)] if _industry(seller_profile) else []
        countries = [_country(seller_profile)] if _country(seller_profile) else []
        ranges = [_employee_range(seller_profile)] if _employee_range(seller_profile) else []

    filters_fixed = bool(industries and countries and ranges)
    llm = get_llm("strong")
    if filters_fixed:
        prompt = (
            "You are a B2B sales strategist. Industries/countries/size are FIXED from customer "
            "evidence — copy them into the output and do not invent replacements.\n"
            "Propose who can APPROVE SPEND for this product (economic buyers: C-level, VP, Head, "
            "Director, Founder). Do NOT list Staff/Software/Platform Engineers as buyers.\n"
            "Champions are optional influencers only.\n"
            f"Seller: {seller.company_name} — {seller.one_liner}\n"
            f"Products: {seller.products}\nValue props: {seller.value_props}\n"
            f"Pricing: {seller.pricing_notes}\n"
            f"Named customers: {seller.named_customers}\n"
            f"Fixed industries: {industries}\nFixed countries: {countries}\n"
            f"Fixed size bands: {ranges}\n"
        )
    else:
        prompt = (
            "You are a B2B sales strategist. Derive a lookalike ICP from the product itself.\n"
            "Propose industries, countries, and employee_count_ranges suitable for Crustdata "
            "(use bands like 11-50, 51-200, 201-500, 501-1000, 1001-5000).\n"
            "Propose who can APPROVE SPEND (CTO, VP Engineering, VP Infrastructure, Head of "
            "Platform, etc.). Never list individual-contributor engineers as economic buyers.\n"
            f"Seller: {seller.company_name} — {seller.one_liner}\n"
            f"Products: {seller.products}\nValue props: {seller.value_props}\n"
            f"Pricing: {seller.pricing_notes}\n"
            f"Named customers (may be unverified): {seller.named_customers}\n"
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
            industries=industries or ["Technology, Information and Internet"],
            countries=countries or ["United States"],
            employee_count_ranges=ranges or ["51-200", "201-500", "501-1000"],
            economic_buyer_titles=list(_DEFAULT_BUYER_TITLES),
            champion_titles=["Engineering Manager", "Director of Engineering"],
            rationale="Fallback ICP from seller brief because structured LLM output failed.",
            buyer_why="Owns infrastructure and platform budget",
            champion_why="Evaluates day-to-day fit before the buyer signs",
        )

    if not filters_fixed:
        industries = list(draft.industries or industries) or ["Technology, Information and Internet"]
        countries = list(draft.countries or countries) or ["United States"]
        ranges = list(draft.employee_count_ranges or ranges) or ["51-200", "201-500", "501-1000"]

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

    low_conf = len(customer_profiles) < 3
    evidence = list(seller.evidence[:5])
    if low_conf:
        evidence.append(
            make_evidence(
                "ICP confidence lower: fewer than 3 enriched named-customer profiles",
                source_type="user_input",
                source_ref="seller_brief",
                confidence="low",
            )
        )

    buyer_titles = [
        t for t in (draft.economic_buyer_titles or _DEFAULT_BUYER_TITLES) if _is_buyer_title(t)
    ] or list(_DEFAULT_BUYER_TITLES)

    roles = [
        BuyerRole(
            title_variants=buyer_titles,
            kind="economic_buyer",
            why=draft.buyer_why or "Owns budget and vendor approval for this product",
        ),
    ]
    if draft.champion_titles:
        roles.append(
            BuyerRole(
                title_variants=draft.champion_titles,
                kind="champion",
                why=draft.champion_why or "Influences evaluation; not the default recipient",
            )
        )

    icp = ICPProposal(
        industries=industries,
        headcount_min=None,
        headcount_max=None,
        countries=countries,
        employee_count_ranges=ranges,
        funding_stages=draft.funding_stages or [],
        roles=roles,
        rationale=draft.rationale
        or (
            "ICP from enriched named customers"
            if customer_profiles
            else "ICP inferred from seller product brief"
        ),
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
            "source": "customers" if customer_profiles else "seller_product",
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
    """Auto-approve ICP and continue to paid company search (no human interrupt)."""
    from app.infra.events import set_stage

    icp_raw = dict(state.get("icp") or {})
    events = EventBag(state, "buyer_finder")
    if state.get("campaign_id"):
        set_stage(str(state["campaign_id"]), "icp", "done")

    icp = ICPProposal.model_validate(icp_raw)
    icp.approved = True
    events.append(
        {
            "type": "icp.auto_approved",
            "edited_by_user": False,
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
    events = EventBag(state, "buyer_finder")
    errors = list(state.get("errors") or [])
    extras = state.get("extras") or {}
    exclude = list(extras.get("exclude_domains") or [seller.domain])
    customer_domains = list(extras.get("customer_domains") or [])

    client = client_for_campaign(state)
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
            events.append(
                {
                    "type": "buyer.search_failed",
                    "step": "buyer.search_lookalike",
                    "detail": str(exc)[:200],
                }
            )

    # Strategy B: ranked hybrid search with the same hard filters.
    if len(rows) < n:
        body_b = {
            "filters": {"op": "and", "conditions": hard} if hard else None,
            "search": {"query": value_prop or "B2B software platform", "mode": "hybrid"},
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
            events.append(
                {
                    "type": "buyer.search_failed",
                    "step": "buyer.search",
                    "detail": str(exc)[:200],
                }
            )

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
            events.append(
                {
                    "type": "buyer.search_failed",
                    "step": "buyer.search_filters",
                    "detail": str(exc)[:200],
                }
            )

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


def _is_buyer_title(title: str) -> bool:
    """Keep budget owners; drop IC engineer titles."""
    t = (title or "").strip()
    if not t:
        return False
    tl = t.lower()
    if any(x in tl for x in ("cto", "ceo", "cio", "ciso", "cpo", "founder", "vp", "vice president", "head of", "director", "chief")):
        return True
    if "engineer" in tl or "developer" in tl:
        return False
    return True


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
