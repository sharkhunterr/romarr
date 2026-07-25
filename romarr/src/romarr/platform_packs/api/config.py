"""Platform-pack config endpoints — /api/v3/rom/platform-pack-config.

  - GET   /api/v3/rom/platform-pack-config    — read (admin)
  - PATCH /api/v3/rom/platform-pack-config    — update (admin)

Two knobs :

  * ``builtin_enabled`` — bool, gates the boot-time auto-apply of
    the wheel-bundled builtin pack.
  * ``priority`` — ``"builtin"`` | ``"community"``. Which side wins
    when the same slug lives in both packs.

Changes to ``builtin_enabled`` take effect on next boot ; changes
to ``priority`` take effect on the next community sync.
"""
from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin, require_readonly
from romarr.auth import Principal
from romarr.platform_packs.config import get_or_create_platform_pack_config

router = APIRouter(
    prefix="/api/v3/rom/platform-pack-config",
    tags=["Platform Packs"],
)


class ConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    builtin_enabled: bool
    priority: Literal["builtin", "community"]


class ConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    builtin_enabled: bool | None = None
    priority: Literal["builtin", "community"] | None = None


@router.get(
    "",
    response_model=ConfigResponse,
    summary="Read the platform-pack config singleton.",
)
async def get_config(
    _principal: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConfigResponse:
    row = await get_or_create_platform_pack_config(db)
    await db.commit()
    return ConfigResponse.model_validate(row)


@router.patch(
    "",
    response_model=ConfigResponse,
    summary="Update the builtin toggle and/or priority (admin).",
)
async def update_config(
    payload: ConfigUpdate,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ConfigResponse:
    row = await get_or_create_platform_pack_config(db)
    if payload.builtin_enabled is not None:
        row.builtin_enabled = payload.builtin_enabled
    if payload.priority is not None:
        row.priority = payload.priority
    await db.commit()
    await db.refresh(row)
    return ConfigResponse.model_validate(row)


__all__ = ["router"]
