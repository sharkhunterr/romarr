"""Sonarr-compat command endpoint — POST /api/v3/command.

Notifiarr / Recyclarr-style tools post to ``/api/v3/command`` with
a ``name`` field to trigger background search rounds. The endpoint
accepts the four documented Sonarr/Radarr names and dispatches
to the matching round.

For MVP only ``RssSync`` actually fires (the only operator-facing
round whose helper landed in the previous slice). The other three
return HTTP 202 with a structured "deferred" envelope so existing
*arr tooling sees the request acknowledged without an error.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.search._clients import make_indexer_client_factory
from romarr.search.rounds.rss import run_rss_sync
from romarr.search.schemas import CommandRequest

router = APIRouter(prefix="/api/v3/command", tags=["Search"])


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    summary=(
        "Sonarr-compat command dispatch (admin only). Accepts "
        "MissingSearch / CutoffSearch / RssSync / IndexerSearch."
    ),
)
async def dispatch_command(
    body: Annotated[CommandRequest, Body()],
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, Any]:
    if body.name == "RssSync":
        factory = make_indexer_client_factory(db)
        report = await run_rss_sync(
            session=db,
            client_factory=factory,
            indexer_ids=body.indexer_ids,
        )
        return {
            "name": body.name,
            "status": "completed",
            "correlation_id": str(report.correlation_id),
            "candidates": len(report.candidates),
            "grabs": len(report.grabs),
        }

    # MissingSearch / CutoffSearch / IndexerSearch land alongside
    # spec 008 + spec 009 query helpers; surface a deferred envelope
    # so existing *arr tooling sees the request acknowledged without
    # an HTTP error.
    return {
        "name": body.name,
        "status": "deferred",
        "details": (
            f"{body.name} requires the wanted-Game query helper from "
            "spec 008/009; tracked as a follow-up slice."
        ),
    }
