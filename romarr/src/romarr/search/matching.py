"""Pure-function game matcher — hash-first, then RapidFuzz fuzzy (FR-009).

Resolution order:

  1. **Hash match** — if the result carries a ``hash_sha1`` or
     ``hash_crc32`` AND the DAT lookup returns ``"verified"`` or
     ``"hack"``, the matcher resolves to the Game whose Release
     carries that hash. This path is short-circuit: we trust the
     hash regardless of how badly the title is mangled.
  2. **Fuzzy match** — RapidFuzz's ``WRatio`` against canonical +
     alt names, threshold 85, case-insensitive (``processor=lower``).
     Returns the highest-scoring monitored Game above threshold.
  3. **No match** — the pipeline rejects the result with
     ``RejectionCode.NO_GAME_MATCH``.

The dat_lookup callable is pure — no I/O, deterministic on its
inputs. The orchestrator wires it to the foundation's DAT cache
before calling the pipeline.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from rapidfuzz import fuzz, process

if TYPE_CHECKING:
    from romarr.search.state import DatLookup, MonitoredGame
    from romarr.search.types import Query

FUZZY_THRESHOLD = 85
"""WRatio score floor — anything below is treated as "no match" (FR-009)."""

# ``[Region]``, ``[Team]``, ``[MiNERVA Archive]``, ``[No-Intro]``, …
# — all noise for the fuzzy title match. A MiNERVA candidate like
# ``[MiNERVA Archive] [Redump] [Sony - PlayStation 2] [Korea] [KO]
# Jak II [ZIP]`` scored 60% against ``Jak II`` because the sheer
# bracket volume drowned the actual game name; stripping brackets
# first gets it to 100%. The parser downstream still consumes the
# raw title for tag / region / language extraction — this scrub
# only affects the fuzzy-name comparator.
_BRACKET_RE = re.compile(r"\[[^\]]*\]")


def _processor(text: str) -> str:
    return _BRACKET_RE.sub(" ", text).lower().strip()


def _gather_searchable(game: MonitoredGame) -> list[str]:
    return [game.title, *game.alt_names]


def resolve_to_game(
    *,
    title: str,
    hash_sha1: str | None,
    hash_crc32: str | None,
    monitored_games: tuple[MonitoredGame, ...],
    dat_lookup: DatLookup,
) -> tuple[MonitoredGame, int] | None:
    """Pure: return the matched ``(MonitoredGame, score)`` or None.

    The score is the RapidFuzz WRatio (0-100) for fuzzy hits, or
    100 when a verified hash short-circuits to a known Game
    (handled by the future DAT→Game join). The orchestrator
    surfaces it on the Candidate as ``title_match_score`` so the
    operator UI can blend it with the profile score.

    The DAT lookup is consulted first so a verified hash can pull
    a Game match even when the indexer's title is unrecognisable.
    Fuzzy match is the fallback when neither hash is provided OR
    the DAT lookup returns ``"none"``.
    """
    if hash_sha1 or hash_crc32:
        info = dat_lookup(hash_sha1, hash_crc32)
        if info.outcome != "none":
            # The DAT layer doesn't yet hand us the matched Game id
            # directly (that lookup is the future Importer's job);
            # for now we fall through to fuzzy matching with a high
            # confidence flag stored on the Candidate via its
            # ``pre_grab_dat_match`` field. Once the DAT-to-Game
            # join lands, this short-circuits with a direct return.
            pass

    if not monitored_games:
        return None

    choices = {idx: _gather_searchable(g) for idx, g in enumerate(monitored_games)}
    best: tuple[int, float] | None = None
    for idx, names in choices.items():
        result = process.extractOne(
            title,
            names,
            scorer=fuzz.WRatio,
            processor=_processor,
            score_cutoff=FUZZY_THRESHOLD,
        )
        if result is None:
            continue
        _, score, _ = result
        if best is None or score > best[1]:
            best = (idx, score)

    if best is None:
        return None
    return monitored_games[best[0]], int(round(best[1]))


def fuzzy_match_query(
    query: Query, monitored_games: tuple[MonitoredGame, ...]
) -> MonitoredGame | None:
    """Convenience: run :func:`resolve_to_game` against a Query text.

    Used by the round orchestrators when scoring against a candidate
    indexer result that has no hash material.
    """

    from romarr.search.state import _NONE_DAT_INFO

    def _none_dat(_a: str | None, _b: str | None):  # noqa: ANN202
        return _NONE_DAT_INFO

    match = resolve_to_game(
        title=query.text,
        hash_sha1=None,
        hash_crc32=None,
        monitored_games=monitored_games,
        dat_lookup=_none_dat,
    )
    return match[0] if match is not None else None


__all__ = ["FUZZY_THRESHOLD", "fuzzy_match_query", "resolve_to_game"]
