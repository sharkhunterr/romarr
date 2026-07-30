"""Community adapter for ``resource_type = "platform_pack"``.

Delegates to the existing platform-packs subsystem
(:mod:`romarr.platform_packs.remote.fetch_from_source` +
:func:`romarr.platform_packs.ingestor.ingest_pack`) so the
unified Update Center never duplicates YAML validation, ingest
transactions, or the FR-013a version-order rules.

Two source shapes accepted:

  * **JSON manifest** — the modern format shared with
    ``custom_format`` sources. The manifest lists YAML item paths
    (relative to the manifest URL). The adapter fetches each YAML
    and hands the bytes to ``ingest_pack``. ``manifest.version`` is
    the string tracked in ``installed_version`` / ``last_seen_version``.
  * **Legacy raw / github_dir** — the URL points directly at a
    ``.yaml`` file OR a GitHub tree URL. This matches the pre-Update
    Center ``pack_sources`` flow (still exercised via
    ``/api/v3/rom/platform-pack-source/*``). No version is derivable;
    ``last_seen_version`` gets a synthetic ``"fetched@<UTC ISO>"``
    tag so the "update available" indicator falls back to
    "different string ⇒ different content" behaviour.

The adapter's ``kind`` is the ``source.kind`` column value on the
row (``raw`` / ``github_dir``); the manifest path is auto-detected
by attempting a JSON parse first and falling back to the legacy
flow on failure.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import yaml
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.community.adapters import (
    CommunityAdapter,
    FetchError,
    parse_manifest,
)
from romarr.community.fetch import fetch_text, resolve_item_url
from romarr.community.schemas import ApplyResult, CheckResult
from romarr.platform_packs.ingestor import IngestSource, ingest_pack
from romarr.platform_packs.models import PackSource
from romarr.platform_packs.remote import (
    RemotePackError,
    fetch_from_source,
)

_LOG = logging.getLogger(__name__)


def _ensure_pack_version(body: bytes, fallback_version: str) -> bytes:
    """If the YAML body has no top-level ``pack_version`` key, inject
    ``fallback_version`` (typically ``manifest.version``) so the
    operator can maintain the version in a single place — the
    manifest — instead of duplicating it across every YAML.

    Malformed YAML falls through untouched — the ingestor's own
    validator will surface the parse error with the right message.
    """
    try:
        parsed = yaml.safe_load(body)
    except yaml.YAMLError:
        return body
    if not isinstance(parsed, dict):
        return body
    if parsed.get("pack_version"):
        return body
    parsed["pack_version"] = fallback_version
    # ``sort_keys=False`` keeps ``pack_version`` near the top-level
    # ordering the operator's YAML already had — no cosmetic churn.
    return yaml.safe_dump(parsed, sort_keys=False, allow_unicode=True).encode(
        "utf-8"
    )


class PlatformPackAdapter:
    """Adapter for the ``platform_pack`` resource type."""

    resource_type = "platform_pack"

    # ------------------------------------------------------------------
    # check() — try manifest first, fall back to legacy fetch
    # ------------------------------------------------------------------

    async def check(self, source: PackSource) -> CheckResult:
        # Try the JSON manifest path first.
        try:
            manifest = await parse_manifest(source.url)
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
        except (FetchError, ValidationError):
            # Fall through to legacy — the URL might point at a raw
            # YAML or a github_dir without a manifest.
            pass

        # Legacy: fetch YAMLs directly, count them, stamp a synthetic
        # fetched-at version so any drift shows up as "update available".
        try:
            yamls = await fetch_from_source(source.url, source.kind)
        except RemotePackError as exc:
            return CheckResult(error=f"legacy fetch failed: {exc}")

        synthetic = f"fetched@{datetime.now(UTC).isoformat(timespec='seconds')}"
        return CheckResult(
            available_version=synthetic,
            manifest_name=None,
            manifest_description="",
            item_count=len(yamls),
        )

    # ------------------------------------------------------------------
    # apply() — same duality; both paths funnel into ingest_pack()
    # ------------------------------------------------------------------

    async def apply(
        self, source: PackSource, session: AsyncSession
    ) -> ApplyResult:
        sm = async_sessionmaker(session.bind, expire_on_commit=False)
        ingest_source = IngestSource(
            pack_source="community",
            applied_by=f"community_source:{source.id}",
        )

        # Try the manifest path first.
        applied_via_manifest = False
        try:
            manifest = await parse_manifest(source.url)
            if manifest.kind != self.resource_type:
                return ApplyResult(
                    applied_version=source.installed_version or "",
                    applied_count=0,
                    error=(
                        f"manifest declares kind={manifest.kind!r} — "
                        f"expected {self.resource_type!r}"
                    ),
                )
            applied_via_manifest = True
        except (FetchError, ValidationError):
            manifest = None  # type: ignore[assignment]

        applied = 0
        warnings: list[str] = []

        if applied_via_manifest and manifest is not None:
            for item in manifest.items:
                item_url = resolve_item_url(source.url, item.path)
                try:
                    raw = (await fetch_text(item_url)).encode("utf-8")
                except FetchError as exc:
                    warnings.append(f"{item.path}: {exc}")
                    continue
                # Manifest-driven versioning: if the YAML omits
                # ``pack_version``, inject the manifest's version so
                # the operator maintains a single source of truth.
                body = _ensure_pack_version(raw, manifest.version)
                try:
                    await ingest_pack(
                        session,
                        sessionmaker=sm,
                        content=body,
                        source=ingest_source,
                    )
                    applied += 1
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"{item.path}: ingest failed — {exc}")
            applied_version = manifest.version
        else:
            # Legacy path — mirror the existing platform-pack sync.
            try:
                yamls = await fetch_from_source(source.url, source.kind)
            except RemotePackError as exc:
                return ApplyResult(
                    applied_version=source.installed_version or "",
                    applied_count=0,
                    error=f"legacy fetch failed: {exc}",
                )
            for yaml_body in yamls:
                try:
                    await ingest_pack(
                        session,
                        sessionmaker=sm,
                        content=yaml_body.body,
                        source=ingest_source,
                    )
                    applied += 1
                except Exception as exc:  # noqa: BLE001
                    warnings.append(
                        f"{yaml_body.filename}: ingest failed — {exc}"
                    )
            applied_version = (
                f"fetched@{datetime.now(UTC).isoformat(timespec='seconds')}"
            )

        return ApplyResult(
            applied_version=applied_version,
            applied_count=applied,
            warnings=tuple(warnings),
        )


__all__ = ["PlatformPackAdapter"]
