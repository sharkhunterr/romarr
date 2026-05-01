"""Bad-template corpus (T031, FR-013, SC-007).

Operator-supplied templates run through :func:`validate_template`
at save time so a typo or sandbox escape can never reach the
dispatcher. This module's corpus covers — at minimum — the ten
distinct rejection paths a hostile or fat-fingered template can
take. Every entry MUST raise :class:`TemplateError`.
"""

from __future__ import annotations

import pytest

from romarr.notifications.errors import TemplateError
from romarr.notifications.templates import validate_template
from romarr.notifications.types import EventType

# ---------------------------------------------------------------------------
# Corpus — (template, event_type, label)
#
# Each row pairs a template with the EventType it claims to be a
# format for; ``validate_template`` builds a stub payload of that
# event type and renders. Templates referencing variables that
# don't exist on the stub (or using forbidden constructs) raise.
# ---------------------------------------------------------------------------

BAD_TEMPLATES: list[tuple[str, EventType, str]] = [
    # 1. Unknown top-level variable
    (
        "Hello {{ nope }}",
        EventType.ON_IMPORT,
        "unknown-variable-top-level",
    ),
    # 2. Unknown nested attribute on a real namespace
    (
        "{{ game.does_not_exist }}",
        EventType.ON_IMPORT,
        "unknown-attribute-on-game",
    ),
    # 3. Reference to a namespace from a different event
    #    (``indexer`` exists on OnGrab, not on OnImport)
    (
        "{{ indexer.name }}",
        EventType.ON_IMPORT,
        "wrong-event-namespace",
    ),
    # 4. Jinja syntax error — unclosed expression
    (
        "Hello {{ game.title",
        EventType.ON_IMPORT,
        "unclosed-expression",
    ),
    # 5. Jinja syntax error — mismatched block
    (
        "{% if game.title %}hi",
        EventType.ON_IMPORT,
        "unclosed-block",
    ),
    # 6. Sandbox escape — class walk
    (
        "{{ ''.__class__.__mro__ }}",
        EventType.ON_GAME_ADDED,
        "sandbox-class-walk",
    ),
    # 7. Sandbox escape — reaching subclasses
    (
        "{{ ''.__class__.__base__.__subclasses__() }}",
        EventType.ON_GAME_ADDED,
        "sandbox-subclasses",
    ),
    # 8. Forbidden builtin reference (not in env globals)
    (
        "{{ open('/etc/passwd').read() }}",
        EventType.ON_IMPORT,
        "forbidden-builtin",
    ),
    # 9. Reference to ``payload`` namespace itself (we unpack
    #    fields, payload is not exposed under that name)
    (
        "{{ payload.event_type }}",
        EventType.ON_IMPORT,
        "no-payload-handle",
    ),
    # 10. Typo on a deeply nested field
    (
        "{{ dump.dat_verifed }}",  # missing 'i'
        EventType.ON_IMPORT,
        "typo-on-nested-field",
    ),
    # 11. Unknown filter
    (
        "{{ game.title | does_not_exist }}",
        EventType.ON_IMPORT,
        "unknown-filter",
    ),
    # 12. ``request`` / framework-leak namespace doesn't exist
    (
        "{{ request.user.id }}",
        EventType.ON_IMPORT,
        "no-framework-leak",
    ),
]


# ---------------------------------------------------------------------------
# T031 — every bad template is rejected with a structured error
# ---------------------------------------------------------------------------


def test_corpus_size_is_at_least_ten() -> None:
    """SC-007 sets the floor at ten distinct rejection paths."""
    assert len(BAD_TEMPLATES) >= 10


@pytest.mark.parametrize(
    "template,event_type",
    [(t, et) for t, et, _ in BAD_TEMPLATES],
    ids=[label for _, _, label in BAD_TEMPLATES],
)
def test_bad_template_rejected(
    template: str, event_type: EventType
) -> None:
    """Every entry MUST raise :class:`TemplateError`. The error
    message is intentionally not asserted here — different
    rejection paths produce different messages by design — but
    the renderer MUST funnel them all through the same public
    exception type so the API can map to a single 400 shape."""
    with pytest.raises(TemplateError) as exc_info:
        validate_template(template, event_type=event_type)
    # Sanity: the TemplateError carries a non-empty message.
    assert str(exc_info.value)


def test_well_formed_templates_are_not_rejected() -> None:
    """Negative control — without this, a global broken validator
    would let all parametrized cases pass spuriously."""
    validate_template(
        "OK {{ game.title }}", event_type=EventType.ON_IMPORT
    )
