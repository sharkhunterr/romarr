"""Format canonical du bundle + payloads API pour /api/v3/backup/.

Une seule enveloppe JSON pour toute la vie du backup :

```
Bundle
├─ romarr_version : str       # version qui a émis le bundle
├─ exported_at    : datetime  # UTC ISO 8601
├─ include_secrets: bool      # opt-in coté export → true si les blobs
│                             #   chiffrés sont inclus (Fernet)
└─ resources      : {ResourceKey -> list[dict]}
                              # ex: {"dat_sources": [...], "quality_profiles": [...]}
```

Les items individuels sont des dicts Python (`serialize`) — chaque
handler choisit sa forme, mais tous incluent `name` comme clé de
dedup à l'import.
"""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ResourceKey(StrEnum):
    """Types de ressources exportables. Ajouter un membre → enregistrer
    un handler dans `registry` pour l'activer.
    """

    DAT_SOURCES = "dat_sources"
    QUALITY_PROFILES = "quality_profiles"
    REGION_PROFILES = "region_profiles"
    DUMP_PROFILES = "dump_profiles"
    LANGUAGE_PROFILES = "language_profiles"
    NAMING_PROFILES = "naming_profiles"
    CUSTOM_FORMATS = "custom_formats"
    INDEXERS = "indexers"
    DOWNLOAD_CLIENTS = "download_clients"
    NOTIFICATIONS = "notifications"
    PLATFORM_PACKS = "platform_packs"
    PACK_SOURCES = "pack_sources"
    PLATFORM_PACK_CONFIG = "platform_pack_config"


class ImportMode(StrEnum):
    """Comportement à l'import quand un item avec le même `name` existe."""

    UPSERT = "upsert"    # Défaut : update les existants, ajoute les nouveaux
    MERGE = "merge"      # Add-only : ignore les existants, ajoute les nouveaux
    REPLACE = "replace"  # Delete-all + recreate : DESTRUCTIF (UI gate obligatoire)


class ManifestEntry(BaseModel):
    """Une ligne du manifest — dit à l'UI ce qui est backupable + combien."""

    key: ResourceKey
    label: str
    """Libellé humain (traduit côté UI via clé i18n si dispo)."""
    count: int
    """Nombre d'items actuellement présents en DB."""
    has_secrets: bool
    """True si cette ressource porte au moins un champ sensible (choix
    `include_secrets` visible dans l'UI seulement pour ces types)."""


class Manifest(BaseModel):
    """Retourné par `GET /api/v3/backup/manifest` — l'UI en dérive les
    checkboxes disponibles + les compteurs."""

    resources: list[ManifestEntry]


class ExportRequest(BaseModel):
    """Body de `POST /api/v3/backup/export`."""

    resources: list[ResourceKey] = Field(
        ..., min_length=1,
        description="Types de ressources à inclure dans le bundle. "
        "Au moins un requis — sinon exporter tout la DB n'a pas de sens.",
    )
    include_secrets: bool = Field(
        False,
        description="Si True, les blobs chiffrés (Fernet) sont inclus. "
        "L'install cible DOIT partager le même ROMARR_AUTH_SECRET_KEY "
        "pour les déchiffrer, sinon les secrets seront perdus au flush.",
    )


class Bundle(BaseModel):
    """Format sur disque du bundle. Sérialisable/parseable en JSON pur
    (les bytes Fernet sont encodés en base64 par les handlers).
    """

    model_config = ConfigDict(str_strip_whitespace=True)

    romarr_version: str
    exported_at: datetime
    include_secrets: bool = False
    resources: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    """Clé = ResourceKey.value. Valeur = liste d'items serialisés."""


class ImportRequest(BaseModel):
    """Body de `POST /api/v3/backup/import`."""

    bundle: Bundle
    resources: list[ResourceKey] | None = Field(
        None,
        description="Sous-ensemble des ressources du bundle à importer. "
        "None = tout ce qui est présent dans le bundle.",
    )
    mode: ImportMode = ImportMode.UPSERT


class ImportOutcome(BaseModel):
    """Bilan par ressource après import."""

    key: ResourceKey
    created: int = 0
    updated: int = 0
    skipped: int = 0
    """Items ignorés — soit parce que mode=merge et le name existait déjà,
    soit parce qu'un secret manquait pour une ressource qui l'exige."""
    errors: list[str] = Field(default_factory=list)


class ImportResult(BaseModel):
    """Retourné par `POST /api/v3/backup/import`."""

    outcomes: list[ImportOutcome]
    """Un ImportOutcome par ressource traitée."""

    @property
    def total_changed(self) -> int:
        return sum(o.created + o.updated for o in self.outcomes)
