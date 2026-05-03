"""SPA mount smoke tests (spec 014 T009).

The mount is gated on ``Settings.spa_enabled`` so the rest of
the test suite stays unaffected. These tests build a synthetic
``dist`` tree in a tmp dir, point the Settings flag at it, and
verify the mount + catch-all behaviour.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from romarr.api.app import create_app


def _make_dist(tmp_path: Path) -> Path:
    """Build a minimal Vite-shaped dist tree."""
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><div id='root'></div>")
    assets = dist / "assets"
    assets.mkdir()
    (assets / "index-deadbeef.js").write_text("console.log('hello');")
    (dist / "manifest.webmanifest").write_text('{"name":"Romarr"}')
    (dist / "icon-192.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    return dist


@pytest.mark.asyncio
async def test_spa_disabled_keeps_json_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default Settings → ``GET /`` returns the legacy JSON
    smoke response (``{"name": "romarr", ...}``)."""
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("ROMARR_OIDC_CLIENT_SECRET", "x")
    monkeypatch.setenv("ROMARR_IMPORTER_WEBHOOK_TOKEN", "x")
    monkeypatch.delenv("ROMARR_SPA_ENABLED", raising=False)
    from romarr.config.settings import get_settings

    get_settings.cache_clear()

    app = create_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.get("/")
        assert r.status_code == 200
        assert r.json()["name"] == "romarr"


@pytest.mark.asyncio
async def test_spa_enabled_serves_index_html_at_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``ROMARR_SPA_ENABLED=true`` → ``GET /`` returns the
    built ``index.html`` body."""
    dist = _make_dist(tmp_path)
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("ROMARR_OIDC_CLIENT_SECRET", "x")
    monkeypatch.setenv("ROMARR_IMPORTER_WEBHOOK_TOKEN", "x")
    monkeypatch.setenv("ROMARR_SPA_ENABLED", "true")
    monkeypatch.setenv("ROMARR_SPA_DIST_PATH", str(dist))
    from romarr.config.settings import get_settings

    get_settings.cache_clear()

    app = create_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.get("/")
        assert r.status_code == 200
        assert "<div id='root'></div>" in r.text
        assert "text/html" in r.headers["content-type"]


@pytest.mark.asyncio
async def test_spa_enabled_serves_assets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hashed asset under ``/assets/<file>`` is served from the
    dist's ``assets`` subdirectory."""
    dist = _make_dist(tmp_path)
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("ROMARR_OIDC_CLIENT_SECRET", "x")
    monkeypatch.setenv("ROMARR_IMPORTER_WEBHOOK_TOKEN", "x")
    monkeypatch.setenv("ROMARR_SPA_ENABLED", "true")
    monkeypatch.setenv("ROMARR_SPA_DIST_PATH", str(dist))
    from romarr.config.settings import get_settings

    get_settings.cache_clear()

    app = create_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.get("/assets/index-deadbeef.js")
        assert r.status_code == 200
        assert "hello" in r.text


@pytest.mark.asyncio
async def test_spa_enabled_falls_through_unmatched_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A path that no router matches and no static file
    matches falls through to ``index.html`` (React Router
    handles it client-side). The ``/library`` SPA route is a
    typical example."""
    dist = _make_dist(tmp_path)
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("ROMARR_OIDC_CLIENT_SECRET", "x")
    monkeypatch.setenv("ROMARR_IMPORTER_WEBHOOK_TOKEN", "x")
    monkeypatch.setenv("ROMARR_SPA_ENABLED", "true")
    monkeypatch.setenv("ROMARR_SPA_DIST_PATH", str(dist))
    from romarr.config.settings import get_settings

    get_settings.cache_clear()

    app = create_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.get("/library")
        assert r.status_code == 200
        assert "<div id='root'></div>" in r.text


@pytest.mark.asyncio
async def test_spa_enabled_does_not_shadow_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unknown ``/api/*`` paths return 404, NOT
    ``index.html``. This catches the regression where a
    catch-all SPA route would mask a typo'd API call."""
    dist = _make_dist(tmp_path)
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("ROMARR_OIDC_CLIENT_SECRET", "x")
    monkeypatch.setenv("ROMARR_IMPORTER_WEBHOOK_TOKEN", "x")
    monkeypatch.setenv("ROMARR_SPA_ENABLED", "true")
    monkeypatch.setenv("ROMARR_SPA_DIST_PATH", str(dist))
    from romarr.config.settings import get_settings

    get_settings.cache_clear()

    app = create_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.get("/api/v3/totally-not-a-route")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_spa_enabled_but_dist_missing_falls_back_to_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Misconfigured: spa_enabled=True but the dist path
    doesn't exist → mount is skipped, JSON fallback registers,
    a warning gets logged. The app still boots."""
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "x" * 32)
    monkeypatch.setenv("ROMARR_OIDC_CLIENT_SECRET", "x")
    monkeypatch.setenv("ROMARR_IMPORTER_WEBHOOK_TOKEN", "x")
    monkeypatch.setenv("ROMARR_SPA_ENABLED", "true")
    monkeypatch.setenv(
        "ROMARR_SPA_DIST_PATH", str(tmp_path / "nonexistent")
    )
    from romarr.config.settings import get_settings

    get_settings.cache_clear()

    app = create_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        r = await client.get("/")
        assert r.status_code == 200
        assert r.json()["name"] == "romarr"
