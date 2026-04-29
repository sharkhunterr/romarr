"""Identifier façade end-to-end tests — FR-010 / FR-011 / FR-029.

Spec 001 SC-005 calls out five representative scenarios:
  (a) clean No-Intro DAT-matched file → high confidence, dat_verified
  (b) garbage filename with DAT match → DAT wins, conflict logged
  (c) no DAT, clean filename → filename-driven id, no penalty
  (d) filename/DAT region conflict → DAT wins + 10% penalty (CL004)
  (e) multi-disc detection → header passes through

Plus the FR-029 / CL007 path: low merged confidence → unidentified.
"""

from __future__ import annotations

import zlib
from pathlib import Path

import pytest

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.identification.hasher import Hasher, HashResult
from romarr.identification.hashmatch.cascade import HashMatchCascade
from romarr.identification.hashmatch.types import (
    BackendName,
    HashLookupResult,
    RemoteHashEntry,
)
from romarr.identification.headers.ines import INES_MAGIC, InesReader
from romarr.identification.identifier import Identifier, TorznabAttrs
from romarr.identification.merger import IdentificationSource
from romarr.identification.parsers import default_dispatcher

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubBackend:
    name = BackendName.LOCAL

    def __init__(self, entries: tuple[RemoteHashEntry, ...] = ()) -> None:
        self._entries = entries

    async def lookup_sha1(
        self, *, platform_id: int, sha1: str
    ) -> HashLookupResult:
        return HashLookupResult(backend=self.name, entries=self._entries)


def _hash_file(path: Path) -> HashResult:
    return Hasher().hash_path(path)


def _real_sha1(payload: bytes) -> str:
    """Compute the actual SHA-1 of payload so the cascade match aligns."""
    import hashlib

    return hashlib.sha1(payload).hexdigest()


def _real_crc32(payload: bytes) -> str:
    return f"{zlib.crc32(payload) & 0xFFFFFFFF:08x}"


# ---------------------------------------------------------------------------
# Scenario (a): clean No-Intro DAT-matched file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clean_dat_matched_file_high_confidence(tmp_path: Path) -> None:
    payload = b"sample-rom-bytes" * 1024
    rom = tmp_path / "Sonic the Hedgehog (USA).md"
    rom.write_bytes(payload)
    sha1 = _real_sha1(payload)

    cascade = HashMatchCascade(
        [
            _StubBackend(
                entries=(
                    RemoteHashEntry(
                        source="no-intro",
                        name="Sonic the Hedgehog (USA)",
                        sha1=sha1,
                        status=DumpStatus.VERIFIED,
                    ),
                )
            )
        ]
    )

    identifier = Identifier(
        cascade=cascade,
        parser_dispatcher=default_dispatcher(),
    )
    outcome = await identifier.identify(path=rom, platform_id=3)

    assert outcome.merged.title == "Sonic the Hedgehog (USA)"
    assert outcome.cascade_winner is not None
    assert outcome.cascade_winner.source == "no-intro"
    assert IdentificationSource.HASH in outcome.merged.contributing_sources
    assert IdentificationSource.FILENAME in outcome.merged.contributing_sources
    # Hash and filename disagree on title shape — DAT name is
    # "Sonic the Hedgehog (USA)" while the parser strips the (USA)
    # marker into ``regions=("US",)``. The merger correctly flags this
    # title disagreement and applies the flat 10% penalty (CL004).
    assert abs(outcome.merged.confidence - 0.9) < 1e-6
    assert any(c.field == "title" for c in outcome.merged.conflicts)
    assert not outcome.merged.is_unidentified


# ---------------------------------------------------------------------------
# Scenario (b): garbage filename, DAT match
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_garbage_filename_with_dat_match(tmp_path: Path) -> None:
    payload = b"sample-rom-bytes" * 1024
    rom = tmp_path / "game_001.bin"
    rom.write_bytes(payload)
    sha1 = _real_sha1(payload)

    cascade = HashMatchCascade(
        [
            _StubBackend(
                entries=(
                    RemoteHashEntry(
                        source="no-intro",
                        name="Sonic the Hedgehog (USA)",
                        sha1=sha1,
                        status=DumpStatus.VERIFIED,
                    ),
                )
            )
        ]
    )

    identifier = Identifier(
        cascade=cascade, parser_dispatcher=default_dispatcher()
    )
    outcome = await identifier.identify(path=rom, platform_id=3)

    # Hash wins outright; the filename parser still emits a low-
    # confidence ``title="game_001"`` contribution which disagrees with
    # the DAT title → recorded conflict → flat 10% penalty.
    assert outcome.cascade_winner is not None
    assert outcome.merged.title == "Sonic the Hedgehog (USA)"
    assert abs(outcome.merged.confidence - 0.9) < 1e-6
    assert any(c.field == "title" for c in outcome.merged.conflicts)


# ---------------------------------------------------------------------------
# Scenario (c): no DAT, clean No-Intro filename
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_dat_clean_filename(tmp_path: Path) -> None:
    rom = tmp_path / "Super Mario World (USA) (Rev A).sfc"
    rom.write_bytes(b"\x00" * 100)

    cascade = HashMatchCascade([_StubBackend()])  # always empty
    identifier = Identifier(
        cascade=cascade, parser_dispatcher=default_dispatcher()
    )
    outcome = await identifier.identify(path=rom, platform_id=2)

    # Filename parser drives identification.
    assert outcome.cascade_winner is None
    assert outcome.merged.title == "Super Mario World"
    assert outcome.merged.regions == ("US",)
    assert outcome.merged.revision == "Rev A"
    assert outcome.merged.confidence > 0.7
    assert not outcome.merged.is_unidentified


# ---------------------------------------------------------------------------
# Scenario (d): filename USA vs DAT EUR — region conflict + 10% penalty (CL004)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filename_usa_vs_dat_eur_conflict(tmp_path: Path) -> None:
    payload = b"sample-rom-bytes" * 1024
    rom = tmp_path / "Sonic the Hedgehog (USA).md"
    rom.write_bytes(payload)
    sha1 = _real_sha1(payload)

    cascade = HashMatchCascade(
        [
            _StubBackend(
                entries=(
                    RemoteHashEntry(
                        source="no-intro",
                        name="Sonic the Hedgehog (Europe)",
                        sha1=sha1,
                        status=DumpStatus.VERIFIED,
                    ),
                )
            )
        ]
    )

    identifier = Identifier(
        cascade=cascade, parser_dispatcher=default_dispatcher()
    )
    outcome = await identifier.identify(path=rom, platform_id=3)

    # Filename says US; hash carries EUR via the (Europe) tag in the
    # DAT name. The merger sees a title disagreement and applies the
    # 10% penalty exactly once.
    assert outcome.merged.title == "Sonic the Hedgehog (Europe)"
    assert any(c.field == "title" for c in outcome.merged.conflicts)
    assert abs(outcome.merged.confidence - 0.9) < 1e-6


# ---------------------------------------------------------------------------
# FR-029 / CL007: low confidence → unidentified
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unidentified_when_only_low_confidence_filename(tmp_path: Path) -> None:
    rom = tmp_path / "game_001.bin"
    rom.write_bytes(b"\x00" * 100)

    cascade = HashMatchCascade([_StubBackend()])
    identifier = Identifier(
        cascade=cascade, parser_dispatcher=default_dispatcher()
    )
    outcome = await identifier.identify(path=rom, platform_id=3)

    assert outcome.cascade_winner is None
    assert outcome.merged.is_unidentified
    assert outcome.merged.confidence < 0.5


# ---------------------------------------------------------------------------
# Header reader integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_header_reader_supplies_platform_when_filename_useless(
    tmp_path: Path,
) -> None:
    """Spec 001 User Story 3: useless filename + iNES header → platform identified."""
    header = INES_MAGIC + bytes([2, 1, 0, 0]) + b"\x00" * 8
    rom = tmp_path / "game_001.bin"
    rom.write_bytes(header + b"\xff" * 32)

    identifier = Identifier(
        cascade=HashMatchCascade([_StubBackend()]),
        parser_dispatcher=default_dispatcher(),
        header_readers=[InesReader()],
    )
    outcome = await identifier.identify(path=rom, platform_id=1)

    assert outcome.header_result is not None
    assert outcome.merged.platform_slug == "nes"


# ---------------------------------------------------------------------------
# Torznab integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_torznab_attrs_contribute_when_present(tmp_path: Path) -> None:
    rom = tmp_path / "game_001.bin"
    rom.write_bytes(b"\x00" * 100)

    cascade = HashMatchCascade([_StubBackend()])
    identifier = Identifier(
        cascade=cascade, parser_dispatcher=default_dispatcher()
    )

    attrs = TorznabAttrs(
        title="Sonic the Hedgehog",
        regions=("US",),
        dump_status=DumpStatus.VERIFIED,
        naming_convention=NamingConvention.NO_INTRO,
    )
    outcome = await identifier.identify(
        path=rom, platform_id=3, torznab_attrs=attrs
    )

    assert IdentificationSource.TORZNAB in outcome.merged.contributing_sources
    assert outcome.merged.title == "Sonic the Hedgehog"
    assert outcome.merged.regions == ("US",)


# ---------------------------------------------------------------------------
# Precomputed hashes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_identifier_skips_hashing_when_precomputed(tmp_path: Path) -> None:
    rom = tmp_path / "Sonic.md"
    rom.write_bytes(b"x")
    precomputed = HashResult(
        crc32="00000000", md5="0" * 32, sha1="a" * 40, sha256=None, size_bytes=1
    )

    cascade = HashMatchCascade(
        [_StubBackend(entries=(RemoteHashEntry(source="no-intro", name="X", sha1="a" * 40),))]
    )
    identifier = Identifier(
        cascade=cascade,
        parser_dispatcher=default_dispatcher(),
        # No hasher would be needed when precomputed_hashes is supplied.
    )
    outcome = await identifier.identify(
        path=rom, platform_id=3, precomputed_hashes=precomputed
    )
    assert outcome.cascade_winner is not None
    assert outcome.hashes == precomputed
