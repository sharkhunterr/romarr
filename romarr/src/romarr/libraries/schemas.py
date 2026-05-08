"""Pydantic schemas for the libraries feature (spec 009).

API surface only — these types never persist directly. Cross-field
invariants live in :func:`model_validator` so the same rules apply
to manual API submissions and to programmatic seeders.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    model_validator,
)

from romarr.libraries.types import LifecyclePolicy  # noqa: TC001 — runtime literal used by pydantic


class _LibraryBase(BaseModel):
    """Fields shared by Read / Create / Update.

    Validation here is **shape-only** — it does NOT touch the
    filesystem (no ``Path.exists()`` calls). The path-existence and
    writability checks live in :class:`LibraryCreate` / on the API
    layer where they can fail with a 422 referring to ``path``.
    """

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=100)]
    path: str
    platform_subfolders: bool = True
    platforms_restricted: bool = False
    quality_profile_id: int
    region_profile_id: int
    dump_profile_id: int
    language_profile_id: int
    naming_profile_id: int
    monitored_default: bool = True
    use_hardlinks: bool = True
    lifecycle_policy: LifecyclePolicy = "hardlink_and_seed"
    delete_after_import: bool = False
    keep_dump_history: bool = False
    min_disk_free_gb: Annotated[int, Field(ge=1)] = 5
    preserve_archive: bool = False
    exporter_romm_enabled: bool = False
    exporter_romm_url: str | None = None
    exporter_esde_enabled: bool = False
    exporter_pegasus_enabled: bool = False
    exporter_launchbox_enabled: bool = False
    exporter_launchbox_per_platform: bool = True
    scan_poll_seconds: Annotated[int, Field(ge=60)] = 3600
    heartbeat_seconds: Annotated[int, Field(ge=5)] = 30

    @model_validator(mode="after")
    def _normalise_path(self) -> Self:
        # Accept both absolute and relative paths; the latter
        # are resolved against the backend's cwd. Slice 370's
        # API-side validator does the actual ``mkdir -p`` and
        # writability check, so we just normalise here. The
        # only path we reject outright is the empty string —
        # everything else falls through to the create handler.
        cleaned = self.path.strip()
        if not cleaned:
            raise ValueError("library.path must not be empty")
        return self


class LibraryCreate(_LibraryBase):
    """Payload for ``POST /api/v3/library``.

    The plaintext RomM API key arrives as :class:`SecretStr` and is
    encrypted by the API handler before it reaches the model layer
    (FR-034).
    """

    platform_ids: list[int] = Field(default_factory=list)
    exporter_romm_api_key: SecretStr | None = None

    @model_validator(mode="after")
    def _restricted_requires_platforms(self) -> Self:
        if self.platforms_restricted and not self.platform_ids:
            raise ValueError(
                "platforms_restricted=true requires at least one platform_id"
            )
        return self

    @model_validator(mode="after")
    def _romm_requires_url_and_key(self) -> Self:
        if self.exporter_romm_enabled:
            if not self.exporter_romm_url:
                raise ValueError(
                    "exporter_romm_enabled=true requires exporter_romm_url"
                )
            if self.exporter_romm_api_key is None:
                raise ValueError(
                    "exporter_romm_enabled=true requires exporter_romm_api_key"
                )
        return self


class LibraryUpdate(BaseModel):
    """All fields optional, ``extra='forbid'`` so typos surface."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=100)] | None = None
    path: str | None = None
    platform_subfolders: bool | None = None
    platforms_restricted: bool | None = None
    quality_profile_id: int | None = None
    region_profile_id: int | None = None
    dump_profile_id: int | None = None
    language_profile_id: int | None = None
    naming_profile_id: int | None = None
    monitored_default: bool | None = None
    use_hardlinks: bool | None = None
    lifecycle_policy: LifecyclePolicy | None = None
    delete_after_import: bool | None = None
    keep_dump_history: bool | None = None
    min_disk_free_gb: Annotated[int, Field(ge=1)] | None = None
    preserve_archive: bool | None = None
    exporter_romm_enabled: bool | None = None
    exporter_romm_url: str | None = None
    exporter_romm_api_key: SecretStr | None = None
    exporter_esde_enabled: bool | None = None
    exporter_pegasus_enabled: bool | None = None
    exporter_launchbox_enabled: bool | None = None
    exporter_launchbox_per_platform: bool | None = None
    scan_poll_seconds: Annotated[int, Field(ge=60)] | None = None
    heartbeat_seconds: Annotated[int, Field(ge=5)] | None = None
    platform_ids: list[int] | None = None


class LibraryRead(_LibraryBase):
    """Read shape — never exposes ``exporter_romm_api_key_encrypted``;
    instead carries ``is_romm_configured`` derived from the blob."""

    id: int
    status: Literal["ok", "unavailable"]
    is_romm_configured: bool
    last_full_scan_at: datetime | None = None
    last_incremental_scan_at: datetime | None = None
    last_scan_status: Literal["success", "partial", "failed"] | None = None
    last_heartbeat_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    platform_ids: list[int] = Field(default_factory=list)

    @classmethod
    def from_orm_with_platforms(
        cls,
        row: Any,
        platform_ids: list[int],
    ) -> LibraryRead:
        """Build a :class:`LibraryRead` from a Library ORM row plus the
        already-loaded m2m platform-id list. Encryption is masked into
        a single ``is_romm_configured`` boolean."""
        return cls.model_validate(
            {
                "id": row.id,
                "name": row.name,
                "path": row.path,
                "platform_subfolders": row.platform_subfolders,
                "platforms_restricted": row.platforms_restricted,
                "quality_profile_id": row.quality_profile_id,
                "region_profile_id": row.region_profile_id,
                "dump_profile_id": row.dump_profile_id,
                "language_profile_id": row.language_profile_id,
                "naming_profile_id": row.naming_profile_id,
                "monitored_default": row.monitored_default,
                "use_hardlinks": row.use_hardlinks,
                "lifecycle_policy": row.lifecycle_policy,
                "delete_after_import": row.delete_after_import,
                "keep_dump_history": row.keep_dump_history,
                "min_disk_free_gb": row.min_disk_free_gb,
                "preserve_archive": row.preserve_archive,
                "exporter_romm_enabled": row.exporter_romm_enabled,
                "exporter_romm_url": row.exporter_romm_url,
                "exporter_esde_enabled": row.exporter_esde_enabled,
                "exporter_pegasus_enabled": row.exporter_pegasus_enabled,
                "exporter_launchbox_enabled": row.exporter_launchbox_enabled,
                "exporter_launchbox_per_platform": (
                    row.exporter_launchbox_per_platform
                ),
                "scan_poll_seconds": row.scan_poll_seconds,
                "heartbeat_seconds": row.heartbeat_seconds,
                "status": row.status,
                "is_romm_configured": row.exporter_romm_api_key_encrypted is not None,
                "last_full_scan_at": row.last_full_scan_at,
                "last_incremental_scan_at": row.last_incremental_scan_at,
                "last_scan_status": row.last_scan_status,
                "last_heartbeat_at": row.last_heartbeat_at,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "platform_ids": platform_ids,
            }
        )


class LibraryPlatformRead(BaseModel):
    """Slim view of a row in the m2m, used by the frontend's
    library-detail page."""

    model_config = ConfigDict(from_attributes=True)

    library_id: int
    platform_id: int
    created_at: datetime


__all__ = [
    "LibraryCreate",
    "LibraryPlatformRead",
    "LibraryRead",
    "LibraryUpdate",
]
