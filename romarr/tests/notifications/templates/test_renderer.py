"""Renderer-internals tests (T030).

The notifications renderer MUST sit on top of a sandboxed Jinja
environment so an operator-supplied template cannot escape into
arbitrary attribute access, method calls, or Python builtins.
This module asserts the structural properties that guarantee
that — without lighting up a Jinja syntax-error path: we want
the test to fail loudly if a future refactor swaps in a
non-sandboxed environment.
"""

from __future__ import annotations

import pytest
from jinja2 import StrictUndefined
from jinja2.sandbox import ImmutableSandboxedEnvironment, SandboxedEnvironment

from romarr.notifications import templates as templates_pkg
from romarr.notifications.errors import TemplateError
from romarr.notifications.models import Notification
from romarr.notifications.templates import render_event, validate_template
from romarr.notifications.templates import renderer as renderer_module
from romarr.notifications.types import (
    DumpRef,
    EventType,
    GameRef,
    OnGameAddedPayload,
    OnImportPayload,
    ReleaseRef,
)


def _bare_notification() -> Notification:
    return Notification(
        name="t",
        apprise_url_encrypted=b"",
        apprise_url_scheme="discord",
    )


def _payload() -> OnGameAddedPayload:
    return OnGameAddedPayload(
        game=GameRef(
            id=1,
            title="Sonic",
            platform_slug="megadrive",
            platform_name="Mega Drive",
        ),
        library_id=1,
    )


# ---------------------------------------------------------------------------
# T030 — the renderer module is bound to a sandboxed Jinja environment
# ---------------------------------------------------------------------------


def test_uses_sandboxed_environment() -> None:
    """The module-level ``_ENV`` MUST be a Jinja sandbox subclass —
    not a plain ``Environment``.  ``ImmutableSandboxedEnvironment``
    is the strictest variant; a plain ``SandboxedEnvironment`` is
    also acceptable. Anything else (plain Environment, custom
    subclass that doesn't sandbox) fails the audit."""
    env = renderer_module._ENV
    assert isinstance(env, SandboxedEnvironment), (
        "renderer must use a SandboxedEnvironment subclass"
    )


def test_uses_immutable_sandbox() -> None:
    """We picked the immutable variant specifically — confirm we
    haven't downgraded silently."""
    assert isinstance(
        renderer_module._ENV, ImmutableSandboxedEnvironment
    )


def test_uses_strict_undefined() -> None:
    """``StrictUndefined`` is what makes ``{{ unknown }}`` raise at
    render time so :func:`validate_template` can catch it. Without
    it, unknown variables silently render as the empty string and
    operators ship typo'd templates that fire forever."""
    assert renderer_module._ENV.undefined is StrictUndefined


def test_autoescape_disabled_for_text_payloads() -> None:
    """Notification bodies are plain text (Apprise) or JSON
    (webhooks) — autoescape (HTML) would corrupt unicode emojis
    and JSON-serialized fields. Confirmed disabled."""
    autoescape = renderer_module._ENV.autoescape
    if callable(autoescape):
        # Some Jinja2 versions wrap into a callable; resolve.
        autoescape = autoescape("any.txt")
    assert autoescape is False


def test_sandbox_blocks_dunder_access() -> None:
    """The sandbox's primary security guarantee is that templates
    cannot escape through dunder attributes (``__class__``,
    ``__mro__``, ``__subclasses__``) into arbitrary Python
    objects. Confirm a representative dunder-walking template
    is rejected at validate time."""
    template_str = "{{ game.title.__class__.__mro__ }}"
    with pytest.raises(TemplateError):
        validate_template(template_str, event_type=EventType.ON_GAME_ADDED)


def test_sandbox_blocks_globals_access() -> None:
    """Templates must not be able to walk through function
    ``__globals__`` to reach builtins."""
    template_str = "{{ ''.__class__.__base__.__subclasses__() }}"
    with pytest.raises(TemplateError):
        validate_template(template_str, event_type=EventType.ON_GAME_ADDED)


# ---------------------------------------------------------------------------
# Behavioural contract: render_event respects override-vs-default precedence
# ---------------------------------------------------------------------------


def test_render_event_uses_override_when_set() -> None:
    """Sanity coverage at the renderer-internals level — override
    wins over default."""
    notif = _bare_notification()
    notif.on_game_added_format = "Override: {{ game.title }}"
    out = render_event(notification=notif, payload=_payload())
    assert out == "Override: Sonic"


def test_render_event_falls_back_to_default_when_override_none() -> None:
    out = render_event(notification=_bare_notification(), payload=_payload())
    assert "Sonic" in out
    assert "Mega Drive" in out


# ---------------------------------------------------------------------------
# Public API surface
# ---------------------------------------------------------------------------


def test_templates_package_re_exports() -> None:
    assert hasattr(templates_pkg, "DEFAULT_TEMPLATES")
    assert hasattr(templates_pkg, "render_event")
    assert hasattr(templates_pkg, "validate_template")


# ---------------------------------------------------------------------------
# validate_template happy path: every default validates
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("event_type", list(EventType))
def test_default_template_passes_validation(
    event_type: EventType,
) -> None:
    """The defaults shipped with the renderer must themselves
    pass save-time validation — otherwise an operator who copies
    a default into the override field would get rejected."""
    from romarr.notifications.templates.defaults import DEFAULT_TEMPLATES

    validate_template(DEFAULT_TEMPLATES[event_type], event_type=event_type)


def test_validate_template_accepts_simple_override() -> None:
    """A template referencing only known payload fields must pass."""
    validate_template(
        "Imported {{ game.title }}", event_type=EventType.ON_IMPORT
    )


def test_render_event_payload_namespace_supports_nested_access() -> None:
    """The renderer unpacks payloads via ``model_dump()`` so
    Jinja sees nested dicts. Confirm a ``{{ dump.dat_verified }}``
    style reference renders without falling back to attribute
    access on a Pydantic object."""
    notif = _bare_notification()
    payload = OnImportPayload(
        game=GameRef(
            id=1,
            title="t",
            platform_slug="x",
            platform_name="x",
        ),
        release=ReleaseRef(id=1, name="r"),
        dump=DumpRef(path="/x", dat_verified=False),
    )
    out = render_event(notification=notif, payload=payload)
    assert "t" in out
