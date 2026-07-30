"""End-to-end tests for the Update Center sync engine.

Covers the check + apply lifecycle using a mocked httpx client so
tests stay hermetic (no network). Uses the CustomFormatAdapter,
which is the primary new-feature path — the platform_pack adapter
wraps existing code that already has its own test coverage.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import romarr.community  # noqa: F401 — registers CustomFormatAdapter
from romarr.community.schemas import PackManifest
from romarr.community.sync import apply_source, check_source
from romarr.community.versioning import is_newer
from romarr.platform_packs.models import PackSource
from romarr.profiles.models import CustomFormat


# ---------------------------------------------------------------------------
# Helpers — a fake httpx AsyncClient that maps URL → JSON body.
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, body: bytes) -> None:
        self.status_code = status_code
        self.content = body
        self.text = body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)


class _FakeClient:
    def __init__(self, routes: dict[str, dict[str, Any]]) -> None:
        self._routes = routes
        self.calls: list[str] = []

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        pass

    async def get(self, url: str) -> _FakeResponse:
        self.calls.append(url)
        if url not in self._routes:
            return _FakeResponse(404, b"not found")
        body = json.dumps(self._routes[url]).encode("utf-8")
        return _FakeResponse(200, body)


@pytest.fixture
def mock_fetch(monkeypatch: pytest.MonkeyPatch) -> dict[str, dict[str, Any]]:
    routes: dict[str, dict[str, Any]] = {}

    def _make_client(*_args: Any, **_kwargs: Any) -> _FakeClient:
        return _FakeClient(routes)

    monkeypatch.setattr("romarr.community.fetch.httpx.AsyncClient", _make_client)
    return routes


# ---------------------------------------------------------------------------
# Version compare
# ---------------------------------------------------------------------------


def test_is_newer_semver() -> None:
    assert is_newer("0.15.0", "0.14.34")
    assert not is_newer("0.14.0", "0.14.0")
    assert not is_newer("0.13.0", "0.14.0")


def test_is_newer_with_v_prefix() -> None:
    assert is_newer("v1.2.3", "v1.2.2")


def test_is_newer_date_tag_falls_back_to_string() -> None:
    # Neither is PEP 440 — fallback: same string = not newer, else newer.
    assert is_newer("2026-07-30", "2026-07-29")
    assert not is_newer("2026-07-30", "2026-07-30")


def test_is_newer_installed_missing_means_newer_when_available() -> None:
    assert is_newer("1.0.0", None)
    assert is_newer("1.0.0", "")


def test_is_newer_no_available_never_newer() -> None:
    assert not is_newer(None, "1.0.0")
    assert not is_newer("", "1.0.0")


# ---------------------------------------------------------------------------
# check_source — updates last_seen_version + status, no CF written
# ---------------------------------------------------------------------------


async def test_check_source_reads_manifest_and_updates_row(
    async_session: AsyncSession, mock_fetch: dict[str, dict[str, Any]]
) -> None:
    manifest_url = "https://example.test/pack/manifest.json"
    mock_fetch[manifest_url] = {
        "romarr_pack": True,
        "kind": "custom_format",
        "version": "2026.07.30",
        "name": "Test pack",
        "description": "unit test",
        "items": [
            {"path": "cf/test.json", "seed_key": "test-cf"},
        ],
    }
    source = PackSource(
        name="test",
        url=manifest_url,
        kind="raw",
        resource_type="custom_format",
        trust_status="trusted",
    )
    async_session.add(source)
    await async_session.commit()

    result = await check_source(source, async_session)

    assert result.error is None
    assert result.available_version == "2026.07.30"
    assert result.item_count == 1
    assert source.last_seen_version == "2026.07.30"
    assert source.installed_version is None  # check-only, no apply
    assert source.last_status == "ok"


async def test_check_source_records_error_on_404(
    async_session: AsyncSession, mock_fetch: dict[str, dict[str, Any]]
) -> None:
    source = PackSource(
        name="test",
        url="https://example.test/missing.json",
        kind="raw",
        resource_type="custom_format",
        trust_status="trusted",
    )
    async_session.add(source)
    await async_session.commit()

    result = await check_source(source, async_session)

    assert result.error is not None
    assert "404" in result.error
    assert source.last_status == "error"
    assert source.last_seen_version is None


async def test_check_source_rejects_wrong_kind(
    async_session: AsyncSession, mock_fetch: dict[str, dict[str, Any]]
) -> None:
    manifest_url = "https://example.test/wrong-kind.json"
    mock_fetch[manifest_url] = {
        "romarr_pack": True,
        "kind": "platform_pack",  # source is registered as custom_format
        "version": "1.0",
        "name": "Wrong kind pack",
        "items": [],
    }
    source = PackSource(
        name="wrong-kind",
        url=manifest_url,
        kind="raw",
        resource_type="custom_format",
        trust_status="trusted",
    )
    async_session.add(source)
    await async_session.commit()

    result = await check_source(source, async_session)

    assert result.error is not None
    assert "kind" in result.error


# ---------------------------------------------------------------------------
# apply_source — writes CF rows, updates installed_version
# ---------------------------------------------------------------------------


async def test_apply_source_ingests_custom_format(
    async_session: AsyncSession, mock_fetch: dict[str, dict[str, Any]]
) -> None:
    manifest_url = "https://example.test/pack/manifest.json"
    item_url = "https://example.test/pack/cf/community-marker.json"
    mock_fetch[manifest_url] = {
        "romarr_pack": True,
        "kind": "custom_format",
        "version": "2026.07.30",
        "name": "Test pack",
        "items": [{"path": "cf/community-marker.json", "seed_key": "community-marker"}],
    }
    mock_fetch[item_url] = {
        "name": "Community Marker",
        "score": 42,
        "conditions": [
            {
                "field": "title",
                "operator": "matches_regex",
                "values": "\\bCOMMUNITY\\b",
            }
        ],
    }
    source = PackSource(
        name="test",
        url=manifest_url,
        kind="raw",
        resource_type="custom_format",
        trust_status="trusted",
    )
    async_session.add(source)
    await async_session.commit()

    result = await apply_source(source, async_session)

    assert result.error is None, result.error
    assert result.applied_count == 1
    assert source.installed_version == "2026.07.30"
    assert source.last_seen_version == "2026.07.30"

    row = (
        await async_session.execute(
            select(CustomFormat).where(CustomFormat.seed_key == "community-marker")
        )
    ).scalar_one()
    assert row.name == "Community Marker"
    assert row.score == 42


async def test_apply_source_skips_user_modified_row(
    async_session: AsyncSession, mock_fetch: dict[str, dict[str, Any]]
) -> None:
    # Pre-existing user-modified CF must not be overwritten.
    async_session.add(
        CustomFormat(
            seed_key="pinned",
            name="OperatorEdit",
            score=999,
            conditions=[],
            is_factory_default=False,
            is_user_modified=True,
        )
    )
    manifest_url = "https://example.test/pack/manifest.json"
    item_url = "https://example.test/pack/cf/pinned.json"
    mock_fetch[manifest_url] = {
        "romarr_pack": True,
        "kind": "custom_format",
        "version": "2.0",
        "name": "Test pack",
        "items": [{"path": "cf/pinned.json", "seed_key": "pinned"}],
    }
    mock_fetch[item_url] = {
        "name": "CommunityName",
        "score": 10,
        "conditions": [],
    }
    source = PackSource(
        name="test",
        url=manifest_url,
        kind="raw",
        resource_type="custom_format",
        trust_status="trusted",
    )
    async_session.add(source)
    await async_session.commit()

    result = await apply_source(source, async_session)

    assert result.applied_count == 0
    assert any("pinned" in w for w in result.warnings)
    row = (
        await async_session.execute(
            select(CustomFormat).where(CustomFormat.seed_key == "pinned")
        )
    ).scalar_one()
    assert row.name == "OperatorEdit"
    assert row.score == 999


async def test_apply_refuses_when_source_pending(
    async_session: AsyncSession, mock_fetch: dict[str, dict[str, Any]]
) -> None:
    source = PackSource(
        name="pending-src",
        url="https://example.test/pack/manifest.json",
        kind="raw",
        resource_type="custom_format",
        trust_status="pending",
    )
    async_session.add(source)
    await async_session.commit()

    result = await apply_source(source, async_session)

    assert result.error is not None
    assert "pending" in result.error


# ---------------------------------------------------------------------------
# Manifest schema — parses required fields, rejects malformed
# ---------------------------------------------------------------------------


def test_manifest_parses_minimal() -> None:
    m = PackManifest.model_validate(
        {
            "kind": "custom_format",
            "version": "1.0",
            "name": "Minimal",
            "items": [],
        }
    )
    assert m.kind == "custom_format"
    assert m.version == "1.0"
    assert m.items == ()
