"""Profiles subsystem (spec 006).

Six profile types (Quality, Region, Dump, Language, Naming,
CustomFormat) drive every grab/upgrade/import decision in Romarr.
The evaluator + scoring engine are pure functions; the naming
template engine is a sandboxed Jinja2 environment.

Slice 1 ships SCAF + PERS — module skeleton, errors, value types,
SQLAlchemy 2.0 models for the six profile tables and the
``library_custom_format`` m2m, Pydantic ``Read/Create/Update``
schemas with cross-field validators, and Alembic migration ``0006``.

The pure-function evaluator + Custom Format scorer + sandboxed
naming engine + idempotent seeders + admin API land in subsequent
slices.
"""

from romarr.profiles.errors import (
    ProfileError,
    ProfileInUseError,
    RegexCompileError,
    SandboxViolationError,
    TemplateSyntaxError,
    TemplateUnknownTokenError,
)
from romarr.profiles.types import (
    Decision,
    EvaluationReason,
    EvaluationResult,
    ForceDeleteResult,
    NamingPreviewResponse,
)

__all__ = [
    "Decision",
    "EvaluationReason",
    "EvaluationResult",
    "ForceDeleteResult",
    "NamingPreviewResponse",
    "ProfileError",
    "ProfileInUseError",
    "RegexCompileError",
    "SandboxViolationError",
    "TemplateSyntaxError",
    "TemplateUnknownTokenError",
]
