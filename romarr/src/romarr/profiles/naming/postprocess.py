"""Post-processing for rendered naming templates (FR-026 / FR-027).

Three pure passes, composed by :func:`postprocess`:

  1. Drop empty bracketed groups — when a token renders to the empty
     string, a wrapping ``( )`` / ``[ ]`` becomes literal noise; the
     pass removes those groups along with the leading whitespace
     they typically introduce. Run first so subsequent passes see
     a tighter string.
  2. Replace illegal filename characters — the platform-specific
     ``/`` (path separator) is left intact because some conventions
     (``es-de``, ``romm``) intentionally render a subfolder; only
     the per-component illegal chars are replaced.
  3. Collapse consecutive whitespace — runs after the bracket pass
     so the gaps left behind by removed groups don't survive.

The filename's path-separator semantics are preserved: each path
component is treated independently for the illegal-char pass, so
``Sonic/Title:Bad`` becomes ``Sonic/Title_Bad`` rather than
``Sonic_Title_Bad``.
"""

from __future__ import annotations

import re

# Per-component illegal characters (FR-026). Excludes ``/`` because
# the engine produces multi-component paths intentionally (e.g.,
# ``{Platform.Slug}/{Game.Title}``).
_ILLEGAL_PER_COMPONENT = '\\:*?"<>|'
_ILLEGAL_RE = re.compile(rf"[{re.escape(_ILLEGAL_PER_COMPONENT)}]")


def replace_illegal_chars(rendered: str) -> str:
    """Replace illegal filename characters with ``_`` per component.

    The path separator ``/`` is preserved — it carries semantic
    meaning for naming profiles that produce subfolders.
    """
    parts = rendered.split("/")
    return "/".join(_ILLEGAL_RE.sub("_", part) for part in parts)


# Empty bracketed group: ``(...)`` or ``[...]`` whose contents are
# only whitespace. Optional leading whitespace is consumed too so we
# don't leave double-spaces behind.
_EMPTY_PARENS_RE = re.compile(r"\s*\(\s*\)")
_EMPTY_BRACKETS_RE = re.compile(r"\s*\[\s*\]")


def drop_empty_bracketed_groups(rendered: str) -> str:
    """Remove ``( )`` and ``[ ]`` whose contents are whitespace-only.

    Iterated until convergence so nested empty groups (rare but
    possible after token expansion) collapse cleanly in one call.
    """
    previous = ""
    current = rendered
    while previous != current:
        previous = current
        current = _EMPTY_PARENS_RE.sub("", current)
        current = _EMPTY_BRACKETS_RE.sub("", current)
    return current


_MULTI_SPACE_RE = re.compile(r" {2,}")


def collapse_whitespace(rendered: str) -> str:
    """Collapse runs of spaces into one + strip outer whitespace.

    Newlines and tabs aren't expected in filename templates; they're
    stripped wholesale so an over-zealous template can't leak them
    into a filename.
    """
    out = rendered.replace("\t", " ").replace("\n", " ")
    out = _MULTI_SPACE_RE.sub(" ", out)
    return out.strip()


def postprocess(rendered: str, *, replace_illegal: bool) -> str:
    """Run the documented passes in order; return the cleaned filename.

    ``replace_illegal=False`` is honoured for operators who deliberately
    want the raw render (e.g., a test-only naming profile) — but the
    UI defaults the column to ``true`` so production paths stay safe.
    """
    out = drop_empty_bracketed_groups(rendered)
    if replace_illegal:
        out = replace_illegal_chars(out)
    out = collapse_whitespace(out)
    return out


__all__ = [
    "collapse_whitespace",
    "drop_empty_bracketed_groups",
    "postprocess",
    "replace_illegal_chars",
]
