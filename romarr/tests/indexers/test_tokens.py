"""App-token generation + bcrypt hashing tests (T009, T010)."""

from __future__ import annotations

import pytest

from romarr.indexers import generate_token, hash_token, verify_token


def test_token_format() -> None:
    """``generate_token`` produces a URL-safe base64-encoded 32-byte
    string (~43 chars) that differs across calls."""
    a = generate_token()
    b = generate_token()
    assert isinstance(a, str)
    assert len(a) >= 32
    # URL-safe alphabet: alphanumeric + '-' + '_' (no '+' / '/').
    assert all(c.isalnum() or c in "-_" for c in a)
    assert a != b


def test_hash_and_verify_round_trip() -> None:
    plain = generate_token()
    hashed = hash_token(plain)
    assert hashed != plain
    assert verify_token(plain, hashed) is True


def test_verify_with_wrong_token_returns_false() -> None:
    a = generate_token()
    hashed = hash_token(a)
    assert verify_token(generate_token(), hashed) is False


def test_hash_token_rejects_empty() -> None:
    with pytest.raises(ValueError):
        hash_token("")


def test_verify_handles_empty_inputs() -> None:
    assert verify_token("", "anything") is False
    assert verify_token("anything", "") is False


def test_verify_handles_garbage_hash() -> None:
    """A non-bcrypt-shaped hash returns False rather than raising."""
    assert verify_token("token", "not-a-real-hash") is False


def test_hashes_have_per_call_salt() -> None:
    """Two hashes of the same plaintext differ (per-row salt)."""
    plain = generate_token()
    h1 = hash_token(plain)
    h2 = hash_token(plain)
    assert h1 != h2
    assert verify_token(plain, h1) is True
    assert verify_token(plain, h2) is True
