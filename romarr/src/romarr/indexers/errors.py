"""Structured error hierarchy for the indexer feature.

  - :class:`IndexerError` — base class; never raised directly.
  - :class:`IndexerAuthError` — HTTP 401/403 from an indexer or app
    token mismatch on inbound Prowlarr-style calls.
  - :class:`IndexerProtocolError` — non-auth HTTP failure or
    malformed response that survives the parser's tolerance.
  - :class:`CircuitOpenError` — re-exported from the foundation
    breaker module so callers don't need a second import.
  - :class:`RateLimitDelayed` — informational marker (NOT raised);
    the registry uses it to log when a rate limiter delayed a call.
"""

from __future__ import annotations

# Re-export the foundation breaker exception so callers have a
# single import surface (Article III: no duplicated breaker library).
from romarr.identification.circuit_breaker import CircuitOpenError


class IndexerError(RuntimeError):
    """Base for every indexer-side failure."""


class IndexerAuthError(IndexerError):
    """The indexer rejected our credentials (401/403) or an inbound
    Prowlarr-style call carried a bad app token."""


class IndexerProtocolError(IndexerError):
    """The indexer returned a 5xx, malformed XML, or otherwise
    violated the Newznab/Torznab contract beyond what the parser
    can tolerate."""


class IndexerRateLimitedError(IndexerProtocolError):
    """Slice 404 — HTTP 429 from the indexer (or whatever it
    proxies, e.g. Prowlarr → upstream tracker). Carries the
    ``Retry-After`` hint (seconds) when the server provided one
    so the caller / UI can tell the operator when to try again.

    Subclasses ``IndexerProtocolError`` so existing
    ``except IndexerProtocolError`` blocks still catch it; new
    code that wants to short-circuit retries on rate-limit hits
    can type-narrow on this class specifically.
    """

    def __init__(self, message: str, *, retry_after_seconds: float | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class RateLimitDelayed(Exception):  # noqa: N818 — informational, not raised
    """Marker attached to log records when the rate limiter delayed
    a call. Never raised; callers structlog with ``extra={"delayed": True}``."""


__all__ = [
    "CircuitOpenError",
    "IndexerAuthError",
    "IndexerError",
    "IndexerProtocolError",
    "IndexerRateLimitedError",
    "RateLimitDelayed",
]
