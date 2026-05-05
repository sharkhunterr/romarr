"""Static exporter registry (slice 279 / spec 009 T077 foundation).

Romarr ships four documented exporters:

  * ES-DE / Batocera / Recalbox compatible ``gamelist.xml`` writer
  * Pegasus front-end ``metadata.txt`` writer
  * LaunchBox XML writer
  * RomM HTTP push (best-effort against a running RomM instance)

The registry is a flat catalog of metadata about each one: a stable
``name`` slug, a human-readable description, and the on-disk format
hint. Per-import dispatch + last-run tracking land in a future slice
when the spec 008 importer's per-import fan-out arrives; today the
registry is read-only metadata for the Settings > Exporters surface.

This module deliberately avoids importing the exporter implementations
themselves (esde / pegasus / etc.) — the operator-facing list doesn't
need them, and the shipped value types pull in lxml as a side effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class ExporterDescriptor:
    """Static metadata about one exporter.

    ``name`` is the stable slug callers use in the
    ``/api/v3/rom/exporters/{name}/run`` URL. ``description`` is the
    operator-facing copy. ``format`` hints at what the on-disk output
    looks like (``"xml"`` / ``"txt"`` / ``"http"``) — the UI uses it
    to render an icon next to each row.
    """

    name: str
    description: str
    format: Literal["xml", "txt", "http"]
    available: bool = True


_REGISTRY: tuple[ExporterDescriptor, ...] = (
    ExporterDescriptor(
        name="esde",
        description=(
            "ES-DE / Batocera / Recalbox compatible gamelist.xml writer. "
            "One file per (library, platform_slug) directory."
        ),
        format="xml",
    ),
    ExporterDescriptor(
        name="pegasus",
        description=(
            "Pegasus front-end metadata.txt writer. One file per "
            "(library, platform_slug) directory; collection header + "
            "per-game key/value blocks."
        ),
        format="txt",
    ),
    ExporterDescriptor(
        name="launchbox",
        description=(
            "LaunchBox XML writer (Platforms.xml + per-platform "
            "Games.xml). One file per (library, platform_slug) "
            "directory."
        ),
        format="xml",
    ),
    ExporterDescriptor(
        name="romm",
        description=(
            "Best-effort HTTP push to a running RomM instance. "
            "Tenacity-retried with Fernet-decrypted credentials per "
            "configured endpoint."
        ),
        format="http",
    ),
)


def list_exporters() -> tuple[ExporterDescriptor, ...]:
    """Return the catalog as a frozen tuple."""
    return _REGISTRY


def get_exporter(name: str) -> ExporterDescriptor | None:
    """Look up a single descriptor by ``name``. Returns ``None``
    when the slug doesn't match."""
    for descriptor in _REGISTRY:
        if descriptor.name == name:
            return descriptor
    return None


__all__ = ["ExporterDescriptor", "get_exporter", "list_exporters"]
