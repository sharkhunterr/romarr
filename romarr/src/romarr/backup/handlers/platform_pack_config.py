"""Handler backup — PlatformPackConfig (singleton row).

Singleton = un handler qui écrase toujours la ligne id=1 (peu
importe le mode — upsert/merge/replace se comportent tous comme
un update in-place car il ne peut y avoir qu'une seule row).

Export : un item avec les 2 valeurs actuelles. Import : override
de la ligne id=1 (get-or-create + patch les 2 champs).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from romarr.backup.registry import register
from romarr.backup.schemas import ImportMode, ImportOutcome, ResourceKey
from romarr.platform_packs.config import get_or_create_platform_pack_config


class PlatformPackConfigHandler:
    key = ResourceKey.PLATFORM_PACK_CONFIG
    label = "Platform Pack Config"
    has_secrets = False

    async def count(self, session: AsyncSession) -> int:
        # Toujours 1 (singleton). Retour rapide sans query.
        return 1

    async def serialize_all(
        self, session: AsyncSession, *, include_secrets: bool
    ) -> list[dict[str, Any]]:
        row = await get_or_create_platform_pack_config(session)
        return [
            {
                "builtin_enabled": row.builtin_enabled,
                "priority": row.priority,
            }
        ]

    async def apply(
        self,
        session: AsyncSession,
        items: list[dict[str, Any]],
        *,
        mode: ImportMode,
    ) -> ImportOutcome:
        outcome = ImportOutcome(key=self.key)
        if not items:
            return outcome
        # Un seul item attendu (singleton). Si plusieurs, on prend le
        # dernier — comportement défensif au cas où quelqu'un aurait
        # édité le bundle à la main.
        payload = items[-1]
        row = await get_or_create_platform_pack_config(session)
        if "builtin_enabled" in payload:
            row.builtin_enabled = bool(payload["builtin_enabled"])
        if "priority" in payload and payload["priority"] in (
            "builtin",
            "community",
        ):
            row.priority = payload["priority"]
        await session.flush()
        outcome.updated = 1
        return outcome


register(PlatformPackConfigHandler())
