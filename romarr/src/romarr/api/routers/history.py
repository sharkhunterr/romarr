"""Unified history endpoint (T058, FR-014).

Spec 013 ships an `/api/v3/history` surface that aggregates the
three append-only audit tables into a single chronological feed:

  * :class:`romarr.importer.models.ImportHistory` — import-pipeline
    rounds (one row per ROM file processed).
  * :class:`romarr.search.models.SearchHistory` — search rounds
    (one row per indexer query).
  * :class:`romarr.tasks.models.JobRun` — scheduled / manual /
    event-driven job runs.

The Activity > History tab consumes this. Each entry projects
to a Sonarr-shape envelope:

  * ``eventType``    one of ``import`` / ``search`` / ``job_run``;
  * ``id``           per-source row id (NOT globally unique —
    the operator pairs ``(eventType, id)`` to drill in);
  * ``date``         ISO-8601 ``started_at`` — the canonical
    sort key;
  * ``gameId`` / ``releaseId``  nullable; absent for job_run
    rows that aren't release-scoped;
  * ``successful``   bool derived from each source's success
    semantics — ``ImportHistory.success`` directly,
    ``SearchHistory.results_count > 0``, ``JobRun.status =
    'success'``;
  * ``durationMs`` / ``correlationId`` / ``data`` — present
    only when the source row has them (job_run carries no
    correlation_id, etc.).

The endpoint pages over the UNION via the canonical
:class:`PaginationEnvelope`. Sortable keys: ``date`` (default
desc), ``event_type``, ``id``.

Companion `/since` endpoint filters on ``date >= since``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_readonly
from romarr.api.envelopes import PaginationEnvelope
from romarr.api.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PageRequest,
    page_request,
    paginate,
)
from romarr.auth import Principal
from romarr.domain.models import Game
from romarr.downloaders.models import DownloadClient
from romarr.importer.models import ImportHistory
from romarr.search.models import SearchHistory
from romarr.tasks.models import JobRun

router = APIRouter(prefix="/api/v3/history", tags=["History"])


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class HistoryEvent(BaseModel):
    """One unified history entry."""

    model_config = ConfigDict(populate_by_name=True)

    event_type: str = Field(alias="eventType")
    id: int
    date: datetime
    finished_at: datetime | None = Field(alias="finishedAt", default=None)
    duration_ms: int | None = Field(alias="durationMs", default=None)
    game_id: int | None = Field(alias="gameId", default=None)
    game_title: str | None = Field(alias="gameTitle", default=None)
    release_id: int | None = Field(alias="releaseId", default=None)
    successful: bool
    # ``summary`` is the search_type for search rows (``manual``
    # / ``rss`` / …), the source basename for import rows, or
    # the job runner name for job_run rows.
    summary: str | None = None
    # Why the event ended up ``successful=false`` (or a hint
    # for search rows that returned 0 candidates).
    reason: str | None = None
    # Search-row specifics — surfaced in the manual-grab line so
    # the operator sees what they queried and which indexer
    # answered.
    query: str | None = None
    chosen_indexer_guid: str | None = Field(
        alias="chosenIndexerGuid", default=None
    )
    score: int | None = None
    # Per-contribution score breakdown — present on search rows the
    # round wrote (RSS / manual / cutoff / missing). The detail
    # modal renders these as a small "+20 region · +100 verified
    # dump · -10 hack penalty" table so the operator can see WHY a
    # candidate scored what it did. Empty / null on import + job_run
    # rows.
    score_breakdown: list[dict[str, Any]] | None = Field(
        alias="scoreBreakdown", default=None
    )
    # Correlation id of the round (UUID) — same for every row a
    # single RSS sync / manual search emitted. The detail modal
    # uses this to fetch sibling rows (other indexer × game pairs
    # of the same round) so the operator sees the full picture
    # instead of one row in isolation.
    correlation_id: str | None = Field(
        alias="correlationId", default=None
    )
    # Free-form per-run counters the runner stashed via
    # :func:`report_progress` + the final ``JobResult.summary``.
    # ``RssSync`` ships ``indexers_succeeded`` / ``candidates`` /
    # ``grabs_dispatched`` / ``grabs_failed``; ``RescanLibrary``
    # ships ``total_items`` / ``matched`` / ``failed``; etc. The
    # detail sheet renders this as a small key/value table so a
    # job_run row carries its operator-relevant numbers instead
    # of just date + status.
    output_summary: dict[str, Any] | None = Field(
        alias="outputSummary", default=None
    )
    # Import-row specifics — where the file landed and how it
    # got picked up.
    dest_path: str | None = Field(alias="destPath", default=None)
    download_client_id: int | None = Field(
        alias="downloadClientId", default=None
    )
    download_client_name: str | None = Field(
        alias="downloadClientName", default=None
    )
    imported_via: str | None = Field(alias="importedVia", default=None)


def _build_union_subquery() -> Any:
    """Build the UNION-ALL projection across the three tables.

    Each branch contributes the same six columns so the union
    is type-clean across SQLite (lenient) and PostgreSQL
    (strict). ``successful`` is derived per-source:

      * ImportHistory: the ``success`` boolean directly.
      * SearchHistory: ``results_count > 0`` — a search with
        zero results is a "no match", semantically a failure
        for the operator's eyes.
      * JobRun: ``status = 'success'`` — partial / cancelled /
        failed all surface as ``successful=false``.
    """
    import_q = select(
        literal("import").label("event_type"),
        ImportHistory.id.label("id"),
        ImportHistory.started_at.label("date"),
        ImportHistory.finished_at.label("finished_at"),
        ImportHistory.duration_ms.label("duration_ms"),
        ImportHistory.game_id.label("game_id"),
        ImportHistory.release_id.label("release_id"),
        ImportHistory.success.label("successful"),
        ImportHistory.source_path.label("summary"),
        ImportHistory.error_msg.label("reason"),
        literal(None).label("query"),
        literal(None).label("chosen_indexer_guid"),
        literal(None).label("score"),
        literal(None).label("score_breakdown"),
        ImportHistory.correlation_id.label("correlation_id"),
        literal(None).label("output_summary"),
        ImportHistory.dest_path.label("dest_path"),
        ImportHistory.download_client_id.label("download_client_id"),
        ImportHistory.imported_via.label("imported_via"),
    )

    search_q = select(
        literal("search").label("event_type"),
        SearchHistory.id.label("id"),
        SearchHistory.started_at.label("date"),
        SearchHistory.finished_at.label("finished_at"),
        SearchHistory.duration_ms.label("duration_ms"),
        SearchHistory.game_id.label("game_id"),
        SearchHistory.release_id.label("release_id"),
        # A search row counts as successful when something was
        # routed (``results_count > 0``) AND no ``no_grab_reason``
        # was recorded. This catches the manual grab path that
        # records ``results_count=1`` even when dispatch failed
        # (no routable client) — which previously made the row
        # look green in history despite the queue never receiving
        # anything.
        (
            (SearchHistory.results_count > 0)
            & SearchHistory.no_grab_reason.is_(None)
        ).label("successful"),
        # Distinguish the search subtype (manual / rss / cutoff /
        # missing / auto_added) so the operator-facing label
        # reads "Manual grab" instead of a bare "Search".
        SearchHistory.search_type.label("summary"),
        SearchHistory.no_grab_reason.label("reason"),
        SearchHistory.query.label("query"),
        SearchHistory.chosen_indexer_guid.label("chosen_indexer_guid"),
        SearchHistory.score.label("score"),
        SearchHistory.score_breakdown.label("score_breakdown"),
        SearchHistory.correlation_id.label("correlation_id"),
        literal(None).label("output_summary"),
        literal(None).label("dest_path"),
        literal(None).label("download_client_id"),
        literal(None).label("imported_via"),
    )

    job_q = select(
        literal("job_run").label("event_type"),
        JobRun.id.label("id"),
        JobRun.started_at.label("date"),
        JobRun.finished_at.label("finished_at"),
        JobRun.duration_ms.label("duration_ms"),
        literal(None).label("game_id"),
        literal(None).label("release_id"),
        (JobRun.status == "success").label("successful"),
        JobRun.job_id.label("summary"),
        JobRun.error_message.label("reason"),
        literal(None).label("query"),
        literal(None).label("chosen_indexer_guid"),
        literal(None).label("score"),
        literal(None).label("score_breakdown"),
        literal(None).label("correlation_id"),
        JobRun.output_summary.label("output_summary"),
        literal(None).label("dest_path"),
        literal(None).label("download_client_id"),
        literal(None).label("imported_via"),
    )

    return import_q.union_all(search_q, job_q).subquery()


async def _enrich_with_titles(
    db: AsyncSession, records: list[HistoryEvent]
) -> None:
    """Batch-fill ``game_title`` + ``download_client_name`` on a
    page of history events.

    The union subquery doesn't carry these strings (joining
    across three branches with different shapes is messy). After
    the page is selected we collect the distinct ids, run two
    short ``IN`` lookups, and stamp the names back onto the
    records — keeps the row count bounded by the page size and
    avoids the N+1 query story.
    """
    game_ids = {r.game_id for r in records if r.game_id is not None}
    client_ids = {
        r.download_client_id
        for r in records
        if r.download_client_id is not None
    }

    titles: dict[int, str] = {}
    if game_ids:
        rows = (
            await db.execute(
                select(Game.id, Game.title).where(Game.id.in_(game_ids))
            )
        ).all()
        titles = {gid: title for (gid, title) in rows}

    clients: dict[int, str] = {}
    if client_ids:
        rows = (
            await db.execute(
                select(DownloadClient.id, DownloadClient.name).where(
                    DownloadClient.id.in_(client_ids)
                )
            )
        ).all()
        clients = {cid: name for (cid, name) in rows}

    for r in records:
        if r.game_id is not None:
            r.game_title = titles.get(r.game_id)
        if r.download_client_id is not None:
            r.download_client_name = clients.get(r.download_client_id)


def _adapt(row: Any) -> HistoryEvent:
    """Adapt a Row from the union subquery into the envelope schema."""
    summary = getattr(row, "summary", None)
    # Import rows ship a ``source_path`` — keep the basename only so
    # the row stays readable on a phone screen.
    dest_path = getattr(row, "dest_path", None)
    if row.event_type == "import":
        from os.path import basename

        if summary:
            summary = basename(summary) or summary
        if dest_path:
            dest_path = basename(dest_path) or dest_path
    # ``score_breakdown`` is a JSON column on ``search_history``. When
    # we read it through the union subquery (which discards
    # column-level type metadata), SQLite returns the raw stored
    # string instead of letting SQLAlchemy's JSON type deserialize.
    # Decode it here so Pydantic gets the structured list it expects.
    raw_breakdown = getattr(row, "score_breakdown", None)
    score_breakdown: list[dict[str, Any]] | None = None
    if raw_breakdown is None:
        score_breakdown = None
    elif isinstance(raw_breakdown, list):
        score_breakdown = raw_breakdown
    elif isinstance(raw_breakdown, str):
        import json as _json

        try:
            parsed = _json.loads(raw_breakdown)
        except ValueError:
            parsed = None
        score_breakdown = parsed if isinstance(parsed, list) else None
    # Same SQLite-JSON-as-string story for ``output_summary`` on
    # the job_run branch — UNION discards column-type metadata so
    # we re-decode manually.
    raw_summary = getattr(row, "output_summary", None)
    output_summary: dict[str, Any] | None = None
    if raw_summary is None:
        output_summary = None
    elif isinstance(raw_summary, dict):
        output_summary = raw_summary
    elif isinstance(raw_summary, str):
        import json as _json

        try:
            parsed = _json.loads(raw_summary)
        except ValueError:
            parsed = None
        output_summary = parsed if isinstance(parsed, dict) else None
    return HistoryEvent.model_validate(
        {
            "eventType": row.event_type,
            "id": row.id,
            "date": row.date,
            "finishedAt": getattr(row, "finished_at", None),
            "durationMs": getattr(row, "duration_ms", None),
            "gameId": row.game_id,
            "releaseId": row.release_id,
            "successful": bool(row.successful),
            "summary": summary,
            "reason": getattr(row, "reason", None),
            "query": getattr(row, "query", None),
            "chosenIndexerGuid": getattr(row, "chosen_indexer_guid", None),
            "score": getattr(row, "score", None),
            "scoreBreakdown": score_breakdown,
            "correlationId": getattr(row, "correlation_id", None),
            "outputSummary": output_summary,
            "destPath": dest_path,
            "downloadClientId": getattr(row, "download_client_id", None),
            "importedVia": getattr(row, "imported_via", None),
        }
    )


# ---------------------------------------------------------------------------
# GET /api/v3/history
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=PaginationEnvelope[HistoryEvent],
    response_model_by_alias=True,
    summary=(
        "Unified history: import / search / job_run rows merged "
        "and paginated chronologically."
    ),
)
async def list_history(
    _principal: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page_req: Annotated[PageRequest, Depends(page_request)],
    game_id: Annotated[
        int | None,
        Query(
            alias="gameId",
            ge=1,
            description=(
                "Filter to entries whose ``gameId`` matches. "
                "Job-run rows (which carry no game_id) are excluded "
                "when this is set."
            ),
        ),
    ] = None,
    event_type: Annotated[
        Literal["import", "search", "job_run"] | None,
        Query(
            alias="eventType",
            description=(
                "Filter to one of the three documented event types. "
                "Drives the Activity > History filter chips."
            ),
        ),
    ] = None,
    successful: Annotated[
        bool | None,
        Query(
            description=(
                "Filter on the derived ``successful`` flag — `true` for "
                "successes, `false` for the failure subset. The "
                "failure-only view is the most common operator workflow."
            ),
        ),
    ] = None,
    since: Annotated[
        datetime | None,
        Query(
            description=(
                "ISO-8601 datetime — only entries whose ``date`` is at "
                "or after this value are returned. Drives the Activity "
                "> History time-range chips."
            ),
        ),
    ] = None,
) -> PaginationEnvelope[HistoryEvent]:
    sq = _build_union_subquery()
    base_query = select(sq)
    if game_id is not None:
        base_query = base_query.where(sq.c.game_id == game_id)
    if event_type is not None:
        base_query = base_query.where(sq.c.event_type == event_type)
    if successful is not None:
        base_query = base_query.where(sq.c.successful.is_(successful))
    if since is not None:
        base_query = base_query.where(sq.c.date >= since)
    sortable_keys = {
        "date": sq.c.date,
        "event_type": sq.c.event_type,
        "id": sq.c.id,
    }
    envelope = await paginate(
        session=db,
        base_query=base_query,
        page_request=page_req,
        sortable_keys=sortable_keys,
        record_adapter=_adapt,
        scalars=False,
    )
    await _enrich_with_titles(db, envelope.records)
    return envelope


# ---------------------------------------------------------------------------
# GET /api/v3/history/since
# ---------------------------------------------------------------------------


@router.get(
    "/since",
    response_model=PaginationEnvelope[HistoryEvent],
    response_model_by_alias=True,
    summary=(
        "Unified history filtered to entries whose ``date`` is "
        ">= ``date`` query param."
    ),
)
async def list_history_since(
    _principal: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
    date: Annotated[
        datetime,
        Query(
            description=(
                "ISO-8601 datetime; only events with "
                "``date >= since`` are returned."
            ),
        ),
    ],
    page: Annotated[int, Query(ge=1)] = 1,
    pageSize: Annotated[  # noqa: N803
        int, Query(ge=1, le=MAX_PAGE_SIZE)
    ] = DEFAULT_PAGE_SIZE,
    sortKey: Annotated[str | None, Query()] = None,  # noqa: N803
    sortDirection: Annotated[  # noqa: N803
        str, Query(pattern=r"^(asc|desc)$")
    ] = "desc",
) -> PaginationEnvelope[HistoryEvent]:
    """Strict ``date >= since`` filter, paginated like the
    parent endpoint. Useful for "what happened since I last
    checked" polling without dragging the whole feed."""
    sq = _build_union_subquery()
    base = select(sq).where(sq.c.date >= date)
    sortable_keys = {
        "date": sq.c.date,
        "event_type": sq.c.event_type,
        "id": sq.c.id,
    }
    page_req = PageRequest.model_validate(
        {
            "page": page,
            "pageSize": pageSize,
            "sortKey": sortKey,
            "sortDirection": sortDirection,
        }
    )
    envelope = await paginate(
        session=db,
        base_query=base,
        page_request=page_req,
        sortable_keys=sortable_keys,
        record_adapter=_adapt,
        scalars=False,
    )
    await _enrich_with_titles(db, envelope.records)
    return envelope


__all__ = ["router"]
