"""Company CSV parser and provided-list planner routing."""

from __future__ import annotations

from app.agents.buyer_finder import buyer_import_node
from app.agents.planner import planner_node
from app.infra.company_list import normalize_domain, parse_companies_csv, validate_provided_companies
from app.infra.event_messages import format_message


def test_normalize_domain_strips_scheme_www_path():
    assert normalize_domain("https://www.Acme.com/about?x=1") == "acme.com"
    assert normalize_domain("acme.com") == "acme.com"
    assert normalize_domain("not a domain") is None


def test_parse_headerless_single_line():
    """Paste like 'Mindarmor, https://mindarmor.ai' must not swallow the row as headers."""
    out = parse_companies_csv("Mindarmor, https://mindarmor.ai")
    assert out["ok_count"] == 1
    assert out["rows"][0]["name"] == "Mindarmor"
    assert out["rows"][0]["domain"] == "mindarmor.ai"
    assert out["rows"][0]["status"] == "ok"


def test_parse_headerless_multi_line():
    csv = "Acme, https://acme.com\nBeta Inc, beta.example.com, notes here\n"
    out = parse_companies_csv(csv)
    assert out["ok_count"] == 2
    assert out["rows"][0]["domain"] == "acme.com"
    assert out["rows"][1]["description"] == "notes here"


def test_parse_header_variants_and_bom():
    csv = "\ufeffCompany Name,URL,Notes\nAcme,https://acme.com,Hello\n"
    out = parse_companies_csv(csv)
    assert out["ok_count"] == 1
    assert out["rows"][0]["domain"] == "acme.com"
    assert out["rows"][0]["status"] == "ok"


def test_parse_quotes_duplicates_bad_urls():
    csv = (
        "company_name,website,description\n"
        '"Acme, Inc.",https://acme.com,"A ""quoted"" note"\n'
        "Dup,acme.com,\n"
        "Bad,,missing\n"
        "NoName,,\n"
        ",https://orphan.com,\n"
    )
    out = parse_companies_csv(csv)
    statuses = [r["status"] for r in out["rows"]]
    assert "ok" in statuses
    assert "duplicate_domain" in statuses
    assert "bad_website" in statuses
    assert "missing_name" in statuses
    assert out["ok_count"] == 1


def test_parse_max_50_rows():
    lines = ["company_name,website"]
    for i in range(52):
        lines.append(f"Co{i},co{i}.example.com")
    out = parse_companies_csv("\n".join(lines))
    assert out["ok_count"] == 50
    assert any(r["status"] == "too_many" for r in out["rows"])


def test_validate_provided_companies():
    rows = validate_provided_companies(
        [{"name": "Acme", "domain": "https://www.acme.com/x", "description": "x" * 400}]
    )
    assert rows[0]["domain"] == "acme.com"
    assert len(rows[0]["description"]) == 300


def test_planner_routes_to_buyer_import_when_provided(monkeypatch):
    monkeypatch.setenv("MAX_CREDITS", "400")
    from app.config import clear_settings_cache

    clear_settings_cache()
    # After product: skip ICP entirely for provided lists.
    out = planner_node(
        {
            "campaign_id": "prov-1",
            "input": {
                "n": 3,
                "target_mode": "provided",
                "provided_companies": [
                    {"name": "A", "domain": "a.example.com", "description": ""},
                ],
            },
            "plan": {
                "initialized": True,
                "phase": "after_product",
                "target_mode": "provided",
                "max_widenings": 0,
            },
            "budget": {"credits_spent": 0},
            "seller": {"company_name": "S"},
            "events": [],
        }
    )
    assert out["plan"]["next"] == "buyer_import"
    assert out["plan"]["phase"] == "searching"


def test_planner_provided_init_skips_icp_steps(monkeypatch):
    monkeypatch.setenv("MAX_CREDITS", "400")
    from app.config import clear_settings_cache

    clear_settings_cache()
    out = planner_node(
        {
            "campaign_id": "prov-init",
            "input": {"n": 2, "target_mode": "provided"},
            "plan": {},
            "budget": {"credits_spent": 0},
            "events": [],
        }
    )
    steps = out["plan"]["steps"]
    assert "buyer_import" in steps
    assert "buyer_propose_icp" not in steps
    assert "icp_gate" not in steps


def test_planner_provided_skips_widen(monkeypatch):
    monkeypatch.setenv("MAX_CREDITS", "400")
    from app.config import clear_settings_cache

    clear_settings_cache()
    out = planner_node(
        {
            "campaign_id": "prov-2",
            "input": {"n": 5, "target_mode": "provided"},
            "plan": {
                "initialized": True,
                "phase": "after_search",
                "widenings": 0,
                "max_widenings": 0,
                "target_mode": "provided",
            },
            "budget": {"credits_spent": 0},
            "companies": [{"status": "kept", "id": "1"}],
            "events": [],
        }
    )
    assert out["plan"]["next"] == "account_researcher"
    assert not any(e.get("type") == "replan.widen_icp" for e in out["events"])


def test_buyer_import_not_found_never_kept(monkeypatch):
    class _FakeClient:
        class ledger:
            @staticmethod
            def spent(_cid):
                return 0.0

        def company_identify(self, body, **kwargs):
            return [{"matched_on": d, "matches": []} for d in body.get("domains") or []]

        def close(self):
            pass

    monkeypatch.setattr(
        "app.agents.buyer_finder.client_for_campaign",
        lambda _state: _FakeClient(),
    )
    state = {
        "campaign_id": "imp-1",
        "input": {
            "n": 2,
            "target_mode": "provided",
            "provided_companies": [
                {"name": "Missing Co", "domain": "missing.example.com", "description": "note"},
            ],
        },
        "companies": [],
        "events": [],
        "errors": [],
        "extras": {},
        "budget": {"credits_spent": 0},
        "plan": {},
    }
    out = buyer_import_node(state)
    kept = [c for c in out["companies"] if c.get("status") == "kept"]
    assert kept == []
    types = [e["type"] for e in out["events"] if isinstance(e, dict)]
    assert "buyers.import_not_found" in types
    assert out["extras"]["import_not_found"]


def test_buyer_import_matched_uses_identify(monkeypatch):
    class _FakeClient:
        class ledger:
            @staticmethod
            def spent(_cid):
                return 0.0

        def company_identify(self, body, **kwargs):
            return [
                {
                    "matched_on": "acme.com",
                    "matches": [
                        {
                            "confidence_score": 0.99,
                            "company_data": {
                                "crustdata_company_id": 42,
                                "basic_info": {
                                    "name": "Acme",
                                    "primary_domain": "acme.com",
                                    "industries": ["Software"],
                                },
                            },
                        }
                    ],
                }
            ]

        def close(self):
            pass

    monkeypatch.setattr(
        "app.agents.buyer_finder.client_for_campaign",
        lambda _state: _FakeClient(),
    )
    out = buyer_import_node(
        {
            "campaign_id": "imp-2",
            "input": {
                "n": 1,
                "provided_companies": [
                    {"name": "Acme", "domain": "acme.com", "description": "user note"},
                ],
            },
            "companies": [],
            "events": [],
            "errors": [],
            "extras": {},
            "budget": {"credits_spent": 0},
            "plan": {},
        }
    )
    kept = [c for c in out["companies"] if c.get("status") == "kept"]
    assert len(kept) == 1
    assert kept[0]["id"] == "42"
    assert "user_list" in kept[0]["fit_reasons"]
    assert out["extras"]["user_list_context"]["42"]["description"] == "user note"


def test_import_event_messages():
    assert "instead of searching" in format_message("buyers.import_started", {"n": 5})
    assert "Acme" in format_message(
        "buyers.import_matched", {"company": "Acme", "domain": "acme.com"}
    )
    assert "skipping" in format_message(
        "buyers.import_not_found", {"domain": "x.com", "company": "X"}
    )
    assert "ready for research" in format_message(
        "buyers.import_done", {"matched": 2, "n": 3}
    )


def test_estimate_provided_skips_search():
    from app.infra.budget import estimate_campaign

    discover = estimate_campaign(10, "live", target_mode="discover")
    provided = estimate_campaign(10, "live", target_mode="provided")
    discover_steps = {s["step"] for s in discover["by_step"]}
    provided_steps = {s["step"] for s in provided["by_step"]}
    if "ballpark" in discover_steps:
        # No price file — ballpark totals still differ by mode
        assert provided["total"] <= discover["total"]
    else:
        assert "buyer.search" in discover_steps
        assert "buyer.search" not in provided_steps
        assert "buyers.import_identify" in provided_steps
