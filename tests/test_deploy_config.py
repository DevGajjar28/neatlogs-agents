"""Deploy settings: API host + CORS origins stay safe by default."""

from app.config import clear_settings_cache, cors_origin_list, get_settings


def test_cors_default_localhost(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000")
    clear_settings_cache()
    assert cors_origin_list() == ["http://localhost:3000"]


def test_cors_comma_list(monkeypatch):
    monkeypatch.setenv(
        "CORS_ORIGINS",
        "http://localhost:3000, https://signalsdr.vercel.app ",
    )
    clear_settings_cache()
    assert cors_origin_list() == [
        "http://localhost:3000",
        "https://signalsdr.vercel.app",
    ]


def test_api_host_default(monkeypatch):
    monkeypatch.delenv("API_HOST", raising=False)
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    clear_settings_cache()
    assert get_settings().api_host == "127.0.0.1"


def test_api_host_ec2(monkeypatch):
    monkeypatch.setenv("API_HOST", "0.0.0.0")
    clear_settings_cache()
    assert get_settings().api_host == "0.0.0.0"
