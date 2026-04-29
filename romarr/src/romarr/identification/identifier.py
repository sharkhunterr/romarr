"""Identifier façade — the public entry point of the identification layer.

Per FR-010 the system exposes a single entry point that produces a
structured :class:`MergedIdentification` combining inputs from up to
four sources (FR-011): hash match, Torznab extended attributes,
header read, filename parse.

Typical usage from an async context::

    identifier = Identifier(
        cascade=HashMatchCascade([LocalDatBackend(dat_manager), ...]),
        parser_dispatcher=default_dispatcher(),
        header_readers=[InesReader(), MegaDriveReader(), Iso9660Reader()],
    )

    merged = await identifier.identify(
        path=Path("/imports/Sonic the Hedgehog (USA).md"),
        torznab_attrs=None,  # optional
    )

    if merged.is_unidentified:
        # Park in unidentified_dump per CL007 / FR-029
        ...

The Identifier is intentionally thin — every step delegates to a
purpose-built component (Hasher, parser dispatcher, header readers,
hash-match cascade, merger). Tests can swap in stubs for any of these
pieces.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.identification.hasher import Hasher, HashResult
from romarr.identification.headers.base import (
    BaseHeaderReader,
    HeaderReadResult,
    HeaderReadStatus,
    UnsupportedPlatformError,
)
from romarr.identification.merger import (
    IdentificationSource,
    MergedIdentification,
    SourceContribution,
    merge,
)

if TYPE_CHECKING:
    from romarr.identification.hashmatch.cascade import HashMatchCascade
    from romarr.identification.hashmatch.types import RemoteHashEntry
    from romarr.identification.parsers import ParsedFilename, ParserDispatcher

# ---------------------------------------------------------------------------
# Torznab extended-attributes shape (FR-003 of spec 004 will refine this)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TorznabAttrs:
    """Subset of extended Torznab attributes relevant to identification.

    Spec 004 ships the full Torznab parser; spec 001's identifier
    consumes the structured value object only.
    """

    title: str | None = None
    regions: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    revision: str | None = None
    dump_status: DumpStatus | None = None
    naming_convention: NamingConvention | None = None
    sha1: str | None = None
    crc32: str | None = None


# ---------------------------------------------------------------------------
# Identifier façade
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class IdentifyOutcome:
    """Top-level outcome of :meth:`Identifier.identify`.

    Carries the merged identification plus the structured byproducts
    from each layer so downstream consumers (importer, search engine)
    can persist them on the resulting Dump / SearchResult / event.
    """

    merged: MergedIdentification
    hashes: HashResult | None
    parsed_filename: ParsedFilename | None
    header_result: HeaderReadResult | None
    cascade_winner: RemoteHashEntry | None
    cascade_losers: tuple[RemoteHashEntry, ...]


class Identifier:
    """Orchestrates the identification pipeline.

    Steps (per FR-010 / FR-011):
      1. **Hash** the file (FR-014). Skip when ``compute_hashes=False``
         (e.g., the importer already hashed for atomic move).
      2. **Hash-match** the SHA-1 across the cascade (FR-026).
      3. **Header read** — try each registered reader; first OK wins.
      4. **Filename parse** via the parser dispatcher (FR-021/023).
      5. **Merge** all contributions per FR-011 / FR-012 / FR-029.
    """

    def __init__(
        self,
        *,
        cascade: HashMatchCascade | None = None,
        parser_dispatcher: ParserDispatcher | None = None,
        header_readers: Sequence[BaseHeaderReader] = (),
        hasher: Hasher | None = None,
    ) -> None:
        self._cascade = cascade
        self._parser_dispatcher = parser_dispatcher
        self._header_readers = tuple(header_readers)
        self._hasher = hasher or Hasher()

    async def identify(
        self,
        *,
        path: str | PathLike[str],
        platform_id: int | None = None,
        torznab_attrs: TorznabAttrs | None = None,
        compute_hashes: bool = True,
        precomputed_hashes: HashResult | None = None,
    ) -> IdentifyOutcome:
        """Run the full identification pipeline against a single file.

        ``platform_id`` scopes the hash-match cascade. When ``None``
        (e.g., we don't yet know the platform), the hash-match step
        is skipped and identification proceeds with header + filename
        sources only.

        ``compute_hashes=False`` + ``precomputed_hashes=None`` is the
        "I just want filename + header" mode used in tests.
        """
        path_obj = Path(path)

        # Step 1: hash
        hashes = precomputed_hashes
        if compute_hashes and hashes is None:
            hashes = self._hasher.hash_path(path_obj)

        # Step 2: hash-match cascade (only when we have a SHA-1 and a platform)
        cascade_winner: RemoteHashEntry | None = None
        cascade_losers: tuple[RemoteHashEntry, ...] = ()
        hash_contribution: SourceContribution | None = None

        if (
            self._cascade is not None
            and hashes is not None
            and platform_id is not None
        ):
            cascade = await self._cascade.lookup_sha1(
                platform_id=platform_id, sha1=hashes.sha1
            )
            cascade_winner = cascade.winner
            cascade_losers = cascade.losers
            if cascade_winner is not None:
                hash_contribution = _contribution_from_remote(
                    cascade_winner, confidence=1.0
                )

        # If Torznab carried a hash that the cascade didn't already
        # find, cross-check via Torznab attributes path.
        if (
            hash_contribution is None
            and torznab_attrs is not None
            and torznab_attrs.sha1
            and self._cascade is not None
            and platform_id is not None
        ):
            cascade = await self._cascade.lookup_sha1(
                platform_id=platform_id, sha1=torznab_attrs.sha1
            )
            cascade_winner = cascade.winner
            cascade_losers = cascade.losers
            if cascade_winner is not None:
                hash_contribution = _contribution_from_remote(
                    cascade_winner, confidence=1.0
                )

        # Step 3: header readers
        header_result: HeaderReadResult | None = None
        header_contribution: SourceContribution | None = None
        for reader in self._header_readers:
            try:
                candidate = reader.read(path_obj)
            except UnsupportedPlatformError:
                continue  # FR-025 stub — try the next reader
            except OSError:
                continue
            if candidate.status == HeaderReadStatus.OK:
                header_result = candidate
                header_contribution = _contribution_from_header(candidate)
                break

        # Step 4: filename parse
        parsed: ParsedFilename | None = None
        filename_contribution: SourceContribution | None = None
        if self._parser_dispatcher is not None:
            parsed = self._parser_dispatcher.parse(path_obj.name)
            filename_contribution = _contribution_from_parsed(parsed)

        # Step 5: Torznab contribution (if any)
        torznab_contribution: SourceContribution | None = None
        if torznab_attrs is not None:
            torznab_contribution = _contribution_from_torznab(torznab_attrs)

        # Step 6: merge
        contributions: list[SourceContribution] = []
        for c in (
            hash_contribution,
            torznab_contribution,
            header_contribution,
            filename_contribution,
        ):
            if c is not None:
                contributions.append(c)

        merged = merge(contributions)

        return IdentifyOutcome(
            merged=merged,
            hashes=hashes,
            parsed_filename=parsed,
            header_result=header_result,
            cascade_winner=cascade_winner,
            cascade_losers=cascade_losers,
        )


# ---------------------------------------------------------------------------
# Adapter helpers — translate per-layer results into SourceContribution
# ---------------------------------------------------------------------------


def _contribution_from_remote(
    entry: RemoteHashEntry, *, confidence: float
) -> SourceContribution:
    """Translate a hash-match cascade winner into a HASH-source contribution."""
    return SourceContribution(
        source=IdentificationSource.HASH,
        confidence=confidence,
        title=entry.name or None,
        regions=(),  # remote entries don't carry parsed regions
        languages=(),
        dump_status=entry.status,
        extra={"dat_source": entry.source},
    )


def _contribution_from_header(result: HeaderReadResult) -> SourceContribution:
    """Translate a header-reader result into a HEADER-source contribution."""
    extra = {
        k: str(v)
        for k, v in result.data.items()
        if isinstance(v, (str, int))
    }
    return SourceContribution(
        source=IdentificationSource.HEADER,
        confidence=result.confidence,
        platform_slug=result.platform_slug,
        serial=str(result.data.get("serial") or "") or None,
        extra=extra,
    )


def _contribution_from_parsed(parsed: ParsedFilename) -> SourceContribution:
    """Translate a parser dispatcher result into a FILENAME-source contribution."""
    return SourceContribution(
        source=IdentificationSource.FILENAME,
        confidence=parsed.confidence,
        title=parsed.title,
        regions=parsed.regions,
        languages=parsed.languages,
        revision=parsed.revision,
        dump_status=parsed.dump_status if parsed.dump_status != DumpStatus.UNKNOWN else None,
        naming_convention=parsed.convention if parsed.convention != NamingConvention.UNKNOWN else None,
        extra=dict(parsed.extra),
    )


def _contribution_from_torznab(attrs: TorznabAttrs) -> SourceContribution:
    """Translate Torznab extended attrs into a TORZNAB-source contribution."""
    return SourceContribution(
        source=IdentificationSource.TORZNAB,
        confidence=0.85,  # Torznab attrs are operator-curated; high but not hash-perfect
        title=attrs.title,
        regions=attrs.regions,
        languages=attrs.languages,
        revision=attrs.revision,
        dump_status=attrs.dump_status,
        naming_convention=attrs.naming_convention,
    )
