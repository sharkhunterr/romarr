"""Handler backup — Notification (Apprise-based).

Le secret `apprise_url_encrypted` est **obligatoire en DB** (colonne
NOT NULL). Sans include_secrets, on ne peut pas créer une notification
importée — les items concernés sont SKIPPED avec un warning explicite.

Alternative : accepter l'import et poser une URL bidon en attendant
que l'user la corrige. Rejeté car ça produirait des notifications
silencieusement cassées (apprise 4xx sur envoi).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.backup.handlers._shared import SimpleModelHandler, _b64_to_bytes
from romarr.backup.registry import register
from romarr.backup.schemas import ImportMode, ImportOutcome, ResourceKey
from romarr.notifications.models import Notification


class NotificationHandler(SimpleModelHandler):
    key = ResourceKey.NOTIFICATIONS
    label = "Notifications"
    has_secrets = True

    model_class = Notification
    FIELDS = [
        "name",
        "apprise_url_scheme",
        "on_grab",
        "on_import",
        "on_upgrade",
        "on_fail",
        "on_health_issue",
        "on_dat_update",
        "on_game_added",
        "tags",
        "enabled",
        "include_health_warnings",
        "include_health_errors",
        "on_grab_format",
        "on_import_format",
        "on_upgrade_format",
        "on_fail_format",
        "on_health_issue_format",
        "on_dat_update_format",
        "on_game_added_format",
    ]
    SECRET_FIELDS = ["apprise_url_encrypted"]

    async def apply(
        self,
        session: AsyncSession,
        items: list[dict[str, Any]],
        *,
        mode: ImportMode,
    ) -> ImportOutcome:
        outcome = ImportOutcome(key=self.key)

        def _requires_url_or_skip(item: dict[str, Any]) -> bytes | None:
            enc = item.get("apprise_url_encrypted")
            if not enc:
                outcome.errors.append(
                    f"notification {item.get('name')!r} skipped: "
                    f"apprise URL required (import with include_secrets=True)"
                )
                return None
            return _b64_to_bytes(enc)

        if mode is ImportMode.REPLACE:
            await session.execute(delete(Notification))
            for item in items:
                enc_url = _requires_url_or_skip(item)
                if enc_url is None:
                    outcome.skipped += 1
                    continue
                cols = self._payload_to_columns(item)
                cols["apprise_url_encrypted"] = enc_url
                try:
                    session.add(Notification(**cols))
                    outcome.created += 1
                except Exception as e:
                    outcome.errors.append(f"insert {item.get('name')!r}: {e}")
            await session.flush()
            return outcome

        existing = {
            r.name: r
            for r in (await session.execute(select(Notification))).scalars().all()
        }
        for item in items:
            name = item.get("name")
            if not name:
                outcome.skipped += 1
                continue
            row = existing.get(name)
            if row is None:
                enc_url = _requires_url_or_skip(item)
                if enc_url is None:
                    outcome.skipped += 1
                    continue
                cols = self._payload_to_columns(item)
                cols["apprise_url_encrypted"] = enc_url
                try:
                    session.add(Notification(**cols))
                    outcome.created += 1
                except Exception as e:
                    outcome.errors.append(f"insert {name!r}: {e}")
            else:
                if mode is ImportMode.MERGE:
                    outcome.skipped += 1
                    continue
                cols = self._payload_to_columns(item)
                # Sur update : ne pas écraser l'URL existante si le
                # bundle n'en a pas (permet update des flags sans
                # devoir tout re-fournir).
                if "apprise_url_encrypted" not in cols:
                    cols.pop("apprise_url_encrypted", None)
                try:
                    for k, v in cols.items():
                        if k == "name":
                            continue
                        setattr(row, k, v)
                    outcome.updated += 1
                except Exception as e:
                    outcome.errors.append(f"update {name!r}: {e}")
        await session.flush()
        return outcome


register(NotificationHandler())
