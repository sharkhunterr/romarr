"""Structured error hierarchy for the platform-packs feature.

Validation errors carry a list of :class:`Violation` rows so the
HTTP layer can surface a structured 400 response that pinpoints
exactly which JSON path / pack platform / parsing strategy went wrong.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Violation:
    """One failure in a pack validation pass.

    ``path`` follows the JSON-pointer convention (``/platforms/0/slug``)
    so the UI can highlight the offending field. ``message`` is a
    human-readable explanation; ``code`` is a machine-stable identifier
    callers can match against.
    """

    path: str
    message: str
    code: str


class PackValidationError(ValueError):
    """A pack failed JSON-Schema or cross-reference validation."""

    def __init__(
        self,
        message: str,
        *,
        violations: list[Violation] | None = None,
    ) -> None:
        super().__init__(message)
        self.violations: list[Violation] = list(violations or [])

    def __repr__(self) -> str:
        return (
            f"PackValidationError({self.args[0]!r}, "
            f"violations={self.violations!r})"
        )


class SchemaVersionTooHighError(PackValidationError):
    """The pack declares a ``schema_version`` greater than this build."""

    def __init__(self, requested: int, supported: int) -> None:
        super().__init__(
            f"pack schema_version {requested} > supported {supported}",
            violations=[
                Violation(
                    path="/schema_version",
                    message=(
                        f"requested schema_version {requested} > "
                        f"supported {supported}"
                    ),
                    code="schema_version_too_high",
                )
            ],
        )
        self.requested = requested
        self.supported = supported


class PackVersionConflictError(ValueError):
    """An upload reuses an existing ``pack_version`` with a different
    ``contents_hash`` — pack versions are immutable once recorded."""

    def __init__(self, pack_version: str) -> None:
        super().__init__(
            f"pack version {pack_version!r} already recorded with a "
            "different contents hash"
        )
        self.pack_version = pack_version


@dataclass
class _OverrideContext:
    """Context the override-required error attaches for the HTTP layer."""

    platform_id: int | None = None
    platform_slug: str | None = None
    fields: list[str] = field(default_factory=list)


class OverrideRequiredError(ValueError):
    """A mutation against a non-user-overridden platform was rejected.

    Format-CRUD endpoints raise this when the operator tries to add /
    edit / delete a format on a platform whose ``pack_source`` is not
    ``'user'``. The HTTP layer translates to 409 Conflict so the UI
    can offer "mark this platform as user-overridden first?".
    """

    def __init__(
        self,
        message: str,
        *,
        platform_id: int | None = None,
        platform_slug: str | None = None,
    ) -> None:
        super().__init__(message)
        self.context = _OverrideContext(
            platform_id=platform_id,
            platform_slug=platform_slug,
        )
