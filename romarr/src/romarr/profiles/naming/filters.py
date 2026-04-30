"""Allowed Jinja filters (FR-025).

Exactly four filters are exposed to operator templates:

  * ``lower`` — lowercase the string.
  * ``upper`` — uppercase the string.
  * ``replace`` — substring replacement: ``{{ x | replace("a", "b") }}``.
  * ``truncate`` — first ``n`` characters: ``{{ x | truncate(N) }}``.

Anything Jinja ships by default (``length``, ``default``, ``join``,
``escape``, ``string``, …) is REMOVED from the env's filter dict at
construction time — operator templates raise
:class:`SandboxViolationError` on use.

The implementations are tiny pure functions because the sandbox
calls them with arbitrary user-supplied arguments; coercing inputs
through :func:`str` keeps them safe regardless of token type.
"""

from __future__ import annotations


def filter_lower(value: object) -> str:
    return str(value).lower()


def filter_upper(value: object) -> str:
    return str(value).upper()


def filter_replace(value: object, old: object, new: object) -> str:
    return str(value).replace(str(old), str(new))


def filter_truncate(value: object, length: int) -> str:
    """Return the first ``length`` characters of ``value`` as a string.

    Negative ``length`` is treated as zero — operator typos shouldn't
    raise; the engine prefers a quiet empty string over a render-time
    exception that breaks a hot import path.
    """
    if length <= 0:
        return ""
    return str(value)[:length]


ALLOWED_FILTERS = {
    "lower": filter_lower,
    "upper": filter_upper,
    "replace": filter_replace,
    "truncate": filter_truncate,
}


__all__ = ["ALLOWED_FILTERS"]
