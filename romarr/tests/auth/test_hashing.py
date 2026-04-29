"""Password + API-key hashing tests — FR-004 / FR-005 / FR-006."""

from __future__ import annotations

import re

import pytest

from romarr.auth.hashing import (
    API_KEY_PREFIX,
    BCRYPT_COST,
    BLAKE2B_DIGEST_SIZE,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_api_key,
    verify_password,
)

# ---------------------------------------------------------------------------
# Passwords (FR-004)
# ---------------------------------------------------------------------------


def test_hash_password_round_trip() -> None:
    h = hash_password("correcthorsebatterystaple")
    assert verify_password("correcthorsebatterystaple", h) is True
    assert verify_password("wrong", h) is False


def test_hash_password_uses_bcrypt_cost_12() -> None:
    h = hash_password("anything")
    # bcrypt hashes look like ``$2b$12$...`` — the cost is the digit pair.
    assert re.match(r"^\$2[abxy]\$" + str(BCRYPT_COST) + r"\$", h)


def test_hash_password_rejects_empty() -> None:
    with pytest.raises(ValueError):
        hash_password("")


def test_verify_password_handles_garbage_hash_gracefully() -> None:
    """FR-004 — verification must NOT raise on a malformed hash."""
    assert verify_password("anything", "not-a-bcrypt-hash") is False
    assert verify_password("anything", "") is False
    assert verify_password("", "") is False


def test_hash_password_two_runs_produce_different_hashes() -> None:
    """Salts ensure two hashes of the same plaintext differ."""
    h1 = hash_password("secret")
    h2 = hash_password("secret")
    assert h1 != h2
    # ...but both verify against the original plaintext.
    assert verify_password("secret", h1) is True
    assert verify_password("secret", h2) is True


# ---------------------------------------------------------------------------
# API keys (FR-005 / FR-006)
# ---------------------------------------------------------------------------


def test_generate_api_key_format() -> None:
    plaintext, key_hash, key_prefix = generate_api_key()
    assert plaintext.startswith(API_KEY_PREFIX)
    # rmk_ + 43 url-safe chars (32 bytes b64 without padding)
    assert len(plaintext) == len(API_KEY_PREFIX) + 43
    assert len(key_hash) == BLAKE2B_DIGEST_SIZE * 2  # hex
    assert len(key_prefix) == 8


def test_generate_api_key_is_unique_across_calls() -> None:
    keys = {generate_api_key()[0] for _ in range(20)}
    assert len(keys) == 20  # 32 random bytes → astronomically unlikely to collide


def test_hash_api_key_deterministic() -> None:
    h1 = hash_api_key("rmk_xyz")
    h2 = hash_api_key("rmk_xyz")
    assert h1 == h2
    assert h1 != hash_api_key("rmk_abc")


def test_hash_api_key_rejects_empty() -> None:
    with pytest.raises(ValueError):
        hash_api_key("")


def test_verify_api_key_constant_time_compare() -> None:
    plaintext, expected_hash, _ = generate_api_key()
    assert verify_api_key(plaintext, expected_hash) is True
    assert verify_api_key("rmk_wrong", expected_hash) is False
    assert verify_api_key("", expected_hash) is False
    assert verify_api_key(plaintext, "") is False


def test_generate_api_key_round_trip_via_verify() -> None:
    plaintext, key_hash, key_prefix = generate_api_key()
    # Independently re-hash the plaintext and ensure it matches.
    assert hash_api_key(plaintext) == key_hash
    assert plaintext[len(API_KEY_PREFIX) : len(API_KEY_PREFIX) + 8] == key_prefix
