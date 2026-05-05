"""Built-in pack resolution + first-boot auto-apply (T037, T038).

The built-in pack ships at:

  1. The path in ``ROMARR_BUILTIN_PACK_PATH`` (highest precedence).
  2. The wheel resource ``romarr.builtin_packs/builtin-<version>.yaml``
     (the production path inside the Docker image).
  3. ``/opt/romarr/builtin-packs/builtin-<version>.yaml`` (operator
     can drop a replacement file there to override the wheel).

``apply_builtin_pack(session, sessionmaker)`` is the runtime entry
point: it resolves the path, reads the bytes, and dispatches to
:func:`ingest_pack` with ``IngestSource(pack_source='builtin',
applied_by='system')``. When no built-in pack is present (the
operator has stripped the file out and not pointed
``ROMARR_BUILTIN_PACK_PATH`` at one), the function logs a structured
warning and returns without writing anything (FR-019).
"""

from __future__ import annotations

import logging
import os
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

from romarr.platform_packs.ingestor import IngestSource, ingest_pack

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from romarr.platform_packs.types import PackUploadResult

logger = logging.getLogger(__name__)

# The version baked into the wheel. Bumping the built-in pack means
# bumping this string AND adding a new ``builtin-<version>.yaml`` next
# to it under ``src/romarr/builtin_packs/``.
_BUILTIN_PACK_VERSION = "2026.05.001"

_OPERATOR_DROP_DIR = Path("/opt/romarr/builtin-packs")


def resolve_builtin_pack_path() -> Path | None:
    """Return the on-disk / wheel-resource path to the built-in pack.

    Returns ``None`` when no candidate file exists. Callers MUST treat
    that as a benign "operator stripped the built-in pack" condition
    rather than a hard error (FR-019).

    Slice 174 / T005 — the typed ``Settings.builtin_pack_path``
    field (loaded from ``ROMARR_BUILTIN_PACK_PATH`` via the
    Pydantic Settings env-prefix) takes precedence over the
    bare ``os.environ`` lookup. The bare lookup is kept as a
    fallback so older deployments that set the env var
    without restarting still see it picked up before the
    settings cache primes.
    """
    from romarr.config.settings import get_settings

    try:
        settings_path = get_settings().builtin_pack_path
    except Exception:
        # Settings construction can fail in test contexts that
        # haven't seeded the required ``ROMARR_AUTH_SECRET_KEY``;
        # fall through to the bare env lookup below.
        settings_path = None

    if settings_path:
        candidate = Path(settings_path)
        return candidate if candidate.is_file() else None
    if env := os.environ.get("ROMARR_BUILTIN_PACK_PATH"):
        candidate = Path(env)
        return candidate if candidate.is_file() else None

    operator_drop = _OPERATOR_DROP_DIR / f"builtin-{_BUILTIN_PACK_VERSION}.yaml"
    if operator_drop.is_file():
        return operator_drop

    try:
        wheel_resource = (
            resources.files("romarr.builtin_packs")
            / f"builtin-{_BUILTIN_PACK_VERSION}.yaml"
        )
        wheel_path = Path(str(wheel_resource))
        if wheel_path.is_file():
            return wheel_path
    except (ModuleNotFoundError, FileNotFoundError):
        return None

    return None


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
                "version": _BUILTIN_PACK_VERSION,
                "search_paths": [
                    "ROMARR_BUILTIN_PACK_PATH",
                    str(_OPERATOR_DROP_DIR),
                    "<wheel resource>",
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
    "resolve_builtin_pack_path",
]
