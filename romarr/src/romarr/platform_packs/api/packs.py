"""Pack-lifecycle endpoints — /api/v3/rom/platform-pack/*.

  - POST   /api/v3/rom/platform-pack             — multipart upload + apply
  - GET    /api/v3/rom/platform-pack             — list (most-recent first)
  - GET    /api/v3/rom/platform-pack/{ver}       — detail + audit history
  - POST   /api/v3/rom/platform-pack/{ver}/apply — re-apply a known pack
  - POST   /api/v3/rom/platform-pack/validate    — dry-run, never writes

All endpoints require the ``admin`` role from spec 010 (FR-026a).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Annotated, Any

import yaml
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    status,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.api.dependencies import get_db, get_sessionmaker, require_admin
from romarr.auth import Principal
from romarr.domain.models import PlatformPack
from romarr.platform_packs import (
    IngestSource,
    PackUploadResult,
    PackValidationError,
    PackVersionConflictError,
    SchemaVersionTooHighError,
    ValidateResult,
    ingest_pack,
)
from romarr.platform_packs.models import PlatformPackApplicationLog
from romarr.platform_packs.snapshot import (
    compute_platform_diff,
    load_snapshot,
)
from romarr.platform_packs.validator import validate_pack
from romarr.platform_packs.yaml_loader import (
    MAX_PACK_BYTES,
    compute_contents_hash,
    load_pack,
)

router = APIRouter(prefix="/api/v3/rom/platform-pack", tags=["Platform Packs"])


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


class PackSummary(_Base):
    pack_version: str
    schema_version: int
    description: str | None
    author: str | None
    pack_source: str
    contents_hash: str
    applied_at: datetime
    applied_by: str


class PackHistoryRow(_Base):
    id: int
    action: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    platforms_affected: list[str]
    parsing_strategies_affected: list[str]
    error_message: str | None
    applied_by: str | None


class PackDetail(PackSummary):
    source_url: str | None
    history: list[PackHistoryRow] = Field(default_factory=list)


def _pack_to_summary(row: PlatformPack) -> PackSummary:
    return PackSummary(
        pack_version=row.pack_version,
        schema_version=row.schema_version,
        description=row.description,
        author=row.author,
        pack_source=row.pack_source,
        contents_hash=row.contents_hash,
        applied_at=row.applied_at,
        applied_by=row.applied_by,
    )


def _validation_error_to_400(exc: PackValidationError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={
            "errorMessage": "pack_validation_failed",
            "errorCode": "validation_failed",
            "details": [
                {"path": v.path, "message": v.message, "code": v.code}
                for v in exc.violations
            ]
            or str(exc),
        },
    )


async def _read_upload(file: UploadFile) -> bytes:
    body = await file.read()
    if len(body) > MAX_PACK_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail={
                "errorMessage": "pack_too_large",
                "errorCode": "pack_too_large",
                "details": (
                    f"pack body is {len(body)} bytes; "
                    f"maximum allowed is {MAX_PACK_BYTES} bytes (1 MiB)"
                ),
            },
        )
    return body


def _ingest_with_http_translation(
    body: bytes,
    *,
    source: IngestSource,
) -> Callable[
    [AsyncSession, async_sessionmaker[AsyncSession]],
    Awaitable[PackUploadResult],
]:
    """Wrap the ingestor's typed exceptions into HTTPExceptions.

    Returns a coroutine — the FastAPI handler awaits it. Centralising
    the translation here keeps the upload + re-apply endpoints DRY.
    """

    async def _go(db: AsyncSession, sm: async_sessionmaker[AsyncSession]) -> PackUploadResult:
        try:
            return await ingest_pack(db, sessionmaker=sm, content=body, source=source)
        except PackVersionConflictError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "errorMessage": "pack_version_conflict",
                    "errorCode": "pack_version_conflict",
                    "details": str(exc),
                },
            ) from exc
        except SchemaVersionTooHighError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "errorMessage": "schema_version_too_high",
                    "errorCode": "schema_version_too_high",
                    "details": str(exc),
                },
            ) from exc
        except PackValidationError as exc:
            raise _validation_error_to_400(exc) from exc

    return _go


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=PackUploadResult,
    status_code=status.HTTP_200_OK,
    summary="Upload + apply a community pack (admin only).",
)
async def upload_pack(
    admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    sessionmaker: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_sessionmaker)
    ],
    file: Annotated[UploadFile, File(description="The YAML pack body")],
) -> PackUploadResult:
    body = await _read_upload(file)
    source = IngestSource(pack_source="community", applied_by=str(admin.user_id))
    return await _ingest_with_http_translation(body, source=source)(db, sessionmaker)


# ---------------------------------------------------------------------------
# List + detail
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[PackSummary],
    summary="List every persisted platform pack (admin only).",
)
async def list_packs(
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PackSummary]:
    rows = (
        (
            await db.execute(
                select(PlatformPack).order_by(PlatformPack.applied_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_pack_to_summary(r) for r in rows]


@router.get(
    "/{pack_version}",
    response_model=PackDetail,
    summary="Detail + audit history for a single pack (admin only).",
)
async def read_pack(
    pack_version: str,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PackDetail:
    row = (
        await db.execute(
            select(PlatformPack).where(PlatformPack.pack_version == pack_version)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "pack_not_found",
                "errorCode": "not_found",
                "details": f"no pack at version {pack_version!r}",
            },
        )
    history_rows = (
        (
            await db.execute(
                select(PlatformPackApplicationLog)
                .where(PlatformPackApplicationLog.pack_version == pack_version)
                .order_by(PlatformPackApplicationLog.id.desc())
            )
        )
        .scalars()
        .all()
    )
    detail = _pack_to_summary(row).model_dump()
    detail["source_url"] = row.source_url
    detail["history"] = [
        PackHistoryRow.model_validate(h) for h in history_rows
    ]
    return PackDetail.model_validate(detail)


# ---------------------------------------------------------------------------
# Re-apply
# ---------------------------------------------------------------------------


@router.post(
    "/{pack_version}/apply",
    response_model=PackUploadResult,
    summary="Re-apply a known pack (idempotent skip if state matches).",
)
async def reapply_pack(
    pack_version: str,
    admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    sessionmaker: Annotated[
        async_sessionmaker[AsyncSession], Depends(get_sessionmaker)
    ],
) -> PackUploadResult:
    """Re-applying without the body is only meaningful when the pack
    body is reachable from the original source — at MVP we mark this
    endpoint as ``not_implemented`` because we don't persist pack
    bodies. The endpoint signature is locked in so callers can target
    a stable URL; a v1+ slice can store ``platform_pack.body`` and
    drop in the real implementation."""
    row = (
        await db.execute(
            select(PlatformPack).where(PlatformPack.pack_version == pack_version)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "errorMessage": "pack_not_found",
                "errorCode": "not_found",
                "details": f"no pack at version {pack_version!r}",
            },
        )
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "errorMessage": "reapply_requires_body",
            "errorCode": "not_implemented",
            "details": (
                "MVP doesn't persist pack bodies; re-upload the YAML to "
                "the POST endpoint. Re-apply by reference lands in v1+."
            ),
        },
    )


# ---------------------------------------------------------------------------
# Validate-only (no DB writes)
# ---------------------------------------------------------------------------


@router.post(
    "/validate",
    response_model=ValidateResult,
    summary="Validate a pack without applying it (admin only).",
)
async def validate_only(
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
    file: Annotated[UploadFile, File(description="The YAML pack body")],
) -> ValidateResult:
    body = await _read_upload(file)
    started = datetime.now(UTC)

    try:
        snapshot = await load_snapshot(db)
        existing_slugs = set(snapshot.platforms_by_slug)

        try:
            parsed = validate_pack(body, existing_slugs=existing_slugs)
        except (PackValidationError, SchemaVersionTooHighError) as exc:
            # Surface the violations BUT keep the contract of "no DB writes":
            # parse what we can to compute pack_version / hash; failure to
            # parse means we synthesize empty values.
            try:
                parsed_dict = load_pack(body)
            except yaml.YAMLError:
                parsed_dict = {}
            return ValidateResult(
                pack_version=str(parsed_dict.get("pack_version") or "<invalid>"),
                contents_hash=compute_contents_hash(parsed_dict)
                if parsed_dict
                else "",
                action="would_fail",
                diff=[],
                parsing_strategies_affected=[],
                started_at=started,
                finished_at=datetime.now(UTC),
                database_state_unchanged=True,
                error_message=str(exc),
            )
    except Exception as exc:  # pragma: no cover — guard
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "errorMessage": "validate_internal_error",
                "errorCode": "internal_error",
                "details": str(exc),
            },
        ) from exc

    diff = compute_platform_diff(parsed.parsed.get("platforms") or [], snapshot)
    parsing_strategies_affected = [
        s["id"] for s in parsed.parsed.get("parsing_strategies") or []
    ]
    # Decide ``would_apply`` vs ``would_skip`` by checking whether
    # this (pack_version, contents_hash) is already on file.
    existing = (
        await db.execute(
            select(PlatformPack).where(
                PlatformPack.pack_version == parsed.pack_version
            )
        )
    ).scalar_one_or_none()
    action: Any
    if existing is not None and existing.contents_hash == parsed.contents_hash:
        action = "would_skip"
    elif existing is not None:
        action = "would_fail"
        return ValidateResult(
            pack_version=parsed.pack_version,
            contents_hash=parsed.contents_hash,
            action=action,
            diff=diff,
            parsing_strategies_affected=parsing_strategies_affected,
            started_at=started,
            finished_at=datetime.now(UTC),
            database_state_unchanged=True,
            error_message=(
                f"pack version {parsed.pack_version!r} already exists with a "
                "different contents_hash; the upload would be rejected"
            ),
        )
    else:
        action = "would_apply"

    return ValidateResult(
        pack_version=parsed.pack_version,
        contents_hash=parsed.contents_hash,
        action=action,
        diff=diff,
        parsing_strategies_affected=parsing_strategies_affected,
        started_at=started,
        finished_at=datetime.now(UTC),
        database_state_unchanged=True,
    )
