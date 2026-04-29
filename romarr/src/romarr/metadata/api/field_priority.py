"""Admin endpoints for the per-field provider priority list.

  - GET /api/v3/metadata/field-priority             — full layout grouped
                                                       by field
  - PUT /api/v3/metadata/field-priority/{field}     — replace the ordered
                                                       provider list for one
                                                       field; updates ranks
                                                       atomically.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.metadata.models import KNOWN_PROVIDERS, FieldPriority

router = APIRouter(prefix="/api/v3/metadata/field-priority", tags=["Metadata"])


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


class FieldPriorityEntry(_Base):
    field_name: str
    providers: list[str]


class UpdateFieldPriorityRequest(_Base):
    providers: list[str]


@router.get(
    "",
    response_model=list[FieldPriorityEntry],
    summary="Return the per-field provider priority list (admin only).",
)
async def list_field_priority(
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[FieldPriorityEntry]:
    rows = (
        (
            await db.execute(
                select(FieldPriority).order_by(
                    FieldPriority.field_name, FieldPriority.priority_order
                )
            )
        )
        .scalars()
        .all()
    )
    grouped: dict[str, list[str]] = {}
    for row in rows:
        grouped.setdefault(row.field_name, []).append(row.provider_name)
    return [
        FieldPriorityEntry(field_name=name, providers=providers)
        for name, providers in grouped.items()
    ]


@router.put(
    "/{field_name}",
    response_model=FieldPriorityEntry,
    summary="Replace the ordered provider list for a single field (admin only).",
)
async def update_field_priority(
    field_name: str,
    payload: UpdateFieldPriorityRequest,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> FieldPriorityEntry:
    if not payload.providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": "providers_must_not_be_empty",
                "errorCode": "validation_failed",
            },
        )
    seen: set[str] = set()
    for provider_name in payload.providers:
        if provider_name not in KNOWN_PROVIDERS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "errorMessage": "unknown_provider",
                    "errorCode": "validation_failed",
                    "details": provider_name,
                },
            )
        if provider_name in seen:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "errorMessage": "duplicate_provider",
                    "errorCode": "validation_failed",
                    "details": provider_name,
                },
            )
        seen.add(provider_name)

    existing = (
        (
            await db.execute(
                select(FieldPriority).where(FieldPriority.field_name == field_name)
            )
        )
        .scalars()
        .all()
    )
    for row in existing:
        await db.delete(row)
    await db.flush()

    now = datetime.now(UTC)
    for order, provider_name in enumerate(payload.providers, start=1):
        db.add(
            FieldPriority(
                field_name=field_name,
                provider_name=provider_name,
                priority_order=order,
                updated_at=now,
            )
        )
    await db.commit()

    return FieldPriorityEntry(field_name=field_name, providers=list(payload.providers))
