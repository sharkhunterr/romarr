"""Handler backup — Indexer.

Le champ `api_key_encrypted` est le secret opt-in. Le champ
`download_client_id` est une FK vers un download_client : on
sérialise le NAME du client cible (pas l'id) et à l'import on
re-résout par name — permet le portage entre installs même si les
ids diffèrent.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.backup.handlers._shared import SimpleModelHandler, _b64_to_bytes
from romarr.backup.registry import register
from romarr.backup.schemas import ImportMode, ImportOutcome, ResourceKey
from romarr.downloaders.models import DownloadClient
from romarr.indexers.models import Indexer


class IndexerHandler(SimpleModelHandler):
    key = ResourceKey.INDEXERS
    label = "Indexers"
    has_secrets = True

    model_class = Indexer
    FIELDS = [
        "name",
        "implementation",
        "url",
        "categories",
        "priority",
        "enabled",
        "enable_rss",
        "enable_automatic_search",
        "enable_interactive_search",
        "tags",
        "rate_limit_seconds",
        "min_seeders",
        "source",
        "seed_ratio",
        "seed_time_minutes",
        "discount_only",
        "priority_indexer",
        "timeout_seconds",
        "result_limit",
        "rss_auto_grab",
    ]
    SECRET_FIELDS = ["api_key_encrypted"]

    async def serialize_all(
        self, session: AsyncSession, *, include_secrets: bool
    ) -> list[dict[str, Any]]:
        # Résout `download_client_id` → name pour la portabilité
        stmt = (
            select(Indexer, DownloadClient.name)
            .outerjoin(
                DownloadClient, Indexer.download_client_id == DownloadClient.id
            )
        )
        rows = (await session.execute(stmt)).all()
        out: list[dict[str, Any]] = []
        for idx, dc_name in rows:
            item = self._serialize_one(idx, include_secrets)
            # Traduction seed_ratio (Decimal) → str pour JSON
            if item.get("seed_ratio") is not None:
                item["seed_ratio"] = str(item["seed_ratio"])
            item["download_client_name"] = dc_name  # None si aucun rattaché
            out.append(item)
        return out

    async def apply(
        self,
        session: AsyncSession,
        items: list[dict[str, Any]],
        *,
        mode: ImportMode,
    ) -> ImportOutcome:
        # Résout name → id des download_clients (mapping courant)
        dcs = (await session.execute(select(DownloadClient))).scalars().all()
        dc_by_name = {dc.name: dc.id for dc in dcs}

        outcome = ImportOutcome(key=self.key)

        def _hydrate(item: dict[str, Any]) -> dict[str, Any]:
            k = self._payload_to_columns(item)
            # Recompose seed_ratio Decimal si présent
            if item.get("seed_ratio") is not None:
                from decimal import Decimal
                try:
                    k["seed_ratio"] = Decimal(str(item["seed_ratio"]))
                except Exception:
                    k["seed_ratio"] = None
            # Résout FK download_client
            dc_name = item.get("download_client_name")
            if dc_name:
                k["download_client_id"] = dc_by_name.get(dc_name)  # None si absent
            return k

        if mode is ImportMode.REPLACE:
            await session.execute(delete(Indexer))
            for item in items:
                try:
                    session.add(Indexer(**_hydrate(item)))
                    outcome.created += 1
                except Exception as e:
                    outcome.errors.append(f"insert {item.get('name')!r}: {e}")
            await session.flush()
            return outcome

        existing = {
            r.name: r
            for r in (await session.execute(select(Indexer))).scalars().all()
        }
        for item in items:
            name = item.get("name")
            if not name:
                outcome.skipped += 1
                continue
            row = existing.get(name)
            if row is None:
                try:
                    session.add(Indexer(**_hydrate(item)))
                    outcome.created += 1
                except Exception as e:
                    outcome.errors.append(f"insert {name!r}: {e}")
            else:
                if mode is ImportMode.MERGE:
                    outcome.skipped += 1
                    continue
                try:
                    for k, v in _hydrate(item).items():
                        if k == "name":
                            continue
                        setattr(row, k, v)
                    outcome.updated += 1
                except Exception as e:
                    outcome.errors.append(f"update {name!r}: {e}")
        await session.flush()
        return outcome


register(IndexerHandler())
