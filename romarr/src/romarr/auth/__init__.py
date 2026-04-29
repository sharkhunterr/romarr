"""Authentication & multi-user (spec 010).

Public surface:
- Domain models (`User`, `Session`, `ApiKey`, `SetupToken`)
- Hashing helpers (bcrypt for passwords, BLAKE2b for API keys)
- Constants (role tier, scope vocabulary)
- Services (login, sessions, api_keys, setup, chain, permissions)

The HTTP layer (`/api/v3/auth/*` endpoints) lands in a later slice.
"""

from romarr.auth.api_keys import (
    CreatedApiKey,
    ResolvedApiKey,
    create_api_key,
    list_api_keys_for_user,
    resolve_api_key,
    revoke_api_key,
    touch_api_key,
)
from romarr.auth.chain import (
    SESSION_COOKIE_NAME,
    ChainConfig,
    RequestContext,
    resolve_principal,
)
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
    role_to_required_scope,
    scope_implies,
)
from romarr.auth.errors import (
    ApiKeyExpiredError,
    ApiKeyInvalidError,
    ApiKeyRevokedError,
    AuthError,
    InsufficientScopeError,
    InvalidCredentialsError,
    RateLimitedError,
    SessionExpiredError,
    SessionNotFoundError,
    SetupTokenAlreadyConsumedError,
    SetupTokenExpiredError,
    SetupTokenInvalidError,
    UserDeactivatedError,
)
from romarr.auth.hashing import (
    BCRYPT_COST,
    BLAKE2B_DIGEST_SIZE,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_api_key,
    verify_password,
)
from romarr.auth.login import authenticate
from romarr.auth.models import ApiKey, Session, SetupToken, User
from romarr.auth.permissions import Principal, require_role
from romarr.auth.rate_limit import (
    DEFAULT_LIMIT,
    DEFAULT_WINDOW_SECONDS,
    IpRateLimiter,
)
from romarr.auth.sessions import (
    SESSION_TTL_DAYS,
    CreatedSession,
    ResolvedSession,
    create_session,
    resolve_session,
    revoke_all_for_user,
    revoke_session,
)
from romarr.auth.setup import (
    SETUP_TOKEN_TTL_HOURS,
    SetupBootstrapResult,
    consume_setup_token,
    maybe_bootstrap_setup_token,
)

__all__ = [
    "BCRYPT_COST",
    "BLAKE2B_DIGEST_SIZE",
    "DEFAULT_LIMIT",
    "DEFAULT_WINDOW_SECONDS",
    "ROLE_ADMIN",
    "ROLE_READONLY",
    "ROLE_USER",
    "SCOPE_ADMIN",
    "SCOPE_READ",
    "SCOPE_WRITE",
    "SESSION_COOKIE_NAME",
    "SESSION_TTL_DAYS",
    "SETUP_TOKEN_TTL_HOURS",
    "ApiKey",
    "ApiKeyExpiredError",
    "ApiKeyInvalidError",
    "ApiKeyRevokedError",
    "AuthError",
    "ChainConfig",
    "CreatedApiKey",
    "CreatedSession",
    "InsufficientScopeError",
    "InvalidCredentialsError",
    "IpRateLimiter",
    "Principal",
    "RateLimitedError",
    "RequestContext",
    "ResolvedApiKey",
    "ResolvedSession",
    "Role",
    "Scope",
    "Session",
    "SessionExpiredError",
    "SessionNotFoundError",
    "SetupBootstrapResult",
    "SetupToken",
    "SetupTokenAlreadyConsumedError",
    "SetupTokenExpiredError",
    "SetupTokenInvalidError",
    "User",
    "UserDeactivatedError",
    "authenticate",
    "consume_setup_token",
    "create_api_key",
    "create_session",
    "generate_api_key",
    "hash_api_key",
    "hash_password",
    "list_api_keys_for_user",
    "maybe_bootstrap_setup_token",
    "require_role",
    "resolve_api_key",
    "resolve_principal",
    "resolve_session",
    "revoke_all_for_user",
    "revoke_api_key",
    "revoke_session",
    "role_implies",
    "role_to_required_scope",
    "scope_implies",
    "touch_api_key",
    "verify_api_key",
    "verify_password",
]
