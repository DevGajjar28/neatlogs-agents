"""Header-only finance / OTP denylist. Never fetch bodies for these messages."""

from __future__ import annotations

import re
from typing import Any

# Subject / From tokens that mean "do not open" (banking, OTP, payroll, tax).
_SUBJECT_PATTERNS = (
    r"\botp\b",
    r"\bone[-\s]?time\s+(passcode|password|code)\b",
    r"\bverification\s+code\b",
    r"\bdo not share\b",
    r"\bsecurity\s+code\b",
    r"\bbank\b",
    r"\bbanking\b",
    r"\bstatement\b",
    r"\binvoice\b",
    r"\bwire\s+transfer\b",
    r"\biban\b",
    r"\bswift\b",
    r"\bpayroll\b",
    r"\btax\b",
    r"\birs\b",
    r"\bpayment\s+due\b",
    r"\baccount\s+alert\b",
    r"\bfraud\b",
    r"\bcvv\b",
    r"\bcredit\s+card\b",
    r"\bdebit\s+card\b",
    r"\brouting\s+number\b",
)

_FROM_DOMAIN_HINTS = (
    "bank",
    "chase.com",
    "wellsfargo",
    "bankofamerica",
    "paypal.com",
    "stripe.com",
    "square.com",
    "venmo",
    "wise.com",
    "transferwise",
    "plaid.com",
    "intuit.com",
    "quickbooks",
    "adp.com",
    "gusto.com",
    "irs.gov",
    "tax",
)

_SUBJECT_RE = re.compile("|".join(f"(?:{p})" for p in _SUBJECT_PATTERNS), re.I)


def finance_blocked(*, subject: str = "", from_addr: str = "") -> str | None:
    """Return a short reason if headers look like finance/OTP; else None.

    Call this on headers only — before BODY fetch.
    """
    subj = (subject or "").strip()
    if subj and _SUBJECT_RE.search(subj):
        return "subject_finance_or_otp"
    from_l = (from_addr or "").lower()
    # domain part after @
    domain = from_l.rsplit("@", 1)[-1] if "@" in from_l else from_l
    for hint in _FROM_DOMAIN_HINTS:
        if hint in domain or hint in from_l:
            return "from_finance_domain"
    return None


def headers_look_safe(headers: dict[str, Any] | None = None) -> bool:
    """Convenience: True when finance_blocked returns None."""
    headers = headers or {}
    reason = finance_blocked(
        subject=str(headers.get("Subject") or headers.get("subject") or ""),
        from_addr=str(headers.get("From") or headers.get("from") or ""),
    )
    return reason is None
