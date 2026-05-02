"""Build :class:`ReleaseFacts` for the profile gate (slice 82).

The orchestrator's PROFILEGATE step needs a
:class:`ReleaseFacts` value: the parsed regions / languages /
dump_status / naming_convention plus the file-level signals
(format, dat_verified, size). All those signals are produced
by upstream pipeline steps; this helper assembles them into
the frozen value type the gate consumes.

Single source of truth for the assembly so the orchestrator's
PROFILEGATE call doesn't reach into the identification +
extract + dat_match outputs separately. Tests cover the
field-by-field passthrough so a future spec change to either
:class:`MergedIdentification` or :class:`ReleaseFacts` shows
up loudly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from romarr.profiles.types import ReleaseFacts

if TYPE_CHECKING:
    from romarr.identification.merger import MergedIdentification


def build_release_facts(
    *,
    merged: MergedIdentification,
    file_format: str,
    dat_verified: bool,
    release_size: int | None = None,
    indexer_source: str | None = None,
    release_group: str | None = None,
    tags: tuple[str, ...] = (),
) -> ReleaseFacts:
    """Project the merged identification + per-file signals
    into a :class:`ReleaseFacts`.

    Field mapping:

    * ``title`` ← ``merged.title or ""`` (the gate works with
      empty title — the title doesn't drive any decision but
      Custom Format conditions may key on it).
    * ``regions`` / ``languages`` / ``revision`` /
      ``dump_status`` / ``naming_convention`` ← passthrough.
    * ``file_format`` — comes from the EXTRACT step's
      detected container (``raw`` / ``zip`` / ``7z`` / ``chd``
      / etc.); the Quality profile's ``allowed_formats`` keys
      on it.
    * ``dat_verified`` — set by the DATMATCH step when the
      cascade winner came from a No-Intro / Redump / TOSEC
      DAT.
    * ``indexer_source`` — the originating indexer's protocol
      (``newznab`` / ``torznab`` / ``None`` for direct adds).
    * ``release_size`` — bytes; consumed by the
      ``release_size`` Custom Format condition.
    * ``release_group`` — the scene release group name when
      parseable from the filename.
    * ``tags`` — operator-applied tags for tag-filter Custom
      Formats.
    """
    return ReleaseFacts(
        title=merged.title or "",
        regions=merged.regions,
        languages=merged.languages,
        revision=merged.revision,
        dump_status=merged.dump_status,
        tags=tags,
        naming_convention=merged.naming_convention,
        file_format=file_format,
        dat_verified=dat_verified,
        indexer_source=indexer_source,
        release_size=release_size,
        release_group=release_group,
    )


__all__ = ["build_release_facts"]
