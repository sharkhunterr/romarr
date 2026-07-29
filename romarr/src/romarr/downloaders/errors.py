"""Structured error hierarchy for the download-clients feature.

Each implementation raises one of these typed errors; the
connectivity tester translates them to a flat
:class:`romarr.downloaders.types.ConnectivityTestResult` so the UI
never has to disambiguate via string-matching exception messages.
"""

from __future__ import annotations


class DownloaderError(RuntimeError):
    """Base class for every download-client-side failure.

    Never raised directly; always one of the concrete subclasses
    below. The connectivity tester uses :func:`isinstance` to fan
    out to the right ``error_code`` literal.
    """


class ConnectionError(DownloaderError):
    """Network-layer failure (DNS, refused, timeout) reaching the client."""


class AuthError(DownloaderError):
    """The client rejected our credentials (HTTP 401/403, invalid api_key)."""


class TLSError(DownloaderError):
    """TLS handshake failed (bad cert, expired, hostname mismatch).

    Distinct from :class:`ConnectionError` so the operator UI can
    surface ``ssl_cert_validation`` knob suggestions.
    """


class VersionError(DownloaderError):
    """The client is older than the supported floor.

    Currently raised by qBittorrent when ``webapiVersion`` < 2.8.3
    (qBittorrent < 4.4.0) per FR-005a / CL003.
    """


class CategoryWarning(DownloaderError):  # noqa: N818 — domain-specific name (FR-011)
    """Non-blocking — the ``romarr`` category is missing.

    Raised internally by an implementation's connectivity check when
    the per-client category creation cannot be performed automatically
    (SAB requires a manual category add). Translated into a
    :class:`~romarr.downloaders.types.ConnectivityWarning` with
    ``code='category_missing'`` and ``ok=True`` (FR-011).
    """


class NoEligibleClientError(DownloaderError):
    """Routing returned ``chosen_via == 'no_eligible_client'``.

    Raised by the wrapper that consumes a
    :class:`~romarr.downloaders.types.RoutingDecision` when the
    grab cannot proceed (FR-016 / SC-005).
    """


class NeedsMagnetClientError(DownloaderError):
    """``grabarr_direct`` resolved a candidate to a magnet URI but
    can't handle magnets itself. The dispatcher catches this and
    re-routes the dispatch to the next torrent-capable client (the
    operator's qBittorrent, typically), passing the magnet through
    as a :class:`~romarr.downloaders.types.TorrentMagnet` source.

    Carries the resolved ``magnet_uri`` so the dispatcher can build
    the new source without re-hitting ``/resolve``. ``internal_file_path``
    (optional) is the specific file path INSIDE a bundle meta-torrent
    (Minerva / …) — the dispatcher forwards it on the
    ``TorrentMagnet.internal_file_path`` field so qBit can prioritise
    the right file via ``filePrio`` after metadata comes in.
    """

    def __init__(
        self, magnet_uri: str, internal_file_path: str | None = None
    ) -> None:
        super().__init__(
            "grabarr_direct resolved to torrent_magnet — needs a "
            "magnet-capable client (qBittorrent)"
        )
        self.magnet_uri = magnet_uri
        self.internal_file_path = internal_file_path


__all__ = [
    "AuthError",
    "CategoryWarning",
    "ConnectionError",
    "DownloaderError",
    "NeedsMagnetClientError",
    "NoEligibleClientError",
    "TLSError",
    "VersionError",
]
