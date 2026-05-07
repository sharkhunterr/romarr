"""Newznab/Torznab HTTP client (Phase 4).

End-to-end pipeline per outbound call:

    rate_limiter.acquire()
        → CircuitBreaker.call(
            tenacity AsyncRetrying(
                httpx.get(...)
            )
        )
        → parse_caps / parse_search

Failure modes:

  - HTTP 401 / 403       → :class:`IndexerAuthError` (NOT retried).
  - HTTP 5xx             → :class:`IndexerProtocolError`, retried by
                           tenacity, then trips the breaker.
  - Network / timeout    → :class:`IndexerProtocolError` (retried).
  - Malformed XML        → swallowed by the search method;
                           ``IndexerHealthIssue(category='parser')`` is
                           produced and the result list is empty.

Filename-fallback (FR-004): for any ``SearchResult`` field whose
``*_provenance`` is None after the parser ran (i.e. the indexer
didn't emit an extended attr for it), the client invokes the
foundation filename-parser dispatcher on the result's ``title`` and
fills in region / languages / revision / dump_tags / naming_convention
with ``provenance = FieldProvenance.FILENAME``.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from romarr.domain.enums import DumpStatus
from romarr.identification.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
)
from romarr.identification.parsers import default_dispatcher

_DUMP_UNKNOWN = DumpStatus.UNKNOWN
from romarr.indexers.errors import (
    IndexerAuthError,
    IndexerProtocolError,
)
from romarr.indexers.parser.caps import parse_caps
from romarr.indexers.parser.extended_attrs import (
    normalize_languages,
    normalize_region,
)
from romarr.indexers.parser.search import parse_search
from romarr.indexers.rate_limiter import RateLimiter
from romarr.indexers.types import (
    FieldProvenance,
    IndexerCapabilities,
    IndexerHealthIssue,
    SearchResult,
)

if TYPE_CHECKING:
    from collections.abc import Iterable

logger = logging.getLogger(__name__)


class NewznabClient:
    """Single-indexer Newznab/Torznab client.

    Built per-indexer by :class:`IndexerRegistry` (Phase 6); operators
    don't construct it directly.
    """

    def __init__(
        self,
        *,
        indexer_id: int,
        name: str,
        base_url: str,
        api_key: str | None,
        timeout_seconds: int = 30,
        rate_limiter: RateLimiter | None = None,
        breaker: CircuitBreaker | None = None,
        result_limit: int = 100,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.indexer_id = indexer_id
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.result_limit = result_limit
        self._rate_limiter = rate_limiter or RateLimiter(seconds=0)
        self._breaker = breaker or CircuitBreaker(f"indexers.{indexer_id}")
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds)
        )
        self._owns_client = client is None
        self._dispatcher = default_dispatcher()
        self._health_issues: list[IndexerHealthIssue] = []

    @property
    def health_issues(self) -> list[IndexerHealthIssue]:
        """Issues that have occurred since the client was built.

        Tests + the Phase 9 RSS sync read this to surface failures
        without needing to subclass the client.
        """
        return list(self._health_issues)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Public surface
    # ------------------------------------------------------------------

    async def caps(self) -> IndexerCapabilities:
        body = await self._call("caps", params={"t": "caps"})
        return parse_caps(body)

    async def search(
        self,
        query: str,
        *,
        categories: Iterable[int] | None = None,
    ) -> list[SearchResult]:
        params: dict[str, Any] = {"t": "search", "q": query}
        if categories:
            params["cat"] = ",".join(str(c) for c in categories)
        if self.result_limit:
            params["limit"] = str(self.result_limit)
        try:
            body = await self._call("search", params=params)
        except IndexerAuthError:
            raise
        except IndexerProtocolError:
            raise
        try:
            results = parse_search(body, indexer_id=self.indexer_id)
        except IndexerProtocolError as exc:
            self._record_issue("parser", str(exc))
            return []
        return [self._enrich_with_filename(r) for r in results]

    async def rss(
        self, *, categories: Iterable[int] | None = None
    ) -> list[SearchResult]:
        params: dict[str, Any] = {"t": "rss"}
        if categories:
            params["cat"] = ",".join(str(c) for c in categories)
        try:
            body = await self._call("rss", params=params)
        except IndexerProtocolError:
            raise
        try:
            results = parse_search(body, indexer_id=self.indexer_id)
        except IndexerProtocolError as exc:
            self._record_issue("parser", str(exc))
            return []
        return [self._enrich_with_filename(r) for r in results]

    # ------------------------------------------------------------------
    # Filename fallback (FR-004)
    # ------------------------------------------------------------------

    def _enrich_with_filename(self, item: SearchResult) -> SearchResult:
        """Fill any ``*_provenance is None`` field from the foundation
        filename parser dispatcher's interpretation of ``item.title``.

        The provenance stamp is :attr:`FieldProvenance.FILENAME` so the
        UI can show "this region was inferred from the filename, not
        from the indexer's extended attrs".
        """
        # If every fillable field already has provenance, skip the parse.
        if (
            item.region_provenance is not None
            and item.languages_provenance is not None
            and item.revision_provenance is not None
            and item.naming_convention_provenance is not None
        ):
            return item

        parsed = self._dispatcher.parse(item.title)

        update: dict[str, Any] = {}
        if item.region_provenance is None and parsed.regions:
            iso = normalize_region(parsed.regions[0])
            if iso is not None:
                update["region"] = iso
                update["region_provenance"] = FieldProvenance.FILENAME
        if item.languages_provenance is None and parsed.languages:
            langs = normalize_languages(list(parsed.languages))
            if langs:
                update["languages"] = langs
                update["languages_provenance"] = FieldProvenance.FILENAME
        if item.revision_provenance is None and parsed.revision:
            update["revision"] = parsed.revision
            update["revision_provenance"] = FieldProvenance.FILENAME
        if (
            item.naming_convention_provenance is None
            and parsed.confidence > 0
        ):
            update["naming_convention"] = parsed.convention
            update["naming_convention_provenance"] = FieldProvenance.FILENAME
        if item.dump_tags_provenance is None and parsed.tags:
            update["dump_tags"] = list(parsed.tags)
            update["dump_tags_provenance"] = FieldProvenance.FILENAME
        # Project the parser's bracketed-tag dump_status through to the
        # SearchResult so the pipeline's dump-profile gate can reject
        # ``[Hack]`` / ``[Proto]`` / ``[Demo]`` titles even when the
        # indexer didn't fill the extended attr — without this the
        # dump_status sat at UNKNOWN regardless of what the title said.
        if (
            item.dump_status_provenance is None
            and parsed.dump_status is not None
            and parsed.dump_status != _DUMP_UNKNOWN
        ):
            update["dump_status"] = parsed.dump_status
            update["dump_status_provenance"] = FieldProvenance.FILENAME

        if not update:
            return item
        return item.model_copy(update=update)

    # ------------------------------------------------------------------
    # HTTP + breaker chain
    # ------------------------------------------------------------------

    async def _call(self, operation: str, *, params: dict[str, Any]) -> bytes:
        """Issue one outbound request through rate limiter + breaker + retry."""
        merged: dict[str, Any] = dict(params)
        if self.api_key:
            merged["apikey"] = self.api_key

        delay = await self._rate_limiter.acquire()
        if delay > 0:
            logger.info(
                "indexers.client.rate_delay",
                extra={
                    "indexer_id": self.indexer_id,
                    "operation": operation,
                    "delay_seconds": delay,
                },
            )

        async def _attempt() -> bytes:
            return await self._do_request(merged)

        try:
            async for attempt in AsyncRetrying(
                reraise=True,
                stop=stop_after_attempt(3),
                wait=wait_exponential_jitter(initial=0.5, max=4.0),
                retry=retry_if_exception_type(IndexerProtocolError),
            ):
                with attempt:
                    return await self._breaker.call(_attempt)
        except CircuitOpenError as exc:
            self._record_issue("circuit_open", str(exc))
            raise
        except RetryError as exc:  # pragma: no cover — reraise=True covers
            raise IndexerProtocolError(
                "retry budget exhausted for indexer call"
            ) from exc
        # AsyncRetrying with reraise=True always returns or raises; this
        # line is unreachable in practice.
        raise RuntimeError("unreachable")  # pragma: no cover

    async def _do_request(self, params: dict[str, Any]) -> bytes:
        try:
            # Follow redirects: Prowlarr's per-indexer URLs sometimes
            # redirect (trailing slash, base-path setups) and the
            # apikey query param survives the redirect. Without
            # follow_redirects=True the 302 surfaces as "unexpected
            # HTTP 302" and the operator sees a confusing error
            # instead of the actual indexer caps.
            response = await self._client.get(
                f"{self.base_url}/api",
                params=params,
                follow_redirects=True,
            )
        except httpx.TimeoutException as exc:
            self._record_issue("connectivity", "timeout")
            raise IndexerProtocolError("indexer timeout") from exc
        except httpx.HTTPError as exc:
            self._record_issue("connectivity", str(exc))
            raise IndexerProtocolError(f"indexer network error: {exc}") from exc

        if response.status_code in (401, 403):
            self._record_issue("auth", f"HTTP {response.status_code}")
            raise IndexerAuthError(
                f"indexer rejected credentials (HTTP {response.status_code})"
            )
        if response.status_code >= 500:
            self._record_issue("protocol", f"HTTP {response.status_code}")
            raise IndexerProtocolError(
                f"indexer 5xx (HTTP {response.status_code})"
            )
        # follow_redirects=True hides 30x — but the *final* URL may
        # still be a login page (HTTP 200 + HTML body). Detect that
        # before the parser tries to extract <item>s from HTML and
        # silently returns an empty list. Common cause: the indexer
        # URL was pasted with ``/api`` already appended, doubling
        # the suffix and bouncing the request through Prowlarr's
        # auth gate.
        final_url = str(response.url).lower()
        if "login" in final_url or "signin" in final_url:
            self._record_issue("auth", "redirected to login")
            raise IndexerProtocolError(
                f"indexer redirected to {response.url} — apikey may be "
                "wrong or the URL has an extra ``/api`` suffix; the "
                "base URL should be the per-indexer root (e.g. "
                "``http://prowlarr:9696/5``)"
            )
        if response.status_code != 200:
            self._record_issue("protocol", f"HTTP {response.status_code}")
            raise IndexerProtocolError(
                f"indexer unexpected HTTP {response.status_code}"
            )
        return response.content

    def _record_issue(self, category: str, message: str) -> None:
        from romarr.indexers.types import HealthCategory  # local for typing

        # Cast through Any keeps the StrEnum-like Literal narrow.
        cat: Any = category
        self._health_issues.append(
            IndexerHealthIssue(
                indexer_id=self.indexer_id,
                indexer_name=self.name,
                category=cat,
                message=message,
                occurred_at=datetime.now(UTC),
            )
        )
        # Defensive: keep the warning here too so structured logging
        # picks it up even if the registry never reads health_issues.
        # ``message`` is a reserved LogRecord attribute, so we rename
        # the per-issue payload to ``detail``.
        logger.warning(
            "indexers.client.health_issue",
            extra={
                "indexer_id": self.indexer_id,
                "indexer_name": self.name,
                "category": category,
                "detail": message,
            },
        )
        # Silence unused import warning when running without
        # ``HealthCategory`` referenced.
        _ = HealthCategory


__all__ = ["NewznabClient"]
