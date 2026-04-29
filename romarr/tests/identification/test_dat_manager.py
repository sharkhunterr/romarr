"""DAT manager + Logiqx parser tests — FR-017/018/019/020/020a."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.enums import DumpStatus
from romarr.domain.models import Platform
from romarr.identification.dat.logiqx import parse_logiqx
from romarr.identification.dat.manager import (
    DatManager,
    _resolve_authority,
)

# ---------------------------------------------------------------------------
# Logiqx parser (pure functions; no DB)
# ---------------------------------------------------------------------------


_LOGIQX_SAMPLE = b"""<?xml version="1.0"?>
<datafile>
  <header>
    <name>Sega - Mega Drive</name>
    <description>Sample DAT</description>
    <version>20260401-001</version>
  </header>
  <game name="Sonic the Hedgehog (USA)">
    <description>Sonic the Hedgehog (USA)</description>
    <rom name="Sonic the Hedgehog (USA).md"
         size="524288"
         crc="ABCD1234"
         md5="0123456789abcdef0123456789abcdef"
         sha1="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"/>
  </game>
  <game name="Final Fantasy IX (USA)">
    <description>Final Fantasy IX (USA)</description>
    <rom name="Final Fantasy IX (USA) (Disc 1).bin"
         size="700000000"
         sha1="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"/>
    <rom name="Final Fantasy IX (USA) (Disc 2).bin"
         size="700000000"
         sha1="cccccccccccccccccccccccccccccccccccccccc"/>
  </game>
</datafile>
"""


def test_parse_logiqx_yields_each_rom() -> None:
    roms = list(parse_logiqx(_LOGIQX_SAMPLE))
    assert len(roms) == 3
    sonic = roms[0]
    assert sonic.parent_game_name == "Sonic the Hedgehog (USA)"
    assert sonic.rom_name == "Sonic the Hedgehog (USA).md"
    assert sonic.size_bytes == 524288
    assert sonic.crc32 == "abcd1234"  # lowercased
    assert sonic.sha1 == "a" * 40

    ff9_disc2 = roms[2]
    assert ff9_disc2.parent_game_name == "Final Fantasy IX (USA)"
    assert ff9_disc2.rom_name == "Final Fantasy IX (USA) (Disc 2).bin"
    assert ff9_disc2.sha1 == "c" * 40


def test_parse_logiqx_normalises_uppercase_hex() -> None:
    payload = b"""<datafile>
      <game name="x">
        <rom name="x.bin" sha1="ABCDEF0123456789ABCDEF0123456789ABCDEF01" size="1"/>
      </game>
    </datafile>"""
    roms = list(parse_logiqx(payload))
    assert roms[0].sha1 == "abcdef0123456789abcdef0123456789abcdef01"


def test_parse_logiqx_skips_missing_hashes_gracefully() -> None:
    """A ROM with no hashes at all is yielded; the manager filters it."""
    payload = b"""<datafile>
      <game name="x"><rom name="x.bin" size="1"/></game>
    </datafile>"""
    roms = list(parse_logiqx(payload))
    assert roms[0].sha1 is None
    assert roms[0].crc32 is None


# ---------------------------------------------------------------------------
# DatManager — FR-017 / FR-018 / FR-019
# ---------------------------------------------------------------------------


async def _seed_platform(session: AsyncSession, slug: str = "megadrive") -> Platform:
    p = Platform(slug=slug, name=slug.upper())
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return p


async def test_dat_manager_ingests_and_looks_up_by_sha1(
    async_session: AsyncSession,
) -> None:
    p = await _seed_platform(async_session)
    mgr = DatManager(async_session)
    stats = await mgr.ingest(
        platform_id=p.id, source="no-intro", dat_bytes=_LOGIQX_SAMPLE
    )
    assert stats.inserted == 3
    assert stats.skipped_idempotent is False

    matches = await mgr.lookup_by_sha1(platform_id=p.id, sha1="a" * 40)
    assert len(matches) == 1
    assert matches[0].name == "Sonic the Hedgehog (USA)"
    assert matches[0].source == "no-intro"
    assert matches[0].status == DumpStatus.VERIFIED


async def test_dat_manager_ingestion_idempotent(async_session: AsyncSession) -> None:
    """FR-019 — re-ingesting the same DAT yields zero new rows."""
    p = await _seed_platform(async_session)
    mgr = DatManager(async_session)
    first = await mgr.ingest(
        platform_id=p.id, source="no-intro", dat_bytes=_LOGIQX_SAMPLE
    )
    second = await mgr.ingest(
        platform_id=p.id, source="no-intro", dat_bytes=_LOGIQX_SAMPLE
    )
    assert first.skipped_idempotent is False
    assert second.skipped_idempotent is True
    assert second.contents_hash == first.contents_hash

    matches = await mgr.lookup_by_sha1(platform_id=p.id, sha1="a" * 40)
    assert len(matches) == 1


async def test_dat_manager_lookup_by_other_hashes(
    async_session: AsyncSession,
) -> None:
    p = await _seed_platform(async_session)
    mgr = DatManager(async_session)
    await mgr.ingest(
        platform_id=p.id, source="no-intro", dat_bytes=_LOGIQX_SAMPLE
    )

    by_crc = await mgr.lookup_by_crc32(platform_id=p.id, crc32="abcd1234")
    assert len(by_crc) == 1

    by_md5 = await mgr.lookup_by_md5(
        platform_id=p.id, md5="0123456789abcdef0123456789abcdef"
    )
    assert len(by_md5) == 1

    by_name = await mgr.lookup_by_name(
        platform_id=p.id, name="Sonic the Hedgehog (USA)"
    )
    assert len(by_name) == 1


async def test_dat_manager_lookup_returns_empty_on_miss(
    async_session: AsyncSession,
) -> None:
    p = await _seed_platform(async_session)
    mgr = DatManager(async_session)
    matches = await mgr.lookup_by_sha1(platform_id=p.id, sha1="0" * 40)
    assert matches == []


async def test_dat_manager_rejects_unknown_source(
    async_session: AsyncSession,
) -> None:
    p = await _seed_platform(async_session)
    mgr = DatManager(async_session)
    with pytest.raises(ValueError, match="unknown DAT source"):
        await mgr.ingest(
            platform_id=p.id, source="my-fanmade-dat", dat_bytes=_LOGIQX_SAMPLE
        )


async def test_dat_manager_rejects_both_path_and_bytes(
    async_session: AsyncSession,
) -> None:
    p = await _seed_platform(async_session)
    mgr = DatManager(async_session)
    with pytest.raises(ValueError):
        await mgr.ingest(
            platform_id=p.id,
            source="no-intro",
            dat_bytes=_LOGIQX_SAMPLE,
            dat_path="/not-allowed-with-bytes.dat",
        )


async def test_dat_manager_best_match_no_intro_wins_over_tosec(
    async_session: AsyncSession,
) -> None:
    """CL001 / FR-020a — same SHA-1 in two DATs; No-Intro wins."""
    p = await _seed_platform(async_session)
    mgr = DatManager(async_session)
    no_intro_dat = _LOGIQX_SAMPLE
    # Build a TOSEC DAT that asserts the same SHA-1 with a different name.
    tosec_dat = b"""<datafile>
      <game name="Sonic the Hedgehog (TOSEC name)">
        <description>TOSEC alternate</description>
        <rom name="x.md"
             size="524288"
             sha1="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"/>
      </game>
    </datafile>"""
    await mgr.ingest(platform_id=p.id, source="no-intro", dat_bytes=no_intro_dat)
    await mgr.ingest(platform_id=p.id, source="tosec", dat_bytes=tosec_dat)

    best = await mgr.best_match_by_sha1(platform_id=p.id, sha1="a" * 40)
    assert best is not None
    assert best.winner.source == "no-intro"
    assert best.winner.name == "Sonic the Hedgehog (USA)"
    assert len(best.losers) == 1
    assert best.losers[0].source == "tosec"


def test_resolve_authority_handles_empty() -> None:
    assert _resolve_authority([]) is None
