"""Naming-template token whitelist (FR-024 / FR-028).

Four namespace classes — :class:`GameTokens`, :class:`ReleaseTokens`,
:class:`DumpTokens`, :class:`PlatformTokens` — each frozen Pydantic
model whose attributes ARE the allowed tokens. The engine wires
these as the only top-level names in the Jinja context, and an AST
walk at SAVE time confirms templates reference no other names or
attributes (FR-028 — unknown-token rejection at save time, not render
time).

Why namespace classes (and not bare dicts)? Pydantic's frozen=True
makes the whole context shallowly immutable, which combined with
:class:`jinja2.sandbox.ImmutableSandboxedEnvironment` makes
template-time mutation impossible — operator-supplied templates run
in a hard-frozen room.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

_FROZEN = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class GameTokens(BaseModel):
    """``{{ Game.* }}`` accessors available to a naming template."""

    model_config = _FROZEN

    Title: str = ""
    SortTitle: str = ""
    Year: str = ""
    Publisher: str = ""


class ReleaseTokens(BaseModel):
    """``{{ Release.* }}`` accessors available to a naming template.

    List-valued tokens (``Languages``, ``Tags``) are pre-rendered to
    their canonical separator form by the engine before being put on
    the context — Templates never see Python lists, only strings, so
    ``join`` is not needed (and not whitelisted).
    """

    model_config = _FROZEN

    Region: str = ""
    Languages: str = ""        # comma-separated, e.g. "en, fr"
    Revision: str = ""
    Tags: str = ""             # space-separated, e.g. "[!] [T+En]"
    OriginalName: str = ""


class DumpTokens(BaseModel):
    """``{{ Dump.* }}`` accessors available to a naming template."""

    model_config = _FROZEN

    Extension: str = ""        # without leading dot — engine concatenates
    Hash: str = ""             # short SHA-1 prefix; FR-024 leaves the form open


class PlatformTokens(BaseModel):
    """``{{ Platform.* }}`` accessors available to a naming template."""

    model_config = _FROZEN

    Slug: str = ""
    Name: str = ""


# Namespace name → set of allowed attribute names. Consumed by the
# engine's ``validate`` AST walk and by the runtime
# ``is_safe_attribute`` override. Single source of truth for the
# whitelist — keep both gates in sync via this dict.
TOKEN_WHITELIST: dict[str, frozenset[str]] = {
    "Game": frozenset(GameTokens.model_fields.keys()),
    "Release": frozenset(ReleaseTokens.model_fields.keys()),
    "Dump": frozenset(DumpTokens.model_fields.keys()),
    "Platform": frozenset(PlatformTokens.model_fields.keys()),
}


__all__ = [
    "TOKEN_WHITELIST",
    "DumpTokens",
    "GameTokens",
    "PlatformTokens",
    "ReleaseTokens",
]
