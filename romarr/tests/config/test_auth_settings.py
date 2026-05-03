"""Tests for the spec-010 auth settings (T005, slice 175).

The auth-related Pydantic Settings fields colocate in the
shared ``romarr.config.settings.Settings`` class rather than
the dedicated ``src/romarr/auth/settings.py`` module the spec
originally called for. These tests pin the env-prefix loading
+ defaults so the auth chain has a stable contract.
"""

from __future__ import annotations

import pytest

from romarr.config.settings import Settings, get_settings


def test_auth_settings_defaults() -> None:
    """Defaults match what the spec documents."""
    settings = Settings(auth_secret_key="x" * 32)
    assert settings.auth_session_ttl_seconds == 86_400  # 24h
    assert settings.bcrypt_cost == 12
    assert settings.trust_proxy_auth is False
    assert settings.trusted_proxy_headers == []
    assert settings.oidc_issuer_url == ""
    assert settings.oidc_client_id == ""
    assert settings.oidc_client_secret == ""
    assert settings.redis_url == ""


def test_auth_settings_load_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each field reads from the ``ROMARR_`` env prefix."""
    monkeypatch.setenv(
        "ROMARR_AUTH_SECRET_KEY", "test-secret-key-xxxxxxxxxxxxxxxx"
    )
    monkeypatch.setenv("ROMARR_AUTH_SESSION_TTL_SECONDS", "3600")
    monkeypatch.setenv("ROMARR_BCRYPT_COST", "14")
    monkeypatch.setenv("ROMARR_TRUST_PROXY_AUTH", "true")
    monkeypatch.setenv(
        "ROMARR_TRUSTED_PROXY_HEADERS",
        '["X-Forwarded-User", "X-Auth-User"]',
    )
    monkeypatch.setenv(
        "ROMARR_OIDC_ISSUER_URL", "https://idp.example.com"
    )
    monkeypatch.setenv("ROMARR_OIDC_CLIENT_ID", "romarr")
    monkeypatch.setenv("ROMARR_OIDC_CLIENT_SECRET", "shh")
    monkeypatch.setenv("ROMARR_REDIS_URL", "redis://localhost:6379/0")

    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.auth_session_ttl_seconds == 3600
        assert settings.bcrypt_cost == 14
        assert settings.trust_proxy_auth is True
        assert settings.trusted_proxy_headers == [
            "X-Forwarded-User",
            "X-Auth-User",
        ]
        assert settings.oidc_issuer_url == "https://idp.example.com"
        assert settings.oidc_client_id == "romarr"
        assert settings.oidc_client_secret == "shh"
        assert settings.redis_url == "redis://localhost:6379/0"
    finally:
        get_settings.cache_clear()


def test_bcrypt_cost_bounds() -> None:
    """bcrypt cost is bounded to a sane range."""
    Settings(auth_secret_key="x" * 32, bcrypt_cost=4)  # min
    Settings(auth_secret_key="x" * 32, bcrypt_cost=20)  # max
    with pytest.raises(Exception):
        Settings(auth_secret_key="x" * 32, bcrypt_cost=3)
    with pytest.raises(Exception):
        Settings(auth_secret_key="x" * 32, bcrypt_cost=21)


def test_session_ttl_minimum() -> None:
    """Session TTL must be at least 60s — a one-second TTL
    would log every request out instantly."""
    Settings(auth_secret_key="x" * 32, auth_session_ttl_seconds=60)  # min
    with pytest.raises(Exception):
        Settings(
            auth_secret_key="x" * 32, auth_session_ttl_seconds=30
        )
