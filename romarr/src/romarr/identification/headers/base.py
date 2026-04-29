"""Header-reader interface + result types.

A header reader inspects the leading bytes of a ROM file (or, in the
ISO9660 case, the volume metadata) and returns structured findings:

- ``status`` — ``OK`` / ``UNSUPPORTED`` / ``UNRECOGNIZED``
- ``platform_slug`` — best-guess platform; may be ``None`` when the
  reader is platform-agnostic and only emits structural findings.
- ``confidence`` — ``[0.0, 1.0]`` with the same scale as filename parsers
- ``data`` — reader-specific dict of extracted fields (mapper, region
  byte, in-cart serial, volume identifier, etc.)
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from enum import StrEnum
from os import PathLike
from pathlib import Path


class HeaderReadStatus(StrEnum):
    OK = "ok"
    UNSUPPORTED = "unsupported"  # FR-025 stubs raise this
    UNRECOGNIZED = "unrecognized"  # signature didn't match


@dataclass(frozen=True, slots=True)
class HeaderReadResult:
    """Structured output of a single header-reader invocation."""

    status: HeaderReadStatus
    platform_slug: str | None = None
    confidence: float = 0.0
    data: dict[str, str | int | bytes] = field(default_factory=dict)
    error_message: str | None = None


class UnsupportedPlatformError(NotImplementedError):
    """Raised by FR-025 stub readers (3DS, NDS, PSP, etc.)."""

    def __init__(self, platform_slug: str) -> None:
        super().__init__(
            f"header reader for platform {platform_slug!r} is not yet supported"
        )
        self.platform_slug = platform_slug


class BaseHeaderReader(abc.ABC):
    """Common contract for header readers."""

    #: The platform slug the reader claims when it produces an OK result.
    #: ``None`` for readers that disambiguate at runtime (e.g., ISO9660).
    platform_slug: str | None = None

    def read(self, path: str | PathLike[str]) -> HeaderReadResult:
        """Read header bytes from ``path`` and return a structured result."""
        return self._read_path(Path(path))

    @abc.abstractmethod
    def _read_path(self, path: Path) -> HeaderReadResult:  # pragma: no cover
        """Read from a concrete filesystem path."""
