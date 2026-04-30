"""Pegasus front-end ``metadata.txt`` writer.

Pegasus consumes a per-collection text file in a colon-separated
key/value format. Reference:
https://pegasus-frontend.org/docs/user-guide/meta-files/

The renderer is **pure** — it consumes a list of :class:`PegasusGame`
value types and emits the file body as bytes. The writer reuses
the shared atomic+lock helper so the per-output advisory lock and
the ``.tmp`` + ``os.replace`` atomic rename pattern carry over
identically from ES-DE (FR-017 + FR-017a, with a per-output lock
file name so Pegasus and ES-DE never block each other).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import StringIO
from typing import TYPE_CHECKING

from romarr.libraries.exporters._atomic import write_atomic_with_lock

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


@dataclass(frozen=True)
class PegasusCollection:
    """Header block at the top of ``metadata.txt`` describing the
    collection (one per file)."""

    name: str
    shortname: str
    extensions: tuple[str, ...]


@dataclass(frozen=True)
class PegasusGame:
    """One game block in ``metadata.txt``.

    ``rom_path`` is relative to the metadata.txt's directory (a
    Pegasus convention so collection files relocate cleanly).
    ``rating`` is the same 0..1 float as ES-DE; we render it as a
    percentage to match Pegasus's expected ``XX%`` format.
    """

    title: str
    rom_path: str
    description: str | None = None
    developer: str | None = None
    publisher: str | None = None
    genres: tuple[str, ...] = ()
    release_date: datetime | None = None
    players_min: int | None = None
    players_max: int | None = None
    rating: float | None = None
    cover_relative: str | None = None


def _line(buf: StringIO, key: str, value: str) -> None:
    buf.write(f"{key}: {value}\n")


def _format_players(low: int | None, high: int | None) -> str | None:
    if low is None and high is None:
        return None
    if low is not None and high is not None:
        return f"{low}-{high}" if high > low else str(low)
    return str(low if low is not None else high)


def render_metadata_txt(
    collection: PegasusCollection,
    games: Sequence[PegasusGame],
) -> bytes:
    """Build the metadata.txt body. Pure: deterministic for a given
    input, no I/O.

    Order: header block → blank line → one ``game:`` block per
    game, separated by blank lines.
    """
    buf = StringIO()
    _line(buf, "collection", collection.name)
    _line(buf, "shortname", collection.shortname)
    _line(buf, "extensions", ", ".join(collection.extensions))

    for game in games:
        buf.write("\n")
        _line(buf, "game", game.title)
        _line(buf, "file", game.rom_path)
        if game.description:
            _line(buf, "description", game.description)
        if game.developer:
            _line(buf, "developer", game.developer)
        if game.publisher:
            _line(buf, "publisher", game.publisher)
        if game.genres:
            _line(buf, "genre", ", ".join(game.genres))
        if game.release_date is not None:
            _line(buf, "release", game.release_date.strftime("%Y-%m-%d"))
        players = _format_players(game.players_min, game.players_max)
        if players is not None:
            _line(buf, "players", players)
        if game.rating is not None:
            _line(buf, "rating", f"{round(game.rating * 100)}%")
        if game.cover_relative:
            _line(buf, "assets.boxFront", game.cover_relative)

    return buf.getvalue().encode("utf-8")


def write_metadata_atomic(target_dir: Path, body: bytes) -> bool:
    """Write ``body`` to ``<target_dir>/metadata.txt`` atomically.

    Returns ``True`` when written, ``False`` when another process
    holds the per-output advisory lock at
    ``<target_dir>/.metadata.txt.lock``. See
    :func:`romarr.libraries.exporters._atomic.write_atomic_with_lock`.
    """
    return write_atomic_with_lock(
        target_dir=target_dir, filename="metadata.txt", body=body
    )


__all__ = [
    "PegasusCollection",
    "PegasusGame",
    "render_metadata_txt",
    "write_metadata_atomic",
]
