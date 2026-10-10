"""PII masking before logs, reports, and exported traces."""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(
    r"(?P<local>[a-zA-Z0-9._%+\-]+)@(?P<domain>[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,})"
)
# E.164-ish or common local forms: +1 415-555-2671, (415) 555-2671, 4155552671
_PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?\d{1,3}[\s\-.]*)?(?:\(?\d{2,4}\)?[\s\-.]*)?\d{3,4}[\s\-.]?\d{3,4}(?!\w)"
)


def mask_email(email: str) -> str:
    """Mask a single email: rahul@finly.io -> r***@finly.io."""
    if not email or "@" not in email:
        return email
    local, _, domain = email.partition("@")
    if not local:
        return f"***@{domain}"
    return f"{local[0]}***@{domain}"


def mask_phone(phone: str) -> str:
    """Mask a phone number, keeping the last 2 digits."""
    if not phone:
        return phone
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 4:
        return "***"
    return f"***{digits[-2:]}"


def redact_text(text: str) -> str:
    """Mask every email and phone-like token in free text."""
    if not text:
        return text

    def _email_sub(match: re.Match[str]) -> str:
        return mask_email(match.group(0))

    out = _EMAIL_RE.sub(_email_sub, text)

    def _phone_sub(match: re.Match[str]) -> str:
        raw = match.group(0)
        # Avoid eating bare years / short numbers with few digits
        digits = re.sub(r"\D", "", raw)
        if len(digits) < 7:
            return raw
        return mask_phone(raw)

    return _PHONE_RE.sub(_phone_sub, out)
