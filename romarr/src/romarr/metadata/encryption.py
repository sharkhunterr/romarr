"""At-rest encryption for provider credentials (FR-019, FR-021).

Provider API keys, OAuth client secrets, and any other credential
material are wrapped in a Fernet token derived from
``ROMARR_AUTH_SECRET_KEY`` via scrypt.

Threat model: the master key lives in environment / orchestrator
secrets, NEVER in the database. If the DB is exfiltrated alone, the
encrypted blobs are unreadable. If the master key changes, run the
``romarr metadata reencrypt`` CLI sub-command (defined as a stub in
spec 002 HARD phase, full impl deferred to spec 010).
"""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from romarr.config.settings import get_settings

# Per-installation salt. Constant so that the derived key is stable
# across processes — the secret strength comes from ROMARR_AUTH_SECRET_KEY,
# not the salt. Using a constant salt is acceptable because each
# installation has its own master key, and the salt's only job here is
# to defeat rainbow tables against scrypt.
_SCRYPT_SALT = b"romarr.metadata.config.encryption.v1"

_SCRYPT_PARAMS = {
    "n": 2**14,
    "r": 8,
    "p": 1,
    "length": 32,
}


class EncryptionKeyMissingError(RuntimeError):
    """Raised when ``ROMARR_AUTH_SECRET_KEY`` is unset and an encrypted
    operation is requested. The application should refuse to start when
    encrypted rows exist but no key is configured (FR-021)."""


def _derive_fernet_key(master_key: str) -> bytes:
    if not master_key:
        raise EncryptionKeyMissingError(
            "ROMARR_AUTH_SECRET_KEY is not set; cannot encrypt or "
            "decrypt provider credentials. Set it in the environment "
            "and restart."
        )
    kdf = Scrypt(salt=_SCRYPT_SALT, **_SCRYPT_PARAMS)
    raw = kdf.derive(master_key.encode("utf-8"))
    return base64.urlsafe_b64encode(raw)


def _fernet() -> Fernet:
    settings = get_settings()
    return Fernet(_derive_fernet_key(settings.auth_secret_key))


def encrypt(plaintext: bytes) -> bytes:
    """Wrap ``plaintext`` in a Fernet token using the installation key."""
    return _fernet().encrypt(plaintext)


def decrypt(ciphertext: bytes) -> bytes:
    """Unwrap a Fernet token. Raises ``InvalidToken`` on tampering."""
    return _fernet().decrypt(ciphertext)


def decrypt_secret(ciphertext: bytes) -> str:
    """Decode a stored secret string and trim legacy JSON quoting.

    Earlier slices wrapped the plaintext in ``json.dumps`` before
    encrypting, which left every secret (indexer api_key, application
    prowlarr_api_key, downloader password) with literal ``"…"`` chars
    around the value. Those quotes were sent verbatim to the upstream
    service and produced silent 401s. The encrypt path no longer adds
    them, but blobs persisted before the fix still carry them — strip
    one balanced layer of double or single quotes on read so existing
    rows decode cleanly without a migration.
    """
    plain = _fernet().decrypt(ciphertext).decode("utf-8")
    if len(plain) >= 2 and plain[0] == plain[-1] and plain[0] in ('"', "'"):
        return plain[1:-1]
    return plain
