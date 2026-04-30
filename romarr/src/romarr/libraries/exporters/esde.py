"""ES-DE / Batocera / Recalbox compatible ``gamelist.xml`` writer.

The renderer is **pure**: it consumes a list of :class:`EsdeGame`
value types (preloaded from the ORM by the orchestrator) and emits
the XML bytes. The writer wraps the renderer in:

  * an :func:`fcntl.flock` advisory lock at
    ``<library>/<platform_slug>/.gamelist.lock`` (FR-017a);
  * an atomic-rename pattern (write to ``.tmp`` then
    :func:`os.replace`) so a crash mid-write preserves the prior
    file (FR-017).

When the lock is unavailable (another process is currently
regenerating), the writer **coalesces** — i.e., returns silently
without re-emitting. The in-flight emission already covers the
latest catalog state at lock-release time.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING

from lxml import etree

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence


# ---------------------------------------------------------------------------
# Value types


@dataclass(frozen=True)
class EsdeGame:
    """Value type the renderer consumes — one per imported Game on
    the platform being emitted. The orchestrator preloads these
    from a streaming SQLAlchemy query so the renderer never sees an
    ORM session.

    ``cover_relative`` is either the relative ``./media/covers/...``
    path that ES-DE expects, or ``None`` to omit ``<image>`` entirely
    per FR-018a.
    """

    slug: str
    title: str
    rom_path: str  # relative to the gamelist.xml's directory
    summary: str | None = None
    developer: str | None = None
    publisher: str | None = None
    genres: tuple[str, ...] = ()
    rating: float | None = None  # 0..1
    release_date: datetime | None = None
    players_min: int | None = None
    players_max: int | None = None
    cover_relative: str | None = None
    thumbnail_relative: str | None = None
    marquee_relative: str | None = None


# ---------------------------------------------------------------------------
# XML renderer (pure)


def _format_players(low: int | None, high: int | None) -> str | None:
    """ES-DE expects ``<players>1-2</players>`` style ranges. A
    single value emits ``<players>2</players>``. Empty when neither
    bound is known."""
    if low is None and high is None:
        return None
    if low is not None and high is not None:
        return f"{low}-{high}" if high > low else str(low)
    return str(low if low is not None else high)


def _format_release_date(d: datetime) -> str:
    """ES-DE expects ``YYYYMMDDT000000`` (no timezone)."""
    return d.strftime("%Y%m%dT000000")


def render_gamelist_xml(games: Sequence[EsdeGame]) -> bytes:
    """Build the ``gameList`` document and return UTF-8 bytes with
    XML prolog. Pure: no I/O, deterministic output for a given
    input.

    Games are emitted in the order they're given — the orchestrator
    is the one that decides ordering (typically by title, but the
    renderer doesn't impose that)."""
    root = etree.Element("gameList")

    for game in games:
        node = etree.SubElement(root, "game")

        path_el = etree.SubElement(node, "path")
        path_el.text = game.rom_path

        name_el = etree.SubElement(node, "name")
        name_el.text = game.title

        if game.summary:
            desc_el = etree.SubElement(node, "desc")
            desc_el.text = game.summary

        # FR-018a: omit <image>/<thumbnail>/<marquee> entirely when
        # the underlying asset is not present.
        if game.cover_relative:
            image_el = etree.SubElement(node, "image")
            image_el.text = game.cover_relative
        if game.thumbnail_relative:
            thumb_el = etree.SubElement(node, "thumbnail")
            thumb_el.text = game.thumbnail_relative
        if game.marquee_relative:
            marquee_el = etree.SubElement(node, "marquee")
            marquee_el.text = game.marquee_relative

        if game.rating is not None:
            rating_el = etree.SubElement(node, "rating")
            rating_el.text = f"{game.rating:.6f}".rstrip("0").rstrip(".")
        if game.release_date is not None:
            release_el = etree.SubElement(node, "releasedate")
            release_el.text = _format_release_date(game.release_date)
        if game.developer:
            dev_el = etree.SubElement(node, "developer")
            dev_el.text = game.developer
        if game.publisher:
            pub_el = etree.SubElement(node, "publisher")
            pub_el.text = game.publisher
        if game.genres:
            # ES-DE accepts a single <genre> element; join multiple
            # with a comma, which matches the most common community
            # gamelist.xml convention.
            genre_el = etree.SubElement(node, "genre")
            genre_el.text = ", ".join(game.genres)
        players = _format_players(game.players_min, game.players_max)
        if players is not None:
            players_el = etree.SubElement(node, "players")
            players_el.text = players

    buf = BytesIO()
    tree = etree.ElementTree(root)
    tree.write(
        buf,
        xml_declaration=True,
        encoding="utf-8",
        pretty_print=True,
    )
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Atomic writer with advisory lock


@contextlib.contextmanager
def _gamelist_lock(target_dir: Path) -> Iterator[bool]:
    """Acquire the advisory lock at
    ``<target_dir>/.gamelist.lock`` (FR-017a).

    Yields ``True`` when the lock was acquired, ``False`` when it
    couldn't be (another process is currently regenerating). The
    writer coalesces on ``False`` so the operator never observes a
    queue.

    The lock is released automatically on ``fd.close()`` and on
    process death (a property ``fcntl.flock`` provides natively).
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    lock_path = target_dir / ".gamelist.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def write_gamelist_atomic(target_dir: Path, xml_bytes: bytes) -> bool:
    """Write ``xml_bytes`` to ``<target_dir>/gamelist.xml`` atomically.

    Returns:
      ``True``  — the file was written.
      ``False`` — coalesced because another process holds the lock.

    Atomicity is provided by writing to ``gamelist.xml.tmp`` then
    :func:`os.replace`; a crash between the two steps leaves the
    prior ``gamelist.xml`` untouched (FR-017).
    """
    with _gamelist_lock(target_dir) as acquired:
        if not acquired:
            return False

        target = target_dir / "gamelist.xml"
        tmp = target_dir / "gamelist.xml.tmp"
        try:
            tmp.write_bytes(xml_bytes)
            os.replace(tmp, target)
        except Exception:
            # Defensive cleanup — leave the previous gamelist.xml
            # untouched, drop the partial .tmp.
            with contextlib.suppress(FileNotFoundError):
                tmp.unlink()
            raise
        return True


__all__ = [
    "EsdeGame",
    "render_gamelist_xml",
    "write_gamelist_atomic",
]
