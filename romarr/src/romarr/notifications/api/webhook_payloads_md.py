"""Serve the webhook-payloads cross-walk doc as Markdown (T070).

The full FR-006a Sonarr v3 envelope contract lives in
``docs/api/notification/webhook-payloads.md``. The API exposes
that file at ``GET /api/v3/notification/webhook-payloads.md``
so the frontend's "configure webhook" UI can render the
cross-walk inline (and so external tooling has a stable URL to
link to).

The file is read once on app startup and cached at module
scope; reloading is unnecessary because the doc ships with the
binary.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, HTTPException, Response, status

router = APIRouter(
    prefix="/api/v3/notification", tags=["Notifications"]
)

# Walk up from this file: src/romarr/notifications/api/<this>
# → repo root, then into docs/. The check is intentionally
# pinned to the project layout — moving the doc requires
# updating this constant alongside.
_DOC_RELATIVE_PATH = Path(
    "docs/api/notification/webhook-payloads.md"
)


@lru_cache(maxsize=1)
def _doc_text() -> str:
    """Find and read the cross-walk markdown.

    Walks up from this file's parent until a directory contains
    the docs/ subtree, then reads the file. lru_cache(1) keeps
    the file content in memory after first load.
    """
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate = ancestor / _DOC_RELATIVE_PATH
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise FileNotFoundError(
        f"could not locate {_DOC_RELATIVE_PATH} relative to "
        f"{here}"
    )


@router.get("/webhook-payloads.md", response_class=Response)
async def webhook_payloads_md() -> Response:
    """Return the FR-006a cross-walk as ``text/markdown``."""
    try:
        body = _doc_text()
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="webhook-payloads doc unavailable",
        ) from exc
    return Response(content=body, media_type="text/markdown")


__all__ = ["router"]
