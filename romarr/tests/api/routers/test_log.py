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
    """The endpoint returns the canonical pagination envelope,
    even when the in-memory ring buffer is empty (it may still
    hold app-startup records — we just check the shape)."""
    resp = await authed_client.get("/api/v3/system/log?page=1&pageSize=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 1
    assert body["pageSize"] == 10
    # totalRecords + records are buffer-driven; we just check
    # types so the contract holds even when the buffer has any
    # number of entries.
    assert isinstance(body["totalRecords"], int)
    assert isinstance(body["records"], list)


@pytest.mark.asyncio
async def test_log_entries_capture_emitted_records(
    authed_client: httpx.AsyncClient, log_dir: Path
) -> None:
    """Slice 391 — emitted log records surface on the endpoint
    via the in-memory ring buffer."""
    import logging

    from romarr.api.log_capture import LOG_BUFFER, install

    install()  # idempotent — the lifespan also calls this
    LOG_BUFFER.clear()
    test_logger = logging.getLogger("romarr.test_capture")
    test_logger.setLevel(logging.DEBUG)
    test_logger.error("boom: %s", "kapow")
    try:
        raise ValueError("explicit traceback")
    except ValueError:
        test_logger.exception("with_traceback")

    resp = await authed_client.get(
        "/api/v3/system/log?page=1&pageSize=50&logger=test_capture"
    )
    assert resp.status_code == 200
    body = resp.json()
    titles = [r["message"] for r in body["records"]]
    assert "boom: kapow" in titles
    assert "with_traceback" in titles
    # Newest first.
    assert body["records"][0]["message"] == "with_traceback"
    # Exception payload includes the traceback.
    excepted = next(
        r for r in body["records"] if r["message"] == "with_traceback"
    )
    assert "ValueError" in (excepted["exception"] or "")


@pytest.mark.asyncio
async def test_log_entries_level_filter(
    authed_client: httpx.AsyncClient, log_dir: Path
) -> None:
    """``?level=error`` keeps only ERROR + CRITICAL records."""
    import logging

    from romarr.api.log_capture import LOG_BUFFER, install

    install()
    LOG_BUFFER.clear()
    lg = logging.getLogger("romarr.test_capture_level")
    lg.setLevel(logging.DEBUG)
    lg.info("info-line")
    lg.error("error-line")

    resp = await authed_client.get(
        "/api/v3/system/log?page=1&pageSize=50&logger=test_capture_level&level=error"
    )
    assert resp.status_code == 200
    msgs = [r["message"] for r in resp.json()["records"]]
    assert msgs == ["error-line"]


@pytest.mark.asyncio
async def test_log_entries_invalid_level_400(
    authed_client: httpx.AsyncClient, log_dir: Path
) -> None:
    resp = await authed_client.get(
        "/api/v3/system/log?level=screaming"
    )
    assert resp.status_code == 400
    assert resp.json()["errorCode"] == "invalid_log_level"


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
