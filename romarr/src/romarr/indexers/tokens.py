"""32-byte app-token generation + bcrypt-hash + verify (T014).

Inbound calls from Prowlarr to Romarr's
``/api/v3/indexer*`` endpoints carry an ``X-App-Token`` header (or
equivalent), and the registry verifies it against the stored hash.

Uses :mod:`bcrypt` directly. The urlsafe-base64 token is 43 chars —
well under bcrypt's 72-byte input cap, so no SHA256 prehash needed.
"""

from __future__ import annotations

import secrets

import bcrypt

# Token bytes: 32 random bytes → 43-character urlsafe-base64 string.
_TOKEN_BYTES = 32


def generate_token() -> str:
    """Return a fresh URL-safe token of ``_TOKEN_BYTES`` random bytes."""
    return secrets.token_urlsafe(_TOKEN_BYTES)


def hash_token(plain: str) -> str:
    """Return a bcrypt hash of the token; per-row salt baked in."""
    if not plain:
        raise ValueError("cannot hash empty token")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("ascii")


def verify_token(plain: str, hashed: str) -> bool:
    """Return True iff ``plain`` matches ``hashed``."""
    if not plain or not hashed:
        return False
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
    except (ValueError, TypeError):
        return False


__all__ = ["generate_token", "hash_token", "verify_token"]
