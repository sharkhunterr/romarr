"""Helpers that materialize exporter value types from the ORM.

The renderers themselves (e.g. :func:`render_gamelist_xml`) are pure —
they consume immutable value types and emit bytes. These helpers
bridge the SQLAlchemy session to those value types so the manual-run
endpoint and the per-import dispatch share one materialization path.

Today we ship the ESDE materializer; Pegasus and LaunchBox follow
the same pattern (preload Game + Release + Dump, project to value
type) and land with their respective slices.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select

from romarr.domain.models import Dump, Game, Platform, Release
from romarr.libraries.exporters.esde import EsdeGame
from romarr.libraries.models import Library

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def materialize_esde_games(
    *,
    session: AsyncSession,
    library_id: int,
    platform_slug: str,
) -> list[EsdeGame]:
    """Project every imported Game on (library, platform) to
    :class:`EsdeGame`.

    Each row's rom_path is computed relative to
    ``<library>/<platform_slug>/`` — the directory where the
    gamelist.xml lives. Games without a Dump (Wanted releases) are
    excluded; ES-DE only catalogs files that physically exist.
    """
    library = await session.get(Library, library_id)
    if library is None:
        return []

    platform = (
        await session.execute(
            select(Platform).where(Platform.slug == platform_slug)
        )
    ).scalar_one_or_none()
    if platform is None:
        return []

    target_dir = Path(library.path) / platform_slug

    rows = (
        await session.execute(
            select(Game, Release, Dump)
            .join(Release, Release.game_id == Game.id)
            .join(Dump, Dump.release_id == Release.id)
            .where(
                Game.platform_id == platform.id,
                Release.library_id == library_id,
            )
            .order_by(Game.title, Release.id)
        )
    ).all()

    out: list[EsdeGame] = []
    seen_slugs: set[str] = set()
    for game, _release, dump in rows:
        if game.slug in seen_slugs:
            continue
        seen_slugs.add(game.slug)
        dump_path = Path(dump.path)
        try:
            rom_relative = dump_path.relative_to(target_dir)
        except ValueError:
            rom_relative = Path(dump_path.name)
        out.append(
            EsdeGame(
                slug=game.slug,
                title=game.title,
                rom_path=f"./{rom_relative}",
            )
        )
    return out


__all__ = ["materialize_esde_games"]
