"""Filter whitelist tests (T036)."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from romarr.profiles.errors import SandboxViolationError
from romarr.profiles.naming import NamingTemplateEngine

# ---------------------------------------------------------------------------
# Allowed filters — table-driven
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        ("{{ Game.Title | lower }}", "sonic the hedgehog"),
        ("{{ Game.Title | upper }}", "SONIC THE HEDGEHOG"),
        (
            "{{ Game.Title | replace('Sonic', 'Mario') }}",
            "Mario the Hedgehog",
        ),
        ("{{ Game.Title | truncate(5) }}", "Sonic"),
    ],
)
def test_allowed_filters_render(
    engine: NamingTemplateEngine,
    make_tokens: Callable[..., tuple[object, object, object, object]],
    template: str,
    expected: str,
) -> None:
    game, release, dump, platform = make_tokens()
    rendered = engine.render(
        template,
        game=game,
        release=release,
        dump=dump,
        platform=platform,
    )
    assert rendered == expected


# ---------------------------------------------------------------------------
# Forbidden Jinja built-in filters
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "filter_name",
    [
        "length",
        "default",
        "join",
        "string",
        "escape",
        "trim",
        "list",
    ],
)
def test_forbidden_jinja_builtin_filters_rejected(
    engine: NamingTemplateEngine, filter_name: str
) -> None:
    with pytest.raises(SandboxViolationError, match=filter_name):
        engine.validate("{{ Game.Title | " + filter_name + " }}")


def test_truncate_negative_returns_empty(
    engine: NamingTemplateEngine,
    make_tokens: Callable[..., tuple[object, object, object, object]],
) -> None:
    """Pragmatic: a negative truncate length returns the empty string
    rather than raising — operator typos shouldn't break import paths."""
    game, release, dump, platform = make_tokens()
    rendered = engine.render(
        "[{{ Game.Title | truncate(-1) }}]",
        game=game,
        release=release,
        dump=dump,
        platform=platform,
    )
    # postprocess collapses the now-empty bracketed group
    assert rendered == ""


def test_replace_with_filter_chain(
    engine: NamingTemplateEngine,
    make_tokens: Callable[..., tuple[object, object, object, object]],
) -> None:
    """Filter chains compose normally."""
    game, release, dump, platform = make_tokens()
    rendered = engine.render(
        "{{ Game.Title | replace(' ', '_') | lower }}",
        game=game,
        release=release,
        dump=dump,
        platform=platform,
    )
    assert rendered == "sonic_the_hedgehog"
