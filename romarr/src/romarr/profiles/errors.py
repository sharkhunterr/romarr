"""Structured error hierarchy for the profiles feature.

  - :class:`ProfileError` — base class.
  - :class:`TemplateSyntaxError` — Jinja parser refused the template.
  - :class:`TemplateUnknownTokenError` — template references an
    attribute outside the documented token whitelist.
  - :class:`SandboxViolationError` — template tried to escape the
    Jinja sandbox (e.g., ``{{ Release.__class__ }}``).
  - :class:`RegexCompileError` — a Custom Format ``matches_regex``
    pattern failed to compile (FR-023).
  - :class:`ProfileInUseError` — DELETE rejected because the profile
    is bound to one or more libraries (FR-032).
"""

from __future__ import annotations


class ProfileError(RuntimeError):
    """Base for every profile-side failure."""


class TemplateSyntaxError(ProfileError):
    """The Jinja2 sandbox could not parse the template."""


class TemplateUnknownTokenError(ProfileError):
    """The template references an attribute outside the whitelist."""


class SandboxViolationError(ProfileError):
    """The template tried to access something the sandbox forbids."""


class RegexCompileError(ProfileError):
    """A Custom Format ``matches_regex`` pattern failed to compile."""


class ProfileInUseError(ProfileError):
    """The profile is bound to a library and cannot be deleted without ``?force=true``."""

    def __init__(self, *, profile_type: str, profile_id: int, library_ids: list[int]) -> None:
        super().__init__(
            f"{profile_type} {profile_id} is bound to libraries "
            f"{library_ids!r}; pass ?force=true to unbind"
        )
        self.profile_type = profile_type
        self.profile_id = profile_id
        self.library_ids = library_ids


__all__ = [
    "ProfileError",
    "ProfileInUseError",
    "RegexCompileError",
    "SandboxViolationError",
    "TemplateSyntaxError",
    "TemplateUnknownTokenError",
]
