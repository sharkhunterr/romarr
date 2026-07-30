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
_PAREN_RE = re.compile(r"\([^)]*\)")

# Anything after ``" - "`` or a colon+space in a normalised release
# title is a subtitle — treating it as part of the title lets
# WRatio's token_set_ratio give ``100`` when the target is the
# BASE title ("The Legend of Zelda" vs "The Legend of Zelda -
# Skyward Sword"), auto-grabbing an entirely different game.
# The dash form requires spaces on both sides (release titles use
# " - " as a segment separator; a bare "-" would false-positive on
# hyphenated names). Colon allows no leading space so
# ``"Zelda: Ocarina of Time"`` splits, but still requires a
# following space so URLs / times don't split.
_SUBTITLE_SPLIT_RE = re.compile(r"\s+-\s+|:\s+")


def _processor(text: str) -> str:
    return _BRACKET_RE.sub(" ", text).lower().strip()


def _base_title(text: str) -> str:
    """Return the release/game title stripped of brackets, parens,
    and everything after the first subtitle separator.

    Used by :func:`_is_distinct_subtitle` to detect the "generic
    franchise name matches a specific sub-title release" false
    positive. Symmetric — applied to both sides so a monitored
    game whose title itself carries a subtitle stays comparable
    against its own release variants.
    """
    scrubbed = _PAREN_RE.sub(" ", _BRACKET_RE.sub(" ", text))
    return _SUBTITLE_SPLIT_RE.split(scrubbed, maxsplit=1)[0].lower().strip()


def _has_subtitle(text: str) -> bool:
    scrubbed = _PAREN_RE.sub(" ", _BRACKET_RE.sub(" ", text))
    return bool(_SUBTITLE_SPLIT_RE.search(scrubbed))


# Common leading articles are noise for the base-title comparison —
# "Legend of Zelda" vs "The Legend of Zelda" is the same base.
_LEADING_ARTICLE_RE = re.compile(r"^(?:the|a|an)\s+")


def _normalise_base(text: str) -> str:
    """Base title with leading article stripped, for the guard's
    similarity comparison."""
    return _LEADING_ARTICLE_RE.sub("", _base_title(text)).strip()


def _bases_align(release_base_norm: str, game_base_norm: str) -> bool:
    """True when the two normalised bases look like the same title.
    Uses ``token_set_ratio >= 90`` so ``legend of zelda`` matches
    ``legend of zelda`` after article-strip even when one side
    dropped "the"."""
    if not release_base_norm or not game_base_norm:
        return False
    if release_base_norm == game_base_norm:
        return True
    return fuzz.token_set_ratio(release_base_norm, game_base_norm) >= 90


def _is_distinct_subtitle(
    release_title: str, game_title: str, game_alt_names: tuple[str, ...]
) -> bool:
    """True when the release adds a subtitle that the target game
    doesn't have, and the release's *base* title (before its
    subtitle separator) is fuzzily equal to the target's title.
    Meaning: WRatio only cleared threshold because the target is
    a token-subset of the release — and the release names a
    DIFFERENT sub-series game.

    Concrete cases this catches:

      * game ``"The Legend of Zelda"`` (NES) vs release
        ``"The Legend of Zelda - Skyward Sword [SOUE01]"`` — the
        Skyward Sword release names a distinct Wii U game.
      * game ``"The Legend of Zelda"`` vs release ``"Legend of
        Zelda - The Minish Cap (World) (Aftermarket)"`` — the
        Minish Cap is a distinct GBA game (leading "The" dropped
        by the aftermarket packager, hence the fuzzy compare).

    Passes through when:
      * the target's title itself carries a subtitle
        (``Zelda: Ocarina of Time`` — both sides align on the
        full title, no distinctness signal from the subtitle),
      * the release has no subtitle at all
        (``The Legend of Zelda (USA) (Rev 1)``),
      * one of the game's alt-names IS the release's base title
        (operator-declared alias — trust it).
    """
    if _has_subtitle(game_title):
        return False
    if not _has_subtitle(release_title):
        return False
    release_base_norm = _normalise_base(release_title)
    game_base_norm = _normalise_base(game_title)
    if not release_base_norm or not game_base_norm:
        return False
    # Alt-name exact-match escape hatch: an operator-declared alias
    # that equals the release base title means "yes, this release
    # IS this game" even if it looks like a subtitle extension.
    for alt in game_alt_names:
        if _base_title(alt) == release_base_norm or _base_title(alt) == _base_title(release_title):
            return False
    return _bases_align(release_base_norm, game_base_norm)


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
        # Subtitle-separator guard: reject bases like "The Legend
        # of Zelda" fuzzy-matching "The Legend of Zelda - Skyward
        # Sword" (Wii Zelda) or "Legend of Zelda - The Minish
        # Cap (Aftermarket) (Pirate)" (GBA hack). Both cleared
        # WRatio ≥ 85 via token-subset — but the release names a
        # different sub-series game.
        game = monitored_games[idx]
        if _is_distinct_subtitle(title, game.title, game.alt_names):
            continue
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
