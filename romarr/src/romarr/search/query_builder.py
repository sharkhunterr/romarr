"""Pure-function query builder (FR-006).

Given a Game + Platform, produce the list of queries the round
orchestrator will fan out to indexers. Variants per FR-006:

  * canonical title;
  * one query per alternative name (if any);
  * canonical + platform short name;
  * canonical + platform manufacturer.

For a Game with two alt names this yields 5 queries; for a Game
with no alt names it yields 3. The orchestrator de-duplicates
identical strings before fanning out so an alt name that matches
the canonical title doesn't waste an indexer call.
"""

from __future__ import annotations

from typing import Protocol

from romarr.search.types import Query


class _GameLike(Protocol):
    title: str
    alt_names: tuple[str, ...]


class _PlatformLike(Protocol):
    short_name: str
    manufacturer: str


def build_queries(game: _GameLike, platform: _PlatformLike) -> list[Query]:
    """Return the deduplicated query list for ``game`` on ``platform``.

    Pure — no I/O, no logging, deterministic on its inputs.
    """
    queries: list[Query] = [Query(text=game.title, label="canonical")]

    for alt in game.alt_names:
        if alt and alt != game.title:
            queries.append(Query(text=alt, label="alt_name"))

    if platform.short_name:
        queries.append(
            Query(
                text=f"{game.title} {platform.short_name}".strip(),
                label="with_platform",
            )
        )
    if platform.manufacturer:
        queries.append(
            Query(
                text=f"{game.title} {platform.manufacturer}".strip(),
                label="with_manufacturer",
            )
        )

    # Deduplicate while preserving order — the canonical query has
    # to come first regardless of how the alt names happen to coincide.
    seen: set[str] = set()
    out: list[Query] = []
    for q in queries:
        if q.text in seen:
            continue
        seen.add(q.text)
        out.append(q)
    return out


__all__ = ["build_queries"]
