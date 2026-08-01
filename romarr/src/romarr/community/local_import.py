"""Local (offline) import of a community pack.

Two shapes accepted :

  * **Single JSON file** — a manifest with either the standard
    ``items: [{path, seed_key}]`` list (paths resolved against a
    provided ``base_url``, if any) OR an ``inline_items: [{...},
    {...}]`` list carrying full bodies. The inline form is the
    natural fit for the air-gapped case where one JSON is easier
    to move than a folder tree.

  * **ZIP archive** — ``manifest.json`` at the archive root plus
    the item files under paths matching ``items[].path``. Same
    layout as the GitHub repo — an operator can literally clone
    the community repo, zip it, and drop it in.

Both paths validate + ingest via the *same* adapters that handle
URL-fetched sources, so the resulting rows are indistinguishable
from an online apply.
"""

from __future__ import annotations

import io
import json
import logging
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.community.adapters import get_adapter
from romarr.community.schemas import ApplyResult, PackManifest
from romarr.platform_packs.models import PackSource
from romarr.profiles.models import CustomFormat
from romarr.profiles.schemas import CustomFormatCreate

_LOG = logging.getLogger(__name__)

_MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MiB — generous for a single ZIP


class LocalImportError(RuntimeError):
    """Raised when the uploaded bytes don't parse into a valid pack."""


@dataclass(frozen=True, slots=True)
class ParsedPack:
    manifest: PackManifest
    # Body per manifest.items[].path (or per inline_items index).
    bodies: dict[str, bytes]


def _read_manifest(payload: dict[str, Any]) -> PackManifest:
    try:
        return PackManifest.model_validate(payload)
    except ValidationError as exc:
        raise LocalImportError(f"invalid manifest: {exc}") from exc


def parse_upload(filename: str, content: bytes) -> ParsedPack:
    """Detect JSON vs ZIP and return a validated pack + item bodies.

    Raises :class:`LocalImportError` with an operator-readable
    message on any parse failure.
    """
    if len(content) > _MAX_UPLOAD_BYTES:
        raise LocalImportError(
            f"upload too large ({len(content)} B > {_MAX_UPLOAD_BYTES} B)"
        )

    lower = filename.lower()
    if lower.endswith(".zip"):
        return _parse_zip(content)
    if lower.endswith(".json"):
        return _parse_json(content)
    # Try JSON first (recover from a mis-named file), fall back to ZIP.
    try:
        return _parse_json(content)
    except LocalImportError:
        return _parse_zip(content)


def _parse_json(content: bytes) -> ParsedPack:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalImportError(f"file is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise LocalImportError("top-level JSON must be an object")

    # inline_items short-circuit — bodies are already in the JSON.
    inline = payload.get("inline_items")
    if inline is not None:
        if not isinstance(inline, list):
            raise LocalImportError("'inline_items' must be a list")
        # Synthesise a matching items[] list keyed by index so the
        # adapter's item-loop resolves via path == "inline:<idx>".
        synthetic_items = []
        bodies: dict[str, bytes] = {}
        for idx, body in enumerate(inline):
            if not isinstance(body, dict):
                raise LocalImportError(
                    f"inline_items[{idx}] must be an object"
                )
            key = f"inline:{idx}"
            seed_key = body.get("seed_key")
            synthetic_items.append({"path": key, "seed_key": seed_key})
            body_wo_key = {k: v for k, v in body.items() if k != "seed_key"}
            bodies[key] = json.dumps(body_wo_key).encode("utf-8")
        # Substitute items in the manifest payload before validation.
        payload = {**payload, "items": synthetic_items}
        payload.pop("inline_items", None)
        manifest = _read_manifest(payload)
        return ParsedPack(manifest=manifest, bodies=bodies)

    # Reference-only manifest — items[].path can only resolve when
    # we have a base URL, which local imports don't. Reject clearly.
    manifest = _read_manifest(payload)
    if manifest.items:
        raise LocalImportError(
            "manifest has items[] with paths — a local JSON import needs "
            "either 'inline_items' (bodies embedded) or a ZIP with the "
            "item files. Use the URL flow for reference-only manifests."
        )
    return ParsedPack(manifest=manifest, bodies={})


def _parse_zip(content: bytes) -> ParsedPack:
    try:
        archive = zipfile.ZipFile(io.BytesIO(content), mode="r")
    except zipfile.BadZipFile as exc:
        raise LocalImportError(f"not a valid ZIP archive: {exc}") from exc

    with archive:
        names = set(archive.namelist())
        # Accept manifest.json at root or under a single top-level
        # subfolder (github zip export puts the repo name in front).
        manifest_path: str | None = None
        for candidate in names:
            if candidate.endswith("manifest.json") and candidate.count("/") <= 1:
                manifest_path = candidate
                break
        if manifest_path is None:
            raise LocalImportError(
                "ZIP is missing a manifest.json at its root"
            )

        base = manifest_path.rsplit("manifest.json", 1)[0]
        try:
            raw = archive.read(manifest_path)
        except KeyError as exc:
            raise LocalImportError(f"manifest read failed: {exc}") from exc
        try:
            manifest_payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise LocalImportError(f"manifest.json not valid JSON: {exc}") from exc
        manifest = _read_manifest(manifest_payload)

        bodies: dict[str, bytes] = {}
        for item in manifest.items:
            entry_name = f"{base}{item.path}"
            if entry_name not in names:
                # Try without base (item paths might already be absolute
                # relative to the archive root).
                if item.path in names:
                    entry_name = item.path
                else:
                    raise LocalImportError(
                        f"ZIP is missing item file {item.path!r} "
                        f"(looked for {entry_name!r})"
                    )
            body_bytes = archive.read(entry_name)
            if len(body_bytes) > _MAX_UPLOAD_BYTES:
                raise LocalImportError(
                    f"item {item.path!r} exceeds {_MAX_UPLOAD_BYTES} B"
                )
            bodies[item.path] = body_bytes

        return ParsedPack(manifest=manifest, bodies=bodies)


# ---------------------------------------------------------------------------
# Ingest — write a synthetic PackSource row + apply the bodies through the
# resource-type adapter. The row is stamped source_url="local:<sha1>" so it
# is visible in the Update Center but obvious as a local drop.
# ---------------------------------------------------------------------------


async def apply_local_pack(
    session: AsyncSession, *, name: str, pack: ParsedPack
) -> tuple[PackSource, ApplyResult]:
    """Create a PackSource row for the imported pack and ingest its bodies.

    Uses the resource_type-appropriate adapter. Returns the row + the
    apply result so the caller (API endpoint) can render both.
    """
    kind = pack.manifest.kind

    existing = (
        await session.execute(
            select(PackSource).where(PackSource.name == name)
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise LocalImportError(
            f"a source named {name!r} already exists — pick another name "
            f"or delete the existing row first"
        )

    row = PackSource(
        name=name,
        url=f"local:{pack.manifest.name}#{pack.manifest.version}",
        kind="raw",
        resource_type=kind,
        enabled=True,
        auto_check=False,  # Local imports have no upstream to poll.
        trust_status="trusted",  # Operator explicitly uploaded.
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    result = await _apply_bodies_via_adapter(session, row=row, pack=pack)
    return row, result


async def _apply_bodies_via_adapter(
    session: AsyncSession,
    *,
    row: PackSource,
    pack: ParsedPack,
) -> ApplyResult:
    """Route bodies through the adapter's ingest path.

    Adapters expect to fetch bodies via HTTP; here we short-circuit
    by feeding pre-loaded bytes directly. For the CF adapter that
    means walking manifest.items ourselves.
    """
    adapter = get_adapter(row.resource_type)
    if adapter is None:
        return ApplyResult(
            applied_version=pack.manifest.version,
            applied_count=0,
            error=f"no adapter for resource_type={row.resource_type!r}",
        )

    if row.resource_type == "custom_format":
        return await _apply_custom_format_bodies(session, row=row, pack=pack)
    if row.resource_type == "platform_pack":
        return await _apply_platform_pack_bodies(session, row=row, pack=pack)

    return ApplyResult(
        applied_version=pack.manifest.version,
        applied_count=0,
        error=f"local import not wired for resource_type={row.resource_type!r}",
    )


async def _apply_custom_format_bodies(
    session: AsyncSession,
    *,
    row: PackSource,
    pack: ParsedPack,
) -> ApplyResult:
    applied = 0
    warnings: list[str] = []
    for item in pack.manifest.items:
        body_bytes = pack.bodies.get(item.path)
        if body_bytes is None:
            warnings.append(f"{item.path}: body missing")
            continue
        try:
            body = json.loads(body_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            warnings.append(f"{item.path}: invalid JSON — {exc}")
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
                select(CustomFormat).where(CustomFormat.seed_key == seed_key)
            )
        ).scalar_one_or_none()
        if existing is None:
            session.add(
                CustomFormat(
                    seed_key=seed_key,
                    is_factory_default=False,
                    is_user_modified=False,
                    source_id=row.id,
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
        existing.source_id = row.id
        applied += 1

    row.last_synced_at = datetime.now(UTC)
    row.last_status = "partial" if warnings else "ok"
    row.last_error = "; ".join(warnings) if warnings else None
    row.installed_version = pack.manifest.version
    row.last_seen_version = pack.manifest.version
    row.last_applied_count = applied
    await session.commit()
    return ApplyResult(
        applied_version=pack.manifest.version,
        applied_count=applied,
        warnings=tuple(warnings),
    )


async def _apply_platform_pack_bodies(
    session: AsyncSession,
    *,
    row: PackSource,
    pack: ParsedPack,
) -> ApplyResult:
    from sqlalchemy.ext.asyncio import async_sessionmaker

    from romarr.community.platform_pack_adapter import _ensure_pack_version
    from romarr.platform_packs.ingestor import IngestSource, ingest_pack

    sm = async_sessionmaker(session.bind, expire_on_commit=False)
    ingest_source = IngestSource(
        pack_source="community",
        applied_by=f"community_source:{row.id}",
        source_id=row.id,
    )

    applied = 0
    warnings: list[str] = []
    for item in pack.manifest.items:
        body_bytes = pack.bodies.get(item.path)
        if body_bytes is None:
            warnings.append(f"{item.path}: body missing")
            continue
        body = _ensure_pack_version(body_bytes, pack.manifest.version)
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

    row.last_synced_at = datetime.now(UTC)
    row.last_status = "partial" if warnings else "ok"
    row.last_error = "; ".join(warnings) if warnings else None
    row.installed_version = pack.manifest.version
    row.last_seen_version = pack.manifest.version
    row.last_applied_count = applied
    await session.commit()
    return ApplyResult(
        applied_version=pack.manifest.version,
        applied_count=applied,
        warnings=tuple(warnings),
    )


__all__ = ["LocalImportError", "ParsedPack", "apply_local_pack", "parse_upload"]
