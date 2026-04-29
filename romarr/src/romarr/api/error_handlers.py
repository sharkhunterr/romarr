"""Error handlers — translate auth exceptions to spec-013 envelopes.

Per spec 013 FR-010 the canonical error response is::

    { "errorMessage": str, "errorCode"?: str, "details"?: object }

Per FR-023 (spec 010, clarified) the auth chain MUST NOT disclose
which method failed — every authentication failure surfaces the
same generic ``unauthenticated`` envelope at HTTP 401. Authorisation
failures (we know who you are; you don't have the role) surface as
``permission_denied`` at HTTP 403. Rate-limit hits surface as
``rate_limited`` at HTTP 429 with a ``Retry-After`` header.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

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

if TYPE_CHECKING:
    from fastapi import FastAPI


def register_error_handlers(app: FastAPI) -> None:
    """Wire AuthError subclasses to canonical JSON responses."""

    @app.exception_handler(HTTPException)
    async def _http_exception(
        _request: Request, exc: HTTPException
    ) -> JSONResponse:
        """Translate ``HTTPException(detail=dict)`` to the spec-013 envelope.

        FastAPI's default handler wraps the detail under a ``detail``
        key. Spec 013 FR-010 calls for the canonical envelope at the
        top level: ``{errorMessage, errorCode?, details?}``. When
        endpoints raise ``HTTPException(detail={"errorMessage": ...,
        "errorCode": ...})`` we surface the dict directly. String
        details fall back to the canonical wrapping.
        """
        if isinstance(exc.detail, dict):
            content = exc.detail
        else:
            content = {
                "errorMessage": str(exc.detail or "error"),
                "errorCode": "http_error",
            }
        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers=exc.headers,
        )

    @app.exception_handler(RateLimitedError)
    async def _rate_limited(_request: Request, exc: RateLimitedError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "errorMessage": "rate_limited",
                "errorCode": exc.code,
            },
            headers={"Retry-After": str(exc.retry_after_seconds)},
        )

    @app.exception_handler(InvalidCredentialsError)
    @app.exception_handler(UserDeactivatedError)
    @app.exception_handler(SessionExpiredError)
    @app.exception_handler(SessionNotFoundError)
    @app.exception_handler(ApiKeyInvalidError)
    @app.exception_handler(ApiKeyExpiredError)
    @app.exception_handler(ApiKeyRevokedError)
    async def _unauthenticated(
        _request: Request, _exc: AuthError
    ) -> JSONResponse:
        # Spec 010 FR-023 — the response body MUST NOT disclose which
        # method failed; we always emit the same generic envelope.
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "errorMessage": "unauthenticated",
                "errorCode": "unauthenticated",
            },
            headers={"WWW-Authenticate": "Cookie"},
        )

    @app.exception_handler(InsufficientScopeError)
    async def _insufficient(
        _request: Request, _exc: InsufficientScopeError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "errorMessage": "permission_denied",
                "errorCode": "permission_denied",
            },
        )

    @app.exception_handler(SetupTokenInvalidError)
    @app.exception_handler(SetupTokenExpiredError)
    @app.exception_handler(SetupTokenAlreadyConsumedError)
    async def _setup_failed(
        _request: Request, exc: AuthError
    ) -> JSONResponse:
        # Setup endpoint emits HTTP 401 across all three cases.
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "errorMessage": "setup_failed",
                "errorCode": exc.code,
            },
        )
