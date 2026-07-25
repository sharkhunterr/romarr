"""Backup & Restore — export/import à la carte des ressources Romarr.

Un opérateur peut à tout moment :
  * exporter un sous-ensemble sélectionné de ses ressources (DAT sources,
    profiles, indexers, download clients, notifications, platform packs)
    dans un bundle JSON téléchargeable.
  * réimporter tout ou partie de ce bundle sur une autre install (ou la
    même après une réinstallation), en choisissant :
    - quelles ressources restaurer,
    - le mode : `upsert` par défaut (add / update par name), `merge`
      (add-only, ignore les existants), `replace` (nuke + recréation —
      dangereux, gate UI).

Secrets (API keys, passwords, Apprise URLs, …) : opt-in au moment de
l'export via `include_secrets=True`. Sans ça, l'export les omet et
les rows importées doivent être re-configurées manuellement côté UI.
Avec, ils sont chiffrés côté source par Fernet + `ROMARR_AUTH_SECRET_KEY` ;
l'install cible DOIT partager la même clé pour les déchiffrer (sinon
le bundle est utilisable mais les secrets sont perdus au flush).

Architecture :
- `registry.py` — Protocol qu'implémente chaque type de ressource.
- `schemas.py` — Format canonical `Bundle` + requests API.
- `service.py` — orchestrateur export/import qui dispatch au registry.
- `handlers/` — 1 fichier par type (DAT, quality, indexer, …).
- `api.py` — endpoints REST à monter sous /api/v3/backup/.
"""

from romarr.backup.registry import ResourceHandler, get_registry, register
from romarr.backup.schemas import (
    Bundle,
    ExportRequest,
    ImportMode,
    ImportRequest,
    ImportResult,
    Manifest,
    ManifestEntry,
    ResourceKey,
)
from romarr.backup.service import export_bundle, import_bundle, list_manifest

__all__ = [
    "Bundle",
    "ExportRequest",
    "ImportMode",
    "ImportRequest",
    "ImportResult",
    "Manifest",
    "ManifestEntry",
    "ResourceHandler",
    "ResourceKey",
    "export_bundle",
    "get_registry",
    "import_bundle",
    "list_manifest",
    "register",
]
