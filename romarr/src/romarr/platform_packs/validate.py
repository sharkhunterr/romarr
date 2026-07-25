"""Reusable pack-body validation → :class:`ValidateResult`.

Extracted from the ``POST /api/v3/rom/platform-pack/validate``
endpoint so callers that already hold the YAML bytes (the pack
sources preview, a scheduled dry-run, etc.) can reach the same
dry-run pipeline without re-implementing it.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.domain.models import PlatformPack
from romarr.platform_packs.errors import (
    PackValidationError,
    SchemaVersionTooHighError,
)
from romarr.platform_packs.snapshot import (
    compute_platform_diff,
    load_snapshot,
)
from romarr.platform_packs.types import ValidateResult
from romarr.platform_packs.validator import validate_pack
from romarr.platform_packs.yaml_loader import compute_contents_hash, load_pack


async def validate_bytes(
    session: AsyncSession, *, body: bytes
) -> ValidateResult:
    """Dry-run a single YAML body — no writes, no side effects.

    Mirrors the behaviour of the ``/validate`` endpoint but takes
    ``bytes`` instead of a multipart ``UploadFile``. Safe to call
    inside a read-only session or inside a loop over remote-fetched
    pack bodies.
    """
    started = datetime.now(UTC)
    snapshot = await load_snapshot(session)
    existing_slugs = set(snapshot.platforms_by_slug)

    try:
        parsed = validate_pack(body, existing_slugs=existing_slugs)
    except (PackValidationError, SchemaVersionTooHighError) as exc:
        try:
            parsed_dict = load_pack(body)
        except yaml.YAMLError:
            parsed_dict = {}
        return ValidateResult(
            pack_version=str(parsed_dict.get("pack_version") or "<invalid>"),
            contents_hash=(
                compute_contents_hash(parsed_dict) if parsed_dict else ""
            ),
            action="would_fail",
            diff=[],
            parsing_strategies_affected=[],
            started_at=started,
            finished_at=datetime.now(UTC),
            database_state_unchanged=True,
            error_message=str(exc),
        )

    diff = compute_platform_diff(parsed.parsed.get("platforms") or [], snapshot)
    parsing_strategies_affected = [
        s["id"] for s in parsed.parsed.get("parsing_strategies") or []
    ]

    existing = (
        await session.execute(
            select(PlatformPack).where(
                PlatformPack.pack_version == parsed.pack_version
            )
        )
    ).scalar_one_or_none()

    action: Any
    if existing is not None and existing.contents_hash == parsed.contents_hash:
        action = "would_skip"
    elif existing is not None:
        action = "would_fail"
        return ValidateResult(
            pack_version=parsed.pack_version,
            contents_hash=parsed.contents_hash,
            action=action,
            diff=diff,
            parsing_strategies_affected=parsing_strategies_affected,
            started_at=started,
            finished_at=datetime.now(UTC),
            database_state_unchanged=True,
            error_message=(
                f"pack version {parsed.pack_version!r} already exists with a "
                "different contents_hash — an apply would fail"
            ),
        )
    else:
        action = "would_apply"

    return ValidateResult(
        pack_version=parsed.pack_version,
        contents_hash=parsed.contents_hash,
        action=action,
        diff=diff,
        parsing_strategies_affected=parsing_strategies_affected,
        started_at=started,
        finished_at=datetime.now(UTC),
        database_state_unchanged=True,
    )


__all__ = ["validate_bytes"]
