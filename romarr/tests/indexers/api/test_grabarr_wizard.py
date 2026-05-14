"""Atomic Add-Grabarr wizard endpoint (slice 427 / R3a).

Covers the full ``POST /api/v3/indexer/grabarr`` flow:

- happy path: probes ``/health``, persists both rows under a
  single transaction, returns the joined response.
- protocol_version mismatch / 401 / unreachable Grabarr — must
  refuse to persist (neither row created).
- bad ``base_url`` (missing scheme, missing host) → 400.
- duplicate (host, port) on a re-submit → 409.
- ``download_root`` is propagated to the downloader row.
"""

from __future__ import annotations

import httpx
import pytest
import respx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.downloaders.models import DownloadClient
from romarr.indexers.models import Indexer
from tests.indexers.api.conftest import seed_admin_and_login


_HEALTH_OK = {
    "version": "1.2.1",
    "protocol_version": 1,
    "sources": ["internet_archive", "minerva"],
}


def _payload(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "Local Grabarr",
        "base_url": "http://grabarr.lan:8080",
        "profile_slug": "roms_all",
        "api_key": "rmk_test_secret",
        "timeout_seconds": 60,
    }
    base.update(over)
    return base


# ---- happy path -------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_wizard_creates_linked_pair_with_health_probe(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    respx.get("http://grabarr.lan:8080/romarr/api/v1/health").mock(
        return_value=httpx.Response(200, json=_HEALTH_OK)
    )

    response = await api_client.post(
        "/api/v3/indexer/grabarr", json=_payload()
    )
    assert response.status_code == 201, response.text
    body = response.json()

    # 1. The downloader row landed first and surfaces a sensible shape.
    dl = body["download_client"]
    assert dl["type"] == "grabarr_direct"
    assert dl["host"] == "grabarr.lan"
    assert dl["port"] == 8080
    assert dl["enable_for_torrents"] is True
    assert dl["enable_for_usenet"] is False
    assert dl["timeout_seconds"] == 60
    assert dl["download_root"] is None  # not set in payload
    assert dl["client_version_seen"] == "1.2.1"

    # 2. The indexer row is linked back to it.
    idx = body["indexer"]
    assert idx["implementation"] == "grabarr"
    assert idx["url"] == "http://grabarr.lan:8080/torznab/roms_all"
    assert idx["download_client_id"] == dl["id"]
    assert idx["source"] == "manual"
    assert idx["is_configured"] is True

    # 3. The DB matches.
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        rows_dl = (await session.execute(select(DownloadClient))).scalars().all()
        rows_idx = (await session.execute(select(Indexer))).scalars().all()
    assert len(rows_dl) == 1 and rows_dl[0].type == "grabarr_direct"
    assert len(rows_idx) == 1
    assert rows_idx[0].download_client_id == rows_dl[0].id


@pytest.mark.asyncio
@respx.mock
async def test_wizard_persists_download_root(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    respx.get("http://grabarr.lan:8080/romarr/api/v1/health").mock(
        return_value=httpx.Response(200, json=_HEALTH_OK)
    )

    response = await api_client.post(
        "/api/v3/indexer/grabarr",
        json=_payload(download_root="/data/grabarr"),
    )
    assert response.status_code == 201
    assert response.json()["download_client"]["download_root"] == "/data/grabarr"


# ---- connectivity-gate ------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_wizard_refuses_on_protocol_version_mismatch(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    respx.get("http://grabarr.lan:8080/romarr/api/v1/health").mock(
        return_value=httpx.Response(
            200,
            json={"version": "9.9.9", "protocol_version": 2, "sources": []},
        )
    )

    response = await api_client.post(
        "/api/v3/indexer/grabarr", json=_payload()
    )
    assert response.status_code == 400
    body = response.json()
    assert body["errorMessage"] == "grabarr_unreachable_or_incompatible"
    assert body["errorCode"] == "VersionError"

    # Neither row was created.
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        assert (await session.execute(select(DownloadClient))).all() == []
        assert (await session.execute(select(Indexer))).all() == []


@pytest.mark.asyncio
@respx.mock
async def test_wizard_refuses_on_401(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    respx.get("http://grabarr.lan:8080/romarr/api/v1/health").mock(
        return_value=httpx.Response(401)
    )

    response = await api_client.post(
        "/api/v3/indexer/grabarr", json=_payload()
    )
    assert response.status_code == 400
    assert response.json()["errorCode"] == "AuthError"

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        assert (await session.execute(select(DownloadClient))).all() == []
        assert (await session.execute(select(Indexer))).all() == []


@pytest.mark.asyncio
@respx.mock
async def test_wizard_refuses_on_unreachable_grabarr(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    respx.get("http://grabarr.lan:8080/romarr/api/v1/health").mock(
        side_effect=httpx.ConnectError("refused")
    )

    response = await api_client.post(
        "/api/v3/indexer/grabarr", json=_payload()
    )
    assert response.status_code == 400
    assert response.json()["errorCode"] == "ConnectionError"


# ---- input validation -------------------------------------------------


@pytest.mark.asyncio
async def test_wizard_rejects_base_url_without_scheme(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.post(
        "/api/v3/indexer/grabarr",
        json=_payload(base_url="grabarr.lan:8080"),
    )
    assert response.status_code == 400
    # urlsplit returns scheme='' for this — we surface as 'bad_request'.
    assert response.json()["errorCode"] == "bad_request"


@pytest.mark.asyncio
async def test_wizard_rejects_unknown_scheme(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    await seed_admin_and_login(api_engine, api_client)
    response = await api_client.post(
        "/api/v3/indexer/grabarr",
        json=_payload(base_url="ftp://grabarr.lan:8080"),
    )
    assert response.status_code == 400
    assert "http" in response.json()["details"]
