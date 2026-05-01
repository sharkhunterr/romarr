"""Payload builders — map ``EventPayload``s to the two on-wire
shapes the dispatcher emits.

* :func:`build_apprise_message` returns the rendered string body
  Apprise sends through whatever transport the URL implies
  (Discord, Telegram, ntfy, …).
* :func:`build_sonarr_webhook_body` returns the Sonarr v3-shaped
  ``dict`` the webhook target POSTs as JSON. Notifiarr / Homepage
  / Tautulli consume Sonarr's keys verbatim, so Romarr remaps its
  Game/Release domain onto the TV-domain envelope per FR-006a.
  The mapping is intentionally one-way and lossy: consumers treat
  the keys as opaque structural contracts rather than as "this is
  TV metadata."

Both functions are pure — no I/O, no DB lookups, no clock reads.
The dispatcher pre-loads everything the payload needs before
calling.

The library path (``series.path`` in the Sonarr envelope) is not
part of any current ``EventPayload`` because the importer/search
layers don't pass library context down to the notification
emission point. Per FR-006a, missing string fields are emitted
as ``""`` rather than omitted, so the Sonarr schema validates
either way; if a future slice plumbs library context through,
this builder can read it without breaking the contract.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from romarr.notifications.templates.renderer import render_event
from romarr.notifications.types import (
    EventType,
    OnDatUpdatePayload,
    OnFailPayload,
    OnGameAddedPayload,
    OnGrabPayload,
    OnHealthIssuePayload,
    OnImportPayload,
    OnUpgradePayload,
)

if TYPE_CHECKING:
    from pydantic import BaseModel

    from romarr.notifications.models import Notification


# ---------------------------------------------------------------------------
# Apprise body — rendered Jinja string

def build_apprise_message(
    *,
    payload: BaseModel,
    notification: Notification,
) -> str:
    """Return the Apprise message body for ``payload`` rendered
    with ``notification``'s configured template (or the default).

    Thin wrapper over :func:`render_event` — kept as a separate
    public name so the dispatcher's call sites read symmetrically
    with :func:`build_sonarr_webhook_body`.
    """
    return render_event(notification=notification, payload=payload)


# ---------------------------------------------------------------------------
# Sonarr-webhook body — fixed-shape dict per FR-006a

def build_sonarr_webhook_body(
    *,
    payload: BaseModel,
    notification: Notification,
) -> dict[str, Any]:
    """Map ``payload`` to a Sonarr v3 webhook envelope.

    The envelope shape is the same regardless of payload type;
    only ``eventType`` and the populated branches differ. Empty
    fields are emitted as ``0`` (numeric Sonarr keys) or ``""``
    (string keys) — never omitted — so consumer schema
    validators always pass (FR-006a).

    ``notification`` is reserved for future use (e.g. webhook-
    specific overrides on the row) but currently unread; the body
    is fully derived from the payload.
    """
    event_type = _event_type_of(payload)
    if isinstance(payload, OnGrabPayload):
        return _build_grab(payload)
    if isinstance(payload, OnImportPayload):
        return _build_import(payload)
    if isinstance(payload, OnUpgradePayload):
        return _build_upgrade(payload)
    if isinstance(payload, OnFailPayload):
        return _build_fail(payload)
    if isinstance(payload, OnHealthIssuePayload):
        return _build_health(payload)
    if isinstance(payload, OnDatUpdatePayload):
        return _build_dat(payload)
    if isinstance(payload, OnGameAddedPayload):
        return _build_game_added(payload)
    raise ValueError(f"unsupported event payload: {event_type}")


# ---------------------------------------------------------------------------
# Per-event builders


def _build_grab(p: OnGrabPayload) -> dict[str, Any]:
    return {
        "eventType": EventType.ON_GRAB.value,
        "instanceName": "Romarr",
        "applicationUrl": "",
        "series": _series_from_game(p.game),
        "episodes": [_episode_from_release(p.release)],
        "release": {
            "releaseTitle": p.release.name,
            "indexer": p.indexer.name,
            "size": 0,
            "releaseGroup": "",
            "quality": _quality_from_release(p.release),
        },
        "downloadClient": p.download_client.name,
        "downloadClientType": p.download_client.type,
        "downloadId": p.download_id,
        "customFormatScore": p.custom_format_score,
    }


def _build_import(p: OnImportPayload) -> dict[str, Any]:
    return {
        # Sonarr's eventType for an import is "Download".
        "eventType": "Download",
        "instanceName": "Romarr",
        "applicationUrl": "",
        "series": _series_from_game(p.game),
        "episodes": [_episode_from_release(p.release)],
        "episodeFile": {
            "relativePath": p.dump.path,
            "path": p.dump.path,
            "quality": _quality_from_release(p.release),
            "size": p.dump.size_bytes or 0,
            "sceneName": "",
            "releaseGroup": "",
        },
        "isUpgrade": p.is_upgrade,
        "downloadClient": "",
        "downloadClientType": "",
        "downloadId": "",
    }


def _build_upgrade(p: OnUpgradePayload) -> dict[str, Any]:
    return {
        "eventType": "Download",
        "instanceName": "Romarr",
        "applicationUrl": "",
        "series": _series_from_game(p.game),
        "episodes": [_episode_from_release(p.new_release)],
        "episodeFile": {
            "relativePath": p.new_dump.path,
            "path": p.new_dump.path,
            "quality": _quality_from_release(p.new_release),
            "size": p.new_dump.size_bytes or 0,
            "sceneName": "",
            "releaseGroup": "",
        },
        "deletedFiles": [
            {
                "relativePath": "",
                "path": "",
                "quality": _quality_from_release(p.old_release),
                "size": 0,
                "sceneName": "",
                "releaseGroup": "",
            }
        ],
        "isUpgrade": True,
        "downloadClient": "",
        "downloadClientType": "",
        "downloadId": "",
    }


def _build_fail(p: OnFailPayload) -> dict[str, Any]:
    return {
        "eventType": "DownloadFailure",
        "instanceName": "Romarr",
        "applicationUrl": "",
        "release": {
            "releaseTitle": p.release.name,
            "indexer": "",
            "size": 0,
            "releaseGroup": "",
            "quality": _quality_from_release(p.release),
        },
        "errorMessage": p.error_msg,
        "downloadClient": (
            p.download_client.name if p.download_client else ""
        ),
        "downloadClientType": (
            p.download_client.type if p.download_client else ""
        ),
    }


def _build_health(p: OnHealthIssuePayload) -> dict[str, Any]:
    # Sonarr maps health to the "Health" eventType with a flat
    # body. We mirror that minimal shape.
    return {
        "eventType": "Health",
        "instanceName": "Romarr",
        "applicationUrl": "",
        "level": p.severity,  # warning | error | recovered
        "type": p.category.value,
        "message": p.message,
        "wikiUrl": "",
    }


def _build_dat(p: OnDatUpdatePayload) -> dict[str, Any]:
    # Sonarr has no native equivalent; we use the "ApplicationUpdate"
    # eventType slot to carry it — Notifiarr-style consumers ignore
    # unknown eventTypes anyway, but the envelope keys remain the
    # documented Sonarr ones so schema validators pass.
    return {
        "eventType": "ApplicationUpdate",
        "instanceName": "Romarr",
        "applicationUrl": "",
        "previousVersion": "",
        "newVersion": p.version,
        # Romarr-specific extension keys — namespaced so they
        # don't collide with future Sonarr additions.
        "romarr": {
            "datSource": p.source,
            "platform": p.platform,
            "entriesCount": p.entries_count,
        },
    }


def _build_game_added(p: OnGameAddedPayload) -> dict[str, Any]:
    return {
        "eventType": "SeriesAdd",
        "instanceName": "Romarr",
        "applicationUrl": "",
        "series": _series_from_game(p.game),
    }


# ---------------------------------------------------------------------------
# Sub-shape helpers — the FR-006a remap, isolated for clarity

def _series_from_game(game: Any) -> dict[str, Any]:
    """``series ↔ Game`` per FR-006a.

    NULL ``igdb_id`` falls back to ``0`` (Sonarr's tvdbId is a
    non-null int). ``series.path`` is left as ``""`` until a
    future slice plumbs library context down to the payload —
    the schema validates either way.
    """
    return {
        "id": game.id,
        "title": game.title,
        "titleSlug": game.platform_slug,
        "path": "",
        "tvdbId": game.igdb_id or 0,
        "tvMazeId": 0,
        "imdbId": "",
        "type": "standard",
        "year": 0,
        "tags": list(game.tags),
    }


def _episode_from_release(release: Any) -> dict[str, Any]:
    """``episodes[0] ↔ Release`` per FR-006a."""
    return {
        "id": release.id,
        "episodeNumber": release.id,
        "seasonNumber": 0,
        "title": release.name,
        "overview": "",
        "airDate": "",
        "airDateUtc": "",
        "qualityVersion": 0,
    }


def _quality_from_release(release: Any) -> dict[str, Any]:
    """``release.quality.quality.name ← release.format``.

    Romarr's ``Release`` doesn't currently carry a ``format``
    field — the closest equivalent is ``naming_convention`` (the
    DAT convention the release was identified against). We use
    that as the quality "name" so Sonarr-shaped consumers see a
    stable string per release; numeric ``id`` falls back to ``0``.
    """
    return {
        "quality": {
            "id": 0,
            "name": release.naming_convention or "unknown",
        },
        "revision": {
            "version": 1,
            "real": 0,
            "isRepack": False,
        },
    }


# ---------------------------------------------------------------------------
# Internals

def _event_type_of(payload: BaseModel) -> EventType:
    raw = getattr(payload, "event_type", None)
    if isinstance(raw, EventType):
        return raw
    if isinstance(raw, str):
        return EventType(raw)
    raise ValueError(
        f"payload {type(payload).__name__} has no event_type discriminator"
    )


__all__ = [
    "build_apprise_message",
    "build_sonarr_webhook_body",
]
