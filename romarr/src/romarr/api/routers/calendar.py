"""Calendar endpoint (T059, MVP — preservation events).

Spec 013 ships a Sonarr-shape `/api/v3/calendar` surface for
showing upcoming preservation events (community-curated upcoming
ROM hacks / homebrew / translations on a given platform). The
MVP returns an empty list with the documented schema; data
sources land later (the spec calls them "TBD").

The endpoint accepts the canonical start / end ISO-8601 query
params so the frontend can drive a month-view date picker
against a stable contract — switching to a real data source
later won't break the JSON shape.

Read-only via :func:`require_readonly`. Authenticated callers
of any role can browse the calendar.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

from romarr.api.dependencies import require_readonly
from romarr.auth import Principal

router = APIRouter(prefix="/api/v3/calendar", tags=["Calendar"])


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


class CalendarEvent(BaseModel):
    """One preservation event on the calendar.

    Modeled on Sonarr's `/calendar` shape but adapted for ROM
    preservation: each event is a community-curated upcoming
    release (ROM hack, homebrew, fan translation). The
    ``platformId`` is nullable — multi-platform events (e.g. a
    cross-platform homebrew port) carry ``null`` here.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )

    id: int
    title: str
    platform_id: int | None = Field(alias="platformId", default=None)
    kind: str = Field(
        description=(
            "Event kind — one of 'rom-hack', 'homebrew', "
            "'translation', 'reissue'."
        )
    )
    release_date: str = Field(
        alias="releaseDate",
        description="Local-date YYYY-MM-DD form, no timezone.",
    )
    release_date_utc: datetime = Field(alias="releaseDateUtc")
    monitored: bool
    summary: str | None = None
    source_url: str | None = Field(alias="sourceUrl", default=None)


# ---------------------------------------------------------------------------
# GET /api/v3/calendar
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=list[CalendarEvent],
    response_model_by_alias=True,
    summary=(
        "Preservation events between start (inclusive) and end "
        "(exclusive). MVP returns []; data sources land later."
    ),
)
async def list_calendar(
    _principal: Annotated[Principal, Depends(require_readonly)],
    start: Annotated[
        datetime,
        Query(
            description=(
                "ISO-8601 datetime; only events with "
                "``releaseDateUtc >= start`` are returned."
            ),
        ),
    ],
    end: Annotated[
        datetime,
        Query(
            description=(
                "ISO-8601 datetime; only events with "
                "``releaseDateUtc < end`` are returned."
            ),
        ),
    ],
) -> list[CalendarEvent]:
    """MVP — returns the empty list. The shape is pinned so the
    frontend month-view can wire against it now and a future
    data-source slice will populate without churn."""
    if end <= start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": "end must be strictly greater than start",
                "errorCode": "calendar_invalid_range",
            },
        )
    return []


__all__ = ["router"]
