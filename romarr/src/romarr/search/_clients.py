"""Async factories that materialise live :class:`NewznabClient` /
:class:`DownloadClient` instances for one call from a persisted row.

Used by the API surface to pass an awaitable factory into the round
orchestrators / dispatcher so the orchestrator stays decoupled from
the persistence layer (tests inject stub factories instead).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from sqlalchemy import select

from romarr.downloaders.factory import build_client_from_row
from romarr.downloaders.models import DownloadClient as DownloadClientRow
from romarr.indexers.client import NewznabClient
from romarr.indexers.models import Indexer
from romarr.metadata.encryption import decrypt

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from romarr.downloaders.base import DownloadClient


def make_indexer_client_factory(
    session: AsyncSession,
) -> Callable[[int], Awaitable[NewznabClient]]:
    """Return an async factory that yields a fresh :class:`NewznabClient`
    for one indexer id.

    The orchestrator calls the factory then ``await client.aclose()``
    after each round so connections aren't pooled across rounds — the
    network round-trip dominates anyway, and per-round close keeps
    the indexer-level rate limiter / breaker scoped to one operation.
    """

    async def _factory(indexer_id: int) -> NewznabClient:
        row = (
            await session.execute(select(Indexer).where(Indexer.id == indexer_id))
        ).scalar_one()
        api_key = (
            decrypt(row.api_key_encrypted).decode("utf-8")
            if row.api_key_encrypted
            else None
        )
        return NewznabClient(
            indexer_id=row.id,
            name=row.name,
            base_url=row.url,
            api_key=api_key,
            timeout_seconds=row.timeout_seconds,
            result_limit=row.result_limit,
        )

    return _factory


def make_download_client_factory(
    session: AsyncSession,
) -> Callable[[int], Awaitable[DownloadClient]]:
    """Return an async factory that yields a fresh :class:`DownloadClient`
    for one download_client id.
    """

    async def _factory(client_id: int) -> DownloadClient:
        row = (
            await session.execute(
                select(DownloadClientRow).where(DownloadClientRow.id == client_id)
            )
        ).scalar_one()
        return build_client_from_row(row)

    return _factory


__all__ = ["make_download_client_factory", "make_indexer_client_factory"]
