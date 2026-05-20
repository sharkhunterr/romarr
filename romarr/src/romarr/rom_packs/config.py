"""ROM-pack global config — the ``rom_pack_config`` singleton.

Slice 464. One get-or-create helper shared by the ingest
pipeline (reads the download dir + default size cap) and the
``/api/v3/rom-pack/config`` API surface (reads + writes them).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from romarr.domain.models import RomPackConfig

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

# The singleton's fixed primary key — the table's CHECK
# constraint pins it to 1.
_CONFIG_ID = 1


async def get_or_create_rom_pack_config(
    session: AsyncSession,
) -> RomPackConfig:
    """Return the singleton :class:`RomPackConfig` row, creating
    it with the schema defaults on first access.

    The caller owns the transaction — we ``flush`` the freshly
    inserted row so its server-side defaults are populated, but
    leave the ``commit`` to the caller so this composes inside a
    larger unit of work.
    """
    row = (
        await session.execute(
            select(RomPackConfig).where(RomPackConfig.id == _CONFIG_ID)
        )
    ).scalar_one_or_none()
    if row is not None:
        return row
    row = RomPackConfig(id=_CONFIG_ID)
    session.add(row)
    await session.flush()
    await session.refresh(row)
    return row


__all__ = ["get_or_create_rom_pack_config"]
