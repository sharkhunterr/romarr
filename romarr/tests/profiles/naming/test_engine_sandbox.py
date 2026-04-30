"""Sandbox-escape rejection tests (T033-T035 / SC-005).

Each test confirms a known sandbox-escape vector is rejected at
SAVE time (validate) — no template should reach the render path
with a forbidden expression.
"""

from __future__ import annotations

import pytest

from romarr.profiles.errors import (
    SandboxViolationError,
    TemplateSyntaxError,
    TemplateUnknownTokenError,
)
from romarr.profiles.naming import NamingTemplateEngine

# ---------------------------------------------------------------------------
# T033 — class-attribute access blocked
# ---------------------------------------------------------------------------


def test_class_attribute_access_blocked(engine: NamingTemplateEngine) -> None:
    """``{{ Release.__class__ }}`` is a classic Python sandbox-escape vector."""
    with pytest.raises(TemplateUnknownTokenError):
        engine.validate("{{ Release.__class__ }}")


def test_mro_attribute_access_blocked(engine: NamingTemplateEngine) -> None:
    with pytest.raises(TemplateUnknownTokenError):
        engine.validate("{{ Game.__mro__ }}")


def test_globals_attribute_access_blocked(engine: NamingTemplateEngine) -> None:
    with pytest.raises(TemplateUnknownTokenError):
        engine.validate("{{ Game.__globals__ }}")


# ---------------------------------------------------------------------------
# T034 — calling globals() etc. blocked
# ---------------------------------------------------------------------------


def test_globals_call_rejected(engine: NamingTemplateEngine) -> None:
    """Even though Jinja's parser would treat ``globals`` as a name access
    (rejected as unknown top-level token), ensure the call form is also
    rejected — defence-in-depth."""
    with pytest.raises(TemplateUnknownTokenError):
        engine.validate("{{ globals() }}")


def test_unknown_function_call_rejected(engine: NamingTemplateEngine) -> None:
    with pytest.raises(TemplateUnknownTokenError):
        engine.validate("{{ open('/etc/passwd') }}")


# ---------------------------------------------------------------------------
# T035 — unknown token at parse time (FR-028)
# ---------------------------------------------------------------------------


def test_unknown_attribute_on_known_namespace_rejected_at_parse(
    engine: NamingTemplateEngine,
) -> None:
    with pytest.raises(TemplateUnknownTokenError, match="SomeForbidden"):
        engine.validate("{{ Game.SomeForbidden }}")


def test_unknown_top_level_namespace_rejected(
    engine: NamingTemplateEngine,
) -> None:
    with pytest.raises(TemplateUnknownTokenError, match="Unknown"):
        engine.validate("{{ Unknown.Title }}")


def test_known_token_accepted(engine: NamingTemplateEngine) -> None:
    """Sanity: well-formed templates pass validation cleanly."""
    engine.validate("{{ Game.Title }} ({{ Release.Region }})")


# ---------------------------------------------------------------------------
# Syntax errors → TemplateSyntaxError
# ---------------------------------------------------------------------------


def test_unterminated_expression_raises_syntax_error(
    engine: NamingTemplateEngine,
) -> None:
    with pytest.raises(TemplateSyntaxError):
        engine.validate("{{ Game.Title")


def test_invalid_jinja_construct_raises(engine: NamingTemplateEngine) -> None:
    with pytest.raises(TemplateSyntaxError):
        engine.validate("{% if Game.Title %}")  # missing endif


# ---------------------------------------------------------------------------
# Method-call attempts → SandboxViolationError
# ---------------------------------------------------------------------------


def test_attribute_method_call_rejected(engine: NamingTemplateEngine) -> None:
    """Even ``Title.upper()`` (rather than ``Title | upper``) is forbidden —
    operators must use the filter form so the engine routes through the
    whitelist."""
    with pytest.raises(SandboxViolationError):
        engine.validate("{{ Game.Title.upper() }}")
