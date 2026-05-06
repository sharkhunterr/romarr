"""Indexer CRUD endpoints — /api/v3/indexer/*.

  - GET    /api/v3/indexer             — list
  - GET    /api/v3/indexer/schema      — Newznab + Torznab schema entries
  - POST   /api/v3/indexer             — create (?test=true runs caps + minimal search first)
  - GET    /api/v3/indexer/{id}        — read
  - PUT    /api/v3/indexer/{id}        — update; api_key re-encrypted only when present
  - DELETE /api/v3/indexer/{id}        — delete (notifies Prowlarr if pushed by it)
  - POST   /api/v3/indexer/{id}/test   — connectivity probe

All endpoints require the admin role (FR-026a).
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.indexers.client import NewznabClient
from romarr.indexers.connectivity import (
    ConnectivityTestResult,
    test_connectivity,
)
from romarr.indexers.models import Application, Indexer
from romarr.indexers.prowlarr import notify_prowlarr_change
from romarr.indexers.registry import IndexerRegistry
from romarr.indexers.schemas import (
    IndexerCreate,
    IndexerRead,
    IndexerSchemaEntry,
    IndexerUpdate,
)
from romarr.metadata.encryption import encrypt

router = APIRouter(prefix="/api/v3/indexer", tags=["Indexers"])

_REGISTRY = IndexerRegistry()


def _to_read(row: Indexer) -> IndexerRead:
    payload = {
        "id": row.id,
        "name": row.name,
        "implementation": row.implementation,
        "url": row.url,
        "is_configured": row.api_key_encrypted is not None,
        "categories": row.categories,
        "priority": row.priority,
        "enable_rss": row.enable_rss,
        "enable_automatic_search": row.enable_automatic_search,
        "enable_interactive_search": row.enable_interactive_search,
        "tags": row.tags,
        "rate_limit_seconds": row.rate_limit_seconds,
        "min_seeders": row.min_seeders,
        "download_client_id": row.download_client_id,
        "source": row.source,
        "prowlarr_app_id": row.prowlarr_app_id,
        "seed_ratio": float(row.seed_ratio) if row.seed_ratio is not None else None,
        "seed_time_minutes": row.seed_time_minutes,
        "discount_only": row.discount_only,
        "priority_indexer": row.priority_indexer,
        "timeout_seconds": row.timeout_seconds,
        "result_limit": row.result_limit,
        "last_health_at": row.last_health_at,
        "last_health_ok": row.last_health_ok,
        "last_health_error": row.last_health_error,
    }
    return IndexerRead.model_validate(payload)


def _client_from_create(payload: IndexerCreate) -> NewznabClient:
    """Build an in-memory NewznabClient (no DB row yet) for ``?test=true``."""
    return NewznabClient(
        indexer_id=0,  # ephemeral; never persisted
        name=payload.name,
        base_url=payload.url,
        api_key=payload.api_key,
        timeout_seconds=payload.timeout_seconds,
        result_limit=payload.result_limit,
    )


# ---------------------------------------------------------------------------
# Schema descriptor (Prowlarr-expected)
# ---------------------------------------------------------------------------


_NEWZNAB_FIELDS: list[dict[str, Any]] = [
    {"name": "baseUrl", "label": "URL", "type": "textbox"},
    {"name": "apiKey", "label": "API Key", "type": "textbox", "secret": True},
    {"name": "categories", "label": "Categories", "type": "select"},
    {
        "name": "rateLimitSeconds",
        "label": "Rate Limit (seconds)",
        "type": "number",
        "advanced": True,
    },
]


@router.get(
    "/schema",
    response_model=list[IndexerSchemaEntry],
    summary="Newznab + Torznab schema entries (Prowlarr expects this).",
)
async def schema_endpoint(
    _admin: Annotated[Principal, Depends(require_admin)],
) -> list[IndexerSchemaEntry]:
    return [
        IndexerSchemaEntry(
            implementation="newznab",
            implementation_name="Newznab",
            config_contract="NewznabSettings",
            fields=_NEWZNAB_FIELDS,
        ),
        IndexerSchemaEntry(
            implementation="torznab",
            implementation_name="Torznab",
            config_contract="TorznabSettings",
            fields=_NEWZNAB_FIELDS,
        ),
    ]


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[IndexerRead],
    summary="List configured indexers (admin only).",
)
async def list_indexers(
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[IndexerRead]:
    rows = (
        (await db.execute(select(Indexer).order_by(Indexer.id)))
        .scalars()
        .all()
    )
    return [_to_read(r) for r in rows]


@router.get(
    "/{indexer_id}",
    response_model=IndexerRead,
    summary="Read one indexer (admin only).",
)
async def read_indexer(
    indexer_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IndexerRead:
    row = await _get_or_404(db, indexer_id)
    return _to_read(row)


async def _get_or_404(db: AsyncSession, indexer_id: int) -> Indexer:
    row = (
        await db.execute(select(Indexer).where(Indexer.id == indexer_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "indexer_not_found",
                "errorCode": "not_found",
            },
        )
    return row


@router.post(
    "",
    response_model=IndexerRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an indexer (admin only). ``?test=true`` runs caps+search first.",
)
async def create_indexer(
    payload: IndexerCreate,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    test: bool = False,
) -> IndexerRead:
    if test:
        client = _client_from_create(payload)
        try:
            result = await test_connectivity(client)
        finally:
            await client.aclose()
        if not result.ok:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "errorMessage": "connectivity_failed",
                    "errorCode": result.category or "connectivity",
                    "details": result.message,
                },
            )

    encrypted = (
        encrypt(json.dumps(payload.api_key).encode())
        if payload.api_key
        else None
    )

    row = Indexer(
        name=payload.name,
        implementation=payload.implementation,
        url=payload.url,
        api_key_encrypted=encrypted,
        categories=payload.categories,
        priority=payload.priority,
        enable_rss=payload.enable_rss,
        enable_automatic_search=payload.enable_automatic_search,
        enable_interactive_search=payload.enable_interactive_search,
        tags=payload.tags,
        rate_limit_seconds=payload.rate_limit_seconds,
        min_seeders=payload.min_seeders,
        download_client_id=payload.download_client_id,
        source=payload.source,
        prowlarr_app_id=payload.prowlarr_app_id,
        seed_ratio=payload.seed_ratio,
        seed_time_minutes=payload.seed_time_minutes,
        discount_only=payload.discount_only,
        priority_indexer=payload.priority_indexer,
        timeout_seconds=payload.timeout_seconds,
        result_limit=payload.result_limit,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": "duplicate_indexer",
                "errorCode": "duplicate",
                "details": (
                    "an indexer is already registered for this "
                    "(implementation, url) pair"
                ),
            },
        ) from exc
    await db.refresh(row)
    return _to_read(row)


@router.put(
    "/{indexer_id}",
    response_model=IndexerRead,
    summary=(
        "Update an indexer (admin only). The ``api_key`` field is "
        "re-encrypted only when present in the body."
    ),
)
async def update_indexer(
    indexer_id: int,
    payload: IndexerUpdate,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IndexerRead:
    row = await _get_or_404(db, indexer_id)
    fields = payload.model_dump(exclude_unset=True)
    for key in (
        "name",
        "implementation",
        "url",
        "categories",
        "priority",
        "enable_rss",
        "enable_automatic_search",
        "enable_interactive_search",
        "tags",
        "rate_limit_seconds",
        "min_seeders",
        "download_client_id",
        "seed_ratio",
        "seed_time_minutes",
        "discount_only",
        "priority_indexer",
        "timeout_seconds",
        "result_limit",
    ):
        if key in fields:
            setattr(row, key, fields[key])
    if "api_key" in fields:
        new_key = fields["api_key"]
        row.api_key_encrypted = (
            encrypt(json.dumps(new_key).encode()) if new_key else None
        )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": "duplicate_indexer",
                "errorCode": "duplicate",
            },
        ) from exc
    await db.refresh(row)
    return _to_read(row)


@router.delete(
    "/{indexer_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an indexer (admin only). Notifies Prowlarr if pushed by it.",
)
async def delete_indexer(
    indexer_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    row = await _get_or_404(db, indexer_id)
    application: Application | None = None
    if row.source == "prowlarr" and row.prowlarr_app_id is not None:
        application = (
            await db.execute(
                select(Application).where(
                    Application.id == row.prowlarr_app_id
                )
            )
        ).scalar_one_or_none()

    await db.delete(row)
    await db.commit()

    if application is not None:
        async with httpx.AsyncClient(timeout=5.0) as transport:
            await notify_prowlarr_change(
                application,
                change="indexer_deleted",
                indexer_id=indexer_id,
                client=transport,
            )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{indexer_id}/test",
    response_model=ConnectivityTestResult,
    summary="Run caps + minimal search to confirm the indexer is reachable.",
)
async def test_indexer(
    indexer_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConnectivityTestResult:
    # Manual operator probes always start with a fresh breaker so
    # an earlier automatic-failure burst doesn't gate the retry —
    # otherwise the operator sees ``circuit_open`` indefinitely
    # without a way to recover.
    _REGISTRY.reset_breaker(indexer_id)
    client = await _REGISTRY.get(db, indexer_id=indexer_id)
    if client is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "indexer_not_found",
                "errorCode": "not_found",
            },
        )
    try:
        return await test_connectivity(client)
    finally:
        await client.aclose()


class _TestProbePayload(BaseModel):
    """Body for ``POST /api/v3/indexer/test`` — probes a transient
    set of values without persisting an Indexer row first.

    Used by the Create / Edit modals so the operator validates
    the URL + key combo before saving.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    implementation: Literal["newznab", "torznab"]
    url: Annotated[str, Field(min_length=1)]
    api_key: str | None = None


@router.post(
    "/test",
    response_model=ConnectivityTestResult,
    summary=(
        "Probe an unsaved (URL, api_key) pair without persisting an "
        "Indexer row. Used by the Create / Edit modals so operators "
        "validate connectivity before saving."
    ),
)
async def probe_indexer_payload(
    payload: _TestProbePayload,
    _admin: Annotated[Principal, Depends(require_admin)],
    _db: Annotated[AsyncSession, Depends(get_db)],
) -> ConnectivityTestResult:
    from romarr.identification.circuit_breaker import CircuitBreaker
    from romarr.indexers.rate_limiter import RateLimiter

    client = NewznabClient(
        indexer_id=0,
        name="probe",
        base_url=payload.url.rstrip("/"),
        api_key=payload.api_key,
        rate_limiter=RateLimiter(seconds=0.0),
        breaker=CircuitBreaker("probe"),
    )
    try:
        return await test_connectivity(client)
    finally:
        await client.aclose()
