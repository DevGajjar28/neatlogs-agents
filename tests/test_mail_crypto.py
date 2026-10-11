"""Fernet crypto for mail app passwords."""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.config import clear_settings_cache
from app.mail.crypto import SecretKeyMissing, decrypt_secret, encrypt_secret, generate_key


@pytest.fixture()
def secret_key(monkeypatch: pytest.MonkeyPatch):
    key = Fernet.generate_key().decode("utf-8")
    monkeypatch.setenv("SIGNALSDR_SECRET_KEY", key)
    clear_settings_cache()
    yield key
    clear_settings_cache()


def test_round_trip(secret_key: str):
    token = encrypt_secret("my-app-password-16")
    assert "my-app-password" not in token
    assert decrypt_secret(token) == "my-app-password-16"


def test_refuse_without_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SIGNALSDR_SECRET_KEY", raising=False)
    monkeypatch.setenv("SIGNALSDR_SECRET_KEY", "")
    clear_settings_cache()
    with pytest.raises(SecretKeyMissing):
        encrypt_secret("x")


def test_generate_key_format():
    key = generate_key()
    Fernet(key.encode("utf-8"))  # valid Fernet key
