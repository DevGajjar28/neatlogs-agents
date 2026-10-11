"""SMTP + IMAP connection verify with sanitized error messages."""

from __future__ import annotations

import imaplib
import smtplib
import ssl
from typing import Any

from app.mail.accounts import get_credentials, set_account_status


def sanitize_error(exc: BaseException, *, host: str = "", port: int = 0) -> str:
    text = str(exc).lower()
    raw = str(exc)
    if "535" in text or "5.7.8" in text or "authenticationfailed" in text:
        return (
            "Gmail rejected the app password. Create a new one at "
            "myaccount.google.com/apppasswords (needs 2-Step Verification) and paste it here."
        )
    if "534" in text or "application-specific password" in text:
        return "This account needs an app password, not your normal Google password."
    if "imap" in text and ("disabled" in text or "not enabled" in text):
        return "IMAP is off for this account. A Workspace admin can enable it in the Admin console."
    if "timed out" in text or "connection refused" in text or "errno" in text:
        return (
            f"Couldn't reach {host}:{port}. Check host, port and security "
            "(587 + STARTTLS or 465 + SSL)."
        )
    if "421" in text or "4.7." in text or "550 5.4.5" in text or "daily" in text and "limit" in text:
        return "Gmail is limiting this account. Sending is paused for it; try again later."
    # Never include password or full banners
    cleaned = raw.replace("\n", " ")[:180]
    if "password" in cleaned.lower() or "secret" in cleaned.lower():
        return "Connection failed. Check the app password and try again."
    return f"Connection failed: {cleaned}"


def discover_drafts_folder(imap: imaplib.IMAP4_SSL) -> str:
    typ, data = imap.list()
    if typ != "OK" or not data:
        return "[Gmail]/Drafts"
    for raw in data:
        line = raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else str(raw)
        if "\\Drafts" in line or "\\Draft" in line:
            # last quoted token is usually the folder name
            parts = line.split('"')
            if len(parts) >= 2:
                return parts[-2]
        if "[Gmail]/Drafts" in line:
            return "[Gmail]/Drafts"
    return "[Gmail]/Drafts"


def verify_account(account_id: str, account: dict[str, Any]) -> dict[str, Any]:
    """Run SMTP + IMAP checks; update account status. Returns {ok, detail, drafts_folder}."""
    host = account["smtp_host"]
    port = int(account["smtp_port"])
    security = (account.get("smtp_security") or "starttls").lower()
    imap_host = account["imap_host"]
    imap_port = int(account.get("imap_port") or 993)
    drafts = None
    try:
        user, password = get_credentials(account_id)
        ctx = ssl.create_default_context()
        # SMTP
        if security == "ssl" or port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=30, context=ctx) as smtp:
                smtp.login(user, password)
                smtp.noop()
        else:
            with smtplib.SMTP(host, port, timeout=30) as smtp:
                smtp.ehlo()
                smtp.starttls(context=ctx)
                smtp.ehlo()
                smtp.login(user, password)
                smtp.noop()
        # IMAP
        with imaplib.IMAP4_SSL(imap_host, imap_port, ssl_context=ctx) as imap:
            imap.login(user, password)
            typ, _ = imap.select("INBOX", readonly=True)
            if typ != "OK":
                # EXAMINE is select readonly
                imap.select("INBOX", readonly=True)
            drafts = discover_drafts_folder(imap)
            imap.logout()
        password = ""
        set_account_status(account_id, "ok", last_error=None, drafts_folder=drafts)
        return {
            "ok": True,
            "detail": "SMTP ok · IMAP ok · Drafts folder found",
            "drafts_folder": drafts,
        }
    except Exception as exc:  # noqa: BLE001
        msg = sanitize_error(exc, host=host, port=port)
        status = "error"
        if "limiting this account" in msg:
            status = "disabled"
        set_account_status(account_id, status, last_error=msg)
        return {"ok": False, "detail": msg, "drafts_folder": drafts}
