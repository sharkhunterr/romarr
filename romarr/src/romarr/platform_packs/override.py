"""User-override + format-CRUD helpers (Phase 6).

  - :func:`mark_overridden` cascades ``pack_source = 'user'`` from the
    Platform row down to every format and naming-token row attached to
    it (FR-020). Once flipped, the platform is permanently protected
    from pack apply: the ingestor's FR-012 short-circuit refuses to
    touch it.
  - :func:`release_override` reverts the override. The Platform row's
    ``pack_source`` reverts to whichever pack-source the most-recent
    pack-applied row of that slug had (the ingestor records this on
    the platform's own ``pack_version`` column — we look up the
    matching ``platform_pack`` row's ``pack_source`` to drive the
    revert). Subsequent pack apply now updates the platform again.
  - :func:`add_format` / :func:`update_format` / :func:`delete_format`
    enforce the FR-026 precondition that platform format mutation
    requires the platform to already be user-overridden. They raise
    :class:`OverrideRequiredError` otherwise.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select, update

from romarr.domain.models import (
    Platform,
    PlatformFormat,
    PlatformNamingToken,
    PlatformPack,
)
from romarr.platform_packs.errors import OverrideRequiredError

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


_USER = "user"


async def _require_platform(session: AsyncSession, platform_id: int) -> Platform:
    row = (
        await session.execute(select(Platform).where(Platform.id == platform_id))
    ).scalar_one_or_none()
    if row is None:
        raise ValueError(f"platform {platform_id} not found")
    return row


async def mark_overridden(session: AsyncSession, *, platform_id: int) -> Platform:
    """Flip the platform + every related format/token to ``pack_source='user'``.

    Idempotent: calling on an already-overridden platform is a no-op.
    """
    platform = await _require_platform(session, platform_id)
    if platform.pack_source != _USER:
        platform.pack_source = _USER

    await session.execute(
        update(PlatformFormat)
        .where(PlatformFormat.platform_id == platform_id)
        .values(pack_source=_USER)
    )
    await session.execute(
        update(PlatformNamingToken)
        .where(PlatformNamingToken.platform_id == platform_id)
        .values(pack_source=_USER)
    )
    await session.commit()
    await session.refresh(platform)
    return platform


async def release_override(
    session: AsyncSession, *, platform_id: int
) -> Platform:
    """Reverse :func:`mark_overridden`.

    Restores ``pack_source`` from the matching ``platform_pack`` row's
    own ``pack_source`` (if any), otherwise falls back to ``'builtin'``.
    Cascades the same value to every format / token of the platform so
    a subsequent pack apply re-touches them.
    """
    platform = await _require_platform(session, platform_id)
    if platform.pack_source != _USER:
        # Already released — nothing to do.
        return platform

    target_source = "builtin"
    if platform.pack_version is not None:
        pack_row = (
            await session.execute(
                select(PlatformPack).where(
                    PlatformPack.pack_version == platform.pack_version
                )
            )
        ).scalar_one_or_none()
        if pack_row is not None:
            target_source = pack_row.pack_source

    platform.pack_source = target_source
    await session.execute(
        update(PlatformFormat)
        .where(PlatformFormat.platform_id == platform_id)
        .values(pack_source=target_source)
    )
    await session.execute(
        update(PlatformNamingToken)
        .where(PlatformNamingToken.platform_id == platform_id)
        .values(pack_source=target_source)
    )
    await session.commit()
    await session.refresh(platform)
    return platform


async def add_format(
    session: AsyncSession,
    *,
    platform_id: int,
    extension: str,
    format_type: str,
    min_size_bytes: int | None = None,
    max_size_bytes: int | None = None,
) -> PlatformFormat:
    """Add a format row to a user-overridden platform. FR-026."""
    platform = await _require_platform(session, platform_id)
    if platform.pack_source != _USER:
        raise OverrideRequiredError(
            "format mutation requires the platform to be user-overridden",
            platform_id=platform.id,
            platform_slug=platform.slug,
        )
    row = PlatformFormat(
        platform_id=platform_id,
        extension=extension,
        format_type=format_type,
        min_size_bytes=min_size_bytes,
        max_size_bytes=max_size_bytes,
        pack_source=_USER,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def update_format(
    session: AsyncSession,
    *,
    format_id: int,
    **fields: Any,
) -> PlatformFormat:
    """Update a format row on a user-overridden platform. FR-026.

    Accepts any of: ``extension``, ``format_type``, ``min_size_bytes``,
    ``max_size_bytes``. Unknown keys are silently ignored to match the
    common PATCH-style semantics.
    """
    row = (
        await session.execute(
            select(PlatformFormat).where(PlatformFormat.id == format_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise ValueError(f"format {format_id} not found")
    platform = await _require_platform(session, row.platform_id)
    if platform.pack_source != _USER:
        raise OverrideRequiredError(
            "format mutation requires the platform to be user-overridden",
            platform_id=platform.id,
            platform_slug=platform.slug,
        )
    for key in (
        "extension",
        "format_type",
        "min_size_bytes",
        "max_size_bytes",
    ):
        if key in fields:
            setattr(row, key, fields[key])
    row.pack_source = _USER
    await session.commit()
    await session.refresh(row)
    return row


async def delete_format(
    session: AsyncSession, *, format_id: int
) -> bool:
    """Delete a format row from a user-overridden platform. FR-026.

    Returns True if a row was deleted; False on idempotent miss.
    """
    row = (
        await session.execute(
            select(PlatformFormat).where(PlatformFormat.id == format_id)
        )
    ).scalar_one_or_none()
    if row is None:
        return False
    platform = await _require_platform(session, row.platform_id)
    if platform.pack_source != _USER:
        raise OverrideRequiredError(
            "format mutation requires the platform to be user-overridden",
            platform_id=platform.id,
            platform_slug=platform.slug,
        )
    await session.delete(row)
    await session.commit()
    return True


__all__ = [
    "add_format",
    "delete_format",
    "mark_overridden",
    "release_override",
    "update_format",
]
