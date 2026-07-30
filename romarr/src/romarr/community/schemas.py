"""Manifest + result schemas shared across community adapters.

**Manifest format** — every community pack (regardless of
resource_type) exposes a ``manifest.json`` at the URL the
operator registered. The single required shape is:

.. code-block:: json

   {
     "romarr_pack": true,
     "kind": "custom_format",
     "version": "2026.07.30",
     "min_romarr_version": "0.14.0",
     "name": "TRaSH-Guides ROMs — pack officiel",
     "description": "...",
     "items": [
       {"path": "cf/no-intro-verified.json", "seed_key": "no-intro-verified"},
       ...
     ]
   }

The manifest itself never carries the item bodies — that
keeps a version check cheap (one HEAD + one small JSON fetch)
and lets the operator preview what an apply would do without
pulling every item body. Bodies are fetched at apply-time,
relative to the manifest URL.

For backwards compatibility, a source URL that points at a
YAML file or a GitHub directory (the pre-manifest format the
existing ``platform_pack`` adapter accepts) is treated as an
implicit v0 manifest by the ``platform_pack`` adapter.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ResourceType = Literal["platform_pack", "custom_format"]
TrustStatus = Literal["pending", "trusted"]

_FROZEN = ConfigDict(extra="ignore", frozen=True, str_strip_whitespace=True)


class ManifestItem(BaseModel):
    """One entry in a manifest's ``items`` list."""

    model_config = _FROZEN

    path: str = Field(min_length=1)
    """Path to the item body, relative to the manifest URL."""

    seed_key: str | None = None
    """Adapter-provided stable identifier for the item. Adapters use
    it to distinguish "update this row" from "insert new". Optional
    — an adapter that doesn't need it (or that derives one from the
    body itself) can leave it blank."""


class PackManifest(BaseModel):
    """The parsed manifest a community source URL resolves to."""

    model_config = _FROZEN

    romarr_pack: bool = True
    kind: ResourceType
    version: str = Field(min_length=1, max_length=64)
    """Free-form version string. Semver preferred (compared via
    :mod:`packaging.version` when both sides parse), else fallback
    to string inequality."""

    name: str = Field(min_length=1, max_length=128)
    description: str = ""
    min_romarr_version: str = ""
    """Optional min-version gate. Empty means "no minimum". Compared
    via :mod:`packaging.version` when both parse."""

    items: tuple[ManifestItem, ...] = ()


class CheckResult(BaseModel):
    """Return value of ``adapter.check(source)``."""

    model_config = _FROZEN

    available_version: str | None = None
    """The version string parsed from the remote manifest. ``None``
    when the source is offline or the manifest is unreadable —
    ``error`` will be populated in that case."""

    manifest_name: str | None = None
    manifest_description: str = ""
    item_count: int = 0
    error: str | None = None


class ApplyResult(BaseModel):
    """Return value of ``adapter.apply(source, session)``."""

    model_config = _FROZEN

    applied_version: str
    applied_count: int
    """Number of items the adapter ingested successfully."""

    warnings: tuple[str, ...] = ()
    error: str | None = None


__all__ = [
    "ApplyResult",
    "CheckResult",
    "ManifestItem",
    "PackManifest",
    "ResourceType",
    "TrustStatus",
]
