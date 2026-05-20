"""ROM content packs (slice 460).

A *content pack* is a downloadable archive holding many ROMs —
a No-Intro full set, an archive.org romset, a curated bundle.
The ingest pipeline downloads the archive (streaming to disk
with a free-space pre-check + a configurable size cap),
extracts it recursively, and runs every ROM through the
importer. A verified DAT match auto-creates the Game when the
operator doesn't already track it; a ROM with no DAT match
lands in the ``awaiting_triage`` bucket for the operator's
per-file decision (slice 462).

Distinct from ``romarr.platform_packs`` — that ships *platform
metadata*; this ships actual ROM content.
"""

from romarr.rom_packs.ingest import ingest_rom_pack

__all__ = ["ingest_rom_pack"]
