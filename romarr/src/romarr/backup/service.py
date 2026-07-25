"""Orchestrateur export/import — dispatch au registry, gère le format
bundle et la transaction globale de l'import.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from romarr.backup.registry import get_handler, get_registry
from romarr.backup.schemas import (
    Bundle,
    ImportMode,
    ImportOutcome,
    ImportResult,
    Manifest,
    ManifestEntry,
    ResourceKey,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _romarr_version() -> str:
    """Version courante du binaire. Lu depuis le pyproject via
    `importlib.metadata` — pas de fallback hardcodé pour éviter la
    dérive avec le tag CI/CD.
    """
    try:
        from importlib.metadata import version
        return version("romarr")
    except Exception:
        return "unknown"


async def list_manifest(session: "AsyncSession") -> Manifest:
    """Retourne le manifest des ressources backupables avec leurs
    compteurs actuels. Utilisé par l'UI pour construire les checkboxes.
    """
    entries: list[ManifestEntry] = []
    for key, handler in get_registry().items():
        try:
            count = await handler.count(session)
        except Exception:
            # Un handler cassé ne doit pas bloquer les autres — le
            # manifest reste consultable même si un module a un souci.
            count = -1
        entries.append(ManifestEntry(
            key=key,
            label=handler.label,
            count=count,
            has_secrets=handler.has_secrets,
        ))
    # Tri par key pour un affichage stable
    entries.sort(key=lambda e: e.key.value)
    return Manifest(resources=entries)


async def export_bundle(
    session: "AsyncSession",
    *,
    resources: list[ResourceKey],
    include_secrets: bool = False,
) -> Bundle:
    """Sérialise les ressources demandées dans un bundle prêt à
    télécharger. Un type inconnu du registry est SKIP silencieusement
    (utile pour la compat descendante — un vieil UI qui demande une
    ressource retirée ne fait pas planter l'export).
    """
    payload: dict[str, list[dict]] = {}
    for key in resources:
        handler = get_handler(key)
        if handler is None:
            continue
        items = await handler.serialize_all(
            session, include_secrets=include_secrets
        )
        payload[key.value] = items
    return Bundle(
        romarr_version=_romarr_version(),
        exported_at=datetime.now(UTC),
        include_secrets=include_secrets,
        resources=payload,
    )


async def import_bundle(
    session: "AsyncSession",
    bundle: Bundle,
    *,
    resources: list[ResourceKey] | None = None,
    mode: ImportMode = ImportMode.UPSERT,
) -> ImportResult:
    """Applique un bundle. `resources=None` → tout ce qui est dans le
    bundle. Un mode `REPLACE` est destructif : la totalité des rows
    existantes pour chaque ressource sélectionnée est supprimée AVANT
    l'insertion des items du bundle (transaction unique par ressource).

    Une erreur sur UNE ressource n'annule pas les autres — chaque
    handler gère sa propre sub-transaction et l'outcome capture les
    erreurs pour affichage côté UI.
    """
    outcomes: list[ImportOutcome] = []

    # Filtre : ne traite que les intersections (demandé × présent dans le bundle)
    bundle_keys = {k for k in bundle.resources.keys()}
    if resources is None:
        wanted = bundle_keys
    else:
        wanted = {k.value for k in resources} & bundle_keys

    for key_str in sorted(wanted):
        try:
            key = ResourceKey(key_str)
        except ValueError:
            # Type inconnu (bundle plus récent que l'install courante)
            outcomes.append(ImportOutcome(
                key=ResourceKey.DAT_SOURCES,  # placeholder — l'UI affiche l'erreur
                errors=[f"unknown resource type in bundle: {key_str!r}"],
            ))
            continue
        handler = get_handler(key)
        if handler is None:
            outcomes.append(ImportOutcome(
                key=key,
                errors=[f"no handler registered for {key.value!r}"],
            ))
            continue
        items = bundle.resources.get(key_str, [])
        try:
            outcome = await handler.apply(session, items, mode=mode)
        except Exception as e:
            outcome = ImportOutcome(
                key=key,
                errors=[f"handler failed: {type(e).__name__}: {e}"],
            )
        outcomes.append(outcome)
    return ImportResult(outcomes=outcomes)
