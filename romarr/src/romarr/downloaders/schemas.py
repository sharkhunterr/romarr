"""Pydantic schemas for the download-clients HTTP layer.

The standard ``Read / Create / Update`` triplet plus
:class:`DownloadClientSchema` (used by the future ``/schema`` endpoint
to drive the UI's add-client form).

All credential validation lives here as Python-side validators —
the SQL CHECK constraints catch the simple shape rules (type
membership, port range, priority range), but the
qBittorrent-needs-password / SABnzbd-needs-api-key cross-field rules
are too rich for SQL CHECK and live as
:func:`pydantic.model_validator` runs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from romarr.downloaders.types import ClientType  # noqa: TC001 — Pydantic v2 runtime use


class _Base(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        str_strip_whitespace=True,
    )


_SslValidation = Literal["enabled", "disabled", "disabled-for-local"]


def _validate_credentials(
    *,
    type_: str,
    username: str | None,
    has_password: bool,
    has_api_key: bool,
) -> None:
    """Cross-field credential rules per data-model.md.

    qbittorrent ⇒ if any credential is present, username + password
                  must both be set; api_key MUST stay NULL. Empty
                  credentials are accepted (auth-bypass via qBit's
                  ``WebUI\\AuthSubnetWhitelist``, slice 379).
    sabnzbd     ⇒ api_key REQUIRED, username + password MUST be NULL.
    Stubs (transmission/deluge/nzbget) accept anything — they'll
    refuse via NotImplementedError before any credential is used.
    """
    if type_ == "qbittorrent":
        if has_api_key:
            raise ValueError("qbittorrent must not carry an api_key")
        if (username or has_password) and not (username and has_password):
            raise ValueError(
                "qbittorrent username and password must both be set, "
                "or both empty (auth-bypass via subnet whitelist)"
            )
    elif type_ == "sabnzbd":
        if username:
            raise ValueError("sabnzbd must not carry a username")
        if has_password:
            raise ValueError("sabnzbd must not carry a password")
        if not has_api_key:
            raise ValueError("sabnzbd requires an api_key")


def _validate_source_type_enabled(
    *, enable_for_torrents: bool, enable_for_usenet: bool
) -> None:
    """FR-023: at least one of (torrents, usenet) must be enabled."""
    if not enable_for_torrents and not enable_for_usenet:
        raise ValueError(
            "at least one of enable_for_torrents / enable_for_usenet must be true"
        )


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------


class DownloadClientRead(_Base):
    """Public read shape — encrypted blobs are NEVER serialised.

    ``is_configured`` is True iff the row carries the credential
    expected for its type (password for qBit, api_key for SAB). The
    field is computed at projection time, not stored.
    """

    id: int
    name: str
    type: str
    host: str
    port: int
    use_ssl: bool
    url_base: str | None
    username: str | None
    is_configured: bool
    category_default: str
    tags: list[Any] | None
    priority: int
    enable_for_torrents: bool
    enable_for_usenet: bool
    enabled: bool
    remove_completed_downloads: bool
    remove_failed_downloads: bool
    ssl_cert_validation: str
    last_health_at: datetime | None
    last_health_ok: bool | None
    last_health_error: str | None
    client_version_seen: str | None
    timeout_seconds: int
    # Slice 427 / R3a — surfaces the per-row download_root the
    # grabarr_direct streamer writes under. NULL for every other
    # client type. Read-only in the API; mutated only via the
    # "Add Grabarr" wizard endpoint.
    download_root: str | None = None


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


class DownloadClientCreate(_Base):
    """POST body for ``/api/v3/downloadclient``.

    Plaintext ``password`` / ``api_key`` are accepted here and
    encrypted by the application before persistence (FR-022).
    """

    name: Annotated[str, Field(min_length=1, max_length=128)]
    type: ClientType
    host: Annotated[str, Field(min_length=1)]
    port: Annotated[int, Field(ge=1, le=65535)]
    use_ssl: bool = False
    url_base: Annotated[str | None, Field(default=None, max_length=255)] = None
    username: Annotated[str | None, Field(default=None, max_length=255)] = None
    password: Annotated[str | None, Field(default=None, max_length=255)] = None
    api_key: Annotated[str | None, Field(default=None, max_length=255)] = None
    category_default: Annotated[str, Field(default="romarr", max_length=64)] = "romarr"
    tags: list[Any] | None = None
    priority: Annotated[int, Field(ge=1, le=100)] = 1
    enable_for_torrents: bool = False
    enable_for_usenet: bool = False
    enabled: bool = True
    remove_completed_downloads: bool = False
    remove_failed_downloads: bool = True
    ssl_cert_validation: _SslValidation = "enabled"
    timeout_seconds: Annotated[int, Field(ge=5, le=600)] = 60
    # Optional override of the streamer base path; only relevant
    # to type='grabarr_direct'. Other types leave it None.
    download_root: Annotated[str | None, Field(default=None, max_length=512)] = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        _validate_credentials(
            type_=self.type.value,
            username=self.username,
            has_password=bool(self.password),
            has_api_key=bool(self.api_key),
        )
        _validate_source_type_enabled(
            enable_for_torrents=self.enable_for_torrents,
            enable_for_usenet=self.enable_for_usenet,
        )
        return self


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


class DownloadClientUpdate(_Base):
    """PUT body — every field optional; ``extra='forbid'``.

    If ``password`` / ``api_key`` is included, the row is re-encrypted;
    if absent, the existing ciphertext is preserved (FR-022).

    Cross-field credential validation is intentionally NOT run here:
    a partial update (e.g., renaming the client) shouldn't require
    re-sending the password. The route handler runs the full
    validation against the merged final state before persisting.
    """

    name: Annotated[str | None, Field(default=None, min_length=1, max_length=128)] = None
    host: Annotated[str | None, Field(default=None, min_length=1)] = None
    port: Annotated[int | None, Field(default=None, ge=1, le=65535)] = None
    use_ssl: bool | None = None
    url_base: Annotated[str | None, Field(default=None, max_length=255)] = None
    username: Annotated[str | None, Field(default=None, max_length=255)] = None
    password: Annotated[str | None, Field(default=None, max_length=255)] = None
    api_key: Annotated[str | None, Field(default=None, max_length=255)] = None
    category_default: Annotated[str | None, Field(default=None, max_length=64)] = None
    tags: list[Any] | None = None
    priority: Annotated[int | None, Field(default=None, ge=1, le=100)] = None
    enable_for_torrents: bool | None = None
    enable_for_usenet: bool | None = None
    enabled: bool | None = None
    remove_completed_downloads: bool | None = None
    remove_failed_downloads: bool | None = None
    ssl_cert_validation: _SslValidation | None = None
    timeout_seconds: Annotated[int | None, Field(default=None, ge=5, le=600)] = None
    download_root: Annotated[str | None, Field(default=None, max_length=512)] = None


# ---------------------------------------------------------------------------
# Schema discovery
# ---------------------------------------------------------------------------


class DownloadClientSchema(_Base):
    """One entry in ``GET /api/v3/downloadclient/schema``.

    Lists the implementation, whether it's available (the three
    v1-deferred stubs report ``available=False``), and the config
    field shape so the UI can render the right add-client form.
    """

    implementation: ClientType
    implementation_name: str
    available: bool
    config_contract: str
    fields: list[dict[str, Any]] = Field(default_factory=list)


__all__ = [
    "DownloadClientCreate",
    "DownloadClientRead",
    "DownloadClientSchema",
    "DownloadClientUpdate",
]
