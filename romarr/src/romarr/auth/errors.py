"""Auth error hierarchy.

Exceptions surfacing across the layer boundary so the eventual
HTTP layer can map them to FastAPI status codes uniformly. The
generic 401 message contract from FR-023 lives in the API layer
(this layer reports the *actual* failure mode for logging /
diagnostics; the API translates everything to a single
``unauthenticated`` response shape).
"""

from __future__ import annotations


class AuthError(Exception):
    """Base of the auth error hierarchy."""

    code: str = "auth_error"


class InvalidCredentialsError(AuthError):
    """Forms-login: bad username or bad password."""

    code = "invalid_credentials"


class UserDeactivatedError(AuthError):
    """User row is_active=False — login must fail closed."""

    code = "user_deactivated"


class SessionExpiredError(AuthError):
    """Session ``expires_at`` has passed."""

    code = "session_expired"


class SessionNotFoundError(AuthError):
    """No session row for the cookie value."""

    code = "session_not_found"


class ApiKeyInvalidError(AuthError):
    """Provided API key did not match any persisted hash."""

    code = "api_key_invalid"


class ApiKeyExpiredError(AuthError):
    """API key matched but ``expires_at`` has passed."""

    code = "api_key_expired"


class ApiKeyRevokedError(AuthError):
    """API key was previously revoked (row deleted)."""

    code = "api_key_revoked"


class InsufficientScopeError(AuthError):
    """Authenticated principal lacks the required scope/role."""

    code = "insufficient_scope"


class RateLimitedError(AuthError):
    """Per-IP rate limit on login / setup / OIDC callback exceeded."""

    code = "rate_limited"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(f"rate limited; retry after {retry_after_seconds}s")
        self.retry_after_seconds = retry_after_seconds


class SetupTokenExpiredError(AuthError):
    code = "setup_token_expired"


class SetupTokenAlreadyConsumedError(AuthError):
    code = "setup_already_completed"


class SetupTokenInvalidError(AuthError):
    code = "setup_token_invalid"
