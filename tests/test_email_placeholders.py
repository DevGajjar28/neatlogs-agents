"""Draft personalization: real names, no leftover {{braces}} or test banners."""

from app.agents.email_writer import fill_placeholders, personalize_copy, strip_test_banner


def test_fill_placeholders_uses_real_names():
    text = "Hi {{first_name}}, {{company}} needs {{seller_name}} for {{role}}."
    out = fill_placeholders(
        text,
        contact_name="Ada Lovelace",
        company_name="Mindarmor",
        role="CTO",
        seller_name="Meruksha",
    )
    assert "{{" not in out
    assert out == "Hi Ada, Mindarmor needs Meruksha for CTO."


def test_strip_test_banner():
    body = (
        "Test send · intended for contact at company (g***@gmail.com)\n\n"
        "Hi Ada,\n\nWorth a chat?"
    )
    assert "Test send" not in strip_test_banner(body)
    assert "Hi Ada," in strip_test_banner(body)


def test_personalize_copy_combo():
    subj, body = personalize_copy(
        "Quick note for {{company}}",
        "Test send · intended for contact at company (x***@y.com)\n\nHi {{first_name}},",
        contact_name="Bob Builder",
        company_name="Acme",
    )
    assert subj == "Quick note for Acme"
    assert "{{" not in body
    assert "Test send" not in body
    assert "Hi Bob," in body
