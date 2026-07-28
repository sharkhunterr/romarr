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
from romarr.profiles.scoring import (
    compute_custom_format_score,
    compute_matched_custom_formats,
)
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

# Slice 456 — soft-scoring model. The only HARD reject left in
# the pipeline is "no monitored game matches" (wrong platform /
# unrecognised title) plus the operator's explicit blocklist.
# Everything else — region, language, dump status, file format,
# size, seeders, custom-format rejectors — is a *malus*: a
# negative ScoreContribution that drags the score down without
# excluding the candidate. Manual search shows every candidate
# ranked; auto-grab only picks those scoring at or above
# ``AUTO_GRAB_FLOOR``.
PENALTY_REGION_EXCLUDED = -60
"""Operator explicitly excluded this region — heavy, but the
release still shows up so the operator can override."""
PENALTY_REGION_NOT_PRIORITY = -10
"""Region isn't in the priority list (fallback path)."""
PENALTY_LANGUAGE_MISSING = -30
"""None of the profile's required languages are present."""
PENALTY_JAPANESE_ONLY = -40
"""Release is Japanese-only and the profile excludes JA-only."""
PENALTY_DUMP_STATUS = -25
"""Dump status (beta / hack / demo / proto / …) the profile
doesn't allow."""
PENALTY_FORMAT_NOT_NATIVE = -15
"""File format isn't the platform's native cartridge/disc format
and isn't an archive container — still grabbable, just not
ideal."""
PENALTY_DAT_REQUIRED = -40
"""Profile wants DAT-verified releases; this one isn't."""
PENALTY_SIZE_OUT_OF_BOUNDS = -25
"""Release size is outside the platform/format bounds."""
PENALTY_SEEDERS_LOW = -20
"""Seeders below the indexer's configured floor."""
PENALTY_CUSTOM_FORMAT_REJECTOR = -100
"""A custom-format rejector matched. Heavy malus instead of the
old hard reject so the operator can still see + override it."""
PENALTY_ALREADY_OWNED = -50
"""A Dump with this hash already exists for the game — almost
certainly a re-grab the operator doesn't want."""

AUTO_GRAB_FLOOR = 0
"""Auto-grab only dispatches candidates whose total score is at
or above this floor. Manual search ignores it (shows everything,
ranked) — the operator decides. Below the floor a candidate is
flagged ``would_auto_reject=True``."""


def _reject(
    *,
    result: SearchResult,
    code: RejectionCode,
    field: str | None,
    message: str,
    matched_game_id: int | None = None,
    matched_release_id: int | None = None,
    pre_grab_dat_match: str = "skipped",
    pre_grab_dat_entry_name: str | None = None,
    pre_grab_dat_entry_source: str | None = None,
    already_owned: bool = False,
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
        file_format=result.file_format,
        score_breakdown=None,
        rejection=Rejection(code=code, field=field, message=message),
        would_auto_reject=True,
        pre_grab_dat_match=pre_grab_dat_match,
        pre_grab_dat_entry_name=pre_grab_dat_entry_name,
        pre_grab_dat_entry_source=pre_grab_dat_entry_source,
        hash_sha1=result.hash_sha1,
        hash_md5=getattr(result, "hash_md5", None),
        hash_crc32=result.hash_crc32,
        already_owned=already_owned,
        title_match_score=title_match_score,
        # Slice 402 — extra torznab/grabarr metadata.
        grabs=result.grabs,
        download_volume_factor=result.download_volume_factor,
        upload_volume_factor=result.upload_volume_factor,
        description=result.description,
        year=result.year,
        genre=result.genre,
        info_url=result.info_url,
        nfo_url=result.nfo_url,
    )


def _compute_match_score(
    title_match_score: int | None,
    breakdown: ScoreBreakdown,
) -> int:
    """Canonical 0-100 acquisition score — the single number the UI
    shows *and* ``auto_grab_min_score`` gates on, so "93 on screen"
    means "93 for the grab decision".

    Equal-weighted, both halves absolute:
      * identification — ``title_match_score`` (0-100): is this the
        right game? Defaults to 100 when unset — an accepted
        candidate matched its game, so identification cleared.
      * quality — the profile score (region + custom formats)
        clamped to 0-100: how good is this release.

    Absolute, NOT round-relative: the same release scores the same
    regardless of what else the round returned, so the value is
    stable to threshold against.
    """
    identification = (
        title_match_score if title_match_score is not None else 100
    )
    quality = max(0, min(100, breakdown.total))
    return round(identification * 0.5 + quality * 0.5)


def _accept(
    *,
    result: SearchResult,
    matched_game_id: int,
    matched_release_id: int | None,
    breakdown: ScoreBreakdown,
    pre_grab_dat_match: str,
    pre_grab_dat_entry_name: str | None = None,
    pre_grab_dat_entry_source: str | None = None,
    already_owned: bool = False,
    title_match_score: int | None = None,
    platform_id: int | None = None,
    naming_convention: Any = None,
    dump_status: Any = None,
) -> Candidate:
    # Slice 456 — soft scoring: a candidate is auto-reject-flagged
    # when the aggregate score (DAT bonus + region bonus minus
    # every malus) lands below ``AUTO_GRAB_FLOOR``. It's still a
    # fully rendered Candidate with a ``score_breakdown`` — manual
    # search shows it ranked; only auto-grab honours the flag.
    would_auto_reject = breakdown.total < AUTO_GRAB_FLOOR
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
        dump_status=(
            dump_status if dump_status is not None else result.dump_status
        ),
        naming_convention=(
            naming_convention
            if naming_convention is not None
            else result.naming_convention
        ),
        file_format=result.file_format,
        score_breakdown=breakdown,
        rejection=None,
        would_auto_reject=would_auto_reject,
        pre_grab_dat_match=pre_grab_dat_match,
        pre_grab_dat_entry_name=pre_grab_dat_entry_name,
        pre_grab_dat_entry_source=pre_grab_dat_entry_source,
        hash_sha1=result.hash_sha1,
        hash_md5=getattr(result, "hash_md5", None),
        hash_crc32=result.hash_crc32,
        already_owned=already_owned,
        title_match_score=title_match_score,
        match_score=_compute_match_score(title_match_score, breakdown),
        # Slice 402 — extra torznab/grabarr metadata.
        grabs=result.grabs,
        download_volume_factor=result.download_volume_factor,
        upload_volume_factor=result.upload_volume_factor,
        description=result.description,
        year=result.year,
        genre=result.genre,
        info_url=result.info_url,
        nfo_url=result.nfo_url,
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
    owned_lookup: Any = None,
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

    # ─────────────────────────────────────────────────────────────
    # Slice 456 — soft scoring. Past this point NOTHING hard-rejects:
    # every gate that used to ``return _reject(...)`` now appends a
    # negative ScoreContribution (a malus) instead. The candidate
    # always reaches ``_accept`` with a full ``score_breakdown``;
    # ``would_auto_reject`` is derived from whether the total lands
    # below ``AUTO_GRAB_FLOOR``. The two hard rejects above
    # (no-game-match, blocklist) stay — wrong platform / explicitly
    # banned content shouldn't even be ranked.
    # ─────────────────────────────────────────────────────────────
    contributions: list[ScoreContribution] = []

    # ---- 5: DAT cascade -------------------------------------------------------
    dat_info = dat_lookup(result.hash_sha1, result.hash_crc32)
    dat_outcome = dat_info.outcome
    dat_entry_name = dat_info.entry_name
    dat_entry_source = dat_info.entry_source
    if dat_outcome == "verified":
        contributions.append(
            ScoreContribution(
                source="dat_match",
                name="verified DAT match",
                value=DAT_VERIFIED_BONUS,
            )
        )

    # Owned-hash check — flag duplicates so the search modal can
    # warn the operator before a re-grab. Soft malus, not a reject:
    # the operator might genuinely want to re-pull a corrupt file.
    already_owned = False
    if owned_lookup is not None:
        already_owned = owned_lookup(
            matched_game.id,
            result.hash_sha1,
            getattr(result, "hash_md5", None),
            result.hash_crc32,
        )
    if already_owned:
        contributions.append(
            ScoreContribution(
                source="already_owned",
                name="hash already on disk for this game",
                value=PENALTY_ALREADY_OWNED,
            )
        )

    # Build the ReleaseFacts the profile evaluator + scorer expect.
    # Pass the DAT outcome through so ``dat_verified`` + the
    # naming-convention derivation land on the facts.
    facts = _release_facts_from_result(
        result,
        matched_release,
        file_format=file_format,
        dat_outcome=dat_outcome,
        dat_entry_source=dat_entry_source,
    )

    # ---- 6: Region — malus, never reject -------------------------------------
    region_outcome = ProfileEvaluator.evaluate_region(region_profile, facts)
    if region_outcome.decision is Decision.REJECT:
        excluded = (
            region_outcome.reason is not None
            and region_outcome.reason.code == "region_excluded"
        )
        contributions.append(
            ScoreContribution(
                source="region",
                name=(
                    f"region excluded {facts.regions!r}"
                    if excluded
                    else f"region not in priorities {facts.regions!r}"
                ),
                value=(
                    PENALTY_REGION_EXCLUDED
                    if excluded
                    else PENALTY_REGION_NOT_PRIORITY
                ),
            )
        )
    elif region_outcome.score:
        contributions.append(
            ScoreContribution(
                source="region",
                name=f"region {facts.regions!r}",
                value=region_outcome.score,
            )
        )

    # ---- 7: Language — malus, never reject -----------------------------------
    language_outcome = ProfileEvaluator.evaluate_language(
        language_profile, facts
    )
    if language_outcome.decision is Decision.REJECT:
        reason_code = (
            language_outcome.reason.code if language_outcome.reason else ""
        )
        contributions.append(
            ScoreContribution(
                source="language",
                name=(
                    language_outcome.reason.message
                    if language_outcome.reason
                    else "language gate"
                ),
                value=(
                    PENALTY_JAPANESE_ONLY
                    if reason_code == "japanese_only_excluded"
                    else PENALTY_LANGUAGE_MISSING
                ),
            )
        )

    # ---- 8: Dump status — malus, never reject --------------------------------
    dump_outcome = ProfileEvaluator.evaluate_dump(dump_profile, facts)
    if dump_outcome.decision is Decision.REJECT:
        contributions.append(
            ScoreContribution(
                source="dump_status",
                name=(
                    f"dump status {facts.dump_status.value!r} "
                    "not allowed by profile"
                ),
                value=PENALTY_DUMP_STATUS,
            )
        )

    # ---- 9: Quality / format — malus, never reject ---------------------------
    quality_outcome = ProfileEvaluator.evaluate_quality(
        quality_profile, facts
    )
    if quality_outcome.decision is Decision.REJECT:
        reason_code = (
            quality_outcome.reason.code if quality_outcome.reason else ""
        )
        if reason_code == "dat_required":
            contributions.append(
                ScoreContribution(
                    source="quality",
                    name="profile wants DAT-verified; release is not",
                    value=PENALTY_DAT_REQUIRED,
                )
            )
        else:
            # ``format_not_allowed`` — but the quality profile's
            # ``allowed_formats`` list is disc/archive-centric and
            # doesn't enumerate cartridge extensions. A ``.gba`` on
            # a GBA game is the platform's NATIVE format and must
            # not be penalised. Check the platform-format table
            # first; only a format that's neither native nor in
            # the profile list takes the malus.
            native_exts = {
                b.extension.lower().lstrip(".")
                for b in library_state.platform_format_bounds
                if b.platform_id == matched_game.platform_id
            }
            fmt = (facts.file_format or "").lower().lstrip(".")
            if fmt and fmt not in native_exts:
                contributions.append(
                    ScoreContribution(
                        source="quality",
                        name=(
                            f"file format {facts.file_format!r} not the "
                            "platform's native format"
                        ),
                        value=PENALTY_FORMAT_NOT_NATIVE,
                    )
                )

    # ---- 10: Custom Format scoring — one contribution per matched CF --------
    # Pre-slice this emitted a single opaque ``custom_format aggregate``
    # line; operators couldn't tell WHICH CustomFormat rejected a
    # candidate. Now every matched CF gets its own contribution
    # (source=custom_format, name=<CF name>, value=<CF score>) so the
    # breakdown reads e.g. ``custom_format · Non-ROM content · -10000``.
    # The rejector penalty is emitted as a separate summary line when
    # the aggregate crosses the threshold — the individual per-CF
    # values remain visible so the operator sees which format(s)
    # caused the rejection.
    matched_cfs = compute_matched_custom_formats(custom_formats, facts)
    cf_score = 0
    for cf_name, cf_value in matched_cfs:
        cf_score += cf_value
        contributions.append(
            ScoreContribution(
                source="custom_format",
                name=cf_name,
                value=cf_value,
            )
        )
    if cf_score <= -1000:  # Configurable rejector threshold per FR-011
        contributions.append(
            ScoreContribution(
                source="custom_format",
                name="rejector threshold reached",
                value=PENALTY_CUSTOM_FORMAT_REJECTOR,
            )
        )

    # ---- 11: Size bounds — malus, never reject -------------------------------
    if file_format and matched_release is not None:
        accepted, reason = _check_size_bounds(
            size_bytes=result.size_bytes,
            file_format=file_format,
            platform_id=matched_game.platform_id,
            bounds=library_state.platform_format_bounds,
        )
        if not accepted:
            contributions.append(
                ScoreContribution(
                    source="size",
                    name=reason or "size out of bounds",
                    value=PENALTY_SIZE_OUT_OF_BOUNDS,
                )
            )

    # ---- 12: Seeders threshold — malus, never reject -------------------------
    indexer = next(
        (m for m in library_state.indexer_meta if m.id == result.indexer_id),
        None,
    )
    if (
        indexer is not None
        and result.seeders is not None
        and result.seeders < indexer.min_seeders
    ):
        contributions.append(
            ScoreContribution(
                source="seeders",
                name=(
                    f"seeders {result.seeders} below indexer floor "
                    f"{indexer.min_seeders}"
                ),
                value=PENALTY_SEEDERS_LOW,
            )
        )

    # ---- 13: Aggregate --------------------------------------------------------
    total = sum(c.value for c in contributions)
    breakdown = ScoreBreakdown(total=total, contributions=contributions)
    # Slice 457 — when the DAT cascade VERIFIED the hash, the type
    # is authoritative: a verified entry is a clean, complete dump
    # (not a hack / demo / beta — those resolve to ``dat_outcome
    # == "hack"`` or never match). Promote the Candidate's
    # ``dump_status`` to VERIFIED so the type facet reads "complete
    # game" instead of whatever the filename parser guessed.
    effective_dump_status = result.dump_status
    if dat_outcome == "verified":
        from romarr.domain.enums import DumpStatus as _DS

        effective_dump_status = _DS.VERIFIED
    return _accept(
        result=result,
        matched_game_id=matched_game.id,
        matched_release_id=matched_release_id,
        breakdown=breakdown,
        pre_grab_dat_match=dat_outcome,
        pre_grab_dat_entry_name=dat_entry_name,
        pre_grab_dat_entry_source=dat_entry_source,
        already_owned=already_owned,
        platform_id=matched_game.platform_id,
        title_match_score=title_match_score,
        naming_convention=facts.naming_convention,
        dump_status=effective_dump_status,
    )


# Slice 456 — a verified DAT match implies the naming
# convention: the entry came from a No-Intro / Redump / TOSEC /
# GoodTools authority, so the release IS that convention even
# when the indexer's filename parser couldn't tell. Maps the
# DAT-source string onto the NamingConvention enum.
_DAT_SOURCE_TO_CONVENTION: dict[str, str] = {
    "no-intro": "no-intro",
    "redump": "redump",
    "tosec": "tosec",
    "goodtools": "goodtools",
}


def _release_facts_from_result(
    result: SearchResult,
    matched_release: MonitoredRelease | None,
    *,
    file_format: str,
    dat_outcome: str = "none",
    dat_entry_source: str | None = None,
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

    dat_verified = dat_outcome == "verified"
    # Slice 456 — when the cascade verified the hash, the naming
    # convention is whatever DAT authority owns the entry, no
    # matter what the filename parser guessed. Falls back to the
    # parsed value otherwise.
    naming_convention = result.naming_convention or NamingConvention.UNKNOWN
    if dat_verified and dat_entry_source:
        mapped = _DAT_SOURCE_TO_CONVENTION.get(dat_entry_source.lower())
        if mapped is not None:
            naming_convention = NamingConvention(mapped)

    return ReleaseFacts(
        title=result.title,
        regions=regions,
        languages=languages,
        revision=result.revision,
        dump_status=dump_status,
        tags=tuple(result.dump_tags or ()),
        naming_convention=naming_convention,
        file_format=file_format,
        dat_verified=dat_verified,
        indexer_source=None,
        release_size=result.size_bytes,
        release_group=None,
        # Free-form projections so Custom Formats can regex over the
        # URLs / notes the operator sees in the manual-search
        # detail. Populated from the indexer's SearchResult when
        # the extended attrs surfaced them.
        info_url=getattr(result, "info_url", None) or "",
        nfo_url=getattr(result, "nfo_url", None) or "",
        download_url=getattr(result, "link", None) or "",
        description=getattr(result, "description", None) or "",
        indexer_guid=getattr(result, "guid", None) or "",
    )


__all__ = ["DAT_VERIFIED_BONUS", "run_pipeline"]
