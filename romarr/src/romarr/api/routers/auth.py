"""Auth endpoints — /api/v3/auth/*.

Endpoints shipped in this slice (per spec 010 FR-026, minus OIDC):

  - POST /api/v3/auth/setup        — bootstrap first admin (FR-020)
  - POST /api/v3/auth/login        — forms login (FR-010)
  - POST /api/v3/auth/logout       — revoke session
  - GET  /api/v3/auth/me           — read current user
  - PUT  /api/v3/auth/me           — self-service update
  - GET  /api/v3/auth/api-key      — list user's API keys
  - POST /api/v3/auth/api-key      — mint a key (plaintext returned ONCE)
  - DELETE /api/v3/auth/api-key/{id} — revoke a key

The OIDC endpoints (``/oidc/start`` + ``/oidc/callback``) ship in
the next slice once the Authlib client wiring is in place.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select

# AsyncSession must be importable at runtime — FastAPI introspects
# ``Annotated[AsyncSession, Depends(get_db)]`` parameters to build
# the OpenAPI schema.
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import (
    client_ip,
    get_db,
    get_login_rate_limiter,
    require_readonly,
    require_user,
)
from romarr.api.routers.auth_schemas import (
    ApiKeyPublic,
    CreateApiKeyRequest,
    CreatedApiKeyResponse,
    LoginRequest,
    SetupRequest,
    SetupResponse,
    UpdateMeRequest,
    UserPublic,
)
from romarr.auth import (
    SESSION_COOKIE_NAME,
    IpRateLimiter,
    Principal,
    authenticate,
    consume_setup_token,
    create_api_key,
    create_session,
    hash_password,
    list_api_keys_for_user,
    revoke_all_for_user,
    revoke_api_key,
    revoke_session,
)
from romarr.auth.models import ApiKey, User

router = APIRouter(prefix="/api/v3/auth", tags=["Auth"])


# ---------------------------------------------------------------------------
# /setup
# ---------------------------------------------------------------------------


@router.post(
    "/setup",
    response_model=SetupResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Consume the bootstrap setup token and create the first admin user",
)
async def setup(
    request: Request,
    response: Response,
    payload: SetupRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    rate_limiter: Annotated[IpRateLimiter, Depends(get_login_rate_limiter)],
) -> SetupResponse:
    """FR-020 / FR-021. Token comes from the ``X-Setup-Token`` header.

    Per FR-010a, this endpoint shares the per-IP rate limit with
    /login and /oidc/callback. Per FR-020 the operation is atomic —
    success returns the new admin and sets a session cookie so the
    operator is logged in immediately.
    """
    ip = client_ip(request)
    rate_limiter.check(ip)
    rate_limiter.record(ip)

    token = request.headers.get("X-Setup-Token", "")
    user = await consume_setup_token(
        db,
        plaintext=token,
        username=payload.username,
        password=payload.password,
    )

    # Auto-login the freshly-minted admin.
    created_session = await create_session(
        db,
        user=user,
        user_agent=request.headers.get("user-agent"),
        ip_address=ip or None,
    )
    _set_session_cookie(response, request, created_session.session_id, created_session.expires_at)
    return SetupResponse(user=UserPublic.model_validate(user))


# ---------------------------------------------------------------------------
# /login + /logout
# ---------------------------------------------------------------------------


@router.post(
    "/login",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Forms login — sets the session cookie",
)
async def login(
    request: Request,
    response: Response,
    payload: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
    rate_limiter: Annotated[IpRateLimiter, Depends(get_login_rate_limiter)],
) -> Response:
    """FR-010 + FR-010a — per-IP rate limit applied first.

    Per FR-010a both successful and failed attempts contribute to the
    bucket, so we ``record`` BEFORE the bcrypt verify; the limiter's
    ``check`` blocks the bcrypt path entirely when over budget (no
    work-factor oracle for an attacker).
    """
    ip = client_ip(request)
    rate_limiter.check(ip)
    rate_limiter.record(ip)

    user = await authenticate(
        db, username=payload.username, password=payload.password
    )
    user.last_login_at = datetime.now(UTC)
    await db.commit()

    created = await create_session(
        db,
        user=user,
        user_agent=request.headers.get("user-agent"),
        ip_address=ip or None,
    )
    _set_session_cookie(response, request, created.session_id, created.expires_at)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the current session and clear the cookie",
)
async def logout(
    request: Request,
    response: Response,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Idempotent — calling logout without a session is a no-op."""
    sid = request.cookies.get(SESSION_COOKIE_NAME)
    if sid:
        await revoke_session(db, session_id=sid)
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        samesite="lax",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


# ---------------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------------


@router.get(
    "/config",
    summary=(
        "Public auth-config probe — what login flows the SPA should "
        "render. No authentication required."
    ),
)
async def get_auth_config() -> dict[str, object]:
    """Return the public auth-config so the Login page knows
    whether to render the OIDC SSO button (spec 014 T101 + spec
    010 FR-026 forward-spec'd OIDC).

    Today OIDC isn't shipped — the endpoint returns
    ``{oidc_enabled: false}``. When the OIDC backend lands the
    body grows ``{oidc_enabled: true, oidc_provider_label,
    oidc_start_url}`` so the Login page can wire the
    ``Sign in with SSO`` button to the right authority.
    """
    return {
        "oidc_enabled": False,
        "oidc_provider_label": None,
        "oidc_start_url": None,
    }


@router.get(
    "/me",
    response_model=UserPublic,
    summary="Return the current authenticated user",
)
async def get_me(
    principal: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserPublic:
    user = (
        await db.execute(select(User).where(User.id == principal.user_id))
    ).scalar_one()
    return UserPublic.model_validate(user)


@router.put(
    "/me",
    response_model=UserPublic,
    summary="Self-service update of password / email / preferences",
)
async def update_me(
    payload: UpdateMeRequest,
    principal: Annotated[Principal, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserPublic:
    user = (
        await db.execute(select(User).where(User.id == principal.user_id))
    ).scalar_one()

    if payload.password is not None:
        user.hashed_password = hash_password(payload.password)
        # Per FR-027 / common sense: password change revokes every
        # other session for this user.
        await revoke_all_for_user(db, user_id=user.id)

    if payload.email is not None:
        user.email = payload.email or None

    if payload.preferences is not None:
        user.preferences = payload.preferences

    await db.commit()
    await db.refresh(user)
    return UserPublic.model_validate(user)


# ---------------------------------------------------------------------------
# /api-key
# ---------------------------------------------------------------------------


@router.get(
    "/api-key",
    response_model=list[ApiKeyPublic],
    summary="List the authenticated user's API keys (plaintext never re-shown)",
)
async def list_my_api_keys(
    principal: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ApiKeyPublic]:
    rows = await list_api_keys_for_user(db, user_id=principal.user_id)
    return [ApiKeyPublic.model_validate(r) for r in rows]


@router.post(
    "/api-key",
    response_model=CreatedApiKeyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Mint an API key (FR-005). Plaintext is returned exactly once.",
)
async def create_my_api_key(
    payload: CreateApiKeyRequest,
    principal: Annotated[Principal, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CreatedApiKeyResponse:
    user = (
        await db.execute(select(User).where(User.id == principal.user_id))
    ).scalar_one()
    try:
        created = await create_api_key(
            db,
            user=user,
            name=payload.name,
            scopes=payload.scopes,
            expires_at=payload.expires_at,
        )
    except ValueError as exc:
        # Translate scope / name validation failures to HTTP 400 with
        # a structured envelope that matches the spec-013 shape.
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": "validation_failed",
                "errorCode": "validation_failed",
                "details": str(exc),
            },
        ) from exc

    # Re-load the freshly-created row to fetch ``created_at``.
    row = (
        await db.execute(select(ApiKey).where(ApiKey.id == created.api_key_id))
    ).scalar_one()
    return CreatedApiKeyResponse(
        id=row.id,
        name=row.name,
        plaintext=created.plaintext,
        key_prefix=created.key_prefix,
        scopes=created.scopes,
        expires_at=created.expires_at,
        created_at=row.created_at,
    )


@router.delete(
    "/api-key/{api_key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke an API key. Idempotent.",
)
async def delete_my_api_key(
    api_key_id: int,
    principal: Annotated[Principal, Depends(require_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    # Refuse to delete keys that don't belong to the caller — admins
    # can revoke any key via the admin user-management endpoints in
    # a later slice.
    row = (
        await db.execute(select(ApiKey).where(ApiKey.id == api_key_id))
    ).scalar_one_or_none()
    if row is None or row.user_id != principal.user_id:
        # Same 404 for "not yours" and "doesn't exist" so the surface
        # doesn't leak the existence of other users' keys.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"errorMessage": "not_found", "errorCode": "not_found"},
        )

    await revoke_api_key(db, api_key_id=api_key_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------


def _set_session_cookie(
    response: Response,
    request: Request,
    session_id: str,
    expires_at: datetime,
) -> None:
    """Stamp the session cookie on the response.

    Per FR-010 / FR-012a:
      - HttpOnly + SameSite=Lax always
      - Secure when the request arrived over HTTPS
      - Max-Age = expires_at - now (mirrors the server-side expiry)
    """
    max_age = max(0, int((expires_at - datetime.now(UTC)).total_seconds()))
    is_secure = request.url.scheme == "https"
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=is_secure,
        path="/",
    )
