"""Base commune pour les handlers backup — factorise le pattern
sérialisation / upsert / count qui est identique pour 90 % des cas.

Un handler concret typiquement :
  * hérite de `SimpleModelHandler`,
  * override `FIELDS` (champs safe à sérialiser) et éventuellement
    `SECRET_FIELDS` (champs chiffrés inclus si `include_secrets=True`),
  * override `model_class` et `name_column`.

Les cas plus tordus (relations M2M, colonnes calculées, plusieurs
tables liées, dédup par une clé composite) doivent implémenter
`ResourceHandler` directement plutôt que d'étendre cette base.
"""
from __future__ import annotations

import base64
from typing import Any, ClassVar

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.backup.schemas import ImportMode, ImportOutcome, ResourceKey


def _bytes_to_b64(b: bytes | None) -> str | None:
    """Fernet blobs → base64 pour tenir dans du JSON."""
    return base64.b64encode(b).decode("ascii") if b else None


def _b64_to_bytes(s: str | None) -> bytes | None:
    """Inverse de `_bytes_to_b64`."""
    return base64.b64decode(s.encode("ascii")) if s else None


class SimpleModelHandler:
    """Base pratique pour un handler simple mono-table.

    Chaque sous-classe déclare :
      * `key`, `label`, `has_secrets` — obligatoires (protocol)
      * `model_class`       : classe ORM cible
      * `name_column`       : nom d'attribut python de la colonne dedup
                              (par défaut "name")
      * `FIELDS`            : champs safe copiés à l'export (list[str])
      * `SECRET_FIELDS`     : champs bytes chiffrés (list[str]) —
                              encodés b64 quand `include_secrets=True`
    """

    # --- meta protocol ---
    key: ClassVar[ResourceKey]
    label: ClassVar[str]
    has_secrets: ClassVar[bool] = False

    # --- meta model ---
    model_class: ClassVar[type]
    name_column: ClassVar[str] = "name"
    FIELDS: ClassVar[list[str]] = []
    SECRET_FIELDS: ClassVar[list[str]] = []

    async def count(self, session: AsyncSession) -> int:
        stmt = select(func.count()).select_from(self.model_class)
        return int((await session.execute(stmt)).scalar_one() or 0)

    async def serialize_all(
        self, session: AsyncSession, *, include_secrets: bool
    ) -> list[dict[str, Any]]:
        rows = (await session.execute(select(self.model_class))).scalars().all()
        return [self._serialize_one(row, include_secrets) for row in rows]

    def _serialize_one(
        self, row: Any, include_secrets: bool
    ) -> dict[str, Any]:
        item: dict[str, Any] = {}
        for f in self.FIELDS:
            v = getattr(row, f, None)
            item[f] = self._json_safe(v)
        if include_secrets:
            for f in self.SECRET_FIELDS:
                blob = getattr(row, f, None)
                if isinstance(blob, (bytes, bytearray)):
                    item[f] = _bytes_to_b64(bytes(blob))
                else:
                    item[f] = None
        return item

    @staticmethod
    def _json_safe(v: Any) -> Any:
        """Convertit les types Python non-JSON-serializable en équivalent."""
        # datetime → isoformat (repris à l'import par les validators ORM)
        from datetime import date, datetime
        if isinstance(v, (datetime, date)):
            return v.isoformat()
        return v

    async def apply(
        self,
        session: AsyncSession,
        items: list[dict[str, Any]],
        *,
        mode: ImportMode,
    ) -> ImportOutcome:
        outcome = ImportOutcome(key=self.key)

        # Mode REPLACE : nuke tout avant d'insérer. Une seule requête
        # `DELETE FROM {table}` — les cascades ON DELETE des FKs
        # s'occupent des enfants (attention : dat_source cascade sur
        # dat_entry qui perd son cache — expected par l'opérateur).
        if mode is ImportMode.REPLACE:
            await session.execute(delete(self.model_class))
            for item in items:
                try:
                    self._insert_new(session, item)
                    outcome.created += 1
                except Exception as e:
                    outcome.errors.append(f"insert {item.get('name','?')}: {e}")
            await session.flush()
            return outcome

        # Modes UPSERT / MERGE : dedup par la colonne `name_column`
        name_col = getattr(self.model_class, self.name_column)
        existing_by_name = {
            getattr(r, self.name_column): r
            for r in (await session.execute(select(self.model_class))).scalars().all()
        }

        for item in items:
            item_name = item.get(self.name_column)
            if not item_name:
                outcome.errors.append(
                    f"item missing {self.name_column!r} — skipped"
                )
                outcome.skipped += 1
                continue
            existing = existing_by_name.get(item_name)
            if existing is None:
                try:
                    self._insert_new(session, item)
                    outcome.created += 1
                except Exception as e:
                    outcome.errors.append(f"insert {item_name!r}: {e}")
            else:
                if mode is ImportMode.MERGE:
                    outcome.skipped += 1
                    continue
                try:
                    self._update_existing(existing, item)
                    outcome.updated += 1
                except Exception as e:
                    outcome.errors.append(f"update {item_name!r}: {e}")
        await session.flush()
        _ = name_col  # keep reference (used only in the query above)
        return outcome

    def _insert_new(
        self, session: AsyncSession, item: dict[str, Any]
    ) -> None:
        """Créé une nouvelle row à partir du payload item. Override
        pour handlers qui ont besoin d'un mapping de colonnes plus
        complexe (secrets à re-chiffrer, FK à résoudre, etc.).
        """
        kwargs = self._payload_to_columns(item)
        row = self.model_class(**kwargs)
        session.add(row)

    def _update_existing(self, row: Any, item: dict[str, Any]) -> None:
        """Met à jour une row existante à partir du payload."""
        for col, val in self._payload_to_columns(item).items():
            if col == self.name_column:
                continue  # jamais toucher au name (clé dedup)
            setattr(row, col, val)

    def _payload_to_columns(self, item: dict[str, Any]) -> dict[str, Any]:
        """Traduit un item du bundle vers les kwargs du constructeur
        ORM. Par défaut copie FIELDS tel quel + décode les secrets si
        présents. Override pour transformer (JSON, FK lookup, etc.).
        """
        out: dict[str, Any] = {}
        for f in self.FIELDS:
            if f in item:
                out[f] = item[f]
        for f in self.SECRET_FIELDS:
            if f in item and item[f] is not None:
                out[f] = _b64_to_bytes(item[f])
        return out
