"""Hash-step tests (T032, T033)."""

from __future__ import annotations

from pathlib import Path

import pytest

from romarr.identification.hasher import Hasher, HashResult
from romarr.importer.steps.hash_step import FormatRule, hash_candidates

# ---------------------------------------------------------------------------
# T032 — walks dir + skips files below min_size_bytes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_walks_extracted_dir_filters_by_extension(tmp_path: Path) -> None:
    rom = tmp_path / "Game.md"
    rom.write_bytes(b"X" * 4096)
    readme = tmp_path / "readme.txt"
    readme.write_bytes(b"hi")
    notes = tmp_path / "notes.gen"
    notes.write_bytes(b"X" * 4096)

    rules = [
        FormatRule(extension=".md", min_size_bytes=1024),
        FormatRule(extension="gen", min_size_bytes=1024),
    ]
    results = await hash_candidates(directory=tmp_path, rules=rules)
    assert set(results) == {rom, notes}


@pytest.mark.asyncio
async def test_walks_extracted_dir_honours_min_size(tmp_path: Path) -> None:
    """Per FR-008 the small-file skip rule honours
    ``platform_format.min_size_bytes`` — readme-style files smaller
    than the rule's floor are silently dropped."""
    big = tmp_path / "Big.md"
    big.write_bytes(b"X" * 4096)
    small = tmp_path / "Small.md"
    small.write_bytes(b"X" * 64)

    rules = [FormatRule(extension="md", min_size_bytes=1024)]
    results = await hash_candidates(directory=tmp_path, rules=rules)
    assert set(results) == {big}


@pytest.mark.asyncio
async def test_walks_extracted_dir_recursively(tmp_path: Path) -> None:
    nested = tmp_path / "deep" / "deeper"
    nested.mkdir(parents=True)
    (nested / "Found.md").write_bytes(b"X" * 4096)

    rules = [FormatRule(extension="md", min_size_bytes=1024)]
    results = await hash_candidates(directory=tmp_path, rules=rules)
    assert len(results) == 1
    assert next(iter(results)).name == "Found.md"


@pytest.mark.asyncio
async def test_unknown_extension_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "noise.unknown").write_bytes(b"X" * 4096)
    rules = [FormatRule(extension="md")]
    results = await hash_candidates(directory=tmp_path, rules=rules)
    assert results == {}


# ---------------------------------------------------------------------------
# T033 — calls go through foundation's Hasher
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_uses_foundation_hasher(tmp_path: Path) -> None:
    rom = tmp_path / "Game.md"
    body = b"sonic-rom-bytes" * 1024
    rom.write_bytes(body)

    rules = [FormatRule(extension="md")]
    results = await hash_candidates(directory=tmp_path, rules=rules)
    assert rom in results
    result = results[rom]
    assert isinstance(result, HashResult)

    # The same body re-hashed via Hasher gives the same output.
    direct = Hasher().hash_path(rom)
    assert result.sha1 == direct.sha1
    assert result.crc32 == direct.crc32
    assert result.md5 == direct.md5
    assert result.size_bytes == len(body)


@pytest.mark.asyncio
async def test_format_rule_normalises_extension() -> None:
    """Both ``.MD`` and ``md`` should match the same rule."""
    rule_dotted = FormatRule(extension=".MD")
    rule_bare = FormatRule(extension="md")
    assert rule_dotted.normalised_extension == "md"
    assert rule_bare.normalised_extension == "md"
