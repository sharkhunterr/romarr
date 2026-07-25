"""Platform-pack global config — the ``platform_pack_config`` singleton.

Mirrors the ``rom_pack_config`` pattern: one row (id=1) holding the
operator's toggles for the builtin pack and the priority resolution
between builtin and community sources.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from romarr.platform_packs.models import PlatformPackConfig

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_CONFIG_ID = 1


async def get_or_create_platform_pack_config(
    session: AsyncSession,
) -> PlatformPackConfig:
    """Return the singleton, creating it with schema defaults on first read.

    Caller owns the transaction. Freshly-inserted rows are flushed +
    refreshed so their server-side defaults are visible on the returned
    object, but the commit belongs to the caller.
    """
    row = (
        await session.execute(
            select(PlatformPackConfig).where(PlatformPackConfig.id == _CONFIG_ID)
        )
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = PlatformPackConfig(id=_CONFIG_ID)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


__all__ = ["get_or_create_platform_pack_config"]
