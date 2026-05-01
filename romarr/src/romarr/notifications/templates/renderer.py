"""Sandboxed Jinja2 renderer for notification message bodies.

Spec 006's :class:`NamingTemplateEngine` is tightly bound to
file-naming with ``Game`` / ``Release`` / ``Dump`` / ``Platform``
token namespaces. Notifications need different namespaces per
event type (the OnGrab payload exposes ``indexer`` and
``download_client``; OnHealthIssue exposes ``component``,
``severity``, ``message``; etc.). Rather than stretch the
naming engine, this module wraps :class:`jinja2.sandbox.SandboxedEnvironment`
directly with the same defensive posture: strict-undefined,
no method calls on tokens, no filter chain expansion.

The validation surface is tied to the ``EventType``: a template
for ``OnImport`` MUST resolve only against
:class:`OnImportPayload`'s field set. We render a stub payload
at save-time to prove the template doesn't reference unknown
variables (FR-013, T031 bad-template corpus).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jinja2 import StrictUndefined, TemplateSyntaxError, UndefinedError
from jinja2.sandbox import ImmutableSandboxedEnvironment

from romarr.notifications.errors import TemplateError
from romarr.notifications.templates.defaults import DEFAULT_TEMPLATES
from romarr.notifications.types import EventType

if TYPE_CHECKING:
    from pydantic import BaseModel

    from romarr.notifications.models import Notification


# Map ``EventType`` to the Notification ORM column carrying the
# operator's optional override. ``None`` (default) falls back to
# :data:`DEFAULT_TEMPLATES`.
_EVENT_TO_FORMAT_FIELD: dict[EventType, str] = {
    EventType.ON_GRAB: "on_grab_format",
    EventType.ON_IMPORT: "on_import_format",
    EventType.ON_UPGRADE: "on_upgrade_format",
    EventType.ON_FAIL: "on_fail_format",
    EventType.ON_HEALTH_ISSUE: "on_health_issue_format",
    EventType.ON_DAT_UPDATE: "on_dat_update_format",
    EventType.ON_GAME_ADDED: "on_game_added_format",
}


def _make_env() -> ImmutableSandboxedEnvironment:
    """Build the project-wide notification renderer environment.

    Strict-undefined so referencing an unknown variable raises at
    render time (caught at save-time by the dry-run validator).
    Immutable sandbox blocks attribute mutation on token objects.
    """
    return ImmutableSandboxedEnvironment(
        autoescape=False,
        undefined=StrictUndefined,
        keep_trailing_newline=False,
    )


_ENV = _make_env()


def render_event(
    *,
    notification: Notification,
    payload: BaseModel,
) -> str:
    """Render the message body for ``payload`` using
    ``notification``'s configured template (or the default).

    The payload's ``event_type`` field selects which template
    column to look up on the notification row. The payload itself
    is unpacked into the template namespace via
    ``model_dump()`` so the template can access nested fields
    like ``{{ game.title }}`` / ``{{ dump.dat_verified }}``.

    Raises :class:`TemplateError` on any render-time failure
    (unknown variable, syntax error, sandbox violation). The
    dispatcher is expected to record the error on the
    ``notification.last_error`` audit column without halting the
    channel.
    """
    event_type = _event_type_of(payload)
    field_name = _EVENT_TO_FORMAT_FIELD[event_type]
    override = getattr(notification, field_name, None)
    template_str = override if override else DEFAULT_TEMPLATES[event_type]
    return _render(template_str, payload)


def validate_template(template_str: str, *, event_type: EventType) -> None:
    """Validate ``template_str`` at save-time against a stub
    payload for ``event_type``. Raises :class:`TemplateError` on
    any of:

      * Jinja syntax errors;
      * unknown variables (caught by ``StrictUndefined`` rendering
        against the stub);
      * forbidden filters / sandbox violations.

    Pure: no I/O, no side effects on the renderer's env.
    """
    stub = _stub_payload_for(event_type)
    try:
        _render(template_str, stub)
    except TemplateError:
        raise
    except Exception as exc:
        raise TemplateError(
            f"template validation failed for {event_type.value}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Internals


def _event_type_of(payload: BaseModel) -> EventType:
    raw = getattr(payload, "event_type", None)
    if isinstance(raw, EventType):
        return raw
    if isinstance(raw, str):
        return EventType(raw)
    raise TemplateError(
        f"payload {type(payload).__name__} has no event_type discriminator"
    )


def _render(template_str: str, payload: BaseModel) -> str:
    try:
        template = _ENV.from_string(template_str)
    except TemplateSyntaxError as exc:
        raise TemplateError(
            f"template syntax error: {exc.message}"
        ) from exc

    namespace = payload.model_dump(mode="python")
    try:
        return template.render(**namespace)
    except UndefinedError as exc:
        raise TemplateError(
            f"template references unknown variable: {exc.message}"
        ) from exc
    except TemplateSyntaxError as exc:
        raise TemplateError(
            f"template syntax error at render: {exc.message}"
        ) from exc
    except Exception as exc:
        raise TemplateError(
            f"template render failed: {exc.__class__.__name__}: {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Stub payloads for save-time validation


def _stub_payload_for(event_type: EventType) -> Any:
    """Build a minimal payload for save-time validation. Each
    payload type is constructable with default-value sentinels;
    we delegate to the type's ``model_construct`` so we don't
    have to mirror the full field set here.

    Imported lazily to avoid an import cycle with
    :mod:`romarr.notifications.types`.
    """
    from romarr.notifications.types import (
        DownloadClientRef,
        DumpRef,
        GameRef,
        IndexerRef,
        OnDatUpdatePayload,
        OnFailPayload,
        OnGameAddedPayload,
        OnGrabPayload,
        OnHealthIssuePayload,
        OnImportPayload,
        OnUpgradePayload,
        ReleaseRef,
    )

    game = GameRef(
        id=1, title="stub", platform_slug="stub", platform_name="stub"
    )
    release = ReleaseRef(id=1, name="stub")
    dump = DumpRef(path="/stub", dat_verified=False)
    indexer = IndexerRef(id=1, name="stub")
    download_client = DownloadClientRef(id=1, name="stub", type="qbittorrent")

    if event_type is EventType.ON_GRAB:
        return OnGrabPayload(
            game=game,
            release=release,
            indexer=indexer,
            download_client=download_client,
            download_id="stub",
        )
    if event_type is EventType.ON_IMPORT:
        return OnImportPayload(game=game, release=release, dump=dump)
    if event_type is EventType.ON_UPGRADE:
        return OnUpgradePayload(
            game=game,
            old_release=release,
            new_release=release,
            new_dump=dump,
        )
    if event_type is EventType.ON_FAIL:
        return OnFailPayload(release=release, error_msg="stub")
    if event_type is EventType.ON_HEALTH_ISSUE:
        from romarr.notifications.types import (
            ComponentCategory,
            HealthStatus,
        )

        return OnHealthIssuePayload(
            component="stub",
            category=ComponentCategory.DB,
            severity="warning",
            previous_status=HealthStatus.OK,
            current_status=HealthStatus.WARNING,
            message="stub",
        )
    if event_type is EventType.ON_DAT_UPDATE:
        return OnDatUpdatePayload(
            source="stub",
            platform="stub",
            entries_count=0,
            version="stub",
        )
    if event_type is EventType.ON_GAME_ADDED:
        return OnGameAddedPayload(game=game, library_id=1)
    raise TemplateError(
        f"unsupported event_type for validation: {event_type}"
    )


__all__ = ["render_event", "validate_template"]
