"""Version-string comparison for community pack version strings.

Two flavours ship:

  * :mod:`packaging.version` — semver / PEP 440. Preferred when
    both sides parse (``0.14.34``, ``1.2.3-alpha`` etc.).
  * Fallback string inequality — for date-flavoured versions
    (``2026-07-30``, ``2026.07.30``) or free-form tags. Not strictly
    correct, but "same string ⇒ up-to-date" is the useful invariant.

The comparison is used exclusively to answer *"is a newer version
available?"* — a boolean. Getting the direction slightly wrong
on a corner case just means the badge shows an update the operator
can dismiss; it never triggers a download.
"""

from __future__ import annotations

from packaging.version import InvalidVersion, Version


def is_newer(available: str | None, installed: str | None) -> bool:
    """True when ``available`` is strictly newer than ``installed``.

    Empty / None ``installed`` means "never applied" — any non-empty
    ``available`` counts as an update. Empty / None ``available``
    means "check hasn't run yet" — returns False.
    """
    if not available:
        return False
    if not installed:
        return True
    if available.strip() == installed.strip():
        return False
    try:
        return Version(available.lstrip("v")) > Version(installed.lstrip("v"))
    except InvalidVersion:
        # Non-PEP 440 (date tags etc.) — fall back to string
        # inequality; the equality short-circuit above already
        # handled the "same version" case.
        return True


__all__ = ["is_newer"]
