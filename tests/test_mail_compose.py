"""Compose rules: citations, opt-out, threading, single recipient."""

from __future__ import annotations

from app.mail.compose import compose, has_opt_out_line, strip_citations


def test_strip_citations():
    assert "[ev_" not in strip_citations("Hello [ev_abc123] world")
    assert "(ev_" not in strip_citations("Hello (ev_abc123, ev_def456) world")
    assert "ev_" not in strip_citations("bare ev_abc123 end").lower()
    assert strip_citations("plain") == "plain"


def test_opt_out_and_footer():
    out = compose(
        subject="Hi [ev_abc123]",
        body="Body without footer",
        to_addr="a@b.com",
        from_email="me@example.com",
        display_name="Me",
        include_postal=True,
        postal_address="123 Main St",
        signature="Best,\nMe",
    )
    assert "[ev_" not in out.subject
    assert "[ev_" not in out.body
    assert has_opt_out_line(out.body)
    assert "123 Main St" in out.body
    assert "Best," in out.body
    assert out.msg["To"] == "a@b.com"
    assert out.msg.get_all("To") == ["a@b.com"]
    assert out.msg["Cc"] is None
    assert out.msg["Bcc"] is None
    assert "List-Unsubscribe" in out.msg


def test_threading_steps():
    out = compose(
        subject="Follow",
        body="Ping\n\nOpt out: reply stop",
        to_addr="a@b.com",
        from_email="me@example.com",
        display_name="Me",
        step=2,
        in_reply_to="<mid1@example.com>",
        step1_subject="Original subject",
    )
    assert out.subject.startswith("Re:")
    assert out.msg["In-Reply-To"] == "<mid1@example.com>"
    assert out.msg["References"] == "<mid1@example.com>"


def test_test_prefix():
    out = compose(
        subject="Hi",
        body="Body\n\nOpt out: reply stop",
        to_addr="test@example.com",
        from_email="me@example.com",
        display_name="Me",
        test_prefix="Test send · intended for contact",
    )
    assert out.subject.startswith("[TEST]")
    assert "Test send" in out.body
