"""Pure-function multi-library router (spec 009 — Phase 3 ROUTE).

Given a parsed release and a preloaded set of
:class:`LibrarySnapshot` rows plus the libraries' Quality / Region
profiles, decide which library should receive the file.

Per FR-006, the routing score is

    routing_score = region_score + quality_bonus

  * ``region_score`` is the spec 006 FR-013 formula
    (``len(priorities) - index``, 0-based; ``0`` when the fallback
    branch fires; the library is excluded outright when the
    release's region is on the library's Region profile
    ``exclude_regions`` list).
  * ``quality_bonus`` is ``1`` when the library's Quality profile
    evaluates the file as ``ACCEPT``; ``0`` otherwise. A Quality
    REJECT does NOT disqualify the library — the file still has to
    go somewhere; the bonus is purely a tie-breaker.

Custom Format scores are deliberately excluded — those belong to
the search engine (spec 007), not the importer.

The router is **pure**: no I/O, no DB session, no logging side
effects. Determinism is guaranteed by sorting on
``(routing_score DESC, library.id ASC)``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from romarr.libraries.types import LibraryStatus, RoutingChoice
from romarr.profiles.evaluator import ProfileEvaluator
from romarr.profiles.types import Decision

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from romarr.libraries.types import LibrarySnapshot
    from romarr.profiles.types import ReleaseFacts


_NO_LIBRARY_FOR_PLATFORM = "routing:no_library_for_platform"


def _platform_accepted(lib: LibrarySnapshot, platform_id: int) -> bool:
    """Empty m2m + ``platforms_restricted=False`` ⇒ accept any platform.
    Empty m2m + ``platforms_restricted=True`` is a validation error
    that should never reach the router; we still treat it as
    "no platforms accepted" for safety."""
    if not lib.platforms_restricted:
        return True
    return platform_id in lib.accepted_platform_ids


def _score_library(
    lib: LibrarySnapshot,
    facts: ReleaseFacts,
    quality_profiles: Mapping[int, object],
    region_profiles: Mapping[int, object],
) -> int | None:
    """Return the library's routing_score, or ``None`` if the region
    profile excludes this release outright."""
    region_profile = region_profiles[lib.region_profile_id]
    region_result = ProfileEvaluator.evaluate_region(region_profile, facts)  # type: ignore[arg-type]
    if region_result.decision is Decision.REJECT:
        return None

    quality_profile = quality_profiles[lib.quality_profile_id]
    quality_result = ProfileEvaluator.evaluate_quality(quality_profile, facts)  # type: ignore[arg-type]
    quality_bonus = 1 if quality_result.decision is Decision.ACCEPT else 0

    return region_result.score + quality_bonus


def route_to_library(
    *,
    facts: ReleaseFacts,
    inferred_platform_id: int,
    libraries: Sequence[LibrarySnapshot],
    quality_profiles: Mapping[int, object],
    region_profiles: Mapping[int, object],
) -> RoutingChoice:
    """Pick the library that should receive the file.

    Steps (in order):

      1. Drop libraries with ``status == 'unavailable'`` (FR-008).
      2. Drop libraries whose platform allowlist excludes the
         release's inferred platform (FR-005 + FR-006).
      3. Score remaining libraries via :func:`_score_library`. A
         library whose Region profile excludes the release outright
         is dropped here; a library whose Quality profile is
         neutral or rejects merely loses the tie-breaking bonus.
      4. Pick the highest score; final ties go to the lowest
         ``library.id`` (oldest, deterministic).

    Returns a :class:`RoutingChoice` carrying ``chosen_via`` so the
    caller can audit the decision path.
    """
    available = [lib for lib in libraries if lib.status is LibraryStatus.OK]
    eligible = [
        lib for lib in available if _platform_accepted(lib, inferred_platform_id)
    ]
    candidates_considered = tuple(lib.id for lib in eligible)

    if not eligible:
        return RoutingChoice(
            chosen_library_id=None,
            chosen_via="no_eligible_library",
            candidates_considered=candidates_considered,
            rejection_reason=_NO_LIBRARY_FOR_PLATFORM,
        )

    scored: list[tuple[int, int]] = []  # (library.id, score) — score >= 0
    for lib in eligible:
        score = _score_library(lib, facts, quality_profiles, region_profiles)
        if score is None:
            continue
        scored.append((lib.id, score))

    if not scored:
        return RoutingChoice(
            chosen_library_id=None,
            chosen_via="no_eligible_library",
            candidates_considered=candidates_considered,
            rejection_reason=_NO_LIBRARY_FOR_PLATFORM,
        )

    if len(scored) == 1:
        return RoutingChoice(
            chosen_library_id=scored[0][0],
            chosen_via="only_eligible",
            candidates_considered=candidates_considered,
        )

    # Sort: highest score first; final tie-break on lowest id.
    scored.sort(key=lambda pair: (-pair[1], pair[0]))
    top_score = scored[0][1]
    tied_at_top = [lib_id for lib_id, score in scored if score == top_score]

    chosen_via = (
        "profile_match" if len(tied_at_top) == 1 else "lower_id_tiebreak"
    )

    return RoutingChoice(
        chosen_library_id=scored[0][0],
        chosen_via=chosen_via,
        candidates_considered=candidates_considered,
    )


__all__ = ["route_to_library"]
