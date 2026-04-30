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
from romarr.profiles.evaluator import ProfileEvaluator, evaluate_all
from romarr.profiles.naming import (
    DumpTokens,
    GameTokens,
    NamingTemplateEngine,
    PlatformTokens,
    ReleaseTokens,
)
from romarr.profiles.scoring import compute_custom_format_score
from romarr.profiles.seeders import SCENE_GROUPS, seed_defaults
from romarr.profiles.types import (
    Decision,
    EvaluationReason,
    EvaluationResult,
    ForceDeleteResult,
    NamingPreviewResponse,
    ReleaseFacts,
)

__all__ = [
    "SCENE_GROUPS",
    "Decision",
    "DumpTokens",
    "EvaluationReason",
    "EvaluationResult",
    "ForceDeleteResult",
    "GameTokens",
    "NamingPreviewResponse",
    "NamingTemplateEngine",
    "PlatformTokens",
    "ProfileError",
    "ProfileEvaluator",
    "ProfileInUseError",
    "RegexCompileError",
    "ReleaseFacts",
    "ReleaseTokens",
    "SandboxViolationError",
    "TemplateSyntaxError",
    "TemplateUnknownTokenError",
    "compute_custom_format_score",
    "evaluate_all",
    "seed_defaults",
]
