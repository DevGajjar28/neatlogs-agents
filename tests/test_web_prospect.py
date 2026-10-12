"""Prospect website URL discovery."""

from app.tools import web


def test_prospect_candidate_urls_includes_about_and_team():
    urls = web.prospect_candidate_urls("https://acme.example")
    joined = " ".join(urls).lower()
    assert "acme.example/about" in joined or joined.endswith("/about")
    assert any("team" in u or "people" in u for u in urls)


def test_fetch_prospect_pages_empty_for_bad_host():
    assert web.fetch_prospect_pages("") == []
