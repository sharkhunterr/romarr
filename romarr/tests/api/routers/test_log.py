"""Log router tests (T038, T039, FR-014).

Three endpoints: paginated reader stub, file listing, file
download. Each is exercised against a tmp directory configured
via ``Settings.log_dir`` to keep tests filesystem-isolated.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from romarr.config import get_settings
from tests.api.test_auth_endpoints import _seed_admin_user

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def log_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Point ``Settings.log_dir`` at a fresh tmp dir for the
    duration of the test. Clears the lru_cache so the new value
    takes effect."""
    monkeypatch.setenv("ROMARR_LOG_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        yield tmp_path
    finally:
        get_settings.cache_clear()


@pytest.fixture
async def authed_client(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> httpx.AsyncClient:
    await _seed_admin_user(api_engine)
    login = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "goodpassword"},
    )
    assert login.status_code == 204
    return api_client


# ---------------------------------------------------------------------------
# T038 — paginated entries (MVP empty stub)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_paginated_log_entries_returns_canonical_envelope(
    authed_client: httpx.AsyncClient, log_dir: Path
) -> None:
    """MVP — empty list with the pinned schema. Frontend wires
    against the documented camelCase keys today; entries
    materialise once the structlog → JSON-line file sink ships."""
    resp = await authed_client.get("/api/v3/system/log?page=1&pageSize=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 1
    assert body["pageSize"] == 10
    assert body["totalRecords"] == 0
    assert body["records"] == []


# ---------------------------------------------------------------------------
# /file — listing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_log_files_empty_dir(
    authed_client: httpx.AsyncClient, log_dir: Path
) -> None:
    """An empty log_dir returns ``[]`` rather than 404."""
    resp = await authed_client.get("/api/v3/system/log/file")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_log_files_missing_dir_returns_empty_list(
    authed_client: httpx.AsyncClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``log_dir`` may not exist on a fresh install — return
    ``[]`` rather than crashing."""
    missing = tmp_path / "absent"
    monkeypatch.setenv("ROMARR_LOG_DIR", str(missing))
    get_settings.cache_clear()
    try:
        resp = await authed_client.get("/api/v3/system/log/file")
        assert resp.status_code == 200
        assert resp.json() == []
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_list_log_files_returns_metadata(
    authed_client: httpx.AsyncClient, log_dir: Path
) -> None:
    """Each file entry carries filename / lastWriteTime /
    contentsSize. Files are sorted newest-first."""
    a = log_dir / "romarr.log"
    a.write_text("hello\n")
    b = log_dir / "romarr.log.1"
    b.write_text("older\n")

    resp = await authed_client.get("/api/v3/system/log/file")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    names = {entry["filename"] for entry in body}
    assert names == {"romarr.log", "romarr.log.1"}
    for entry in body:
        assert "lastWriteTime" in entry
        assert "contentsSize" in entry
        assert isinstance(entry["contentsSize"], int)


# ---------------------------------------------------------------------------
# T039 — /file/{filename} — download
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_download_log_file_returns_bytes(
    authed_client: httpx.AsyncClient, log_dir: Path
) -> None:
    """A real file streams as text/plain with the expected
    body."""
    payload = "line1\nline2\nline3\n"
    (log_dir / "romarr.log").write_text(payload)

    resp = await authed_client.get(
        "/api/v3/system/log/file/romarr.log"
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    assert resp.text == payload


@pytest.mark.asyncio
async def test_download_unknown_file_returns_404(
    authed_client: httpx.AsyncClient, log_dir: Path
) -> None:
    resp = await authed_client.get(
        "/api/v3/system/log/file/missing.log"
    )
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "not_found"


def test_safe_log_path_rejects_traversal_directly(
    log_dir: Path,
) -> None:
    """Defense-in-depth unit test on the path resolver. URL
    normalization in the router layer already strips ``..``
    segments before they reach the handler, but if a future
    refactor passes a programmatic filename through, the
    resolver MUST reject any value that contains a separator
    or escapes ``log_dir``."""
    from fastapi import HTTPException

    from romarr.api.routers.log import _safe_log_path

    for sketchy in ("../etc/passwd", "..\\windows\\system32", ".env"):
        with pytest.raises(HTTPException) as exc_info:
            _safe_log_path(sketchy)
        assert exc_info.value.status_code == 400
        assert (
            exc_info.value.detail["errorCode"]  # type: ignore[index,call-overload]
            == "invalid_log_filename"
        )


@pytest.mark.asyncio
async def test_download_rejects_dotfile(
    authed_client: httpx.AsyncClient, log_dir: Path
) -> None:
    """Dotfile-prefixed names are rejected — defensive against
    e.g. ``.env`` accidentally falling under log_dir."""
    resp = await authed_client.get("/api/v3/system/log/file/.env")
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Auth gates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_files_requires_auth(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.get("/api/v3/system/log/file")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_paginated_log_requires_auth(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.get("/api/v3/system/log")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_download_log_requires_auth(
    api_client: httpx.AsyncClient,
) -> None:
    resp = await api_client.get(
        "/api/v3/system/log/file/anything.log"
    )
    assert resp.status_code == 401
