"""Apprise dispatcher wrapper (FR-002, FR-004).

Apprise is the unified backend for every operator-configured
notification target. The library is sync; we wrap each call in
:func:`asyncio.to_thread` so the dispatcher's async lifecycle
isn't blocked while a slow webhook target stalls.

The wrapper:

  * Decrypts the Fernet-wrapped Apprise URL on **every call**
    so plaintext never lives in memory between dispatches.
  * Validates the URL via ``Apprise.add(...)`` — a False return
    surfaces as :class:`AppriseInvalidUrl` with the
    Apprise-supplied error message.
  * Returns a structured :class:`AppriseSendResult` so the
    dispatcher can record success/failure on the
    ``notification.last_status`` audit column.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

import apprise

from romarr.metadata.encryption import decrypt
from romarr.notifications.errors import AppriseInvalidUrl

if TYPE_CHECKING:
    from romarr.notifications.models import Notification


@dataclass(frozen=True)
class AppriseSendResult:
    """Outcome of one :func:`send` call.

    ``success`` is True iff Apprise's ``notify`` returned True
    (Apprise itself sweeps every configured service and reports
    aggregate success). ``error_message`` is operator-facing on
    failure; otherwise None."""

    success: bool
    error_message: str | None = None


def _validate_url(url: str) -> apprise.Apprise:
    """Build an :class:`apprise.Apprise` object with ``url``
    attached. Raises :class:`AppriseInvalidUrl` when Apprise
    rejects the URL (typo, unknown scheme, malformed token)."""
    apobj = apprise.Apprise()
    if not apobj.add(url):
        raise AppriseInvalidUrl(
            f"apprise rejected URL (scheme/format invalid): "
            f"{url.split('://', 1)[0]}://..."
        )
    return apobj


async def send(
    *,
    notification: Notification,
    title: str,
    body: str,
    notify_type: str = "info",
) -> AppriseSendResult:
    """Dispatch a notification to the operator's configured
    Apprise target.

    Returns an :class:`AppriseSendResult` instead of raising on
    failure — the dispatcher records the result on the
    ``notification`` row's audit columns and keeps draining
    other events. The only exception path is
    :class:`AppriseInvalidUrl` for the validation-time misuse
    case (the URL was bad to begin with).
    """
    plaintext = decrypt(notification.apprise_url_encrypted).decode("utf-8")
    apobj = _validate_url(plaintext)

    try:
        result = await asyncio.to_thread(
            apobj.notify,
            body=body,
            title=title,
            notify_type=notify_type,
        )
    except Exception as exc:
        return AppriseSendResult(
            success=False,
            error_message=f"{exc.__class__.__name__}: {exc}",
        )

    if result:
        return AppriseSendResult(success=True)
    return AppriseSendResult(
        success=False,
        error_message="apprise returned a non-success aggregate",
    )


def validate_url(url: str) -> None:
    """Public alias of :func:`_validate_url` for the API layer.

    Raises :class:`AppriseInvalidUrl` if Apprise rejects the URL.
    The Apprise object built during validation is discarded — the
    API layer only needs the success/failure bit."""
    _validate_url(url)


__all__ = ["AppriseSendResult", "send", "validate_url"]
