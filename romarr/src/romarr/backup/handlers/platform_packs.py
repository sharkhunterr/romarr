"""Handler backup — PlatformPack (metadata seule).

Limitation MVP : les YAML body des packs ne sont PAS persistés en DB
(cf `packs.py:317` — "MVP doesn't persist pack bodies; re-upload the
YAML to..."). Cet export sort donc juste la liste des packs
INSTALLÉS avec leur `pack_version` + `source_url` — l'opérateur peut
re-fetch les YAML depuis les `source_url` originales (typiquement des
raw.githubusercontent.com URLs).

À l'import, on ne réhydrate PAS les packs (impossible sans le YAML) :
on ajoute juste des lignes dans une future collection « packs à
réinstaller » qu'un endpoint dédié pourrait re-fetch. Pour l'instant
l'import de ce type émet un warning explicite et skip tout — l'user
doit re-upload les YAML manuellement via le workflow existant.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.backup.handlers._shared import SimpleModelHandler
from romarr.backup.registry import register
from romarr.backup.schemas import ImportMode, ImportOutcome, ResourceKey
from romarr.domain.models import PlatformPack


class PlatformPackHandler(SimpleModelHandler):
    key = ResourceKey.PLATFORM_PACKS
    label = "Platform Packs"
    has_secrets = False

    model_class = PlatformPack
    name_column = "pack_version"  # les packs se dedup par version, pas par nom
    FIELDS = [
        "pack_version",
        "pack_source",
        "source_url",
        "applied_by",
        "contents_hash",
    ]

    async def serialize_all(
        self, session: AsyncSession, *, include_secrets: bool
    ) -> list[dict[str, Any]]:
        rows = (await session.execute(select(PlatformPack))).scalars().all()
        return [self._serialize_one(row, include_secrets) for row in rows]

    async def apply(
        self,
        session: AsyncSession,
        items: list[dict[str, Any]],
        *,
        mode: ImportMode,
    ) -> ImportOutcome:
        # Aucune réinstallation possible depuis le bundle seul — le
        # YAML body n'a jamais été persisté (design MVP). On émet un
        # warning listant les source_url à re-fetch manuellement.
        outcome = ImportOutcome(key=self.key)
        for item in items:
            src = item.get("source_url") or "<no source_url>"
            outcome.errors.append(
                f"pack {item.get('pack_version')!r} not re-installed "
                f"(YAML body not in bundle) — re-upload from: {src}"
            )
            outcome.skipped += 1
        return outcome


register(PlatformPackHandler())
