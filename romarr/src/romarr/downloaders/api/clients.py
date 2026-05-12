"""Download-client CRUD + /test endpoints — /api/v3/downloadclient/*.

  - GET    /api/v3/downloadclient             — list
  - POST   /api/v3/downloadclient             — create (?test=true probes connectivity first)
  - GET    /api/v3/downloadclient/{id}        — read
  - PUT    /api/v3/downloadclient/{id}        — update; password/api_key
                                                re-encrypted only when present
  - DELETE /api/v3/downloadclient/{id}        — delete
  - POST   /api/v3/downloadclient/{id}/test   — connectivity probe

All endpoints require the admin role (FR-026a / CL005). Encrypted
credential blobs NEVER appear in any read response regardless of
caller role — :func:`_to_read` projects the row to
:class:`DownloadClientRead` which has no ``*_encrypted`` field.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.downloaders.connectivity import test_connectivity
from romarr.downloaders.factory import build_client_from_row
from romarr.downloaders.implementations import (
    QBittorrentClient,
    SabnzbdClient,
)
from romarr.downloaders.models import DownloadClient as DownloadClientRow
from romarr.downloaders.schemas import (
    DownloadClientCreate,
    DownloadClientRead,
    DownloadClientUpdate,
)
from romarr.downloaders.tls import SslCertValidation
from romarr.downloaders.types import ClientType, ConnectivityTestResult
from romarr.metadata.encryption import encrypt

router = APIRouter(prefix="/api/v3/downloadclient", tags=["DownloadClients"])


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------


def _to_read(row: DownloadClientRow) -> DownloadClientRead:
    is_configured = (
        row.password_encrypted is not None
        if row.type == ClientType.QBITTORRENT.value
        else row.api_key_encrypted is not None
        if row.type == ClientType.SABNZBD.value
        else False
    )
    return DownloadClientRead.model_validate(
        {
            "id": row.id,
            "name": row.name,
            "type": row.type,
            "host": row.host,
            "port": row.port,
            "use_ssl": row.use_ssl,
            "url_base": row.url_base,
            "username": row.username,
            "is_configured": is_configured,
            "category_default": row.category_default,
            "tags": row.tags,
            "priority": row.priority,
            "enable_for_torrents": row.enable_for_torrents,
            "enable_for_usenet": row.enable_for_usenet,
            "enabled": row.enabled,
            "remove_completed_downloads": row.remove_completed_downloads,
            "remove_failed_downloads": row.remove_failed_downloads,
            "ssl_cert_validation": row.ssl_cert_validation,
            "last_health_at": row.last_health_at,
            "last_health_ok": row.last_health_ok,
            "last_health_error": row.last_health_error,
            "client_version_seen": row.client_version_seen,
            "timeout_seconds": row.timeout_seconds,
        }
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_or_404(db: AsyncSession, client_id: int) -> DownloadClientRow:
    row = (
        await db.execute(
            select(DownloadClientRow).where(DownloadClientRow.id == client_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "download_client_not_found",
                "errorCode": "not_found",
            },
        )
    return row


def _ephemeral_client_from_create(
    payload: DownloadClientCreate,
) -> QBittorrentClient | SabnzbdClient:
    """Build an in-memory client (no DB row yet) for ``?test=true``.

    The stub types are gated upstream by
    :class:`DownloadClientCreate`'s validators (qbit needs creds, sab
    needs api_key); a stub-typed payload would have failed validation.
    """
    if payload.type is ClientType.QBITTORRENT:
        # Slice 379 — qBit credentials are optional (subnet
        # auth-bypass workflow). Empty strings POST to
        # ``/auth/login`` and qBit returns 204 when the caller
        # falls inside ``WebUI\AuthSubnetWhitelist``; the schema
        # validator already rejected the half-set case so we
        # only see "both" or "neither" here.
        return QBittorrentClient(
            client_id=0,
            name=payload.name,
            host=payload.host,
            port=payload.port,
            username=payload.username or "",
            password=payload.password or "",
            use_ssl=payload.use_ssl,
            url_base=payload.url_base,
            ssl_cert_validation=payload.ssl_cert_validation,
            category_default=payload.category_default,
            timeout_seconds=payload.timeout_seconds,
        )
    if payload.type is ClientType.SABNZBD:
        assert payload.api_key is not None
        return SabnzbdClient(
            client_id=0,
            name=payload.name,
            host=payload.host,
            port=payload.port,
            api_key=payload.api_key,
            use_ssl=payload.use_ssl,
            url_base=payload.url_base,
            ssl_cert_validation=payload.ssl_cert_validation,
            category_default=payload.category_default,
            timeout_seconds=payload.timeout_seconds,
        )
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "errorMessage": "stub_implementation_not_configurable",
            "errorCode": "unavailable",
            "details": (
                f"{payload.type.value} is deferred to v1 and cannot be configured"
            ),
        },
    )


def _connectivity_failure(result: ConnectivityTestResult) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "errorMessage": "connectivity_failed",
            "errorCode": result.error_code or "connectivity",
            "details": result.error_message,
        },
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[DownloadClientRead],
    summary="List configured download clients (admin only).",
)
async def list_clients(
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[DownloadClientRead]:
    rows = (
        (
            await db.execute(
                select(DownloadClientRow).order_by(DownloadClientRow.id)
            )
        )
        .scalars()
        .all()
    )
    return [_to_read(r) for r in rows]


@router.get(
    "/{client_id}",
    response_model=DownloadClientRead,
    summary="Read one download client (admin only).",
)
async def read_client(
    client_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DownloadClientRead:
    return _to_read(await _get_or_404(db, client_id))


@router.post(
    "",
    response_model=DownloadClientRead,
    status_code=status.HTTP_201_CREATED,
    summary=(
        "Create a download client (admin only). ``?test=true`` runs "
        "connectivity probe before persistence."
    ),
)
async def create_client(
    payload: DownloadClientCreate,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    test: bool = False,
) -> DownloadClientRead:
    if test:
        result = await test_connectivity(_ephemeral_client_from_create(payload))
        if not result.ok:
            raise _connectivity_failure(result)

    password_encrypted = (
        encrypt(payload.password.encode("utf-8")) if payload.password else None
    )
    api_key_encrypted = (
        encrypt(payload.api_key.encode("utf-8")) if payload.api_key else None
    )

    row = DownloadClientRow(
        name=payload.name,
        type=payload.type.value,
        host=payload.host,
        port=payload.port,
        use_ssl=payload.use_ssl,
        url_base=payload.url_base,
        username=payload.username,
        password_encrypted=password_encrypted,
        api_key_encrypted=api_key_encrypted,
        category_default=payload.category_default,
        tags=payload.tags,
        priority=payload.priority,
        enable_for_torrents=payload.enable_for_torrents,
        enable_for_usenet=payload.enable_for_usenet,
        enabled=payload.enabled,
        remove_completed_downloads=payload.remove_completed_downloads,
        remove_failed_downloads=payload.remove_failed_downloads,
        ssl_cert_validation=payload.ssl_cert_validation,
        timeout_seconds=payload.timeout_seconds,
    )
    db.add(row)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": "duplicate_download_client",
                "errorCode": "duplicate",
                "details": (
                    "a download client is already registered for this "
                    "(type, host, port) tuple"
                ),
            },
        ) from exc
    await db.refresh(row)
    return _to_read(row)


@router.put(
    "/{client_id}",
    response_model=DownloadClientRead,
    summary=(
        "Update a download client (admin only). ``password`` / ``api_key`` "
        "are re-encrypted only when present in the body."
    ),
)
async def update_client(
    client_id: int,
    payload: DownloadClientUpdate,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DownloadClientRead:
    row = await _get_or_404(db, client_id)
    fields = payload.model_dump(exclude_unset=True)

    for key in (
        "name",
        "host",
        "port",
        "use_ssl",
        "url_base",
        "username",
        "category_default",
        "tags",
        "priority",
        "enable_for_torrents",
        "enable_for_usenet",
        "enabled",
        "remove_completed_downloads",
        "remove_failed_downloads",
        "timeout_seconds",
    ):
        if key in fields:
            setattr(row, key, fields[key])

    if "ssl_cert_validation" in fields:
        ssl_value: SslCertValidation = fields["ssl_cert_validation"]
        row.ssl_cert_validation = ssl_value

    if "password" in fields:
        plaintext = fields["password"]
        row.password_encrypted = (
            encrypt(plaintext.encode("utf-8")) if plaintext else None
        )
    if "api_key" in fields:
        plaintext = fields["api_key"]
        row.api_key_encrypted = (
            encrypt(plaintext.encode("utf-8")) if plaintext else None
        )

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "errorMessage": "duplicate_download_client",
                "errorCode": "duplicate",
            },
        ) from exc
    await db.refresh(row)
    return _to_read(row)


@router.delete(
    "/{client_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a download client (admin only).",
)
async def delete_client(
    client_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    row = await _get_or_404(db, client_id)
    await db.delete(row)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{client_id}/test",
    response_model=ConnectivityTestResult,
    summary="Run a connectivity probe against the configured client (admin only).",
)
async def test_client(
    client_id: int,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConnectivityTestResult:
    row = await _get_or_404(db, client_id)
    impl = build_client_from_row(row)
    return await test_connectivity(impl)


@router.post(
    "/test",
    response_model=ConnectivityTestResult,
    summary=(
        "Probe an unsaved download-client payload without persisting "
        "a row. Used by the Create / Edit modals so operators can "
        "validate connectivity before saving."
    ),
)
async def probe_client_payload(
    payload: DownloadClientCreate,
    _admin: Annotated[Principal, Depends(require_admin)],
    _db: Annotated[AsyncSession, Depends(get_db)],
) -> ConnectivityTestResult:
    impl = _ephemeral_client_from_create(payload)
    return await test_connectivity(impl)
