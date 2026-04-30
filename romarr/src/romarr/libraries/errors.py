"""Domain errors for the libraries subsystem (spec 009).

Domain-specific names per Article XII; the ``noqa: N818`` markers
acknowledge that these are exceptions whose names intentionally
diverge from the ``…Error`` ruff convention because they read more
naturally in the surface they're raised in.
"""

from __future__ import annotations


class LibraryError(Exception):
    """Base class for every domain-level library failure."""


class PathUnwritable(LibraryError):  # noqa: N818 — domain-specific name (FR-004)
    """Raised when ``library.path`` either does not exist or cannot
    be written to. Surfaced at save-time validation (FR-004) and
    again from the heartbeat loop, which flips ``library.status =
    'unavailable'`` on this error."""


class NoEligibleLibrary(LibraryError):  # noqa: N818 — domain-specific name
    """The router could not pick a library for the file (no library
    accepts the platform, or every eligible library is unavailable).

    Carries a ``reason`` string the router records on the
    ``unidentified_dump`` row's ``rejection_reason``."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class LibraryUnavailable(LibraryError):  # noqa: N818 — domain-specific name
    """The chosen library is currently unreachable (mountpoint gone,
    permission revoked, free space below ``min_disk_free_gb``).

    The scan / import pipeline parks the file for retry rather than
    failing it permanently."""


class DiskFullError(LibraryUnavailable):
    """Specialisation of :class:`LibraryUnavailable` for the disk-full
    case — distinct so the notification consumer can render a
    different message."""


class ExporterError(LibraryError):
    """An exporter run failed. Carries a ``cause`` describing the
    underlying problem (network, schema mismatch, lock contention)."""

    def __init__(self, name: str, cause: str) -> None:
        super().__init__(f"{name} exporter: {cause}")
        self.name = name
        self.cause = cause
