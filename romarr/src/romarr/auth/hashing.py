"""Password + API-key hashing helpers.

Spec 010 mandates:
  - bcrypt cost factor 12 (FR-004) for passwords
  - BLAKE2b for API-key hashing (FR-006); plaintext returned exactly
    once at creation (FR-005) and never persisted
  - constant-time comparisons everywhere (FR-004 / FR-006)

Plaintext API keys take the form ``rmk_<43 url-safe chars>`` where
``rmk_`` is the recognisable Romarr prefix and the body is 32 random
bytes URL-safe-base64-encoded (32 bytes → 43 chars without padding).
The first 8 chars of the plaintext become ``key_prefix`` for
operator UI display (no security value — search aid only).
"""

from __future__ import annotations

import hmac
import secrets
from hashlib import blake2b

import bcrypt

BCRYPT_COST: int = 12
"""bcrypt cost factor (FR-004)."""

BLAKE2B_DIGEST_SIZE: int = 32
"""BLAKE2b digest size in bytes — produces a 64-char hex output."""

API_KEY_PREFIX: str = "rmk_"
"""Plaintext API-key prefix that identifies a Romarr-issued key."""

API_KEY_BODY_BYTES: int = 32
"""Random bytes encoded into the API-key body."""

API_KEY_PREFIX_LEN: int = 8
"""Stored plaintext prefix length — the first 8 chars after `rmk_`."""


# ---------------------------------------------------------------------------
# Passwords (FR-004)
# ---------------------------------------------------------------------------


def hash_password(plaintext: str) -> str:
    """Return a bcrypt hash for ``plaintext`` at cost 12.

    The output is ASCII; safe to store in a ``VARCHAR``. Use
    :func:`verify_password` to check.
    """
    if not plaintext:
        raise ValueError("password must not be empty")
    salt = bcrypt.gensalt(rounds=BCRYPT_COST)
    digest = bcrypt.hashpw(plaintext.encode("utf-8"), salt)
    return digest.decode("ascii")


def verify_password(plaintext: str, hashed: str) -> bool:
    """Constant-time bcrypt verify.

    Returns ``False`` rather than raising when the hash is malformed —
    spec 010 FR-004 wants the caller to surface a generic
    "invalid_credentials" message, not a stack trace.
    """
    if not plaintext or not hashed:
        return False
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# API keys (FR-005 / FR-006)
# ---------------------------------------------------------------------------


def generate_api_key() -> tuple[str, str, str]:
    """Mint a fresh plaintext API key + its persistence triple.

    Returns ``(plaintext, key_hash_hex, key_prefix)`` where:
      - ``plaintext`` is what the operator copies once (FR-005). Format
        is ``rmk_<43 url-safe chars>``.
      - ``key_hash_hex`` is the BLAKE2b digest the database stores
        (FR-006). 64 lowercase hex chars.
      - ``key_prefix`` is the first :data:`API_KEY_PREFIX_LEN` chars
        AFTER ``rmk_`` — surfaces in the UI for visual identification.
    """
    body = secrets.token_urlsafe(API_KEY_BODY_BYTES)
    plaintext = f"{API_KEY_PREFIX}{body}"
    return plaintext, hash_api_key(plaintext), body[:API_KEY_PREFIX_LEN]


def hash_api_key(plaintext: str) -> str:
    """Return the BLAKE2b digest hex used for indexed lookups."""
    if not plaintext:
        raise ValueError("api key must not be empty")
    h = blake2b(plaintext.encode("utf-8"), digest_size=BLAKE2B_DIGEST_SIZE)
    return h.hexdigest()


def verify_api_key(plaintext: str, expected_hash_hex: str) -> bool:
    """Constant-time API-key check (FR-006)."""
    if not plaintext or not expected_hash_hex:
        return False
    candidate = hash_api_key(plaintext)
    return hmac.compare_digest(candidate, expected_hash_hex)
