"""GET /api/v3/cover/{game_id} tests (slice 159).

The endpoint streams the bytes Romarr previously wrote under
``<data_dir>/covers/`` and tags the response with the
``immutable`` cache directive per spec 014 J. The path-traversal
guard ensures a hand-edited DB row pointing outside the covers
directory still 404s instead of leaking arbitrary files.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.config.settings import get_settings
from romarr.domain.models import Game, Platform
from tests.api.test_auth_endpoints import _seed_admin_user


@pytest.fixture
def cover_data_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point ROMARR_DATA_DIR at a tmp dir for the duration of
    the test so the covers directory is writable + isolated."""
    monkeypatch.setenv("ROMARR_DATA_DIR", str(tmp_path))
    monkeypatch.setenv(
        "ROMARR_AUTH_SECRET_KEY", "test-only-secret-key-do-not-use-in-prod"
    )
    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


@pytest.fixture
async def authed_cover_client(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> httpx.AsyncClient:
    await _seed_admin_user(api_engine)
    login = await api_client.post(
        "/api/v3/auth/login",
        json={"username": "alice", "password": "goodpassword"},
    )
    assert login.status_code == 204
    return api_client


_seed_counter = 0


async def _seed_game_with_cover(
    api_engine: AsyncEngine,
    *,
    cover_path: str | None,
) -> int:
    """Insert a Platform + Game with the given cover_path; return
    the Game id."""
    global _seed_counter
    _seed_counter += 1
    suffix = _seed_counter
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        platform = Platform(
            slug=f"cov-pl-{suffix}",
            name="MD",
            short_name="MD",
        )
        session.add(platform)
        await session.flush()
        game = Game(
            platform_id=platform.id,
            slug=f"cov-{suffix}",
            title=f"Game {suffix}",
            cover_path=cover_path,
        )
        session.add(game)
        await session.flush()
        await session.commit()
        return game.id


@pytest.mark.asyncio
async def test_get_cover_streams_bytes(
    authed_cover_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    cover_data_dir: Path,
) -> None:
    """A real cover file under ``<data_dir>/covers/`` is streamed
    back with the immutable cache header."""
    covers = cover_data_dir / "covers"
    covers.mkdir(parents=True, exist_ok=True)
    game_id = await _seed_game_with_cover(
        api_engine, cover_path=str(covers / "X.jpg")
    )
    cover_file = covers / f"{game_id}.jpg"
    cover_file.write_bytes(b"\xff\xd8\xff\xe0fake-jpeg")

    # Update the seeded cover_path to match the real file (we
    # used a placeholder above so the seeded id can drive the
    # filename).
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = await session.get(Game, game_id)
        assert row is not None
        row.cover_path = str(cover_file)
        await session.commit()

    resp = await authed_cover_client.get(f"/api/v3/cover/{game_id}")
    assert resp.status_code == 200
    assert resp.content == b"\xff\xd8\xff\xe0fake-jpeg"
    assert resp.headers["content-type"] == "image/jpeg"
    cache_control = resp.headers["cache-control"]
    assert "max-age=86400" in cache_control
    assert "immutable" in cache_control


@pytest.mark.asyncio
async def test_get_cover_404_when_game_missing(
    authed_cover_client: httpx.AsyncClient,
    cover_data_dir: Path,
) -> None:
    resp = await authed_cover_client.get("/api/v3/cover/99999")
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "game_not_found"


@pytest.mark.asyncio
async def test_get_cover_404_when_cover_path_null(
    authed_cover_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    cover_data_dir: Path,
) -> None:
    """Game exists but has no cover stored — distinct error code
    from the 'game not found' case."""
    game_id = await _seed_game_with_cover(api_engine, cover_path=None)
    resp = await authed_cover_client.get(f"/api/v3/cover/{game_id}")
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "no_cover"


@pytest.mark.asyncio
async def test_get_cover_404_when_file_missing_on_disk(
    authed_cover_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    cover_data_dir: Path,
) -> None:
    """DB has a path but the file's been removed — 404, no 500."""
    covers = cover_data_dir / "covers"
    covers.mkdir(parents=True, exist_ok=True)
    ghost = covers / "ghost.jpg"  # never created
    game_id = await _seed_game_with_cover(api_engine, cover_path=str(ghost))

    resp = await authed_cover_client.get(f"/api/v3/cover/{game_id}")
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "no_cover"


@pytest.mark.asyncio
async def test_get_cover_rejects_path_outside_covers_dir(
    authed_cover_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    cover_data_dir: Path,
    tmp_path: Path,
) -> None:
    """Belt-and-suspenders: a hand-edited DB row pointing
    outside the covers/ directory must NOT serve the file."""
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"top-secret")
    game_id = await _seed_game_with_cover(
        api_engine, cover_path=str(outside)
    )

    resp = await authed_cover_client.get(f"/api/v3/cover/{game_id}")
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "no_cover"


@pytest.mark.asyncio
async def test_get_cover_unauthenticated_401(
    api_client: httpx.AsyncClient,
    cover_data_dir: Path,
) -> None:
    resp = await api_client.get("/api/v3/cover/1")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_get_cover_serves_png_with_correct_media_type(
    authed_cover_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    cover_data_dir: Path,
) -> None:
    """Content-type follows the file extension Romarr wrote."""
    covers = cover_data_dir / "covers"
    covers.mkdir(parents=True, exist_ok=True)
    game_id = await _seed_game_with_cover(
        api_engine, cover_path=str(covers / "X.png")
    )
    cover_file = covers / f"{game_id}.png"
    cover_file.write_bytes(b"\x89PNGfake")

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = await session.get(Game, game_id)
        assert row is not None
        row.cover_path = str(cover_file)
        await session.commit()

    resp = await authed_cover_client.get(f"/api/v3/cover/{game_id}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"


# ---------------------------------------------------------------------------
# slice 160 — PUT/DELETE /api/v3/cover/{game_id}
# ---------------------------------------------------------------------------


def _patch_httpx_response(
    monkeypatch: pytest.MonkeyPatch,
    *,
    status_code: int,
    content: bytes = b"",
    content_type: str = "image/jpeg",
    raises: Exception | None = None,
) -> None:
    """Replace ``httpx.AsyncClient.get`` so the cover-override
    endpoint never hits the network in tests."""

    class _FakeResp:
        def __init__(self) -> None:
            self.status_code = status_code
            self.content = content
            self.headers = {"content-type": content_type}

    async def _fake_get(self, url, **kwargs):  # noqa: ARG001, ANN001
        if raises is not None:
            raise raises
        return _FakeResp()

    monkeypatch.setattr("httpx.AsyncClient.get", _fake_get)


@pytest.mark.asyncio
async def test_put_cover_writes_bytes_and_locks_field(
    authed_cover_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    cover_data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Happy path: 200 from upstream, jpeg bytes land on disk
    under <data_dir>/covers/, Game.cover_path updates, the
    cover field is added to locked_fields by default."""
    game_id = await _seed_game_with_cover(api_engine, cover_path=None)
    payload = b"\xff\xd8\xff\xe0fake-jpeg-bytes"
    _patch_httpx_response(
        monkeypatch,
        status_code=200,
        content=payload,
        content_type="image/jpeg",
    )

    resp = await authed_cover_client.put(
        f"/api/v3/cover/{game_id}",
        json={"url": "https://example.com/cover.jpg"},
    )
    assert resp.status_code == 200, resp.json()
    body = resp.json()
    expected_path = (cover_data_dir / "covers" / f"{game_id}.jpg").resolve()
    assert Path(body["cover_path"]).resolve() == expected_path
    assert "cover" in body["locked_fields"]
    assert expected_path.read_bytes() == payload


@pytest.mark.asyncio
async def test_put_cover_can_skip_auto_lock(
    authed_cover_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    cover_data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game_id = await _seed_game_with_cover(api_engine, cover_path=None)
    _patch_httpx_response(
        monkeypatch,
        status_code=200,
        content=b"\x89PNGfake",
        content_type="image/png",
    )

    resp = await authed_cover_client.put(
        f"/api/v3/cover/{game_id}",
        json={
            "url": "https://example.com/cover.png",
            "auto_lock": False,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["locked_fields"] == []


@pytest.mark.asyncio
async def test_put_cover_502_when_upstream_fails(
    authed_cover_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    cover_data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game_id = await _seed_game_with_cover(api_engine, cover_path=None)
    _patch_httpx_response(monkeypatch, status_code=500)

    resp = await authed_cover_client.put(
        f"/api/v3/cover/{game_id}",
        json={"url": "https://example.com/cover.jpg"},
    )
    assert resp.status_code == 502
    assert resp.json()["errorCode"] == "cover_fetch_failed"


@pytest.mark.asyncio
async def test_put_cover_502_on_network_error(
    authed_cover_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    cover_data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    game_id = await _seed_game_with_cover(api_engine, cover_path=None)
    _patch_httpx_response(
        monkeypatch,
        status_code=200,
        raises=httpx.ConnectError("boom"),
    )

    resp = await authed_cover_client.put(
        f"/api/v3/cover/{game_id}",
        json={"url": "https://example.com/cover.jpg"},
    )
    assert resp.status_code == 502
    assert resp.json()["errorCode"] == "cover_fetch_failed"


@pytest.mark.asyncio
async def test_put_cover_400_on_unsupported_content_type(
    authed_cover_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    cover_data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GIF / BMP / AVIF are not in the supported set."""
    game_id = await _seed_game_with_cover(api_engine, cover_path=None)
    _patch_httpx_response(
        monkeypatch,
        status_code=200,
        content=b"GIF89a-fake",
        content_type="image/gif",
    )

    resp = await authed_cover_client.put(
        f"/api/v3/cover/{game_id}",
        json={"url": "https://example.com/cover.gif"},
    )
    assert resp.status_code == 400
    assert resp.json()["errorCode"] == "unsupported_content_type"


@pytest.mark.asyncio
async def test_put_cover_400_when_too_large(
    authed_cover_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    cover_data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The 20 MB cap protects against a runaway URL paste."""
    game_id = await _seed_game_with_cover(api_engine, cover_path=None)
    payload = b"x" * (20 * 1024 * 1024 + 1)
    _patch_httpx_response(
        monkeypatch,
        status_code=200,
        content=payload,
        content_type="image/jpeg",
    )

    resp = await authed_cover_client.put(
        f"/api/v3/cover/{game_id}",
        json={"url": "https://example.com/huge.jpg"},
    )
    assert resp.status_code == 400
    assert resp.json()["errorCode"] == "cover_too_large"


@pytest.mark.asyncio
async def test_put_cover_404_when_game_missing(
    authed_cover_client: httpx.AsyncClient,
    cover_data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_httpx_response(
        monkeypatch, status_code=200, content=b"x", content_type="image/jpeg"
    )
    resp = await authed_cover_client.put(
        "/api/v3/cover/9999999",
        json={"url": "https://example.com/cover.jpg"},
    )
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "game_not_found"


@pytest.mark.asyncio
async def test_put_cover_rejects_non_http_url(
    authed_cover_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    cover_data_dir: Path,
) -> None:
    """Pydantic ``HttpUrl`` rejects ``file://`` etc. — never
    hits our handler."""
    game_id = await _seed_game_with_cover(api_engine, cover_path=None)
    resp = await authed_cover_client.put(
        f"/api/v3/cover/{game_id}",
        json={"url": "file:///etc/passwd"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_put_cover_unauthenticated_401(
    api_client: httpx.AsyncClient,
    cover_data_dir: Path,
) -> None:
    resp = await api_client.put(
        "/api/v3/cover/1",
        json={"url": "https://example.com/cover.jpg"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_delete_cover_removes_file_and_clears_path(
    authed_cover_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    cover_data_dir: Path,
) -> None:
    """Happy path: file goes away on disk and Game.cover_path
    becomes null."""
    covers = cover_data_dir / "covers"
    covers.mkdir(parents=True, exist_ok=True)
    game_id = await _seed_game_with_cover(
        api_engine, cover_path=str(covers / "X.jpg")
    )
    cover_file = covers / f"{game_id}.jpg"
    cover_file.write_bytes(b"\xff\xd8\xff\xe0jpg")

    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        row = await session.get(Game, game_id)
        assert row is not None
        row.cover_path = str(cover_file)
        await session.commit()

    resp = await authed_cover_client.delete(f"/api/v3/cover/{game_id}")
    assert resp.status_code == 200
    assert resp.json()["cover_path"] is None
    assert not cover_file.exists()


@pytest.mark.asyncio
async def test_delete_cover_idempotent_when_no_cover(
    authed_cover_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    cover_data_dir: Path,
) -> None:
    """Deleting when no cover is set is a no-op, not an error."""
    game_id = await _seed_game_with_cover(api_engine, cover_path=None)
    resp = await authed_cover_client.delete(f"/api/v3/cover/{game_id}")
    assert resp.status_code == 200
    assert resp.json()["cover_path"] is None


@pytest.mark.asyncio
async def test_delete_cover_skips_unlink_for_outside_paths(
    authed_cover_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    cover_data_dir: Path,
    tmp_path: Path,
) -> None:
    """A hand-edited row pointing outside covers/ must NOT be
    unlinked. The path is just cleared from the row."""
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"top-secret")
    game_id = await _seed_game_with_cover(
        api_engine, cover_path=str(outside)
    )

    resp = await authed_cover_client.delete(f"/api/v3/cover/{game_id}")
    assert resp.status_code == 200
    assert resp.json()["cover_path"] is None
    # The outside file is untouched.
    assert outside.read_bytes() == b"top-secret"


@pytest.mark.asyncio
async def test_delete_cover_404_when_game_missing(
    authed_cover_client: httpx.AsyncClient,
    cover_data_dir: Path,
) -> None:
    resp = await authed_cover_client.delete("/api/v3/cover/9999999")
    assert resp.status_code == 404
    assert resp.json()["errorCode"] == "game_not_found"


@pytest.mark.asyncio
async def test_delete_cover_unauthenticated_401(
    api_client: httpx.AsyncClient,
    cover_data_dir: Path,
) -> None:
    resp = await api_client.delete("/api/v3/cover/1")
    assert resp.status_code == 401
