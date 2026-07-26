"""Admin endpoints for metadata-provider configuration.

  - GET    /api/v3/metadata/provider              — list every config row
  - GET    /api/v3/metadata/provider/{name}       — read one
  - PUT    /api/v3/metadata/provider/{name}       — update toggle / config /
                                                    rate-limit / TTL.
  - POST   /api/v3/metadata/provider/{name}/test  — ``health_check()`` probe

The provider list is fixed (the ``KNOWN_PROVIDERS`` enum); we don't
support **creation** — every row was inserted by migration 0002. The
endpoints simply update the seeded rows.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.metadata import (
    PROVIDER_REGISTRY,
    decrypt,
    encrypt,
)
from romarr.metadata.models import KNOWN_PROVIDERS, MetadataProviderConfig

router = APIRouter(prefix="/api/v3/metadata/provider", tags=["Metadata"])


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


class ProviderConfigRead(_Base):
    provider_name: str
    enabled: bool
    is_configured: bool
    priority_global: int
    cache_ttl_seconds: int
    rate_limit_rps: int
    rate_limit_burst: int
    last_health_check_at: datetime | None
    last_health_check_ok: bool | None


class ProviderConfigUpdate(_Base):
    enabled: bool | None = None
    config: dict[str, Any] | None = Field(default=None)
    priority_global: int | None = Field(default=None, ge=1, le=999)
    cache_ttl_seconds: int | None = Field(default=None, ge=60, le=2_592_000 * 12)
    rate_limit_rps: int | None = Field(default=None, ge=1, le=100)
    rate_limit_burst: int | None = Field(default=None, ge=1, le=1000)


class ProviderTestResponse(_Base):
    provider_name: str
    ok: bool
    error: str | None = None


def _to_read(row: MetadataProviderConfig) -> ProviderConfigRead:
    return ProviderConfigRead(
        provider_name=row.provider_name,
        enabled=row.enabled,
        is_configured=row.config_encrypted is not None,
        priority_global=row.priority_global,
        cache_ttl_seconds=row.cache_ttl_seconds,
        rate_limit_rps=row.rate_limit_rps,
        rate_limit_burst=row.rate_limit_burst,
        last_health_check_at=row.last_health_check_at,
        last_health_check_ok=row.last_health_check_ok,
    )


async def _get_or_404(
    db: AsyncSession, provider_name: str
) -> MetadataProviderConfig:
    if provider_name not in KNOWN_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "unknown_provider",
                "errorCode": "unknown_provider",
            },
        )
    row = (
        await db.execute(
            select(MetadataProviderConfig).where(
                MetadataProviderConfig.provider_name == provider_name
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "not_found",
                "errorCode": "not_found",
            },
        )
    return row


@router.get(
    "",
    response_model=list[ProviderConfigRead],
    summary="List every metadata provider's config (admin only).",
)
async def list_providers(
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ProviderConfigRead]:
    rows = (
        (
            await db.execute(
                select(MetadataProviderConfig).order_by(
                    MetadataProviderConfig.priority_global
                )
            )
        )
        .scalars()
        .all()
    )
    return [_to_read(r) for r in rows]


@router.get(
    "/{provider_name}",
    response_model=ProviderConfigRead,
    summary="Read one metadata provider's config (admin only).",
)
async def read_provider(
    provider_name: str,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProviderConfigRead:
    return _to_read(await _get_or_404(db, provider_name))


@router.get(
    "/{provider_name}/secrets",
    response_model=dict[str, Any],
    summary=(
        "Return a provider's DECRYPTED config as a plain JSON object "
        "(admin only). Used by the UI to pre-fill the configure modal "
        "so operators can edit an existing key without re-typing it. "
        "``{}`` if the provider isn't configured yet."
    ),
)
async def read_provider_secrets(
    provider_name: str,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    row = await _get_or_404(db, provider_name)
    if row.config_encrypted is None:
        return {}
    try:
        return json.loads(decrypt(row.config_encrypted).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 — surface the cause safely
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "errorMessage": "decrypt_failed",
                "errorCode": "decrypt_failed",
                "details": str(exc),
            },
        ) from exc


@router.put(
    "/{provider_name}",
    response_model=ProviderConfigRead,
    summary="Update a metadata provider's toggle / config / limits (admin only).",
)
async def update_provider(
    provider_name: str,
    payload: ProviderConfigUpdate,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProviderConfigRead:
    row = await _get_or_404(db, provider_name)
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.priority_global is not None:
        row.priority_global = payload.priority_global
    if payload.cache_ttl_seconds is not None:
        row.cache_ttl_seconds = payload.cache_ttl_seconds
    if payload.rate_limit_rps is not None:
        row.rate_limit_rps = payload.rate_limit_rps
    if payload.rate_limit_burst is not None:
        row.rate_limit_burst = payload.rate_limit_burst
    if payload.config is not None:
        row.config_encrypted = encrypt(json.dumps(payload.config).encode("utf-8"))
    await db.commit()
    await db.refresh(row)
    return _to_read(row)


@router.post(
    "/{provider_name}/test",
    response_model=ProviderTestResponse,
    summary="Probe a configured provider's reachability (admin only).",
)
async def test_provider(
    provider_name: str,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProviderTestResponse:
    row = await _get_or_404(db, provider_name)
    cls = PROVIDER_REGISTRY.get(provider_name)
    if cls is None:
        return ProviderTestResponse(
            provider_name=provider_name,
            ok=False,
            error="provider_not_implemented",
        )
    if row.config_encrypted is None:
        return ProviderTestResponse(
            provider_name=provider_name,
            ok=False,
            error="not_configured",
        )
    config = json.loads(decrypt(row.config_encrypted).decode("utf-8"))
    provider = cls(
        rate_limit_rps=row.rate_limit_rps,
        rate_limit_burst=row.rate_limit_burst,
    )
    try:
        provider.configure(config)
        ok = await provider.health_check()
    except Exception as exc:
        return ProviderTestResponse(
            provider_name=provider_name,
            ok=False,
            error=str(exc),
        )
    return ProviderTestResponse(provider_name=provider_name, ok=ok)
