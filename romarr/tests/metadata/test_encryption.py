"""Encryption helper round-trip + tampering tests (T007 / FR-019)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cryptography.fernet import InvalidToken

from romarr.config.settings import get_settings
from romarr.metadata.encryption import (
    EncryptionKeyMissingError,
    decrypt,
    encrypt,
)


def test_round_trip_json(metadata_env: Path) -> None:
    payload = json.dumps({"client_id": "abc", "client_secret": "shhh"}).encode()
    token = encrypt(payload)
    assert token != payload
    # Ciphertext is NOT JSON-parseable.
    with pytest.raises(json.JSONDecodeError):
        json.loads(token)
    assert decrypt(token) == payload


def test_decrypt_with_wrong_key_raises(
    metadata_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = encrypt(b"hello")
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "a-completely-different-key")
    get_settings.cache_clear()
    with pytest.raises(InvalidToken):
        decrypt(token)


def test_missing_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "")
    get_settings.cache_clear()
    try:
        with pytest.raises(EncryptionKeyMissingError):
            encrypt(b"x")
    finally:
        get_settings.cache_clear()
