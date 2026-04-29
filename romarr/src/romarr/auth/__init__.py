"""Authentication & multi-user (spec 010).

Public surface:
- Domain models (`User`, `Session`, `ApiKey`, `SetupToken`)
- Hashing helpers (bcrypt for passwords, BLAKE2b for API keys)
- Constants (role tier, scope vocabulary)

The HTTP layer (`/api/v3/auth/*` endpoints) lands in a later slice.
"""

from romarr.auth.constants import (
    ROLE_ADMIN,
    ROLE_READONLY,
    ROLE_USER,
    SCOPE_ADMIN,
    SCOPE_READ,
    SCOPE_WRITE,
    Role,
    Scope,
    role_implies,
    scope_implies,
)
from romarr.auth.hashing import (
    BCRYPT_COST,
    BLAKE2B_DIGEST_SIZE,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)
from romarr.auth.models import ApiKey, Session, SetupToken, User

__all__ = [
    "BCRYPT_COST",
    "BLAKE2B_DIGEST_SIZE",
    "ROLE_ADMIN",
    "ROLE_READONLY",
    "ROLE_USER",
    "SCOPE_ADMIN",
    "SCOPE_READ",
    "SCOPE_WRITE",
    "ApiKey",
    "Role",
    "Scope",
    "Session",
    "SetupToken",
    "User",
    "generate_api_key",
    "hash_api_key",
    "hash_password",
    "role_implies",
    "scope_implies",
    "verify_password",
]
