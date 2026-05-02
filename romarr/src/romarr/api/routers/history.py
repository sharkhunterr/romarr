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
from typing import Annotated, Any

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
    game_id: int | None = Field(alias="gameId", default=None)
    release_id: int | None = Field(alias="releaseId", default=None)
    successful: bool


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
        ImportHistory.game_id.label("game_id"),
        ImportHistory.release_id.label("release_id"),
        ImportHistory.success.label("successful"),
    )

    search_q = select(
        literal("search").label("event_type"),
        SearchHistory.id.label("id"),
        SearchHistory.started_at.label("date"),
        SearchHistory.game_id.label("game_id"),
        SearchHistory.release_id.label("release_id"),
        (SearchHistory.results_count > 0).label("successful"),
    )

    job_q = select(
        literal("job_run").label("event_type"),
        JobRun.id.label("id"),
        JobRun.started_at.label("date"),
        literal(None).label("game_id"),
        literal(None).label("release_id"),
        (JobRun.status == "success").label("successful"),
    )

    return import_q.union_all(search_q, job_q).subquery()


def _adapt(row: Any) -> HistoryEvent:
    """Adapt a Row from the union subquery into the envelope schema."""
    return HistoryEvent.model_validate(
        {
            "eventType": row.event_type,
            "id": row.id,
            "date": row.date,
            "gameId": row.game_id,
            "releaseId": row.release_id,
            "successful": bool(row.successful),
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
) -> PaginationEnvelope[HistoryEvent]:
    sq = _build_union_subquery()
    sortable_keys = {
        "date": sq.c.date,
        "event_type": sq.c.event_type,
        "id": sq.c.id,
    }
    return await paginate(
        session=db,
        base_query=select(sq),
        page_request=page_req,
        sortable_keys=sortable_keys,
        record_adapter=_adapt,
        scalars=False,
    )


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
    return await paginate(
        session=db,
        base_query=base,
        page_request=page_req,
        sortable_keys=sortable_keys,
        record_adapter=_adapt,
        scalars=False,
    )


__all__ = ["router"]
