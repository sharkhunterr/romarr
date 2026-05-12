"""POST /api/v3/indexer/grabarr — atomic "Add Grabarr" wizard.

Slice 427 / R3a. Operators who want to add a Grabarr instance go
through this single endpoint instead of the two-step
``POST /api/v3/downloadclient`` + ``POST /api/v3/indexer`` dance:

1. The wizard takes ``{name, base_url, profile_slug, api_key,
   timeout_seconds?, download_root?}``.
2. Probes Grabarr's ``/romarr/api/v1/health`` to validate
   reachability + protocol_version BEFORE persisting (refuses to
   persist on mismatch so a misconfigured row never reaches the
   queue).
3. Creates the ``download_client`` row first (the indexer's
   ``download_client_id`` FK requires the target to exist) and
   then the ``indexer`` row pointing at it, all under a single
   transaction. A failure between the two rolls everything back.

The two rows are deliberately linkable later — operators who want
to swap which downloader an indexer talks to can ``PUT
/api/v3/indexer/{id}`` with a different ``download_client_id``,
or delete one half without the other if they really want to.
"""

from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth.permissions import Principal
from romarr.downloaders.api.clients import _to_read as _client_to_read
from romarr.downloaders.implementations.grabarr_direct import (
    GrabarrDirectClient,
)
from romarr.downloaders.models import DownloadClient
from romarr.downloaders.schemas import DownloadClientRead
from romarr.downloaders.types import ClientType
from romarr.indexers.models import Indexer
from romarr.indexers.schemas import IndexerRead
from romarr.metadata.encryption import encrypt

router = APIRouter(prefix="/api/v3/indexer", tags=["Indexers — Grabarr"])


class GrabarrWizardRequest(BaseModel):
    """POST body for the atomic Add-Grabarr flow."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: Annotated[str, Field(min_length=1, max_length=128)]
    base_url: Annotated[str, Field(min_length=1, max_length=512)]
    profile_slug: Annotated[str, Field(min_length=1, max_length=128)]
    api_key: Annotated[str, Field(min_length=1, max_length=255)]
    timeout_seconds: Annotated[int, Field(ge=5, le=600)] = 60
    download_root: Annotated[str | None, Field(default=None, max_length=512)] = None


class GrabarrWizardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    indexer: IndexerRead
    download_client: DownloadClientRead


def _split_base_url(url: str) -> tuple[str, int, bool, str | None]:
    """Parse ``base_url`` into the column shape ``download_client``
    + ``indexer`` rows expect. Returns ``(host, port, use_ssl,
    url_base)``."""
    parts = urlsplit(url.rstrip("/"))
    if parts.scheme not in ("http", "https"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": "invalid_base_url",
                "errorCode": "bad_request",
                "details": "base_url must be http:// or https://",
            },
        )
    use_ssl = parts.scheme == "https"
    if not parts.hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": "invalid_base_url",
                "errorCode": "bad_request",
                "details": "base_url is missing a host",
            },
        )
    host = parts.hostname
    port = parts.port or (443 if use_ssl else 80)
    url_base = parts.path or None
    return host, port, use_ssl, url_base


async def _probe_connectivity(
    *,
    host: str,
    port: int,
    use_ssl: bool,
    url_base: str | None,
    api_key: str,
    timeout_seconds: int,
) -> str:
    """Run ``GrabarrDirectClient.test_connection`` against an
    ephemeral instance (no DB row yet). Returns the upstream
    version string on success; converts the typed errors into a
    structured 400."""
    probe = GrabarrDirectClient(
        client_id=0,
        name="__probe__",
        host=host,
        port=port,
        api_key=api_key,
        use_ssl=use_ssl,
        url_base=url_base,
        ssl_cert_validation="enabled",
        timeout_seconds=timeout_seconds,
    )
    try:
        return await probe.test_connection()
    except Exception as exc:  # noqa: BLE001 — fan out via type below
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": "grabarr_unreachable_or_incompatible",
                "errorCode": exc.__class__.__name__,
                "details": str(exc)[:500],
            },
        ) from exc


@router.post(
    "/grabarr",
    response_model=GrabarrWizardResponse,
    status_code=status.HTTP_201_CREATED,
    summary=(
        "Atomic Add-Grabarr wizard (admin only). Creates a linked "
        "download_client + indexer pair after a /health probe."
    ),
)
async def add_grabarr(
    payload: GrabarrWizardRequest,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GrabarrWizardResponse:
    host, port, use_ssl, url_base = _split_base_url(payload.base_url)

    # 1. Probe the Grabarr deploy before persisting anything —
    # protocol_version mismatch and bad apikeys never produce a
    # half-formed config that confuses the queue page later.
    grabarr_version = await _probe_connectivity(
        host=host, port=port, use_ssl=use_ssl,
        url_base=url_base, api_key=payload.api_key,
        timeout_seconds=payload.timeout_seconds,
    )

    api_key_encrypted = encrypt(payload.api_key.encode("utf-8"))

    # 2. Create the downloader row first — the indexer's
    # ``download_client_id`` FK requires the target to exist
    # (well, technically the column is nullable + FK-less today,
    # but ordering this way keeps the link valid for routing as
    # soon as the indexer row commits).
    client_row = DownloadClient(
        name=payload.name,
        type=ClientType.GRABARR_DIRECT.value,
        host=host,
        port=port,
        use_ssl=use_ssl,
        url_base=url_base,
        api_key_encrypted=api_key_encrypted,
        category_default="romarr",
        priority=1,
        # Grabarr-direct's add_torrent serves the http_direct
        # streamer + the magnet-misconfig safety net — both
        # belong to the torrent capability slot. Routing already
        # filters the magnet branch back out (slice 426) so this
        # being True is safe.
        enable_for_torrents=True,
        enable_for_usenet=False,
        enabled=True,
        client_version_seen=grabarr_version,
        timeout_seconds=payload.timeout_seconds,
        download_root=payload.download_root,
    )
    db.add(client_row)
    try:
        await db.flush()  # populates client_row.id
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": "duplicate_grabarr_client",
                "errorCode": "duplicate",
                "details": (
                    "a grabarr_direct download client already exists for "
                    "this (host, port)"
                ),
            },
        ) from exc

    # 3. Create the indexer row pinned to the downloader.
    indexer_url = f"{payload.base_url.rstrip('/')}/torznab/{payload.profile_slug}"
    indexer_row = Indexer(
        name=payload.name,
        implementation="grabarr",
        url=indexer_url,
        api_key_encrypted=api_key_encrypted,
        categories=[],
        priority=25,
        enable_rss=True,
        enable_automatic_search=True,
        enable_interactive_search=True,
        rate_limit_seconds=5,
        min_seeders=0,
        download_client_id=client_row.id,
        source="manual",
        timeout_seconds=payload.timeout_seconds,
        result_limit=100,
    )
    db.add(indexer_row)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": "duplicate_grabarr_indexer",
                "errorCode": "duplicate",
                "details": (
                    "a grabarr indexer already exists for this base_url + "
                    "profile_slug"
                ),
            },
        ) from exc
    await db.refresh(client_row)
    await db.refresh(indexer_row)

    return GrabarrWizardResponse(
        indexer=_indexer_to_read(indexer_row),
        download_client=_client_to_read(client_row),
    )


def _indexer_to_read(row: Indexer) -> IndexerRead:
    payload: dict[str, Any] = {
        "id": row.id,
        "name": row.name,
        "implementation": row.implementation,
        "url": row.url,
        "is_configured": row.api_key_encrypted is not None,
        "categories": row.categories or [],
        "priority": row.priority,
        "enabled": row.enabled,
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


__all__ = [
    "GrabarrWizardRequest",
    "GrabarrWizardResponse",
    "router",
]
