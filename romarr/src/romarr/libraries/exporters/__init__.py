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

Slices 4-6 ship the four exporter primitives:
  * ES-DE renderer + atomic writer + media mirror (slice 4)
  * Pegasus + LaunchBox renderers reusing the shared atomic writer (slice 5)
  * RomM remote push with tenacity retry + Fernet decryption (slice 6)

The full per-import dispatch (which exporters fire, in what order,
on which (library, platform_slug) pair) lives in spec 008's
importer + spec 011's notification consumer for the post-failure
debounce.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from romarr.libraries.exporters._media_mirror import materialise_cover
from romarr.libraries.exporters.esde import (
    EsdeGame,
    render_gamelist_xml,
    write_gamelist_atomic,
)
from romarr.libraries.exporters.launchbox import (
    LaunchBoxGame,
    render_launchbox_xml,
    write_launchbox_atomic,
)
from romarr.libraries.exporters.pegasus import (
    PegasusCollection,
    PegasusGame,
    render_metadata_txt,
    write_metadata_atomic,
)
from romarr.libraries.exporters.romm import RommPushOutcome, push_to_romm


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
    "LaunchBoxGame",
    "PegasusCollection",
    "PegasusGame",
    "RommPushOutcome",
    "materialise_cover",
    "push_to_romm",
    "render_gamelist_xml",
    "render_launchbox_xml",
    "render_metadata_txt",
    "write_gamelist_atomic",
    "write_launchbox_atomic",
    "write_metadata_atomic",
]
