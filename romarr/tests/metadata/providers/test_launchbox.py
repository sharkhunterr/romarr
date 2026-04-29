"""LaunchBox provider tests (T034, T035)."""

from __future__ import annotations

from pathlib import Path

import pytest

from romarr.metadata import PROVIDER_REGISTRY, ProviderField
from romarr.metadata.errors import NotFoundError
from romarr.metadata.providers.launchbox import (
    LaunchBoxBulkImporter,
    LaunchBoxProvider,
)


def _make_provider(*, cache: dict[str, dict] | None = None) -> LaunchBoxProvider:
    p = LaunchBoxProvider(rate_limit_rps=100, rate_limit_burst=100)
    if cache is not None:
        p.configure({"cache": cache})
    else:
        p.configure({})
    return p


# ---------------------------------------------------------------------------
# T034 — per-Game query path
# ---------------------------------------------------------------------------


async def test_per_game_query_finds_cached_row() -> None:
    cache = {
        "Sonic the Hedgehog": {
            "id": "1234",
            "title": "Sonic the Hedgehog",
            "platform": "Sega Genesis",
            "year": 1991,
            "summary": "Genesis classic.",
            "developer": "Sonic Team",
            "publisher": "Sega",
            "genres": ["Platform", "Action"],
            "cover_url": "https://lb.example/cover.jpg",
        }
    }
    p = _make_provider(cache=cache)

    results = await p.search_games("Sonic the Hedgehog", platform_slug="megadrive")
    assert len(results) == 1
    assert results[0].provider_game_id == "1234"

    meta = await p.get_game("1234")
    assert meta.fields[ProviderField.TITLE] == "Sonic the Hedgehog"
    assert meta.fields[ProviderField.SUMMARY] == "Genesis classic."
    assert meta.fields[ProviderField.GENRES] == ["Platform", "Action"]
    assert meta.fields[ProviderField.DEVELOPER] == "Sonic Team"
    assert meta.fields[ProviderField.PUBLISHER] == "Sega"
    assert meta.fields[ProviderField.RELEASE_DATE].year == 1991
    assert meta.fields[ProviderField.COVER] == "https://lb.example/cover.jpg"


async def test_search_filters_by_platform() -> None:
    cache = {
        "Sonic": {
            "id": "1",
            "title": "Sonic",
            "platform": "Sega Genesis",
        },
        "Sonic GBA": {
            "id": "2",
            "title": "Sonic Advance",
            "platform": "Nintendo Game Boy Advance",
        },
    }
    p = _make_provider(cache=cache)

    md = await p.search_games("sonic", platform_slug="megadrive")
    assert {r.title for r in md} == {"Sonic"}

    gba = await p.search_games("sonic", platform_slug="gba")
    assert {r.title for r in gba} == {"Sonic Advance"}


async def test_empty_cache_returns_empty_search() -> None:
    """No bulk import has run yet → search degrades silently."""
    p = _make_provider()
    assert await p.search_games("anything") == []


async def test_get_game_unknown_id_raises_not_found() -> None:
    p = _make_provider()
    with pytest.raises(NotFoundError):
        await p.get_game("999")


async def test_get_cover_raises_not_implemented() -> None:
    p = _make_provider()
    with pytest.raises(NotImplementedError):
        await p.get_cover("1")


# ---------------------------------------------------------------------------
# T035 — bulk-importer stub
# ---------------------------------------------------------------------------


async def test_bulk_importer_stub_raises_not_implemented(tmp_path: Path) -> None:
    importer = LaunchBoxBulkImporter(tmp_path / "Metadata.zip")
    with pytest.raises(NotImplementedError, match="deferred to v1"):
        await importer.run()


def test_bulk_importer_holds_archive_path(tmp_path: Path) -> None:
    archive = tmp_path / "Metadata.zip"
    importer = LaunchBoxBulkImporter(archive)
    assert importer.archive_path == archive


# ---------------------------------------------------------------------------
# Self-registration + capabilities + platform mapping
# ---------------------------------------------------------------------------


def test_self_registered() -> None:
    assert PROVIDER_REGISTRY.get("launchbox") is LaunchBoxProvider


def test_capabilities_no_auth_required() -> None:
    cap = LaunchBoxProvider.capabilities
    assert cap.requires_auth is False
    assert cap.invoked_in_scan is True


def test_platform_mapping_megadrive_is_genesis_string() -> None:
    p = LaunchBoxProvider(rate_limit_rps=100, rate_limit_burst=100)
    assert p.get_platform_mapping("megadrive") == "Sega Genesis"


async def test_health_check_reflects_cache_population() -> None:
    p = _make_provider()
    # Empty cache — health-check returns False (operator hasn't imported).
    assert await p.health_check() is False
    p_seeded = _make_provider(cache={"foo": {"id": "1", "title": "foo"}})
    assert await p_seeded.health_check() is True
