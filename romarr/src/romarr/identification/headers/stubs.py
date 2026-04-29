"""Stub header readers for FR-025 platforms.

These readers exist so the upstream identifier can route around them
with a clear structured error rather than crashing or silently
defaulting. Each stub raises :class:`UnsupportedPlatformError` on
call, with the platform slug it would have classified.

When real implementations land in a later spec / slice, drop the
``StubReader`` registration and add a concrete ``BaseHeaderReader``
subclass.
"""

from __future__ import annotations

from pathlib import Path

from romarr.identification.headers.base import (
    BaseHeaderReader,
    HeaderReadResult,
    UnsupportedPlatformError,
)

UNSUPPORTED_SLUGS: tuple[str, ...] = (
    "3ds",
    "nds",
    "psp",
    "vita",
    "switch",
    "wii",
    "gamecube",
    "gba",
)


class StubReader(BaseHeaderReader):
    """A reader that raises ``UnsupportedPlatformError`` on any call.

    Tag the instance with the platform slug it would have read for so
    callers can present a useful diagnostic.
    """

    def __init__(self, platform_slug: str) -> None:
        if platform_slug not in UNSUPPORTED_SLUGS:
            raise ValueError(
                f"StubReader expects a known unsupported slug; got {platform_slug!r}"
            )
        self.platform_slug = platform_slug

    def _read_path(self, path: Path) -> HeaderReadResult:
        raise UnsupportedPlatformError(self.platform_slug or "<unknown>")
