"""Account researcher: per-company story and contacts (v0: sequential, person search only)."""

from __future__ import annotations

import re
from typing import Any

from app.agents.evidence import make_evidence
from app.llm import get_llm
from app.models import AccountBrief, Company, Contact, ICPProposal
from app.tools.crustdata import CrustdataClient, CrustdataError


def account_researcher_node(state: dict[str, Any]) -> dict[str, Any]:
    """v0: batch enrich kept companies, then sequential person search (no full fallback chain)."""
    campaign_id = state["campaign_id"]
    companies = [Company.model_validate(c) for c in (state.get("companies") or [])]
    icp = ICPProposal.model_validate(state["icp"])
    events = list(state.get("events") or [])
    errors = list(state.get("errors") or [])
    client = CrustdataClient()

    kept = [c for c in companies if c.status == "kept"]
    ids: list[int] = []
    for company in kept:
        try:
            ids.append(int(company.id))
        except ValueError:
            continue

    enrich_by_id: dict[str, dict] = {}
    if ids:
        try:
            enriched = client.company_enrich(
                {
                    "crustdata_company_ids": ids[:25],
                    "fields": ["basic_info", "headcount", "funding", "people", "news", "hiring"],
                },
                campaign_id=campaign_id,
                step="account.enrich",
            )
            enrich_by_id = _index_enrich(enriched)
            events.append({"type": "account.enriched", "count": len(enrich_by_id)})
        except CrustdataError as exc:
            errors.append({"step": "account.enrich", "error": str(exc)})

    titles = []
    for role in icp.roles:
        titles.extend(role.title_variants)
    titles = titles or ["CTO", "VP Engineering", "Head of Product"]

    accounts: dict[str, Any] = {}
    contacts: list[dict] = []

    for company in kept:
        data = enrich_by_id.get(str(company.id), {})
        evidence = [
            make_evidence(
                f"{company.name} is a fit candidate ({company.domain})",
                source_type="crustdata",
                source_ref=f"crustdata:/company/search:{company.id}",
                confidence="medium",
            )
        ]
        news = (data.get("news") or {}) if data else {}
        articles = []
        if isinstance(news, dict):
            articles = news.get("articles") or news.get("items") or []
        if isinstance(news, list):
            articles = news
        why_now: list[str] = []
        for article in articles[:3]:
            if not isinstance(article, dict):
                continue
            title = article.get("article_title") or article.get("title") or "Recent news"
            url = article.get("article_url") or article.get("url") or f"crustdata:/company/enrich:news"
            card = make_evidence(
                str(title)[:200],
                source_type="crustdata",
                source_ref=str(url),
                confidence="medium",
            )
            evidence.append(card)
            why_now.append(f"{title} [{card.id}]")

        if not why_now:
            why_now = [f"Active lookalike of seller ICP [{evidence[0].id}]"]

        story = _story(company, evidence, get_llm("fast"))
        brief = AccountBrief(
            company_id=company.id,
            story=story,
            why_now=why_now,
            evidence=evidence,
        )
        accounts[company.id] = brief.model_dump(mode="json")

        contact = _find_contact_v0(
            client,
            company=company,
            data=data,
            titles=titles,
            campaign_id=campaign_id,
            events=events,
            errors=errors,
        )
        if contact:
            contacts.append(contact.model_dump(mode="json"))
        else:
            events.append({"type": "account.no_contact", "company_id": company.id})

    spent = client.ledger.spent(campaign_id)
    client.close()
    return {
        "accounts": accounts,
        "contacts": contacts,
        "events": events,
        "errors": errors,
        "budget": {"credits_spent": spent},
    }


def _story(company: Company, evidence: list, llm) -> str:
    prompt = (
        "Write 3 short sentences about why this company might buy. "
        "Only use the facts below; cite evidence ids in parentheses.\n"
        f"Company: {company.name} ({company.domain})\n"
        f"Facts: {[e.fact + ' [' + e.id + ']' for e in evidence]}"
    )
    try:
        result = llm.invoke(prompt)
        text = getattr(result, "content", str(result))
        if isinstance(text, list):
            text = " ".join(str(part) for part in text)
        return str(text)[:800]
    except Exception:  # noqa: BLE001
        eid = evidence[0].id if evidence else "ev_none"
        return (
            f"{company.name} matches the seller ICP ({eid}). "
            f"They operate in {company.industry or 'a related industry'} ({eid}). "
            f"Worth a first outreach based on fit score {company.fit_score:.2f} ({eid})."
        )


def _find_contact_v0(
    client: CrustdataClient,
    *,
    company: Company,
    data: dict,
    titles: list[str],
    campaign_id: str,
    events: list[dict],
    errors: list[dict],
) -> Contact | None:
    # v0 naive: try enrich people first, else one person/search (no explain/fallback chain)
    people = data.get("people") or {}
    candidates = []
    if isinstance(people, dict):
        for key in ("decision_makers", "cxos", "founders"):
            block = people.get(key) or []
            if isinstance(block, list):
                candidates.extend([p for p in block if isinstance(p, dict)])

    picked = _pick_by_title(candidates, titles)
    profile_url = None
    name = None
    title = None
    if picked:
        name = picked.get("name") or picked.get("full_name")
        title = picked.get("title") or picked.get("current_title") or "Leader"
        profile_url = (
            picked.get("profile_url")
            or picked.get("linkedin_profile_url")
            or picked.get("professional_network_url")
        )
        events.append({"type": "account.contact_from_people", "company_id": company.id})

    if not profile_url:
        try:
            company_id_int = int(company.id)
        except ValueError:
            return None
        title_conditions = [
            {
                "field": "experience.employment_details.current.title",
                "type": "[.]",
                "value": t,
            }
            for t in titles[:6]
        ]
        body = {
            "filters": {
                "op": "and",
                "conditions": [
                    {
                        "field": "experience.employment_details.current.company_id",
                        "type": "=",
                        "value": company_id_int,
                    },
                    {
                        "field": "experience.employment_details.current.is_default",
                        "type": "=",
                        "value": True,
                    },
                    {"op": "or", "conditions": title_conditions},
                    {"field": "contact.has_business_email", "type": "=", "value": True},
                ],
            },
            "fields": [
                "crustdata_person_id",
                "basic_profile.name",
                "basic_profile.current_title",
                "social_handles.professional_network_identifier.profile_url",
                "contact.has_business_email",
            ],
            "limit": 5,
        }
        try:
            result = client.person_search(body, campaign_id=campaign_id, step="account.person_search")
            profiles = result.get("profiles") if isinstance(result, dict) else []
            if profiles:
                person = profiles[0]
                basic = person.get("basic_profile") or {}
                name = basic.get("name") or person.get("name")
                title = basic.get("current_title") or person.get("title") or titles[0]
                social = person.get("social_handles") or {}
                pn = social.get("professional_network_identifier") or {}
                profile_url = pn.get("profile_url") or person.get("profile_url")
                events.append({"type": "account.contact_from_search", "company_id": company.id})
        except CrustdataError as exc:
            errors.append({"step": "account.person_search", "error": str(exc), "company_id": company.id})
            return None

    if not name:
        return None

    email = None
    email_source = "none"
    email_confidence = "none"
    if profile_url:
        try:
            enriched = client.person_enrich(
                {
                    "professional_network_profile_urls": [profile_url],
                    "fields": ["basic_profile", "experience", "contact.business_emails"],
                },
                campaign_id=campaign_id,
                step="account.person_enrich",
            )
            email = _extract_email(enriched)
            if email:
                email_source = "crustdata"
                email_confidence = "likely"
        except CrustdataError as exc:
            errors.append({"step": "account.person_enrich", "error": str(exc)})

    contact_id = f"{company.id}:{_slug(name)}"
    return Contact(
        id=contact_id,
        company_id=company.id,
        name=str(name),
        title=str(title or "Leader"),
        role_kind="economic_buyer",
        email=email,
        email_source=email_source,  # type: ignore[arg-type]
        email_confidence=email_confidence,  # type: ignore[arg-type]
        profile_url=profile_url,
    )


def _pick_by_title(people: list[dict], titles: list[str]) -> dict | None:
    lowered = [t.lower() for t in titles]

    def score(person: dict) -> int:
        title = str(person.get("title") or person.get("current_title") or "").lower()
        return sum(1 for t in lowered if t in title)

    ranked = sorted(people, key=score, reverse=True)
    if ranked and score(ranked[0]) > 0:
        return ranked[0]
    return ranked[0] if ranked else None


def _index_enrich(payload: Any) -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not isinstance(payload, list):
        return out
    for item in payload:
        if not isinstance(item, dict):
            continue
        matches = item.get("matches") or []
        if not matches:
            continue
        data = matches[0].get("company_data") or matches[0]
        cid = data.get("crustdata_company_id") or (data.get("basic_info") or {}).get("company_id")
        if cid is not None:
            out[str(cid)] = data
    return out


def _extract_email(payload: Any) -> str | None:
    text = str(payload)
    match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    return match.group(0) if match else None


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40]
