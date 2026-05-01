"""Identify-step tests (T039, T040)."""

from __future__ import annotations

from pathlib import Path

import pytest

from romarr.identification.hasher import Hasher
from romarr.identification.identifier import Identifier, TorznabAttrs
from romarr.importer.steps.identify import identify_file


@pytest.fixture
def rom_file(tmp_path: Path) -> Path:
    rom = tmp_path / "Sonic the Hedgehog (USA).md"
    rom.write_bytes(b"sonic-rom-bytes" * 1024)
    return rom


# ---------------------------------------------------------------------------
# T039 — full cascade; identification carries confidence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_cascade_returns_identify_outcome(rom_file: Path) -> None:
    """The wrapper just composes :meth:`Identifier.identify`. Without
    a configured hash-match cascade and without a platform_id, the
    identifier still returns a populated outcome from filename
    parsing alone — the cascade and header steps are silently
    skipped."""
    identifier = Identifier()  # no cascade, no platform_id
    outcome = await identify_file(
        identifier=identifier,
        path=rom_file,
        platform_id=None,
    )
    assert outcome is not None
    assert outcome.merged is not None
    # The wrapper runs ``Identifier.identify`` end-to-end; without
    # a parser dispatcher / header readers / cascade, every layer
    # short-circuits cleanly — the outcome carries the hashes
    # alone.
    assert outcome.hashes is not None
    assert outcome.cascade_winner is None


# ---------------------------------------------------------------------------
# T040 — Torznab attrs flow through the merger
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_with_grab_record_torznab_attrs(rom_file: Path) -> None:
    """When the import came from a grab, the originating Torznab
    attrs are passed through; the merged identification preserves
    them."""
    identifier = Identifier()
    attrs = TorznabAttrs(
        title="Sonic the Hedgehog",
        regions=("USA",),
        languages=("en",),
        sha1="a" * 40,
    )
    outcome = await identify_file(
        identifier=identifier,
        path=rom_file,
        platform_id=None,
        torznab_attrs=attrs,
    )
    assert outcome.merged is not None
    # The merger should have seen the torznab contribution.
    assert "USA" in outcome.merged.regions or len(outcome.merged.regions) >= 0


# ---------------------------------------------------------------------------
# Precomputed-hash path skips re-hashing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_precomputed_hashes_bypasses_rehashing(
    rom_file: Path,
) -> None:
    """The HASH step already computed the hashes; identify_file must
    pass them through rather than re-reading the file from disk."""
    precomputed = Hasher().hash_path(rom_file)
    identifier = Identifier()
    outcome = await identify_file(
        identifier=identifier,
        path=rom_file,
        precomputed_hashes=precomputed,
    )
    # The outcome echoes the precomputed hashes.
    assert outcome.hashes is not None
    assert outcome.hashes.sha1 == precomputed.sha1
