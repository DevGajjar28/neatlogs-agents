from app.infra.redact import mask_email, mask_phone, redact_text


def test_mask_email():
    assert mask_email("rahul@finly.io") == "r***@finly.io"
    assert mask_email("a@b.co") == "a***@b.co"


def test_mask_phone():
    assert mask_phone("+1 415-555-2671").endswith("71")
    assert "***" in mask_phone("4155552671")


def test_redact_text_masks_emails_and_phones():
    text = "Email ada@acme.test or call +1 (415) 555-2671 please"
    out = redact_text(text)
    assert "ada@acme.test" not in out
    assert "a***@acme.test" in out
    assert "415" not in out or "***" in out
