"""Fernet encryption for mail app passwords. Never log decrypted values."""

from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class SecretKeyMissing(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "SIGNALSDR_SECRET_KEY is not set. Run: python cli.py gen-key"
        )


def _fernet() -> Fernet:
    key = (get_settings().signalsdr_secret_key or "").strip()
    if not key:
        raise SecretKeyMissing()
    try:
        return Fernet(key.encode("utf-8") if isinstance(key, str) else key)
    except Exception as exc:  # noqa: BLE001
        raise SecretKeyMissing() from exc


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Could not decrypt stored password") from exc


def generate_key() -> str:
    return Fernet.generate_key().decode("utf-8")
