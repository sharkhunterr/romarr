"""Prowlarr-side callback helper (T057).

When an operator deletes (or otherwise modifies) a Romarr-side indexer
that originated from Prowlarr, Romarr notifies the upstream Prowlarr
instance so its UI stays in sync.

Failures in the callback path log a warning but **never** propagate
upstream — the local mutation has already happened (FR-016 isolation).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

import httpx

from romarr.metadata.encryption import decrypt_secret

if TYPE_CHECKING:
    from romarr.indexers.models import Application

logger = logging.getLogger(__name__)

ChangeKind = Literal["indexer_deleted", "indexer_updated"]


async def notify_prowlarr_change(
    application: Application,
    *,
    change: ChangeKind,
    indexer_id: int,
    client: httpx.AsyncClient | None = None,
) -> bool:
    """Best-effort notification to a Prowlarr instance.

    Returns ``True`` on a 2xx response, ``False`` on any failure
    (the caller does not retry — Prowlarr's reconciliation loop will
    pick up the divergence on its next sync cycle).
    """
    api_key = decrypt_secret(application.prowlarr_api_key_encrypted)

    url = (
        f"{application.prowlarr_url.rstrip('/')}/api/v1/applications/notify"
    )
    payload = {
        "applicationId": application.id,
        "change": change,
        "indexerId": indexer_id,
    }
    headers = {"X-Api-Key": api_key, "Content-Type": "application/json"}

    own_client = client is None
    http = client or httpx.AsyncClient(timeout=5.0)
    try:
        response = await http.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        logger.warning(
            "indexers.prowlarr.callback_failed",
            extra={
                "application_id": application.id,
                "change": change,
                "indexer_id": indexer_id,
                "exc_type": type(exc).__name__,
                "detail": str(exc),
            },
        )
        return False
    finally:
        if own_client:
            await http.aclose()

    if 200 <= response.status_code < 300:
        return True
    logger.warning(
        "indexers.prowlarr.callback_bad_status",
        extra={
            "application_id": application.id,
            "change": change,
            "indexer_id": indexer_id,
            "status_code": response.status_code,
        },
    )
    return False


__all__ = ["ChangeKind", "notify_prowlarr_change"]
