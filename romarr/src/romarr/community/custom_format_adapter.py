"""Community adapter for ``resource_type = "custom_format"``.

Reuses the existing :class:`~romarr.profiles.schemas.CustomFormatCreate`
schema for validation and the seeder's own upsert semantics
(insert if new ``seed_key``, refresh if unchanged-since-seed, skip
if the operator has flagged the row ``is_user_modified``).

Manifest shape (see :mod:`romarr.community.schemas`) — items look
like ``{"path": "cf/no-intro-verified.json", "seed_key": "no-intro-verified"}``.
Each item body is a single JSON object matching
``CustomFormatCreate``.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.community.adapters import (
    CommunityAdapter,
    FetchError,
    parse_manifest,
)
from romarr.community.fetch import fetch_json, resolve_item_url
from romarr.community.schemas import ApplyResult, CheckResult
from romarr.platform_packs.models import PackSource
from romarr.profiles.models import CustomFormat
from romarr.profiles.schemas import CustomFormatCreate

_LOG = logging.getLogger(__name__)


class CustomFormatAdapter:
    """Ingests JSON custom-format packs from a manifest URL."""

    resource_type = "custom_format"

    async def check(self, source: PackSource) -> CheckResult:
        try:
            manifest = await parse_manifest(source.url)
        except FetchError as exc:
            return CheckResult(error=str(exc))
        except ValidationError as exc:
            return CheckResult(error=f"invalid manifest: {exc}")

        if manifest.kind != self.resource_type:
            return CheckResult(
                error=(
                    f"manifest declares kind={manifest.kind!r} — "
                    f"expected {self.resource_type!r}"
                )
            )

        return CheckResult(
            available_version=manifest.version,
            manifest_name=manifest.name,
            manifest_description=manifest.description,
            item_count=len(manifest.items),
        )

    async def apply(
        self, source: PackSource, session: AsyncSession
    ) -> ApplyResult:
        try:
            manifest = await parse_manifest(source.url)
        except FetchError as exc:
            return ApplyResult(
                applied_version=source.installed_version or "",
                applied_count=0,
                error=str(exc),
            )
        except ValidationError as exc:
            return ApplyResult(
                applied_version=source.installed_version or "",
                applied_count=0,
                error=f"invalid manifest: {exc}",
            )

        if manifest.kind != self.resource_type:
            return ApplyResult(
                applied_version=source.installed_version or "",
                applied_count=0,
                error=(
                    f"manifest declares kind={manifest.kind!r} — "
                    f"expected {self.resource_type!r}"
                ),
            )

        applied = 0
        warnings: list[str] = []
        for item in manifest.items:
            item_url = resolve_item_url(source.url, item.path)
            try:
                body = await fetch_json(item_url)
            except FetchError as exc:
                warnings.append(f"{item.path}: {exc}")
                continue

            seed_key = item.seed_key or body.get("seed_key")
            if not seed_key:
                warnings.append(f"{item.path}: missing seed_key")
                continue

            try:
                create = CustomFormatCreate(
                    **{k: v for k, v in body.items() if k != "seed_key"}
                )
            except ValidationError as exc:
                warnings.append(f"{item.path}: schema mismatch — {exc}")
                continue

            payload: dict[str, Any] = {
                "name": create.name,
                "score": create.score,
                "conditions": [
                    c.model_dump(by_alias=True, exclude_none=True)
                    for c in create.conditions
                ],
            }

            existing = (
                await session.execute(
                    select(CustomFormat).where(
                        CustomFormat.seed_key == seed_key
                    )
                )
            ).scalar_one_or_none()

            if existing is None:
                session.add(
                    CustomFormat(
                        seed_key=seed_key,
                        is_factory_default=False,
                        is_user_modified=False,
                        source_id=source.id,
                        **payload,
                    )
                )
                applied += 1
                continue

            if existing.is_user_modified:
                warnings.append(
                    f"{seed_key}: kept — operator-modified, not overwritten"
                )
                continue

            for key, value in payload.items():
                setattr(existing, key, value)
            existing.is_factory_default = False
            existing.source_id = source.id
            applied += 1

        await session.commit()
        return ApplyResult(
            applied_version=manifest.version,
            applied_count=applied,
            warnings=tuple(warnings),
        )


__all__ = ["CustomFormatAdapter"]
