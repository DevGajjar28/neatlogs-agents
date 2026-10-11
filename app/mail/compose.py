"""Render final outbound messages (no credentials)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import format_datetime, make_msgid

_CITATION = re.compile(r"\[ev_[^\]]*\]", re.IGNORECASE)
_OPT_OUT_MARKERS = ("opt out", "unsubscribe", "reply stop", "stop emailing")


@dataclass
class ComposedMessage:
    msg: EmailMessage
    message_id: str
    subject: str
    body: str
    to_addr: str


def strip_citations(text: str) -> str:
    return _CITATION.sub("", text or "").strip()


def has_opt_out_line(body: str) -> bool:
    lower = (body or "").lower()
    return any(m in lower for m in _OPT_OUT_MARKERS)


def compose(
    *,
    subject: str,
    body: str,
    to_addr: str,
    from_email: str,
    display_name: str,
    step: int = 1,
    in_reply_to: str | None = None,
    step1_subject: str | None = None,
    signature: str = "",
    postal_address: str = "",
    include_postal: bool = False,
    test_prefix: str | None = None,
) -> ComposedMessage:
    clean_subject = strip_citations(subject)
    clean_body = strip_citations(body)
    if test_prefix:
        clean_subject = f"[TEST] {clean_subject}"
        clean_body = f"{test_prefix}\n\n{clean_body}"

    footer_parts: list[str] = []
    if signature.strip():
        footer_parts.append(signature.strip())
    if include_postal and postal_address.strip():
        footer_parts.append(postal_address.strip())
    if not has_opt_out_line(clean_body):
        footer_parts.append("Opt out: reply with unsubscribe and we will not email you again.")
    if footer_parts:
        clean_body = clean_body.rstrip() + "\n\n--\n" + "\n".join(footer_parts)

    if step >= 2 and step1_subject:
        clean_subject = f"Re: {strip_citations(step1_subject)}"

    domain = from_email.split("@")[-1] if "@" in from_email else "localhost"
    message_id = make_msgid(domain=domain)
    # normalize angle brackets storage without angles in DB sometimes — keep full form
    mid = message_id.strip()

    msg = EmailMessage()
    msg["From"] = f'"{display_name}" <{from_email}>' if display_name else from_email
    msg["To"] = to_addr
    msg["Subject"] = clean_subject
    msg["Date"] = format_datetime(datetime.now(timezone.utc))
    msg["Message-ID"] = mid
    msg["List-Unsubscribe"] = f"<mailto:{from_email}?subject=unsubscribe>"
    if step >= 2 and in_reply_to:
        msg["In-Reply-To"] = in_reply_to
        msg["References"] = in_reply_to
    msg.set_content(clean_body)
    # Minimal HTML alternative from plain text (no links rewritten)
    html = "<pre style=\"font-family:sans-serif;white-space:pre-wrap\">" + (
        clean_body.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    ) + "</pre>"
    msg.add_alternative(html, subtype="html")
    return ComposedMessage(
        msg=msg,
        message_id=mid,
        subject=clean_subject,
        body=clean_body,
        to_addr=to_addr,
    )


def new_local_message_id(domain: str = "signalsdr.local") -> str:
    return f"<{uuid.uuid4().hex}@{domain}>"
