"""Handler backup — DatSource.

Particularité : `platform_id` est une FK. On sérialise le SLUG de la
platform en lieu et place de l'id, et à l'import on re-résout le slug
côté cible. Une source pour une platform absente est SKIPPED avec un
warning dans l'outcome — l'opérateur doit importer les Platform Packs
d'abord si besoin.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.backup.handlers._shared import SimpleModelHandler
from romarr.backup.registry import register
from romarr.backup.schemas import ImportMode, ImportOutcome, ResourceKey
from romarr.domain.models import DatSource, Platform


class DatSourceHandler(SimpleModelHandler):
    key = ResourceKey.DAT_SOURCES
    label = "DAT Sources"
    has_secrets = False

    model_class = DatSource
    FIELDS = ["name", "url", "source", "enabled"]

    async def serialize_all(
        self, session: AsyncSession, *, include_secrets: bool
    ) -> list[dict[str, Any]]:
        # Charge sources + slug de la platform en 1 requête pour éviter N+1
        stmt = (
            select(DatSource, Platform.slug)
            .join(Platform, DatSource.platform_id == Platform.id)
        )
        rows = (await session.execute(stmt)).all()
        out: list[dict[str, Any]] = []
        for src, platform_slug in rows:
            item = self._serialize_one(src, include_secrets)
            item["platform_slug"] = platform_slug
            out.append(item)
        return out

    async def apply(
        self,
        session: AsyncSession,
        items: list[dict[str, Any]],
        *,
        mode: ImportMode,
    ) -> ImportOutcome:
        # Pré-charge les platforms pour éviter un SELECT par item
        platforms = (await session.execute(select(Platform))).scalars().all()
        by_slug = {p.slug: p.id for p in platforms}

        outcome = ImportOutcome(key=self.key)

        if mode is ImportMode.REPLACE:
            from sqlalchemy import delete
            await session.execute(delete(DatSource))
            for item in items:
                pid = by_slug.get(item.get("platform_slug"))
                if pid is None:
                    outcome.errors.append(
                        f"platform slug {item.get('platform_slug')!r} "
                        f"unknown — source {item.get('name')!r} skipped"
                    )
                    outcome.skipped += 1
                    continue
                row = DatSource(
                    name=item["name"], url=item["url"],
                    source=item.get("source", "custom"),
                    platform_id=pid,
                    enabled=item.get("enabled", True),
                )
                session.add(row)
                outcome.created += 1
            await session.flush()
            return outcome

        # UPSERT / MERGE : dedup par (name, platform_id)
        existing = {
            (r.name, r.platform_id): r
            for r in (await session.execute(select(DatSource))).scalars().all()
        }
        for item in items:
            name = item.get("name")
            slug = item.get("platform_slug")
            pid = by_slug.get(slug)
            if not name or pid is None:
                outcome.skipped += 1
                if pid is None:
                    outcome.errors.append(
                        f"platform slug {slug!r} unknown — "
                        f"source {name!r} skipped"
                    )
                continue
            row = existing.get((name, pid))
            if row is None:
                session.add(DatSource(
                    name=name, url=item["url"],
                    source=item.get("source", "custom"),
                    platform_id=pid,
                    enabled=item.get("enabled", True),
                ))
                outcome.created += 1
            else:
                if mode is ImportMode.MERGE:
                    outcome.skipped += 1
                    continue
                row.url = item.get("url", row.url)
                row.source = item.get("source", row.source)
                row.enabled = item.get("enabled", row.enabled)
                outcome.updated += 1
        await session.flush()
        return outcome


register(DatSourceHandler())
