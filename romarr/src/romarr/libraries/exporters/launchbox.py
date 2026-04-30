"""LaunchBox XML export writer.

LaunchBox imports a ``<LaunchBox>`` document with one ``<Game>``
element per imported title. The schema is documented informally;
we emit the most-broadly-compatible subset that covers the search,
list, and platform-binding flows operators rely on.

Two emission modes per :data:`Library.exporter_launchbox_per_platform`:

  * ``True`` (default) — one ``launchbox-export.xml`` per platform
    under ``<library>/<platform_slug>/``, mirroring the ES-DE /
    Pegasus layout.
  * ``False`` — one global ``launchbox-export.xml`` at
    ``<library>/launchbox-export.xml`` carrying every imported
    Game across every platform on the library.

Like the ES-DE and Pegasus writers, atomicity comes from the
shared ``.tmp`` + ``os.replace`` helper plus a per-output advisory
lock (FR-017 + FR-017a).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from typing import TYPE_CHECKING

from lxml import etree

from romarr.libraries.exporters._atomic import write_atomic_with_lock

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


_LAUNCHBOX_FILENAME = "launchbox-export.xml"


@dataclass(frozen=True)
class LaunchBoxGame:
    """Value type the renderer consumes — one per imported Game.

    ``platform_name`` is included on every ``<Game>`` element so
    the global emission mode can distinguish PSX vs Mega Drive
    titles when LaunchBox imports the XML. ``application_path`` is
    the relative ROM path the operator clicks to launch the game.
    """

    title: str
    platform_name: str
    application_path: str
    notes: str | None = None
    developer: str | None = None
    publisher: str | None = None
    release_date: datetime | None = None
    genres: tuple[str, ...] = ()
    play_mode: str | None = None
    rating: float | None = None  # 0..1


def _format_release_date(d: datetime) -> str:
    """LaunchBox uses ISO 8601 datetime; we always emit midnight UTC."""
    return d.strftime("%Y-%m-%dT00:00:00")


def render_launchbox_xml(games: Sequence[LaunchBoxGame]) -> bytes:
    """Build the LaunchBox XML body. Pure: deterministic for a
    given input, no I/O."""
    root = etree.Element("LaunchBox")

    for game in games:
        node = etree.SubElement(root, "Game")
        etree.SubElement(node, "Title").text = game.title
        etree.SubElement(node, "Platform").text = game.platform_name
        etree.SubElement(node, "ApplicationPath").text = game.application_path

        if game.notes:
            etree.SubElement(node, "Notes").text = game.notes
        if game.developer:
            etree.SubElement(node, "Developer").text = game.developer
        if game.publisher:
            etree.SubElement(node, "Publisher").text = game.publisher
        if game.release_date is not None:
            etree.SubElement(node, "ReleaseDate").text = _format_release_date(
                game.release_date
            )
        if game.genres:
            # LaunchBox uses semicolon-separated genres in a single
            # <Genre> element.
            etree.SubElement(node, "Genre").text = "; ".join(game.genres)
        if game.play_mode:
            etree.SubElement(node, "PlayMode").text = game.play_mode
        if game.rating is not None:
            # LaunchBox's <CommunityStarRating> is on a 0..5 scale.
            etree.SubElement(node, "CommunityStarRating").text = (
                f"{game.rating * 5:.2f}".rstrip("0").rstrip(".")
            )

    buf = BytesIO()
    etree.ElementTree(root).write(
        buf,
        xml_declaration=True,
        encoding="utf-8",
        pretty_print=True,
    )
    return buf.getvalue()


def write_launchbox_atomic(target_dir: Path, xml_bytes: bytes) -> bool:
    """Write ``xml_bytes`` to
    ``<target_dir>/launchbox-export.xml`` atomically.

    Same FR-017 + FR-017a contract as the other filesystem
    exporters: per-output advisory lock at
    ``<target_dir>/.launchbox-export.xml.lock``, ``.tmp`` +
    ``os.replace`` atomic rename, coalesce on lock contention.

    The caller is responsible for choosing ``target_dir`` —
    ``<library>/<platform_slug>/`` for the per-platform mode or
    ``<library>/`` for the global mode (driven by
    ``library.exporter_launchbox_per_platform``).
    """
    return write_atomic_with_lock(
        target_dir=target_dir, filename=_LAUNCHBOX_FILENAME, body=xml_bytes
    )


__all__ = [
    "LaunchBoxGame",
    "render_launchbox_xml",
    "write_launchbox_atomic",
]
