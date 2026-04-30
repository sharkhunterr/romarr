"""Sandboxed naming-template engine (Phase 4 — Article XI invariant).

Public surface: :class:`NamingTemplateEngine`. Internals are
documented in their own modules:

  - :mod:`romarr.profiles.naming.tokens` — the four namespace
    classes + the :data:`TOKEN_WHITELIST` allowlist.
  - :mod:`romarr.profiles.naming.filters` — the four allowed Jinja
    filters (``lower`` / ``upper`` / ``replace`` / ``truncate``).
  - :mod:`romarr.profiles.naming.postprocess` — drop empty bracketed
    groups, replace illegal chars, collapse whitespace.
  - :mod:`romarr.profiles.naming.engine` — validate-at-save,
    render-through-sandbox, post-process.
"""

from romarr.profiles.naming.engine import NamingTemplateEngine
from romarr.profiles.naming.tokens import (
    DumpTokens,
    GameTokens,
    PlatformTokens,
    ReleaseTokens,
)

__all__ = [
    "DumpTokens",
    "GameTokens",
    "NamingTemplateEngine",
    "PlatformTokens",
    "ReleaseTokens",
]
