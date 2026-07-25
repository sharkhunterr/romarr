"""Unit tests for the pack-source URL classifier + fetcher.

Fetcher tests hit a mocked httpx transport — no real network.
"""
from __future__ import annotations

import pytest

from romarr.platform_packs.remote import (
    RemotePackError,
    classify_url,
    fetch_from_source,
)


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://raw.githubusercontent.com/o/r/main/pack.yaml", "raw"),
        ("https://example.com/somewhere/thing.yml", "raw"),
        (
            "https://github.com/romarr-community/packs/tree/main/packs",
            "github_dir",
        ),
        (
            "https://api.github.com/repos/o/r/contents/packs?ref=main",
            "github_dir",
        ),
        # No YAML suffix, no /tree/ — defaults to raw (fetch will surface any error).
        ("https://example.com/whatever", "raw"),
    ],
)
def test_classify_url(url: str, expected: str) -> None:
    assert classify_url(url) == expected


@pytest.mark.asyncio
async def test_fetch_raw_returns_one_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        return httpx.Response(200, content=b"pack: hi")

    transport = httpx.MockTransport(handler)
    orig_init = httpx.AsyncClient.__init__

    def patched_init(self: httpx.AsyncClient, *a: object, **kw: object) -> None:  # noqa: ANN401
        kw.pop("transport", None)
        orig_init(self, *a, transport=transport, **kw)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    items = await fetch_from_source(
        "https://raw.example.com/some/pack.yaml", "raw"
    )
    assert len(items) == 1
    assert items[0].body == b"pack: hi"
    assert items[0].filename == "pack.yaml"


@pytest.mark.asyncio
async def test_fetch_github_dir_walks_yamls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import httpx

    LISTING = [
        {
            "type": "file",
            "name": "nes.yaml",
            "download_url": "https://raw.example.com/nes.yaml",
        },
        {
            "type": "file",
            "name": "README.md",
            "download_url": "https://raw.example.com/README.md",
        },
        {
            "type": "dir",
            "name": "subdir",
        },
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "api.github.com" in url:
            return httpx.Response(200, json=LISTING)
        if url.endswith("nes.yaml"):
            return httpx.Response(200, content=b"platforms: []")
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    orig_init = httpx.AsyncClient.__init__

    def patched_init(self: httpx.AsyncClient, *a: object, **kw: object) -> None:  # noqa: ANN401
        kw.pop("transport", None)
        orig_init(self, *a, transport=transport, **kw)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    items = await fetch_from_source(
        "https://github.com/o/r/tree/main/packs", "github_dir"
    )
    # Only the .yaml file made it through — README skipped, dir ignored.
    assert len(items) == 1
    assert items[0].filename == "nes.yaml"
    assert items[0].body == b"platforms: []"


@pytest.mark.asyncio
async def test_fetch_raw_raises_on_4xx(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="not found")

    transport = httpx.MockTransport(handler)
    orig_init = httpx.AsyncClient.__init__

    def patched_init(self: httpx.AsyncClient, *a: object, **kw: object) -> None:  # noqa: ANN401
        kw.pop("transport", None)
        orig_init(self, *a, transport=transport, **kw)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", patched_init)

    with pytest.raises(RemotePackError) as exc:
        await fetch_from_source("https://x.example/y.yaml", "raw")
    assert "404" in str(exc.value)
