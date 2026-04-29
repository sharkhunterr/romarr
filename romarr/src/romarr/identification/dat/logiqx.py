"""Streaming parser for Logiqx-XML DAT files.

Logiqx is the de-facto No-Intro / Redump / TOSEC DAT format. A DAT
file looks like::

    <datafile>
      <header>
        <name>Sega - Mega Drive - Genesis</name>
        <description>...</description>
        <version>20260401-001</version>
        ...
      </header>
      <game name="Sonic the Hedgehog (USA)">
        <description>Sonic the Hedgehog (USA)</description>
        <rom name="Sonic the Hedgehog (USA).md"
             size="524288"
             crc="ABCD1234" md5="..." sha1="..."/>
      </game>
      ... more <game> entries ...
    </datafile>

A real DAT can be ~200 MiB (FR-017), so we use ``lxml.etree.iterparse``
with the canonical clear-and-prune cleanup pattern to avoid memory
creep. Each ``<game>`` block yields one or more :class:`LogiqxRom`
records — multi-disc games have multiple ``<rom>`` children.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from os import PathLike
from pathlib import Path

from lxml import etree


@dataclass(frozen=True, slots=True)
class LogiqxRom:
    """One ``<rom>`` row inside a Logiqx ``<game>`` block.

    ``parent_game_name`` tracks the enclosing ``<game name="...">`` so
    callers can group multi-rom releases later if needed (multi-disc
    games carry multiple ``<rom>`` children — they share the parent
    game's name).
    """

    parent_game_name: str
    rom_name: str
    size_bytes: int | None
    crc32: str | None
    md5: str | None
    sha1: str | None
    description: str | None = None


def parse_logiqx(
    source: str | PathLike[str] | bytes,
) -> Iterator[LogiqxRom]:
    """Stream ``<rom>`` rows out of a Logiqx XML file.

    ``source`` may be a path, a path-like, or raw XML bytes (used by
    tests). The generator yields :class:`LogiqxRom` records lazily so
    a caller can stream them straight into a bulk INSERT without
    holding the whole DAT in memory.
    """
    if isinstance(source, bytes):
        from io import BytesIO

        stream = BytesIO(source)
        context = etree.iterparse(stream, events=("end",), tag="game")
    else:
        context = etree.iterparse(
            str(Path(source)),
            events=("end",),
            tag="game",
        )

    try:
        for _event, elem in context:
            game_name = elem.get("name", "").strip()
            description_elem = elem.find("description")
            description = (
                description_elem.text.strip()
                if description_elem is not None and description_elem.text
                else None
            )

            for rom_elem in elem.iterfind("rom"):
                size_str = rom_elem.get("size")
                yield LogiqxRom(
                    parent_game_name=game_name,
                    rom_name=rom_elem.get("name", "").strip(),
                    size_bytes=int(size_str) if size_str is not None else None,
                    crc32=_lower_hex(rom_elem.get("crc")),
                    md5=_lower_hex(rom_elem.get("md5")),
                    sha1=_lower_hex(rom_elem.get("sha1")),
                    description=description,
                )

            # Free memory — clear the element AND prune ancestors so
            # lxml's accumulating tree doesn't grow unboundedly.
            elem.clear()
            for ancestor in elem.xpath("ancestor-or-self::*"):
                while ancestor.getprevious() is not None:
                    parent = ancestor.getparent()
                    if parent is None:
                        break
                    del parent[0]
    finally:
        del context


def _lower_hex(value: str | None) -> str | None:
    """Normalise a hex digest to lowercase, stripping leading zeros padding.

    Logiqx tools sometimes emit uppercase hex — normalise so the same
    SHA-1 lookup works regardless of input casing.
    """
    if value is None:
        return None
    out = value.strip().lower()
    return out or None
