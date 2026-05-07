"""Heuristic platform detection from an indexer title (slice 354).

Indexer titles routinely spell the platform out — ``Mario Kart
Super Circuit (Game Boy Advance)`` or ``[Nintendo - Game Boy
Advance]`` or ``[GBA]``. The manual-search round uses this to
detect when a candidate looks like a *different* platform from
the one the modal is searching for, and the row's platform chip
turns red.

Matching is **token-aware**: both title and alias are tokenised on
non-alphanumeric runs, lowercased, and the alias matches when its
token sequence appears verbatim among the title tokens. Substring
matching on the raw normalised string would have ``Sonic the
Hedgehog (Genesis)`` collide with the ``NES`` slug (``nes`` is a
substring of ``genesis``); requiring a clean token boundary
removes that class of false positive.

Two safeguards keep the false-positive rate low:

  * we require an alias of at least 3 normalised chars so two-
    letter codes like ``GB`` don't bleed into ``GBA`` / ``GBC`` /
    ``GameBoy``;
  * when several platforms match (e.g. ``Game Boy`` *and* ``Game
    Boy Advance`` both appear as substrings), the longest alias
    wins so ``Game Boy Advance`` shadows the parent ``Game Boy``
    that's nested inside it.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from romarr.domain.models import Platform


_MIN_ALIAS_LEN = 3
_TOKEN_SEP = re.compile(r"[^a-zA-Z0-9]+")


def _normalise(text: str) -> str:
    """Lowercase + strip everything that isn't alphanumeric."""
    return "".join(c.lower() for c in text if c.isalnum())


def _tokens(text: str) -> list[str]:
    """Lower-case alphanumeric tokens in ``text`` (in order)."""
    return [t.lower() for t in _TOKEN_SEP.split(text) if t]


def _alias_appears_in(title_tokens: list[str], alias_tokens: list[str]) -> bool:
    """True when the alias matches a contiguous token window of any
    size whose concatenation equals the alias's concatenation.

    This bridges the spelling variants the catalogue ↔ free-text
    title gap:

      * alias ``["game","boy","advance"]`` matches title tokens
        ``["gameboy","advance"]`` (window size 2 → ``gameboyadvance``)
      * alias ``["gba"]`` matches title tokens ``["gba"]`` (window 1)
      * alias ``["nes"]`` does NOT match title tokens ``["genesis"]``
        because no window concatenation equals ``nes``.
    """
    if not alias_tokens or not title_tokens:
        return False
    target = "".join(alias_tokens)
    max_window = max(len(alias_tokens), 1)
    for window in range(1, max_window + 1):
        for i in range(len(title_tokens) - window + 1):
            if "".join(title_tokens[i : i + window]) == target:
                return True
    return False


def _aliases_for(platform: Platform) -> list[str]:
    """Generate every spelling we expect to see for ``platform``.

    Includes the slug, short_name, full name, and the full name
    with the manufacturer prefix dropped (so ``Nintendo Game Boy
    Advance`` also matches a bare ``Game Boy Advance``).
    """
    aliases: list[str] = []
    if platform.slug:
        aliases.append(platform.slug)
    if platform.short_name:
        aliases.append(platform.short_name)
    if platform.name:
        aliases.append(platform.name)
        if platform.manufacturer:
            stripped = platform.name
            prefix = f"{platform.manufacturer} "
            if stripped.lower().startswith(prefix.lower()):
                stripped = stripped[len(prefix):].strip()
                if stripped and stripped != platform.name:
                    aliases.append(stripped)
    return aliases


def match_platform_in_title(
    title: str, platforms: Iterable[Platform]
) -> Platform | None:
    """Return the most specific platform whose alias appears in ``title``.

    ``None`` when no alias clears the minimum length or appears as
    a token subsequence of the title — caller falls back to the
    matched_game's platform (or ``None`` for the standalone facet).
    """
    title_tokens = _tokens(title)
    if not title_tokens:
        return None

    best: tuple[Platform, int] | None = None
    for p in platforms:
        for alias in _aliases_for(p):
            alias_tokens = _tokens(alias)
            joined = "".join(alias_tokens)
            if len(joined) < _MIN_ALIAS_LEN:
                continue
            if not _alias_appears_in(title_tokens, alias_tokens):
                continue
            # Prefer the most specific alias (longest joined form):
            # ``Game Boy Advance`` (15 chars joined) shadows
            # ``Game Boy`` (7 chars) when the title contains both.
            score = len(joined)
            if best is None or score > best[1]:
                best = (p, score)
    return best[0] if best is not None else None


__all__ = ["match_platform_in_title"]
