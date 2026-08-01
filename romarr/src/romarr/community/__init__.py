"""Unified Update Center for Romarr — one place to manage every
community-hosted resource the operator has registered by URL.

The engine is intentionally thin: it owns the ``pack_sources``
table (generalised in migration 0040), the manifest fetch/parse
pipeline, and the check-vs-apply lifecycle. The heavy lifting per
``resource_type`` lives in an *adapter* that maps the manifest to
existing Romarr subsystems:

  * ``platform_pack`` — delegates to
    :mod:`romarr.platform_packs.ingestor` (the YAML directory flow
    that was already there before spec-community-1).
  * ``custom_format`` — delegates to
    :mod:`romarr.profiles.seeders.custom_formats_seeder` via a
    thin JSON-manifest wrapper (new).

Adapters are registered in :mod:`romarr.community.adapters`.
"""

from __future__ import annotations

from romarr.community.adapters import register_adapter
from romarr.community.custom_format_adapter import CustomFormatAdapter
from romarr.community.platform_pack_adapter import PlatformPackAdapter

# Auto-register on module import so the API endpoints and the
# scheduled task never have to remember to call this.
register_adapter(CustomFormatAdapter())
register_adapter(PlatformPackAdapter())

__all__ = ["register_adapter"]
