"""Handler backup — PackSource.

Pas de secret ici (MVP repos publics uniquement). Serialise name,
url, kind, enabled — ré-hydratation directe à l'import via dedup
par ``name`` comme les autres handlers SimpleModel.

Les colonnes runtime (``last_synced_at``, ``last_status``, etc.)
sont volontairement exclues du bundle — elles se reconstruiront
au prochain sync post-import.
"""
from __future__ import annotations

from romarr.backup.handlers._shared import SimpleModelHandler
from romarr.backup.registry import register
from romarr.backup.schemas import ResourceKey
from romarr.platform_packs.models import PackSource


class PackSourceHandler(SimpleModelHandler):
    key = ResourceKey.PACK_SOURCES
    label = "Pack Sources"
    has_secrets = False

    model_class = PackSource
    FIELDS = [
        "name",
        "url",
        "kind",
        "enabled",
    ]


register(PackSourceHandler())
