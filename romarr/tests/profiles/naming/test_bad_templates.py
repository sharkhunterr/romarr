"""Bad-template rejection corpus (T045 / SC-005 — ≥10 rejections).

Every entry exercises a distinct rejection path at SAVE time
(``engine.validate(...)``) — no template should slip through to
the render hot-path with a forbidden expression.
"""

from __future__ import annotations

import pytest

from romarr.profiles.errors import (
    ProfileError,
    SandboxViolationError,
    TemplateSyntaxError,
    TemplateUnknownTokenError,
)
from romarr.profiles.naming import NamingTemplateEngine

_BAD_TEMPLATES: list[tuple[str, str, type[ProfileError]]] = [
    (
        "unterminated-expression",
        "{{ Game.Title",
        TemplateSyntaxError,
    ),
    (
        "missing-endif",
        "{% if Game.Title %}",
        TemplateSyntaxError,
    ),
    (
        "unknown-top-level-name",
        "{{ Unknown.X }}",
        TemplateUnknownTokenError,
    ),
    (
        "unknown-game-attribute",
        "{{ Game.Bogus }}",
        TemplateUnknownTokenError,
    ),
    (
        "class-attribute-escape",
        "{{ Release.__class__ }}",
        TemplateUnknownTokenError,
    ),
    (
        "globals-call-attempt",
        "{{ globals() }}",
        TemplateUnknownTokenError,
    ),
    (
        "open-call-attempt",
        "{{ open('/etc/passwd') }}",
        TemplateUnknownTokenError,
    ),
    (
        "forbidden-filter-length",
        "{{ Game.Title | length }}",
        SandboxViolationError,
    ),
    (
        "forbidden-filter-default",
        "{{ Game.Title | default('x') }}",
        SandboxViolationError,
    ),
    (
        "forbidden-filter-join",
        "{{ Release.Tags | join('+') }}",
        SandboxViolationError,
    ),
    (
        "method-call-attempt",
        "{{ Game.Title.upper() }}",
        SandboxViolationError,
    ),
    (
        "platform-unknown-attr",
        "{{ Platform.Bogus }}",
        TemplateUnknownTokenError,
    ),
    (
        "release-unknown-attr",
        "{{ Release.Forbidden }}",
        TemplateUnknownTokenError,
    ),
]


@pytest.mark.parametrize(
    ("template", "expected_error_cls"),
    [(template, cls) for _, template, cls in _BAD_TEMPLATES],
    ids=[label for label, _, _ in _BAD_TEMPLATES],
)
def test_bad_template_rejected_at_save(
    engine: NamingTemplateEngine,
    template: str,
    expected_error_cls: type[ProfileError],
) -> None:
    with pytest.raises(expected_error_cls):
        engine.validate(template)


def test_corpus_has_at_least_10_rejections() -> None:
    assert len(_BAD_TEMPLATES) >= 10
