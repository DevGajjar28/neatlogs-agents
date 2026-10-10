"""Planner routing and ICP widen decisions."""

from app.agents.planner import estimate_credits, planner_node, widen_icp
from app.models import BuyerRole, ICPProposal


def _base_icp(**overrides) -> ICPProposal:
    data = dict(
        industries=["Software Development"],
        headcount_min=None,
        headcount_max=None,
        countries=["United States"],
        employee_count_ranges=["51-200"],
        funding_stages=[],
        roles=[
            BuyerRole(
                title_variants=["CTO"],
                kind="economic_buyer",
                why="budget",
            )
        ],
        rationale="test",
        evidence=[],
        approved=True,
    )
    data.update(overrides)
    return ICPProposal.model_validate(data)


def test_estimate_scales_with_n():
    assert estimate_credits(10) < estimate_credits(20)


def test_widen_icp_expands_ranges_then_industries():
    icp = _base_icp()
    w1 = widen_icp(icp, 1)
    assert "201-500" in w1.employee_count_ranges or "11-50" in w1.employee_count_ranges
    w2 = widen_icp(w1, 2)
    assert len(w2.industries) >= len(w1.industries)


def test_planner_emits_replan_widen_when_search_thin(monkeypatch):
    monkeypatch.setenv("MAX_CREDITS", "400")
    from app.config import clear_settings_cache

    clear_settings_cache()
    state = {
        "campaign_id": "t1",
        "input": {"n": 5},
        "plan": {
            "initialized": True,
            "phase": "after_search",
            "widenings": 0,
            "max_widenings": 2,
            "max_credits": 400,
        },
        "budget": {"credits_spent": 1},
        "icp": _base_icp().model_dump(mode="json"),
        "companies": [{"status": "kept", "id": "1"}],  # 1 < N=5
        "events": [],
    }
    out = planner_node(state)
    assert out["plan"]["next"] == "buyer_search"
    assert out["plan"]["widenings"] == 1
    assert any(e.get("type") == "replan.widen_icp" for e in out["events"])
    assert out["companies"] == []


def test_planner_start_builds_plan(monkeypatch):
    monkeypatch.setenv("MAX_CREDITS", "400")
    from app.config import clear_settings_cache

    clear_settings_cache()
    out = planner_node(
        {
            "campaign_id": "t1",
            "input": {"n": 10},
            "plan": {},
            "budget": {"credits_spent": 0},
            "events": [],
        }
    )
    assert out["plan"]["initialized"] is True
    assert out["plan"]["next"] == "product_researcher"
    assert any(e.get("type") == "plan.start" for e in out["events"])
