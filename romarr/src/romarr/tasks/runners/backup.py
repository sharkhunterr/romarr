"""BackupRunner (spec 012 T049).

Snapshot the database + a sanitised config TAR.gz under
:attr:`Settings.backup_path`. Honours a 30-backup retention
cap so the directory doesn't grow unbounded.

SQLite path uses the portable ``VACUUM INTO`` syntax (requires
SQLite ≥ 3.27, shipped 2019). PostgreSQL backup via ``pg_dump``
is deferred — the runner detects the dialect and surfaces a
structured "not yet implemented" failure instead of doing the
wrong thing.

The config TAR.gz contains a single ``settings.json`` with the
non-secret fields from the active :class:`Settings` instance.
Secrets (``auth_secret_key``, ``oidc_client_secret``,
``importer_webhook_token``, …) are explicitly redacted so a
restore from backup doesn't leak them onto disk.
"""

from __future__ import annotations

import json
import logging
import tarfile
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

_logger = logging.getLogger(__name__)

# Spec 012 T049 — keep the latest 30 archives; older ones get
# pruned at the end of every successful run.
DEFAULT_RETENTION = 30

# Settings fields whose values must never land on disk in a
# backup archive. Sanitised to ``"<redacted>"`` in the config
# JSON. Anything else is fair game.
_REDACTED_FIELDS: frozenset[str] = frozenset(
    {
        "auth_secret_key",
        "oidc_client_secret",
        "importer_webhook_token",
    }
)


@dataclass
class BackupResult:
    """Outcome of one ``run_backup`` invocation."""

    db_path: Path
    """Path to the database snapshot (``romarr-<ts>.sqlite``)."""
    config_path: Path
    """Path to the config archive (``romarr-<ts>-config.tar.gz``)."""
    pruned: list[Path]
    """Older backup files removed by the retention sweep."""


def _timestamp() -> str:
    """ISO-8601-ish timestamp suitable for filenames (no
    colons or whitespace)."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _sanitise_settings(settings: Any) -> dict[str, Any]:
    """Project the active Settings into a JSON-serialisable
    dict with secrets redacted."""
    raw = settings.model_dump()
    return {
        key: "<redacted>" if key in _REDACTED_FIELDS else value
        for key, value in raw.items()
    }


def _write_config_archive(
    target: Path, *, settings: Any
) -> None:
    """Write a tar.gz containing a single ``settings.json``."""
    payload = json.dumps(
        _sanitise_settings(settings), indent=2, sort_keys=True
    ).encode("utf-8")
    with tarfile.open(target, "w:gz") as tf:
        info = tarfile.TarInfo(name="settings.json")
        info.size = len(payload)
        info.mtime = int(datetime.now(UTC).timestamp())
        info.mode = 0o600
        tf.addfile(info, BytesIO(payload))


async def _vacuum_into(session: "AsyncSession", target: Path) -> None:
    """Use SQLite's ``VACUUM INTO`` to produce a consistent
    snapshot of the live database. Other dialects raise
    NotImplementedError until pg_dump wiring lands."""
    bind = session.get_bind()
    dialect_name = getattr(bind.dialect, "name", "<unknown>")
    if dialect_name != "sqlite":
        raise NotImplementedError(
            f"BackupRunner: dialect {dialect_name!r} not supported "
            "yet (pg_dump wiring deferred)."
        )
    # ``VACUUM INTO`` requires a SQL-string-quoted path. SQLite
    # uses single quotes for string literals; we sanitise the
    # path to forbid single quotes (the OS won't typically allow
    # them, but defence-in-depth).
    target_str = str(target.resolve())
    if "'" in target_str:
        raise ValueError(
            f"backup target path must not contain single quotes: "
            f"{target_str!r}"
        )
    await session.execute(text(f"VACUUM INTO '{target_str}'"))


def _prune_older(
    backup_dir: Path, *, retention: int
) -> list[Path]:
    """Remove backups beyond the retention window. Pairs of
    ``romarr-*.sqlite`` + ``romarr-*-config.tar.gz`` are
    treated as one logical backup keyed on the timestamp prefix."""
    archives = sorted(
        backup_dir.glob("romarr-*.sqlite"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    pruned: list[Path] = []
    for old in archives[retention:]:
        # Pull the timestamp out of "romarr-<ts>.sqlite" and
        # delete the matching config archive too.
        stem = old.stem  # romarr-<ts>
        config = backup_dir / f"{stem}-config.tar.gz"
        old.unlink(missing_ok=True)
        pruned.append(old)
        if config.is_file():
            config.unlink()
            pruned.append(config)
    return pruned


async def run_backup(
    session: "AsyncSession",
    *,
    backup_dir: Path,
    settings: Any,
    retention: int = DEFAULT_RETENTION,
) -> BackupResult:
    """Snapshot the DB + sanitised config to ``backup_dir``.

    Returns the resulting paths + the list of pruned older
    backups. Caller is responsible for ensuring ``backup_dir``
    exists; this helper creates it on demand to keep the
    callsite simple.
    """
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    ts = _timestamp()
    db_target = backup_dir / f"romarr-{ts}.sqlite"
    config_target = backup_dir / f"romarr-{ts}-config.tar.gz"

    await _vacuum_into(session, db_target)
    _write_config_archive(config_target, settings=settings)

    pruned = _prune_older(backup_dir, retention=retention)

    _logger.info(
        "tasks.backup.complete",
        extra={
            "db_path": str(db_target),
            "config_path": str(config_target),
            "pruned_count": len(pruned),
        },
    )

    return BackupResult(
        db_path=db_target,
        config_path=config_target,
        pruned=pruned,
    )


__all__ = ["BackupResult", "DEFAULT_RETENTION", "run_backup"]
