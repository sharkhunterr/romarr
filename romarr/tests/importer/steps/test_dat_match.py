"""DAT-match step tests (T035, T036, T037)."""

from __future__ import annotations

from collections.abc import Iterable
from typing import cast

import pytest

from romarr.domain.enums import DumpStatus
from romarr.identification.hashmatch.cascade import HashMatchCascade
from romarr.identification.hashmatch.types import (
    BackendName,
    HashLookupResult,
    RemoteHashEntry,
)
from romarr.importer.steps.dat_match import match_dat


class _FakeBackend:
    """Stub backend for the cascade. Returns whatever the test
    queues into ``self.entries`` for the next call."""

    name: BackendName

    def __init__(
        self,
        *,
        name: BackendName,
        entries: Iterable[RemoteHashEntry] = (),
        error: str | None = None,
    ) -> None:
        self.name = name
        self._entries = tuple(entries)
        self._error = error

    async def lookup_sha1(
        self, *, platform_id: int, sha1: str
    ) -> HashLookupResult:
        del platform_id, sha1
        if self._error is not None:
            return HashLookupResult(backend=self.name, error=self._error)
        return HashLookupResult(backend=self.name, entries=self._entries)


def _cascade(*backends: _FakeBackend) -> HashMatchCascade:
    return HashMatchCascade(cast("list", list(backends)))


# ---------------------------------------------------------------------------
# T035 — local DAT hit populates dat_verified + source + entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_local_dat_hit_populates_verified_source_entry() -> None:
    entry = RemoteHashEntry(
        source="no-intro",
        name="Sonic the Hedgehog (USA).md",
        sha1="a" * 40,
        crc32="aabbccdd",
        size_bytes=524288,
        status=DumpStatus.VERIFIED,
    )
    cascade = _cascade(
        _FakeBackend(name=BackendName.LOCAL, entries=(entry,)),
    )

    result = await match_dat(
        cascade=cascade,
        platform_id=1,
        sha1="A" * 40,  # case-insensitive
    )
    assert result.dat_verified is True
    assert result.dat_source == "no-intro"
    assert result.entry is entry
    assert result.dump_status is DumpStatus.VERIFIED
    assert result.backend_status[str(BackendName.LOCAL)] == "ok"


# ---------------------------------------------------------------------------
# T036 — no DAT match continues (FR-011)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_no_dat_match_returns_unverified() -> None:
    cascade = _cascade(
        _FakeBackend(name=BackendName.LOCAL, entries=()),
    )

    result = await match_dat(
        cascade=cascade,
        platform_id=1,
        sha1="b" * 40,
    )
    assert result.dat_verified is False
    assert result.dat_source is None
    assert result.entry is None
    assert result.dump_status is DumpStatus.UNKNOWN
    assert result.backend_status[str(BackendName.LOCAL)] == "empty"


# ---------------------------------------------------------------------------
# T037 — baddump status propagates; dat_verified flips to False
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_baddump_propagates_status_and_flips_verified() -> None:
    entry = RemoteHashEntry(
        source="no-intro",
        name="Sonic the Hedgehog (USA) [b].md",
        sha1="c" * 40,
        status=DumpStatus.BADDUMP,
    )
    cascade = _cascade(
        _FakeBackend(name=BackendName.LOCAL, entries=(entry,)),
    )

    result = await match_dat(
        cascade=cascade,
        platform_id=1,
        sha1="c" * 40,
    )
    # Even though we got a hit, the BADDUMP status disqualifies it
    # from being a "verified" entry.
    assert result.dat_verified is False
    assert result.dump_status is DumpStatus.BADDUMP
    assert result.dat_source == "no-intro"
    assert result.entry is entry


@pytest.mark.asyncio
async def test_backend_error_surfaces_in_status() -> None:
    cascade = _cascade(
        _FakeBackend(
            name=BackendName.HASHEOUS,
            error="circuit_open",
        ),
        _FakeBackend(name=BackendName.LOCAL, entries=()),
    )

    result = await match_dat(
        cascade=cascade,
        platform_id=1,
        sha1="d" * 40,
    )
    assert result.dat_verified is False
    assert result.backend_status[str(BackendName.HASHEOUS)] == "circuit_open"
    assert result.backend_status[str(BackendName.LOCAL)] == "empty"
