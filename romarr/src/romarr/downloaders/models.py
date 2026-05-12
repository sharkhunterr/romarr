"""SQLAlchemy model for the download-clients feature.

One new table — ``download_client``. The ``indexer.download_client_id``
FK is added in migration ``0005_download_clients.py`` (the column was
created in spec 004 without a constraint, deferred until this table
existed).

Credentials are stored as Fernet ciphertext via
:mod:`romarr.metadata.encryption` (Article III — single helper).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from romarr.domain.base import Base, TimestampMixin

_TYPE_CHECK = (
    "type IN ('qbittorrent','sabnzbd','transmission','deluge',"
    "'nzbget','grabarr_direct')"
)
_SSL_CHECK = (
    "ssl_cert_validation IN ('enabled','disabled','disabled-for-local')"
)


class DownloadClient(Base, TimestampMixin):
    __tablename__ = "download_client"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    host: Mapped[str] = mapped_column(String, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    use_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    url_base: Mapped[str | None] = mapped_column(String, nullable=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    password_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    api_key_encrypted: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True
    )
    category_default: Mapped[str] = mapped_column(
        String(64), nullable=False, default="romarr"
    )
    tags: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    enable_for_torrents: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    enable_for_usenet: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    remove_completed_downloads: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    remove_failed_downloads: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    ssl_cert_validation: Mapped[str] = mapped_column(
        String(32), nullable=False, default="enabled"
    )
    last_health_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_health_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_health_error: Mapped[str | None] = mapped_column(String, nullable=True)
    client_version_seen: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )
    # Slice 420 — controls every HTTP call this client makes:
    # the client's own API (qBit, SAB) AND the indexer-side
    # ``/download`` URL fetch we do during torrent add when an
    # indexer proxies through a slow upstream (Prowlarr ->
    # Grabarr can take well past the prior hard-coded 15 s).
    timeout_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60
    )
    # Slice 427 / R3a — base directory the grabarr_direct streamer
    # writes to for http_direct grabs. NULL for every other client
    # type (qBit / SAB own their own save paths). When NULL the
    # client falls back to the ``ROMARR_GRABARR_DIRECT_DOWNLOAD_ROOT``
    # env var (default ``/downloads``).
    download_root: Mapped[str | None] = mapped_column(
        String(512), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "type", "host", "port", name="uq_download_client_type_host_port"
        ),
        Index("idx_download_client_enabled", "enabled"),
        CheckConstraint(_TYPE_CHECK, name="ck_download_client_type"),
        CheckConstraint(_SSL_CHECK, name="ck_download_client_ssl_validation"),
        CheckConstraint(
            "port BETWEEN 1 AND 65535", name="ck_download_client_port_range"
        ),
        CheckConstraint(
            "priority BETWEEN 1 AND 100",
            name="ck_download_client_priority_range",
        ),
        CheckConstraint(
            "timeout_seconds BETWEEN 5 AND 600",
            name="ck_download_client_timeout_range",
        ),
    )


__all__ = ["DownloadClient"]
