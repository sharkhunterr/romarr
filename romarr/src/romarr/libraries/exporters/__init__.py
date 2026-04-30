"""Library exporters (spec 009 — Phases 8-11).

Four exporters share a small abstract surface:

  * RomM (best-effort HTTP push to a running RomM instance)
  * ES-DE / Batocera / Recalbox compatible ``gamelist.xml`` writer
  * Pegasus front-end ``metadata.txt`` writer
  * LaunchBox XML writer

Each implementation lives in its own module so it can be tested in
isolation. The :class:`ExporterBase` contract is intentionally
narrow — one async ``run`` per (library, platform_slug) pair —
because every concrete exporter handles its own atomicity, locking,
retry, and idempotence.

Slice 4 ships the ES-DE exporter (XML render + atomic write +
advisory lock + media mirror). RomM / Pegasus / LaunchBox land in
their own slices.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from romarr.libraries.exporters._media_mirror import materialise_cover
from romarr.libraries.exporters.esde import (
    EsdeGame,
    render_gamelist_xml,
    write_gamelist_atomic,
)


class ExporterBase(ABC):
    """Common contract for every per-platform exporter.

    Concrete exporters subclass this and override :meth:`run`. The
    registry returns instances by ``name``.
    """

    name: str

    @abstractmethod
    async def run(self, *, library_id: int, platform_slug: str) -> None:
        """Materialise (or refresh) the exporter's output for one
        (library, platform_slug) pair. Idempotent: re-running on the
        same state must produce the same output. Failures are
        surfaced as :class:`romarr.libraries.errors.ExporterError`."""


__all__ = [
    "EsdeGame",
    "ExporterBase",
    "materialise_cover",
    "render_gamelist_xml",
    "write_gamelist_atomic",
]
