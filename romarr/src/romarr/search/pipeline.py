"""Pure-function decision pipeline (FR-016 / SC-002).

13 ordered steps that run every indexer result through profile
gates + DAT lookup + blocklist + size/seeders bounds + Custom
Format scoring. Returns a :class:`Candidate` populated with EITHER
a :class:`ScoreBreakdown` (accept path) OR a :class:`Rejection`
(reject path) — never both.

Constitutional invariants:

  * **Purity** (FR-016 / SC-001). No DB session, no logging, no
    time, no random. Same input ⇒ same output, every time. The
    1 000-iteration hypothesis property test in
    :mod:`tests.search.test_pipeline_purity` enforces this.
  * **Profile-driven** (Article V). The pipeline never decides
    anything itself — it composes :class:`ProfileEvaluator` +
    :func:`compute_custom_format_score` + the DAT cascade.

Order matters — a blocklist hit short-circuits before the
expensive Custom Format scoring runs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from romarr.profiles.evaluator import ProfileEvaluator
from romarr.profiles.scoring import compute_custom_format_score
from romarr.profiles.types import Decision, ReleaseFacts
from romarr.search.types import (
    Candidate,
    Rejection,
    RejectionCode,
    ScoreBreakdown,
    ScoreContribution,
)

if TYPE_CHECKING:
    from romarr.search.state import (
        BlocklistEntry,
        DatLookup,
        LibraryState,
        MonitoredGame,
        MonitoredRelease,
        PlatformFormatBounds,
        SearchResult,
    )

DAT_VERIFIED_BONUS = 200
"""FR-015: a verified DAT match contributes a fixed +200."""


def _reject(
    *,
    result: SearchResult,
    code: RejectionCode,
    field: str | None,
    message: str,
    matched_game_id: int | None = None,
    matched_release_id: int | None = None,
    pre_grab_dat_match: str = "skipped",
    title_match_score: int | None = None,
    platform_id: int | None = None,
) -> Candidate:
    return Candidate(
        indexer_id=result.indexer_id,
        indexer_guid=result.guid,
        title=result.title,
        download_url=result.link,
        size_bytes=result.size_bytes,
        seeders=result.seeders,
        matched_game_id=matched_game_id,
        matched_release_id=matched_release_id,
        platform_id=platform_id,
        region=result.region,
        languages=list(result.languages or ()),
        dump_status=result.dump_status,
        naming_convention=result.naming_convention,
        score_breakdown=None,
        rejection=Rejection(code=code, field=field, message=message),
        would_auto_reject=True,
        pre_grab_dat_match=pre_grab_dat_match,
        title_match_score=title_match_score,
    )


def _accept(
    *,
    result: SearchResult,
    matched_game_id: int,
    matched_release_id: int | None,
    breakdown: ScoreBreakdown,
    pre_grab_dat_match: str,
    title_match_score: int | None = None,
    platform_id: int | None = None,
) -> Candidate:
    return Candidate(
        indexer_id=result.indexer_id,
        indexer_guid=result.guid,
        title=result.title,
        download_url=result.link,
        size_bytes=result.size_bytes,
        seeders=result.seeders,
        matched_game_id=matched_game_id,
        matched_release_id=matched_release_id,
        platform_id=platform_id,
        region=result.region,
        languages=list(result.languages or ()),
        dump_status=result.dump_status,
        naming_convention=result.naming_convention,
        score_breakdown=breakdown,
        rejection=None,
        would_auto_reject=False,
        pre_grab_dat_match=pre_grab_dat_match,
        title_match_score=title_match_score,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _blocklisted(
    result: SearchResult, blocklist: tuple[BlocklistEntry, ...]
) -> BlocklistEntry | None:
    """First (or none) blocklist entry matching the result.

    Order: GUID match (fastest, most specific) > sha1 hash > crc32 hash.
    Hash comparisons are case-insensitive (lowercase normalised).
    """
    sha1 = (result.hash_sha1 or "").lower()
    crc = (result.hash_crc32 or "").lower()
    for entry in blocklist:
        if (
            entry.indexer_id == result.indexer_id
            and entry.indexer_guid == result.guid
            and entry.indexer_guid
        ):
            return entry
        if entry.hash_sha1 and entry.hash_sha1.lower() == sha1 and sha1:
            return entry
        if entry.hash_crc32 and entry.hash_crc32.lower() == crc and crc:
            return entry
    return None


def _resolve_release(
    matched_game: MonitoredGame, releases: tuple[MonitoredRelease, ...]
) -> MonitoredRelease | None:
    """Pick the first monitored Release for the matched Game.

    The full release-variant resolution (region/revision/dump
    crossover) lands once the importer spec exposes the
    canonical ``ReleaseResolver``. For MVP the search engine
    targets the first monitored release — sufficient for the
    documented test corpus.
    """
    for release in releases:
        if release.game_id == matched_game.id and release.monitored:
            return release
    return None


def _check_size_bounds(
    *,
    size_bytes: int | None,
    file_format: str,
    platform_id: int,
    bounds: tuple[PlatformFormatBounds, ...],
) -> tuple[bool, str | None]:
    """True when the size is within bounds for the platform/format.

    Returns ``(accepted, reason)``; reason is populated when rejected.
    Missing bounds (no PlatformFormatBounds match for this combo) are
    treated as "no opinion" — the size gate is silently skipped.
    """
    if size_bytes is None:
        return True, None
    matching = next(
        (
            b
            for b in bounds
            if b.platform_id == platform_id and b.extension == file_format
        ),
        None,
    )
    if matching is None:
        return True, None
    if matching.min_size_bytes is not None and size_bytes < matching.min_size_bytes:
        return False, (
            f"size {size_bytes} below {matching.min_size_bytes} for "
            f"platform={platform_id} format={file_format!r}"
        )
    if matching.max_size_bytes is not None and size_bytes > matching.max_size_bytes:
        return False, (
            f"size {size_bytes} above {matching.max_size_bytes} for "
            f"platform={platform_id} format={file_format!r}"
        )
    return True, None


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run_pipeline(
    *,
    result: SearchResult,
    library_state: LibraryState,
    dat_lookup: DatLookup,
    quality_profile: Any,
    region_profile: Any,
    dump_profile: Any,
    language_profile: Any,
    custom_formats: list[Any],
    file_format: str = "",
) -> Candidate:
    """Run the 13-step decision pipeline against one indexer result.

    Steps executed in order:

      1. Resolve to a monitored Game (hash-first, then fuzzy).
      2. Resolve to a monitored Release variant.
      3. Blocklist gate by GUID.
      4. Blocklist gate by hash.
      5. DAT cascade (verified | hack | none) → contribution + flag.
      6. Region evaluator.
      7. Language evaluator.
      8. Dump evaluator.
      9. Quality / format evaluator.
      10. Custom Format scoring (any rejector → reject outright).
      11. Size bounds gate.
      12. Seeders threshold gate.
      13. Aggregate contributions into the final score breakdown.
    """
    # ---- 1: Resolve to a monitored Game --------------------------------------
    from romarr.search.matching import resolve_to_game  # local to avoid cycle

    match = resolve_to_game(
        title=result.title,
        hash_sha1=result.hash_sha1,
        hash_crc32=result.hash_crc32,
        monitored_games=library_state.monitored_games,
        dat_lookup=dat_lookup,
    )
    if match is None:
        return _reject(
            result=result,
            code=RejectionCode.NO_GAME_MATCH,
            field="title",
            message=f"no monitored game matches {result.title!r}",
        )
    matched_game, title_match_score = match

    # ---- 2: Resolve to a monitored Release -----------------------------------
    matched_release = _resolve_release(matched_game, library_state.monitored_releases)
    matched_release_id = matched_release.id if matched_release else None

    # ---- 3-4: Blocklist gates -------------------------------------------------
    block = _blocklisted(result, library_state.blocklist)
    if block is not None:
        if block.indexer_guid:
            return _reject(
                result=result,
                code=RejectionCode.BLOCKLISTED_GUID,
                field="indexer_guid",
                message=block.reason,
                matched_game_id=matched_game.id,
                matched_release_id=matched_release_id,
                platform_id=matched_game.platform_id,
                title_match_score=title_match_score,
            )
        return _reject(
            result=result,
            code=RejectionCode.BLOCKLISTED_HASH,
            field="hash_sha1",
            message=block.reason,
            matched_game_id=matched_game.id,
            matched_release_id=matched_release_id,
            platform_id=matched_game.platform_id,
            title_match_score=title_match_score,
        )

    contributions: list[ScoreContribution] = []

    # ---- 5: DAT cascade -------------------------------------------------------
    dat_outcome = dat_lookup(result.hash_sha1, result.hash_crc32)
    if dat_outcome == "verified":
        contributions.append(
            ScoreContribution(
                source="dat_match",
                name="verified DAT match",
                value=DAT_VERIFIED_BONUS,
            )
        )

    # Build the ReleaseFacts the profile evaluator + scorer expect.
    facts = _release_facts_from_result(result, matched_release, file_format=file_format)

    # ---- 6: Region ------------------------------------------------------------
    region_outcome = ProfileEvaluator.evaluate_region(region_profile, facts)
    if region_outcome.decision is Decision.REJECT:
        code = (
            RejectionCode.REGION_EXCLUDED
            if region_outcome.reason and region_outcome.reason.code == "region_excluded"
            else RejectionCode.REGION_OUT_OF_PRIORITIES
        )
        return _reject(
            result=result,
            code=code,
            field="region",
            message=region_outcome.reason.message if region_outcome.reason else "",
            matched_game_id=matched_game.id,
            matched_release_id=matched_release_id,
            platform_id=matched_game.platform_id,
            pre_grab_dat_match=dat_outcome,
            title_match_score=title_match_score,
        )
    if region_outcome.score:
        contributions.append(
            ScoreContribution(
                source="region",
                name=f"region {facts.regions!r}",
                value=region_outcome.score,
            )
        )

    # ---- 7: Language ----------------------------------------------------------
    language_outcome = ProfileEvaluator.evaluate_language(language_profile, facts)
    if language_outcome.decision is Decision.REJECT:
        code_map = {
            "japanese_only_excluded": RejectionCode.JAPANESE_ONLY_EXCLUDED,
            "required_language_missing": RejectionCode.LANGUAGE_REQUIRED,
        }
        reason_code = (
            language_outcome.reason.code if language_outcome.reason else ""
        )
        return _reject(
            result=result,
            code=code_map.get(reason_code, RejectionCode.LANGUAGE_REQUIRED),
            field="languages",
            message=language_outcome.reason.message if language_outcome.reason else "",
            matched_game_id=matched_game.id,
            matched_release_id=matched_release_id,
            platform_id=matched_game.platform_id,
            pre_grab_dat_match=dat_outcome,
            title_match_score=title_match_score,
        )

    # ---- 8: Dump --------------------------------------------------------------
    dump_outcome = ProfileEvaluator.evaluate_dump(dump_profile, facts)
    if dump_outcome.decision is Decision.REJECT:
        return _reject(
            result=result,
            code=RejectionCode.DUMP_STATUS_DISALLOWED,
            field="dump_status",
            message=dump_outcome.reason.message if dump_outcome.reason else "",
            matched_game_id=matched_game.id,
            matched_release_id=matched_release_id,
            platform_id=matched_game.platform_id,
            pre_grab_dat_match=dat_outcome,
            title_match_score=title_match_score,
        )

    # ---- 9: Quality / format --------------------------------------------------
    quality_outcome = ProfileEvaluator.evaluate_quality(quality_profile, facts)
    if quality_outcome.decision is Decision.REJECT:
        code_map = {
            "format_not_allowed": RejectionCode.FORMAT_NOT_ALLOWED,
            "dat_required": RejectionCode.DAT_REQUIRED,
        }
        reason_code = quality_outcome.reason.code if quality_outcome.reason else ""
        return _reject(
            result=result,
            code=code_map.get(reason_code, RejectionCode.FORMAT_NOT_ALLOWED),
            field="format",
            message=quality_outcome.reason.message if quality_outcome.reason else "",
            matched_game_id=matched_game.id,
            matched_release_id=matched_release_id,
            platform_id=matched_game.platform_id,
            pre_grab_dat_match=dat_outcome,
            title_match_score=title_match_score,
        )

    # ---- 10: Custom Format scoring -------------------------------------------
    cf_score = compute_custom_format_score(custom_formats, facts)
    if cf_score <= -1000:  # Configurable rejector threshold per FR-011
        return _reject(
            result=result,
            code=RejectionCode.CUSTOM_FORMAT_REJECT,
            field="custom_format",
            message=f"custom format score {cf_score} below rejector threshold",
            matched_game_id=matched_game.id,
            matched_release_id=matched_release_id,
            platform_id=matched_game.platform_id,
            pre_grab_dat_match=dat_outcome,
            title_match_score=title_match_score,
        )
    if cf_score:
        contributions.append(
            ScoreContribution(
                source="custom_format",
                name="custom_format aggregate",
                value=cf_score,
            )
        )

    # ---- 11: Size bounds ------------------------------------------------------
    if file_format and matched_release is not None:
        accepted, reason = _check_size_bounds(
            size_bytes=result.size_bytes,
            file_format=file_format,
            platform_id=matched_game.platform_id,
            bounds=library_state.platform_format_bounds,
        )
        if not accepted:
            return _reject(
                result=result,
                code=RejectionCode.SIZE_OUT_OF_BOUNDS,
                field="size_bytes",
                message=reason or "",
                matched_game_id=matched_game.id,
                matched_release_id=matched_release_id,
                platform_id=matched_game.platform_id,
                pre_grab_dat_match=dat_outcome,
            )

    # ---- 12: Seeders threshold ------------------------------------------------
    indexer = next(
        (m for m in library_state.indexer_meta if m.id == result.indexer_id),
        None,
    )
    if (
        indexer is not None
        and result.seeders is not None
        and result.seeders < indexer.min_seeders
    ):
        return _reject(
            result=result,
            code=RejectionCode.SEEDERS_BELOW_THRESHOLD,
            field="seeders",
            message=(
                f"seeders={result.seeders} below indexer "
                f"min_seeders={indexer.min_seeders}"
            ),
            matched_game_id=matched_game.id,
            matched_release_id=matched_release_id,
            platform_id=matched_game.platform_id,
            pre_grab_dat_match=dat_outcome,
            title_match_score=title_match_score,
        )

    # ---- 13: Aggregate --------------------------------------------------------
    total = sum(c.value for c in contributions)
    breakdown = ScoreBreakdown(total=total, contributions=contributions)
    return _accept(
        result=result,
        matched_game_id=matched_game.id,
        matched_release_id=matched_release_id,
        breakdown=breakdown,
        pre_grab_dat_match=dat_outcome,
        title_match_score=title_match_score,
    )


def _release_facts_from_result(
    result: SearchResult,
    matched_release: MonitoredRelease | None,
    *,
    file_format: str,
) -> ReleaseFacts:
    """Project a Torznab :class:`SearchResult` + matched Release into the
    Pydantic :class:`ReleaseFacts` shape the profile evaluator + scorer
    consume."""
    from romarr.domain.enums import DumpStatus, NamingConvention

    languages: tuple[str, ...] = tuple(result.languages or ())
    regions: tuple[str, ...] = (result.region,) if result.region else ()
    if matched_release is not None and not languages:
        languages = matched_release.languages
    if matched_release is not None and not regions and matched_release.region:
        regions = (matched_release.region,)

    # Prefer the matched_release's persisted dump_status (the
    # foundation has more context); else trust the SearchResult's
    # filename-parsed dump_status; else UNKNOWN.
    if matched_release is not None:
        dump_status = matched_release.dump_status
    elif result.dump_status is not None:
        dump_status = result.dump_status
    else:
        dump_status = DumpStatus.UNKNOWN
    naming_convention = (
        result.naming_convention or NamingConvention.UNKNOWN
    )

    return ReleaseFacts(
        title=result.title,
        regions=regions,
        languages=languages,
        revision=result.revision,
        dump_status=dump_status,
        tags=tuple(result.dump_tags or ()),
        naming_convention=naming_convention,
        file_format=file_format,
        dat_verified=False,
        indexer_source=None,
        release_size=result.size_bytes,
        release_group=None,
    )


__all__ = ["DAT_VERIFIED_BONUS", "run_pipeline"]
