"""Hash-match cascade tests — FR-026 / FR-027 / FR-028 / FR-020a."""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
import respx
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.config import Settings
from romarr.domain.models import Platform
from romarr.identification.dat.manager import DatManager
from romarr.identification.hashmatch.cascade import (
    HashMatchCascade,
    _resolve_authority,
)
from romarr.identification.hashmatch.local import LocalDatBackend
from romarr.identification.hashmatch.remote import (
    HasheousBackend,
    PlayMatchBackend,
)
from romarr.identification.hashmatch.types import (
    BackendName,
    HashLookupResult,
    RemoteHashEntry,
)

_NO_INTRO_DAT = b"""<datafile>
  <game name="Sonic the Hedgehog (USA)">
    <rom name="sonic.md" size="524288"
         sha1="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"/>
  </game>
</datafile>"""


_SETTINGS = Settings(
    hasheous_base_url="https://api.hasheous.test",
    playmatch_base_url="https://api.playmatch.test",
    hasheous_token="",
    playmatch_token="",
)


@pytest_asyncio.fixture
async def _platform(async_session: AsyncSession) -> Platform:
    p = Platform(slug="megadrive", name="Mega Drive")
    async_session.add(p)
    await async_session.commit()
    await async_session.refresh(p)
    return p


@pytest_asyncio.fixture
async def _seeded_local_backend(
    async_session: AsyncSession, _platform: Platform
) -> AsyncIterator[LocalDatBackend]:
    mgr = DatManager(async_session)
    await mgr.ingest(
        platform_id=_platform.id, source="no-intro", dat_bytes=_NO_INTRO_DAT
    )
    yield LocalDatBackend(mgr)


# ---------------------------------------------------------------------------
# Local backend
# ---------------------------------------------------------------------------


async def test_local_backend_returns_dat_entry(
    _seeded_local_backend: LocalDatBackend, _platform: Platform
) -> None:
    result = await _seeded_local_backend.lookup_sha1(
        platform_id=_platform.id, sha1="a" * 40
    )
    assert result.ok
    assert len(result.entries) == 1
    assert result.entries[0].source == "no-intro"
    assert result.entries[0].name == "Sonic the Hedgehog (USA)"


async def test_local_backend_empty_on_miss(
    _seeded_local_backend: LocalDatBackend, _platform: Platform
) -> None:
    result = await _seeded_local_backend.lookup_sha1(
        platform_id=_platform.id, sha1="0" * 40
    )
    assert result.ok
    assert result.entries == ()


# ---------------------------------------------------------------------------
# Remote backends — Hasheous + PlayMatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hasheous_returns_match_via_respx() -> None:
    sha1 = "a" * 40
    payload = {
        "source": "hasheous",
        "name": "Sonic the Hedgehog (USA)",
        "sha1": sha1,
        "size": 524288,
    }
    with respx.mock(base_url="https://api.hasheous.test") as router:
        router.get(f"/v1/lookup/{sha1}").mock(
            return_value=httpx.Response(200, json=payload)
        )
        backend = HasheousBackend(_SETTINGS)
        result = await backend.lookup_sha1(platform_id=1, sha1=sha1)

    assert result.ok
    assert len(result.entries) == 1
    assert result.entries[0].source == "hasheous"
    assert result.entries[0].sha1 == sha1


@pytest.mark.asyncio
async def test_hasheous_404_returns_empty_no_error() -> None:
    sha1 = "a" * 40
    with respx.mock(base_url="https://api.hasheous.test") as router:
        router.get(f"/v1/lookup/{sha1}").mock(return_value=httpx.Response(404))
        backend = HasheousBackend(_SETTINGS)
        result = await backend.lookup_sha1(platform_id=1, sha1=sha1)

    assert result.ok
    assert result.entries == ()


@pytest.mark.asyncio
async def test_hasheous_429_marks_error_for_breaker() -> None:
    sha1 = "a" * 40
    with respx.mock(base_url="https://api.hasheous.test") as router:
        router.get(f"/v1/lookup/{sha1}").mock(return_value=httpx.Response(429))
        backend = HasheousBackend(_SETTINGS)
        result = await backend.lookup_sha1(platform_id=1, sha1=sha1)
    assert not result.ok
    assert result.error is not None
    assert "rate_limited" in result.error


@pytest.mark.asyncio
async def test_hasheous_5xx_marks_error() -> None:
    sha1 = "a" * 40
    with respx.mock(base_url="https://api.hasheous.test") as router:
        router.get(f"/v1/lookup/{sha1}").mock(return_value=httpx.Response(503))
        backend = HasheousBackend(_SETTINGS)
        result = await backend.lookup_sha1(platform_id=1, sha1=sha1)
    assert not result.ok


@pytest.mark.asyncio
async def test_hasheous_sends_bearer_when_token_set() -> None:
    sha1 = "a" * 40
    settings_with_token = Settings(
        hasheous_base_url="https://api.hasheous.test",
        hasheous_token="secrets-go-here",
    )
    captured: list[httpx.Request] = []

    def _capture(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={})

    with respx.mock(base_url="https://api.hasheous.test") as router:
        router.get(f"/v1/lookup/{sha1}").mock(side_effect=_capture)
        backend = HasheousBackend(settings_with_token)
        await backend.lookup_sha1(platform_id=1, sha1=sha1)

    assert captured
    assert captured[0].headers.get("Authorization") == "Bearer secrets-go-here"


@pytest.mark.asyncio
async def test_playmatch_returns_matches_under_wrapper() -> None:
    sha1 = "a" * 40
    payload = {
        "matches": [
            {
                "source": "playmatch",
                "name": "Sonic the Hedgehog",
                "sha1": sha1,
            }
        ]
    }
    with respx.mock(base_url="https://api.playmatch.test") as router:
        router.get("/api/v1/match", params={"sha1": sha1}).mock(
            return_value=httpx.Response(200, json=payload)
        )
        backend = PlayMatchBackend(_SETTINGS)
        result = await backend.lookup_sha1(platform_id=1, sha1=sha1)

    assert result.ok
    assert len(result.entries) == 1
    assert result.entries[0].source == "playmatch"


# ---------------------------------------------------------------------------
# Cascade orchestration
# ---------------------------------------------------------------------------


class _StubBackend:
    """Tiny in-memory backend used to exercise the cascade orchestrator."""

    def __init__(
        self,
        name: BackendName,
        *,
        result: HashLookupResult | None = None,
        error: str | None = None,
    ) -> None:
        self.name = name
        self.calls = 0
        self._result = result
        self._error = error

    async def lookup_sha1(
        self, *, platform_id: int, sha1: str
    ) -> HashLookupResult:
        self.calls += 1
        if self._error is not None:
            return HashLookupResult(backend=self.name, error=self._error)
        return self._result or HashLookupResult(backend=self.name)


@pytest.mark.asyncio
async def test_cascade_picks_no_intro_winner_across_backends() -> None:
    """CL001: same SHA-1 from local (no-intro) + remote (hasheous) → no-intro wins."""
    local = _StubBackend(
        BackendName.LOCAL,
        result=HashLookupResult(
            backend=BackendName.LOCAL,
            entries=(
                RemoteHashEntry(source="no-intro", name="Sonic (USA)", sha1="a" * 40),
            ),
        ),
    )
    hasheous = _StubBackend(
        BackendName.HASHEOUS,
        result=HashLookupResult(
            backend=BackendName.HASHEOUS,
            entries=(
                RemoteHashEntry(source="hasheous", name="Sonic", sha1="a" * 40),
            ),
        ),
    )
    cascade = HashMatchCascade([local, hasheous])
    match = await cascade.lookup_sha1(platform_id=1, sha1="a" * 40)

    assert match.winner is not None
    assert match.winner.source == "no-intro"
    assert match.losers and match.losers[0].source == "hasheous"
    assert match.backend_status[BackendName.LOCAL] == "ok"
    assert match.backend_status[BackendName.HASHEOUS] == "ok"


@pytest.mark.asyncio
async def test_cascade_returns_local_only_when_remotes_fail() -> None:
    """FR-028: when both remotes are down, local DAT cache continues to serve."""
    local = _StubBackend(
        BackendName.LOCAL,
        result=HashLookupResult(
            backend=BackendName.LOCAL,
            entries=(
                RemoteHashEntry(source="no-intro", name="Sonic (USA)", sha1="a" * 40),
            ),
        ),
    )
    hasheous = _StubBackend(BackendName.HASHEOUS, error="http_error:Timeout")
    playmatch = _StubBackend(BackendName.PLAYMATCH, error="http_error:Timeout")
    cascade = HashMatchCascade([local, hasheous, playmatch])

    match = await cascade.lookup_sha1(platform_id=1, sha1="a" * 40)
    assert match.winner is not None
    assert match.winner.source == "no-intro"
    assert match.backend_status[BackendName.HASHEOUS] == "http_error:Timeout"
    assert match.backend_status[BackendName.PLAYMATCH] == "http_error:Timeout"


@pytest.mark.asyncio
async def test_cascade_breaker_short_circuits_after_5_failures() -> None:
    """FR-027: after 5 failures within 60 s, the breaker short-circuits."""
    failing = _StubBackend(BackendName.HASHEOUS, error="http_status:503")
    cascade = HashMatchCascade([failing])

    # 5 failing calls → breaker opens; the 6th short-circuits without a call.
    for _ in range(5):
        await cascade.lookup_sha1(platform_id=1, sha1="a" * 40)
    pre_call_count = failing.calls
    result = await cascade.lookup_sha1(platform_id=1, sha1="a" * 40)
    assert failing.calls == pre_call_count  # short-circuit; no new outbound call
    assert result.backend_status[BackendName.HASHEOUS] == "circuit_open"


@pytest.mark.asyncio
async def test_cascade_empty_when_no_match_anywhere() -> None:
    a = _StubBackend(BackendName.LOCAL)
    b = _StubBackend(BackendName.HASHEOUS)
    cascade = HashMatchCascade([a, b])
    match = await cascade.lookup_sha1(platform_id=1, sha1="0" * 40)
    assert match.winner is None
    assert match.losers == ()
    assert match.backend_status[BackendName.LOCAL] == "empty"


def test_cascade_requires_at_least_one_backend() -> None:
    with pytest.raises(ValueError):
        HashMatchCascade([])


def test_resolve_authority_dedups_identical_entries() -> None:
    e = RemoteHashEntry(source="no-intro", name="Sonic", sha1="a" * 40)
    winner, losers = _resolve_authority([e, e])
    assert winner is not None
    assert losers == ()
