"""Registry des handlers de backup — un handler par type de ressource.

Le pattern : chaque handler implémente 3 méthodes async standards
(`count`, `serialize_all`, `apply`). Le service backup orchestre
sans savoir quel model se cache derrière — ajouter un nouveau type
= créer un handler + `@register` (aucune modif du service ou de l'API).

Le Protocol (au lieu d'une ABC) permet aux handlers d'être des classes
autonomes qui n'importent rien du reste du module — évite les circular
imports avec les modèles ORM.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from romarr.backup.schemas import ImportMode, ImportOutcome, ResourceKey


@runtime_checkable
class ResourceHandler(Protocol):
    """Contract qu'un handler de ressource implémente.

    Toutes les méthodes prennent une session async ouverte — le service
    la gère au niveau supérieur pour garder les transactions cohérentes
    entre ressources d'un même import.
    """

    key: "ResourceKey"
    label: str
    has_secrets: bool
    """True si au moins un champ de cette ressource est chiffré
    (contrôle l'affichage du toggle include_secrets côté UI)."""

    async def count(self, session: "AsyncSession") -> int:
        """Nombre de rows présentes en DB. Utilisé par /manifest."""

    async def serialize_all(
        self,
        session: "AsyncSession",
        *,
        include_secrets: bool,
    ) -> list[dict]:
        """Liste des items sérialisés. `include_secrets=False` DOIT
        omettre les champs chiffrés — les rows resteront importables
        mais devront être re-configurées côté UI pour ces secrets.
        """

    async def apply(
        self,
        session: "AsyncSession",
        items: list[dict],
        *,
        mode: "ImportMode",
    ) -> "ImportOutcome":
        """Réhydrate les items dans la DB selon le mode. Retourne le
        bilan (created/updated/skipped/errors).

        `mode` :
          * UPSERT  : add si absent (par name), update si présent
          * MERGE   : add-only, ignore les name existants
          * REPLACE : DELETE ALL puis INSERT (transaction unique)
        """


_REGISTRY: dict["ResourceKey", ResourceHandler] = {}


def register(handler: ResourceHandler) -> ResourceHandler:
    """Décorateur / helper pour enregistrer un handler.

    Idempotent : registrer 2× la même clé écrase (utile pour tests
    et pour hot-reload dev). En prod le hook `_load_default_handlers`
    est appelé une seule fois au bootstrap FastAPI.
    """
    _REGISTRY[handler.key] = handler
    return handler


def get_registry() -> dict["ResourceKey", ResourceHandler]:
    """Snapshot du registre courant. Chargé à la 1ère demande via
    `_ensure_loaded()` — évite un side-effect import-time qui
    déclencherait tous les imports circulaires modèles/DB.
    """
    _ensure_loaded()
    return dict(_REGISTRY)


def get_handler(key: "ResourceKey") -> ResourceHandler | None:
    _ensure_loaded()
    return _REGISTRY.get(key)


_loaded = False


def _ensure_loaded() -> None:
    """Import lazy des handlers standard. Le premier appel importe tous
    les modules `romarr.backup.handlers.*` qui font `@register(...)`
    au top-level, ce qui peuple `_REGISTRY`.

    Isoler ça derrière un flag évite de bloquer l'import du package
    `backup` à la stack de dépendances complète (modèles ORM +
    downloaders + indexers + …) — utile pour les tests unitaires du
    registre lui-même.
    """
    global _loaded
    if _loaded:
        return
    _loaded = True
    # Import side-effect : chaque module appelle register() au top-level
    from romarr.backup import handlers  # noqa: F401  — package + submodules
    from romarr.backup.handlers import (  # noqa: F401
        custom_formats,
        dat_sources,
        download_clients,
        indexers,
        notifications,
        platform_packs,
        profiles,
    )
