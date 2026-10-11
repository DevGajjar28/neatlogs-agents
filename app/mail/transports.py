"""Delivery transports. Decrypt credentials only inside connect helpers."""

from __future__ import annotations

import imaplib
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Any, Protocol

from app.config import get_settings
from app.mail.accounts import get_credentials


@dataclass
class DeliveryResult:
    status: str  # sent | drafted | unknown | failed
    provider_response: str = ""
    message_id: str | None = None


class Transport(Protocol):
    def deliver(self, msg: EmailMessage) -> DeliveryResult: ...


class MailpitTransport:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        smtp_send: Any | None = None,
    ) -> None:
        settings = get_settings()
        self.host = host or settings.smtp_host
        self.port = port or settings.smtp_port
        self.smtp_send = smtp_send

    def deliver(self, msg: EmailMessage) -> DeliveryResult:
        if self.smtp_send is not None:
            self.smtp_send(self.host, self.port, msg)
            return DeliveryResult(status="sent", provider_response="mailpit")
        with smtplib.SMTP(self.host, self.port, timeout=15) as smtp:
            smtp.send_message(msg)
        return DeliveryResult(status="sent", provider_response="mailpit")


class GmailSmtpTransport:
    def __init__(self, account: dict[str, Any], *, smtp_send: Any | None = None) -> None:
        self.account = account
        self.smtp_send = smtp_send

    def deliver(self, msg: EmailMessage) -> DeliveryResult:
        if self.smtp_send is not None:
            self.smtp_send(
                self.account["smtp_host"],
                int(self.account["smtp_port"]),
                msg,
            )
            return DeliveryResult(
                status="sent",
                provider_response="injected",
                message_id=msg.get("Message-ID"),
            )
        user, password = get_credentials(self.account["id"])
        host = self.account["smtp_host"]
        port = int(self.account["smtp_port"])
        security = (self.account.get("smtp_security") or "starttls").lower()
        ctx = ssl.create_default_context()
        try:
            if security == "ssl" or port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=30, context=ctx) as smtp:
                    smtp.login(user, password)
                    smtp.send_message(msg)
            else:
                with smtplib.SMTP(host, port, timeout=30) as smtp:
                    smtp.ehlo()
                    smtp.starttls(context=ctx)
                    smtp.ehlo()
                    smtp.login(user, password)
                    # Track whether DATA may have been accepted
                    smtp.send_message(msg)
        except smtplib.SMTPServerDisconnected as exc:
            return DeliveryResult(
                status="unknown",
                provider_response="connection_dropped_after_data",
                message_id=msg.get("Message-ID"),
            )
        except Exception:
            raise
        finally:
            password = ""  # noqa: F841 — drop local ref
        return DeliveryResult(
            status="sent",
            provider_response="smtp_ok",
            message_id=msg.get("Message-ID"),
        )


class GmailDraftsTransport:
    def __init__(self, account: dict[str, Any]) -> None:
        self.account = account

    def deliver(self, msg: EmailMessage) -> DeliveryResult:
        user, password = get_credentials(self.account["id"])
        host = self.account["imap_host"]
        port = int(self.account["imap_port"] or 993)
        folder = self.account.get("drafts_folder") or "[Gmail]/Drafts"
        ctx = ssl.create_default_context()
        try:
            with imaplib.IMAP4_SSL(host, port, ssl_context=ctx) as imap:
                imap.login(user, password)
                # APPEND only to Drafts
                payload = msg.as_bytes()
                imap.append(folder, "\\Draft", None, payload)
                imap.logout()
        finally:
            password = ""  # noqa: F841
        return DeliveryResult(
            status="drafted",
            provider_response=f"appended:{folder}",
            message_id=msg.get("Message-ID"),
        )


def pick_transport(
    send_mode: str,
    account: dict | None,
    *,
    smtp_send: Any | None = None,
) -> Transport:
    if send_mode == "sandbox" or not account:
        return MailpitTransport(smtp_send=smtp_send)
    if send_mode == "gmail_drafts":
        return GmailDraftsTransport(account)
    return GmailSmtpTransport(account, smtp_send=smtp_send)
