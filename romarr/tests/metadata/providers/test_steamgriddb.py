"""SteamGridDB provider tests (T037, T038).

Cover-only provider — search_games / get_game raise
NotImplementedError, get_cover does the real work, and the registry
filter for ``invoked_in_scan=False`` keeps it out of the standard
refresh flow.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.metadata import PROVIDER_REGISTRY, ProviderField, load_enabled_providers
from romarr.metadata.errors import AuthError, NotFoundError
from romarr.metadata.models import MetadataProviderConfig
from romarr.metadata.providers.steamgriddb import SteamGridDBProvider


@pytest.fixture
def sgdb_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(5.0))


def _make_provider(client: httpx.AsyncClient) -> SteamGridDBProvider:
    p = SteamGridDBProvider(rate_limit_rps=100, rate_limit_burst=100, client=client)
    p.configure({"api_key": "sgdb-key"})
    return p


# ---------------------------------------------------------------------------
# T037 — cover-only contract
# ---------------------------------------------------------------------------


async def test_search_games_raises_not_implemented(
    sgdb_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(sgdb_client)
    with pytest.raises(NotImplementedError):
        await p.search_games("Sonic")


async def test_get_cover_returns_bytes(sgdb_client: httpx.AsyncClient) -> None:
    p = _make_provider(sgdb_client)

    with respx.mock:
        respx.get("https://www.steamgriddb.com/api/v2/grids/game/123").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"url": "https://cdn.example/grid.png"}]},
            )
        )
        respx.get("https://cdn.example/grid.png").mock(
            return_value=httpx.Response(
                200, content=b"png-bytes", headers={"content-type": "image/png"}
            )
        )

        data, content_type = await p.get_cover("123")

    assert data == b"png-bytes"
    assert content_type == "image/png"


async def test_get_game_returns_cover_only_metadata(
    sgdb_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(sgdb_client)

    with respx.mock:
        respx.get("https://www.steamgriddb.com/api/v2/grids/game/123").mock(
            return_value=httpx.Response(
                200,
                json={"data": [{"url": "https://cdn.example/grid.png"}]},
            )
        )
        meta = await p.get_game("123")

    assert ProviderField.COVER in meta.fields
    # Strict cover-only contract: no other fields populated.
    assert set(meta.fields.keys()) == {ProviderField.COVER}
    assert meta.cover_url == "https://cdn.example/grid.png"


async def test_get_cover_no_grids_raises_not_found(
    sgdb_client: httpx.AsyncClient,
) -> None:
    p = _make_provider(sgdb_client)
    with respx.mock:
        respx.get("https://www.steamgriddb.com/api/v2/grids/game/999").mock(
            return_value=httpx.Response(200, json={"data": []})
        )
        with pytest.raises(NotFoundError):
            await p.get_cover("999")


async def test_configure_rejects_missing_api_key(
    sgdb_client: httpx.AsyncClient,
) -> None:
    p = SteamGridDBProvider(rate_limit_rps=100, rate_limit_burst=100, client=sgdb_client)
    with pytest.raises(AuthError):
        p.configure({})


# ---------------------------------------------------------------------------
# T038 — registry filter for FR-005
# ---------------------------------------------------------------------------


async def test_excluded_from_scan_flow(
    async_session: AsyncSession, metadata_env: object
) -> None:
    import json

    from romarr.metadata.encryption import encrypt

    async_session.add(
        MetadataProviderConfig(
            provider_name="steamgriddb",
            enabled=True,
            priority_global=90,
            cache_ttl_seconds=2_592_000,
            rate_limit_rps=5,
            rate_limit_burst=10,
            config_encrypted=encrypt(json.dumps({"api_key": "k"}).encode()),
        )
    )
    await async_session.commit()

    scan_only = await load_enabled_providers(async_session, scan=True)
    assert [p.name for p in scan_only] == []

    everything = await load_enabled_providers(async_session, scan=False)
    assert [p.name for p in everything] == ["steamgriddb"]


# ---------------------------------------------------------------------------
# Self-registration
# ---------------------------------------------------------------------------


def test_self_registered() -> None:
    assert PROVIDER_REGISTRY.get("steamgriddb") is SteamGridDBProvider
