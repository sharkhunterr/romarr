"""Manual grab endpoint tests (T063-T064)."""

from __future__ import annotations

from datetime import UTC, datetime

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.indexers.models import Indexer
from romarr.search.models import Blocklist
from tests.search.api.conftest import seed_admin_and_login


async def _seed_indexer(api_engine: AsyncEngine) -> int:
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        idx = Indexer(
            name="Test",
            implementation="newznab",
            url="https://idx.test/api",
            categories=[1060],
            source="manual",
        )
        session.add(idx)
        await session.commit()
        await session.refresh(idx)
        return idx.id


def _grab_payload(indexer_id: int) -> dict[str, object]:
    return {
        "indexer_id": indexer_id,
        "indexer_guid": "guid-abc",
        "download_url": "https://idx.test/abc.torrent",
        "title": "Sonic the Hedgehog (USA)",
    }


@pytest.mark.asyncio
async def test_grab_with_no_eligible_client_returns_no_eligible(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """No download clients configured → dispatch returns
    ``no_eligible_client`` and the history row records it."""
    await seed_admin_and_login(api_engine, api_client)
    indexer_id = await _seed_indexer(api_engine)
    response = await api_client.post(
        "/api/v3/rom/release/grab", json=_grab_payload(indexer_id)
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "no_eligible_client"
    assert body["correlation_id"]


@pytest.mark.asyncio
async def test_grab_blocklisted_returns_409(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """A grab targeting a blocklisted (indexer_id, guid) returns 409
    unless ?force=true is supplied (FR-022 / SC-006)."""
    await seed_admin_and_login(api_engine, api_client)
    indexer_id = await _seed_indexer(api_engine)

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            Blocklist(
                indexer_id=indexer_id,
                indexer_guid="guid-abc",
                release_title="x",
                reason="known-bad",
                added_by="system",
                added_at=datetime.now(UTC),
            )
        )
        await session.commit()

    blocked = await api_client.post(
        "/api/v3/rom/release/grab", json=_grab_payload(indexer_id)
    )
    assert blocked.status_code == 409
    assert blocked.json()["errorCode"] == "blocklisted"


@pytest.mark.asyncio
async def test_grab_blocklisted_force_overrides(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """``?force=true`` skips the blocklist gate but still runs through
    dispatch — with no clients configured, it returns
    ``no_eligible_client`` rather than a 409."""
    await seed_admin_and_login(api_engine, api_client)
    indexer_id = await _seed_indexer(api_engine)

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            Blocklist(
                indexer_id=indexer_id,
                indexer_guid="guid-abc",
                release_title="x",
                reason="known-bad",
                added_by="system",
                added_at=datetime.now(UTC),
            )
        )
        await session.commit()

    forced = await api_client.post(
        "/api/v3/rom/release/grab?force=true",
        json=_grab_payload(indexer_id),
    )
    # The blocklist gate is bypassed; dispatch then runs (and finds
    # no eligible client because none are configured).
    assert forced.status_code == 200
    assert forced.json()["status"] == "no_eligible_client"


@pytest.mark.asyncio
async def test_grab_unauthenticated_401(
    api_client: httpx.AsyncClient,
) -> None:
    response = await api_client.post(
        "/api/v3/rom/release/grab", json=_grab_payload(1)
    )
    assert response.status_code == 401
