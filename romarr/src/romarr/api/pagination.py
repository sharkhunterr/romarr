"""Canonical pagination helper (T016, FR-007 / FR-008 / FR-009).

Used by every list endpoint in the project. Three concerns
collapse into one helper:

  1. **Parameter parsing**: ``?page``, ``?pageSize``, ``?sortKey``,
     ``?sortDirection`` arrive on the URL with documented bounds.
     :class:`PageRequest` is a FastAPI dependency that validates
     them and provides defaults.
  2. **sortKey whitelisting**: invalid sort keys raise HTTP 400
     with the canonical ``ErrorEnvelope`` (FR-008). The endpoint
     declares its allowed keys in ``sortable_keys``; everything
     else trips the gate at parse time.
  3. **pageSize capping**: requests for more than 1000 rows are
     silently capped (FR-009). The cap is the ``Field(le=1000)``
     constraint on :class:`PageRequest.page_size`.

The :func:`paginate` function applies these to a SQLAlchemy
``select`` statement and returns the rendered
:class:`PaginationEnvelope`. Endpoints stay thin — they declare
their `sortable_keys` and pass through.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.envelopes import PaginationEnvelope, SortDirection

DEFAULT_PAGE_SIZE: int = 50
"""Default rows per page when the caller doesn't specify."""


MAX_PAGE_SIZE: int = 1000
"""Spec FR-009: hard ceiling. Higher values silently cap."""


class PageRequest(BaseModel):
    """Validated query parameters for a list endpoint."""

    model_config = ConfigDict(frozen=True)

    page: int = Field(default=1, ge=1)
    page_size: int = Field(
        default=DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        alias="pageSize",
    )
    sort_key: str | None = Field(default=None, alias="sortKey")
    sort_direction: SortDirection = Field(
        default="asc", alias="sortDirection"
    )


# ---------------------------------------------------------------------------
# FastAPI dependency


async def page_request(
    page: Annotated[int, Query(ge=1)] = 1,
    pageSize: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,  # noqa: N803
    sortKey: Annotated[str | None, Query()] = None,  # noqa: N803
    sortDirection: Annotated[SortDirection, Query()] = "asc",  # noqa: N803
) -> PageRequest:
    """FastAPI dependency that parses the canonical query
    parameters. ``pageSize > MAX_PAGE_SIZE`` returns 422 via the
    Pydantic constraint — endpoints that prefer the silent-cap
    behaviour should accept the raw value and call
    :func:`clamp_page_size` themselves before passing in."""
    return PageRequest(
        page=page,
        pageSize=pageSize,
        sortKey=sortKey,
        sortDirection=sortDirection,
    )


def clamp_page_size(raw: int) -> int:
    """Silent-cap form for endpoints that want FR-009's
    'returns 1000 instead of 422' semantics. The
    :class:`PageRequest` validator throws on overflow; this is
    the alternative path."""
    if raw < 1:
        return 1
    if raw > MAX_PAGE_SIZE:
        return MAX_PAGE_SIZE
    return raw


# ---------------------------------------------------------------------------
# paginate() — the main helper


async def paginate(
    *,
    session: AsyncSession,
    base_query: Select[Any],
    page_request: PageRequest,
    sortable_keys: dict[str, Any],
    record_adapter: Any,
    scalars: bool = True,
) -> PaginationEnvelope[Any]:
    """Apply pagination + sort to ``base_query`` and return the
    canonical envelope.

    ``sortable_keys`` is a dict mapping operator-facing names
    (``"id"``, ``"created_at"``, etc.) to SQLAlchemy column
    expressions. When the caller's ``sortKey`` isn't in the
    dict, ``HTTPException(400)`` fires with
    ``errorCode="invalid_sort_key"``.

    ``record_adapter`` is the row → Pydantic-Read converter
    (each endpoint already has one — e.g. ``IndexerRead.from_orm`` /
    ``NotificationRead.from_orm_row``). The helper applies it to
    every fetched row.

    ``scalars`` (default True) controls how rows are extracted.
    For ORM-mapped queries (``select(Foo)``), the result of
    ``.scalars().all()`` is a list of ``Foo`` instances — the
    common case. For projection queries (``select(literal(...),
    table.c.x, ...)`` and especially ``UNION`` subqueries), pass
    ``scalars=False`` so the helper returns full ``Row`` objects
    whose columns are addressable as attributes.

    The total-count query runs alongside the slice query; the
    envelope's ``totalRecords`` field reflects the unfiltered
    count for the caller's filters (filters are part of
    ``base_query``).
    """
    sort_key = page_request.sort_key
    if sort_key is None:
        # Endpoint default — first key in the sortable map.
        sort_key = next(iter(sortable_keys))

    if sort_key not in sortable_keys:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": (
                    f"unknown sortKey: {sort_key!r}. "
                    f"Allowed: {sorted(sortable_keys)}"
                ),
                "errorCode": "invalid_sort_key",
            },
        )

    sort_expr = sortable_keys[sort_key]
    direction = (
        asc(sort_expr)
        if page_request.sort_direction == "asc"
        else desc(sort_expr)
    )

    # Total count (without paging).
    count_query = select(func.count()).select_from(base_query.subquery())
    total_records = (await session.execute(count_query)).scalar_one()

    # Slice.
    paged = (
        base_query.order_by(direction)
        .offset((page_request.page - 1) * page_request.page_size)
        .limit(page_request.page_size)
    )
    result = await session.execute(paged)
    rows = result.scalars().all() if scalars else result.all()
    records = [record_adapter(row) for row in rows]

    return PaginationEnvelope(
        page=page_request.page,
        page_size=page_request.page_size,
        sort_key=sort_key,
        sort_direction=page_request.sort_direction,
        total_records=int(total_records),
        records=records,
    )


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "PageRequest",
    "clamp_page_size",
    "page_request",
    "paginate",
]
