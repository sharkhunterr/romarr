"""Adapter registry for community pack resource types.

Each ``resource_type`` value (``platform_pack``, ``custom_format``,
future kinds) has one registered :class:`CommunityAdapter` that:

  * ``check(source)`` — fetches the manifest, returns available
    version + item count. Never mutates DB rows.
  * ``apply(source, session)`` — fetches the manifest AND the item
    bodies, validates against the adapter's schema, ingests via
    the target subsystem (existing Romarr code paths). Updates
    the source's ``installed_version`` on success.

Adapters are pure orchestration — they don't own any DB tables
beyond the ``pack_sources`` row they receive. Their job is to
translate a manifest into calls on the *existing* Romarr
subsystems (platform_packs.ingestor for platform packs, the
custom_format seeder for CFs).
"""

from __future__ import annotations

import logging
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from romarr.community.fetch import FetchError, fetch_json
from romarr.community.schemas import (
    ApplyResult,
    CheckResult,
    PackManifest,
    ResourceType,
)
from romarr.platform_packs.models import PackSource

_LOG = logging.getLogger(__name__)


class CommunityAdapter(Protocol):
    """One adapter per ``resource_type``."""

    resource_type: ResourceType

    async def check(self, source: PackSource) -> CheckResult: ...

    async def apply(
        self, source: PackSource, session: AsyncSession
    ) -> ApplyResult: ...


_REGISTRY: dict[str, CommunityAdapter] = {}


def register_adapter(adapter: CommunityAdapter) -> None:
    """Register (or replace) the adapter for its ``resource_type``."""
    _REGISTRY[adapter.resource_type] = adapter


def get_adapter(resource_type: str) -> CommunityAdapter | None:
    return _REGISTRY.get(resource_type)


def registered_types() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


# ---------------------------------------------------------------------------
# Manifest-parse helper — shared by every adapter that speaks the
# ``manifest.json`` protocol. Adapters that accept a legacy shape
# (like the platform_pack adapter's YAML-directory URL) do their
# own parse before falling back here.
# ---------------------------------------------------------------------------


async def parse_manifest(url: str) -> PackManifest:
    """Fetch + validate the manifest at ``url``.

    Raises :class:`~romarr.community.fetch.FetchError` on network /
    HTTP / body-too-large errors, or a pydantic ``ValidationError``
    on schema mismatch.
    """
    payload = await fetch_json(url)
    return PackManifest.model_validate(payload)


__all__ = [
    "CommunityAdapter",
    "FetchError",
    "get_adapter",
    "parse_manifest",
    "register_adapter",
    "registered_types",
]
