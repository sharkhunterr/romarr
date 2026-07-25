"""Built-in pack resolution + first-boot auto-apply.

The built-in pack YAMLs live at repo root under
``examples/platform-packs/builtin-<YYYY.MM.NNN>.yaml`` — one file
per historical version. The loader picks the lexically-latest one
at runtime, so shipping a new builtin is a matter of dropping a
new YAML in that folder and bumping ``CHANGELOG`` — no code
change required.

Resolution order for one pack path:

  1. ``ROMARR_BUILTIN_PACK_PATH`` env / :class:`Settings` — exact file.
  2. ``/opt/romarr/builtin-packs/`` — operator drop dir, latest match.
  3. Wheel resource ``romarr.builtin_packs/`` — bundled via pyproject
     ``force-include`` from ``examples/platform-packs/``.

``apply_builtin_pack(session, sessionmaker)`` is the runtime entry
point: it resolves the latest built-in pack, reads the bytes, and
dispatches to :func:`ingest_pack` with
``IngestSource(pack_source='builtin', applied_by='system')``. When
no built-in pack is present (the operator stripped the folder out
and no override is set), the function logs a structured warning and
returns without writing anything (FR-019).
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

from romarr.platform_packs.ingestor import IngestSource, ingest_pack

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from romarr.platform_packs.types import PackUploadResult

logger = logging.getLogger(__name__)

_OPERATOR_DROP_DIR = Path("/opt/romarr/builtin-packs")
_BUILTIN_YAML_RE = re.compile(r"^builtin-(\d{4}\.\d{2}\.\d{3})\.yaml$")


def _latest_builtin_in_dir(directory: Path) -> Path | None:
    """Return the newest ``builtin-<YYYY.MM.NNN>.yaml`` in ``directory``.

    Lexical sort of the version string matches semver-like YYYY.MM.NNN
    ordering exactly. Returns ``None`` for a missing / empty directory.
    """
    if not directory.is_dir():
        return None
    candidates = [
        p for p in directory.iterdir() if _BUILTIN_YAML_RE.match(p.name)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.name, reverse=True)
    return candidates[0]


def _bundled_builtin_dir() -> Path:
    """Filesystem path of the folder the wheel/dev-install exposes.

    - Wheel install : hatchling's ``force-include`` puts
      ``examples/platform-packs/`` at ``romarr/builtin_packs/`` next
      to the source modules, so it's a sibling of this file.
    - Dev / editable install (``pip install -e .``) : same location,
      hatchling generates an editable-install stub that surfaces the
      folder in place.
    - Repo-only mode (no install) : the folder isn't reachable from
      the source tree — resolve it via the repo layout as a fallback
      (``../../examples/platform-packs`` from this file).
    """
    return Path(__file__).resolve().parent.parent / "builtin_packs"


def _repo_layout_dir() -> Path:
    """Fallback for repo-only mode (no install has run yet)."""
    # this file: <inner>/src/romarr/platform_packs/builtin.py
    #     up 3: <inner>/
    #     +examples/platform-packs
    return (
        Path(__file__).resolve().parents[3] / "examples" / "platform-packs"
    )


def _latest_builtin_wheel_resource() -> Path | None:
    """Locate the newest built-in YAML in the installed/dev layout.

    Checks the bundled dir first (wheel + editable install), then
    the repo layout as a fallback for uninstalled checkouts.
    """
    for candidate_dir in (_bundled_builtin_dir(), _repo_layout_dir()):
        latest = _latest_builtin_in_dir(candidate_dir)
        if latest is not None:
            return latest
    return None


def latest_builtin_pack_version() -> str | None:
    """Version string of the newest built-in pack visible at boot.

    Exposed for logging + tests — the runtime uses
    :func:`resolve_builtin_pack_path` directly.
    """
    path = resolve_builtin_pack_path()
    if path is None:
        return None
    m = _BUILTIN_YAML_RE.match(path.name)
    return m.group(1) if m else None


def resolve_builtin_pack_path() -> Path | None:
    """Return the on-disk / wheel-resource path to the built-in pack.

    Returns ``None`` when no candidate file exists. Callers MUST treat
    that as a benign "operator stripped the built-in pack" condition
    rather than a hard error (FR-019).
    """
    from romarr.config.settings import get_settings

    try:
        settings_path = get_settings().builtin_pack_path
    except Exception:
        settings_path = None

    if settings_path:
        candidate = Path(settings_path)
        return candidate if candidate.is_file() else None
    if env := os.environ.get("ROMARR_BUILTIN_PACK_PATH"):
        candidate = Path(env)
        return candidate if candidate.is_file() else None

    if (op := _latest_builtin_in_dir(_OPERATOR_DROP_DIR)) is not None:
        return op

    return _latest_builtin_wheel_resource()


# Backward-compat shim — a handful of tests import this constant to
# assert against the version string. Recomputed on each access so
# adding a new builtin YAML file "just works" without touching Python.
class _LazyVersion(str):
    """Behaves like the version string but resolves on first read."""

    def __new__(cls) -> "_LazyVersion":  # noqa: D401
        v = latest_builtin_pack_version() or ""
        obj = super().__new__(cls, v)
        return obj


_BUILTIN_PACK_VERSION: str = _LazyVersion()


async def apply_builtin_pack(
    session: AsyncSession,
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
) -> PackUploadResult | None:
    """Read + apply the built-in pack via :func:`ingest_pack`.

    Returns the :class:`PackUploadResult` on success, or ``None`` when
    the built-in pack is missing (the call boots normally and a
    structured warning logs).
    """
    path = resolve_builtin_pack_path()
    if path is None:
        logger.warning(
            "platform_packs.builtin.missing",
            extra={
                "search_paths": [
                    "ROMARR_BUILTIN_PACK_PATH",
                    str(_OPERATOR_DROP_DIR),
                    str(_bundled_builtin_dir()),
                    str(_repo_layout_dir()),
                ],
            },
        )
        return None

    content = path.read_bytes()
    return await ingest_pack(
        session,
        sessionmaker=sessionmaker,
        content=content,
        source=IngestSource(pack_source="builtin", applied_by="system"),
    )


__all__ = [
    "apply_builtin_pack",
    "latest_builtin_pack_version",
    "resolve_builtin_pack_path",
]
