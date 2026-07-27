"""Shared scoring helpers for search-round orchestrators.

Both ``manual.py`` and ``rss.py`` need the same pre-pipeline batch
work: turn the hashes shipped by the round's raw indexer results into
a DAT lookup (``dat_entry`` join) and an owned-hash lookup (``dump``
join) so the pure pipeline can score with full information.

Extracting them here keeps a single source of truth for the grab
decision — RSS auto-grabs and the operator's manual-search modal
must produce identical scores on identical input, otherwise
"meilleur score" diverges between the two flows.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Literal

from sqlalchemy import or_, select

from romarr.domain.enums import DumpStatus
from romarr.domain.models import DatEntry, Dump, Release
from romarr.search.state import DatMatchInfo, _NONE_DAT_INFO

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def none_dat(_a: str | None, _b: str | None) -> DatMatchInfo:
    """Fallback DAT lookup — used when no platform scope is given
    (so we can't safely query ``dat_entry`` without risking
    cross-platform hash collisions) or when no candidate ships a
    usable hash. Returns the singleton "no match" info.
    """
    return _NONE_DAT_INFO


def none_owned(
    _game: int | None, _sha1: str | None, _md5: str | None, _crc: str | None
) -> bool:
    return False


def _status_to_outcome(status: str) -> Literal["verified", "hack", "none"]:
    if status == DumpStatus.VERIFIED.value:
        return "verified"
    if status in (
        DumpStatus.HACK.value,
        DumpStatus.BADDUMP.value,
    ):
        return "hack"
    return "none"


async def build_db_dat_lookup(
    session: "AsyncSession",
    platform_id: int | None,
    hashes_sha1: set[str],
    hashes_crc32: set[str],
    *,
    platform_ids: set[int] | None = None,
) -> Callable[[str | None, str | None], DatMatchInfo]:
    """Pre-fetch ``dat_entry`` rows whose hashes appear in the
    candidate set, then expose a sync closure for the pipeline.

    Two scoping modes:
      * ``platform_id`` set → single-platform manual search; query
        scoped tight so cross-platform hash collisions never leak.
      * ``platform_ids`` set (RSS path) → multi-platform pull, scoped
        to the platforms of the games the RSS feed actually matched.
        Wider but still bounded; rank ordering keeps the strongest
        ``DumpStatus`` outcome when the same hash spans two
        platforms (extremely rare).

    Returns :func:`none_dat` when no hashes were supplied or when
    neither scope can constrain the query (no platform at all → too
    risky, fall back to "no match" rather than serve poisoned data).
    """
    if not hashes_sha1 and not hashes_crc32:
        return none_dat

    if platform_id is None and not platform_ids:
        return none_dat

    where_clauses = [
        or_(
            DatEntry.sha1.in_(hashes_sha1) if hashes_sha1 else False,
            DatEntry.crc32.in_(hashes_crc32) if hashes_crc32 else False,
        ),
    ]
    if platform_id is not None:
        where_clauses.insert(0, DatEntry.platform_id == platform_id)
    elif platform_ids:
        where_clauses.insert(0, DatEntry.platform_id.in_(platform_ids))

    rows = (
        await session.execute(
            select(
                DatEntry.sha1,
                DatEntry.crc32,
                DatEntry.status,
                DatEntry.source,
                DatEntry.name,
            ).where(*where_clauses)
        )
    ).all()
    by_sha1: dict[str, DatMatchInfo] = {}
    by_crc32: dict[str, DatMatchInfo] = {}
    # CL001 authority order is enforced by best_match — for the
    # pre-grab cascade a single "is this hash known?" answer is
    # enough, so keep the strongest outcome (verified > hack >
    # none) when the same hash spans multiple sources.
    rank = {"verified": 2, "hack": 1, "none": 0}
    for sha1, crc32, status, src, name in rows:
        outcome = _status_to_outcome(status)
        info = DatMatchInfo(
            outcome=outcome, entry_name=name, entry_source=src
        )
        if sha1 and rank[outcome] > rank.get(
            by_sha1.get(sha1, _NONE_DAT_INFO).outcome, 0
        ):
            by_sha1[sha1] = info
        if crc32 and rank[outcome] > rank.get(
            by_crc32.get(crc32, _NONE_DAT_INFO).outcome, 0
        ):
            by_crc32[crc32] = info

    def _lookup(sha1: str | None, crc32: str | None) -> DatMatchInfo:
        if sha1 and sha1.lower() in by_sha1:
            return by_sha1[sha1.lower()]
        if crc32 and crc32.lower() in by_crc32:
            return by_crc32[crc32.lower()]
        return _NONE_DAT_INFO

    return _lookup


async def build_owned_lookup(
    session: "AsyncSession",
    game_ids: set[int],
    hashes_sha1: set[str],
    hashes_md5: set[str],
    hashes_crc32: set[str],
) -> Callable[[int | None, str | None, str | None, str | None], bool]:
    """Pre-fetch every ``Dump.{sha1, md5, crc32}`` bound to the
    candidate set's matched games, then expose a sync closure that
    answers "does this game already have a Dump with one of these
    hashes?".

    Used to flag duplicates so the operator (and the RSS auto-grab
    decision) don't re-grab a file that already lives on disk.
    Returns False on any input when no game_id is supplied or the
    hash set is empty.
    """
    if not game_ids or not (hashes_sha1 or hashes_md5 or hashes_crc32):
        return none_owned

    rows = (
        await session.execute(
            select(
                Release.game_id, Dump.sha1, Dump.md5, Dump.crc32
            )
            .join(Release, Release.id == Dump.release_id)
            .where(
                Release.game_id.in_(game_ids),
                or_(
                    Dump.sha1.in_(hashes_sha1) if hashes_sha1 else False,
                    Dump.md5.in_(hashes_md5) if hashes_md5 else False,
                    Dump.crc32.in_(hashes_crc32) if hashes_crc32 else False,
                ),
            )
        )
    ).all()
    owned_sha1: set[tuple[int, str]] = set()
    owned_md5: set[tuple[int, str]] = set()
    owned_crc32: set[tuple[int, str]] = set()
    for game_id, sha1, md5, crc32 in rows:
        if sha1:
            owned_sha1.add((int(game_id), sha1.lower()))
        if md5:
            owned_md5.add((int(game_id), md5.lower()))
        if crc32:
            owned_crc32.add((int(game_id), crc32.lower()))

    def _lookup(
        game_id: int | None,
        sha1: str | None,
        md5: str | None,
        crc32: str | None,
    ) -> bool:
        if game_id is None:
            return False
        if sha1 and (game_id, sha1.lower()) in owned_sha1:
            return True
        if md5 and (game_id, md5.lower()) in owned_md5:
            return True
        if crc32 and (game_id, crc32.lower()) in owned_crc32:
            return True
        return False

    return _lookup


async def load_min_score_for_game(
    session: "AsyncSession", game_id: int
) -> int:
    """Resolve the ``auto_grab_min_score`` floor that applies to
    one game.

    Cascade:
      1. Game.library_id → Library.quality_profile_id → profile
      2. Fall back to the first ``QualityProfile`` (factory default)
         when the game has no library binding yet.
      3. 0 when no profile exists at all.

    Each auto-grab round (RSS / on-add / missing / cutoff) calls
    this per game so the threshold honours the operator's per-
    library cascade instead of always reading the first profile in
    the table.
    """
    from sqlalchemy import select as _select

    from romarr.domain.models import Game
    from romarr.libraries.models import Library
    from romarr.profiles.models import QualityProfile

    game = (
        await session.execute(_select(Game).where(Game.id == game_id))
    ).scalar_one_or_none()
    profile: QualityProfile | None = None
    if game is not None and game.library_id is not None:
        library = (
            await session.execute(
                _select(Library).where(Library.id == game.library_id)
            )
        ).scalar_one_or_none()
        if library is not None:
            profile = (
                await session.execute(
                    _select(QualityProfile).where(
                        QualityProfile.id == library.quality_profile_id
                    )
                )
            ).scalar_one_or_none()
    if profile is None:
        profile = (
            await session.execute(_select(QualityProfile).limit(1))
        ).scalar_one_or_none()
    return max(0, int(getattr(profile, "auto_grab_min_score", 0) or 0))


async def load_min_scores_by_game(
    session: "AsyncSession", game_ids: set[int]
) -> dict[int, int]:
    """Batch variant of :func:`load_min_score_for_game` — one
    SQL roundtrip per profile cascade instead of one per game.

    Used by RSS sync where the same round may touch dozens of
    distinct games (each potentially bound to a different
    library + quality profile).
    """
    from sqlalchemy import select as _select

    from romarr.domain.models import Game
    from romarr.libraries.models import Library
    from romarr.profiles.models import QualityProfile

    if not game_ids:
        return {}

    games = (
        await session.execute(
            _select(Game.id, Game.library_id).where(Game.id.in_(game_ids))
        )
    ).all()
    lib_ids = {lid for _gid, lid in games if lid is not None}
    library_to_quality: dict[int, int] = {}
    if lib_ids:
        for lib_id, quality_profile_id in (
            await session.execute(
                _select(Library.id, Library.quality_profile_id).where(
                    Library.id.in_(lib_ids)
                )
            )
        ).all():
            library_to_quality[int(lib_id)] = int(quality_profile_id)

    profile_ids = set(library_to_quality.values())
    profiles_by_id: dict[int, QualityProfile] = {}
    if profile_ids:
        for row in (
            await session.execute(
                _select(QualityProfile).where(
                    QualityProfile.id.in_(profile_ids)
                )
            )
        ).scalars().all():
            profiles_by_id[row.id] = row

    fallback_profile = (
        await session.execute(_select(QualityProfile).limit(1))
    ).scalar_one_or_none()
    fallback_floor = max(
        0,
        int(getattr(fallback_profile, "auto_grab_min_score", 0) or 0),
    )

    out: dict[int, int] = {}
    for game_id, library_id in games:
        if library_id is not None:
            quality_id = library_to_quality.get(int(library_id))
            if quality_id is not None:
                profile = profiles_by_id.get(quality_id)
                if profile is not None:
                    out[int(game_id)] = max(
                        0,
                        int(
                            getattr(profile, "auto_grab_min_score", 0) or 0
                        ),
                    )
                    continue
        out[int(game_id)] = fallback_floor
    return out


async def dispatch_best_for_game(
    session: "AsyncSession",
    *,
    game_id: int,
    candidates: list,
    min_score: int = 0,
) -> dict:
    """Pick the best eligible candidate for ``game_id`` and dispatch.

    Manual search returns ``report.grabs=[]`` by contract (operator
    picks), so every auto-grab path (RSS, on-add, missing, cutoff)
    has to re-derive the winner from ``report.candidates`` and call
    :func:`dispatch_winner` itself. This helper centralises that
    logic so the four paths can't drift.

    Eligibility, in order:
      1. ``matched_game_id == game_id`` (released the manual search
         was scoped to a different game vs the one we want)
      2. ``rejection is None`` (every soft gate passed)
      3. ``match_score >= min_score`` — the operator floor is gated
         on the SAME canonical 0-100 score the search UI shows, so
         "93 on screen" means "93 for this decision".

    Returns a structured dict the caller can stash in its summary:
      * ``dispatched`` (bool) — True iff a candidate landed in the
        download client.
      * ``best_score`` (int|None) — the top candidate's canonical
        ``match_score`` (the same 0-100 number the UI shows), or None
        when no candidate matched the game at all.
      * ``no_grab_reason`` (str|None) — same vocabulary the RSS
        round emits so the History modal renders identical labels.
      * ``status`` (str|None) — ``DispatchStatus.value`` when we
        actually called the dispatcher.
    """
    from romarr.downloaders.is_configured import is_client_configured
    from romarr.downloaders.models import DownloadClient
    from romarr.downloaders.routing import RoutingCandidate
    from romarr.search._clients import make_download_client_factory
    from romarr.search.dispatch import DispatchStatus, dispatch_winner

    # Defensive: callers (and tests) sometimes pass loosely-typed
    # placeholders. Skip anything that doesn't carry the Candidate
    # shape so a stray string never crashes the auto-grab round.
    matching = [
        c
        for c in candidates
        if getattr(c, "matched_game_id", None) == game_id
    ]
    if not matching:
        return {
            "dispatched": False,
            "best_score": None,
            "no_grab_reason": "unidentified",
            "status": None,
        }

    eligible = [
        c
        for c in matching
        if c.rejection is None
        and c.match_score is not None
        and c.match_score >= min_score
    ]

    if not eligible:
        rejected = [c for c in matching if c.rejection is not None]
        if rejected:
            return {
                "dispatched": False,
                "best_score": None,
                "no_grab_reason": (
                    f"rejected: {rejected[0].rejection.code.value}"
                ),
                "status": None,
            }
        scored = [c for c in matching if c.match_score is not None]
        if not scored:
            return {
                "dispatched": False,
                "best_score": None,
                "no_grab_reason": "score_too_low",
                "status": None,
            }
        best_clean = max(scored, key=lambda c: c.match_score or 0)
        best_score = best_clean.match_score
        return {
            "dispatched": False,
            "best_score": best_score,
            "no_grab_reason": f"below_min_score: {best_score}/{min_score}",
            "status": None,
        }

    best = max(eligible, key=lambda c: c.match_score or 0)

    from sqlalchemy import select as _select

    # Anti-double-grab guard: if the matched game already has at
    # least one ``imported`` Release, the auto-grab paths must
    # stand down — the operator has the title on disk and any
    # quality upgrade is the cutoff-search round's job (which
    # gates on ``cutoff_met=False``). Without this guard a
    # second RSS-sync tick would re-grab the same game over and
    # over because every fresh feed item matches the existing
    # game_id and re-passes the score floor.
    from romarr.domain.models import Release as _Release

    already_imported = (
        await session.execute(
            _select(_Release.id)
            .where(_Release.game_id == game_id)
            .where(_Release.status == "imported")
            .limit(1)
        )
    ).scalar_one_or_none()
    if already_imported is not None:
        return {
            "dispatched": False,
            "best_score": best.match_score,
            "no_grab_reason": (
                f"already_imported: release #{already_imported}"
            ),
            "status": None,
        }

    client_rows = (
        (await session.execute(_select(DownloadClient))).scalars().all()
    )
    routing_candidates = [
        RoutingCandidate(
            id=r.id,
            priority=r.priority,
            enabled=r.enabled,
            enable_for_torrents=r.enable_for_torrents,
            enable_for_usenet=r.enable_for_usenet,
            is_configured=is_client_configured(r),
        )
        for r in client_rows
    ]
    download_factory = make_download_client_factory(session)
    outcome = await dispatch_winner(
        candidate=best,
        candidates=routing_candidates,
        client_factory=download_factory,
    )
    dispatched = outcome.status is DispatchStatus.GRABBED

    # When the dispatch landed in the download client, we MUST
    # register a queue_entry that binds the client's native id
    # back to the game we just auto-grabbed for. Without this row
    # the importer fans out the completed file via filename
    # parsing alone and falls back to ``match:no_game`` for
    # anything the DAT / hash lookup can't resolve. The manual
    # grab API at ``search/api/grab.py`` does the same insert,
    # so this keeps the auto path on the same contract.
    if dispatched and outcome.client_native_id:
        await _ensure_queue_entry_for_grab(
            session,
            game_id=game_id,
            release_id=best.matched_release_id,
            candidate_title=getattr(best, "title", None),
            client_id=outcome.client_id,
            client_native_id=outcome.client_native_id,
        )

    return {
        "dispatched": dispatched,
        "best_score": best.match_score,
        "no_grab_reason": (
            None
            if dispatched
            # Include the dispatcher's underlying ``reason`` when it
            # supplied one — a bare ``pending_retry`` tells the
            # operator nothing about which client failed or why,
            # while ``pending_retry: transient: Deluge auth failed``
            # points straight at the fix.
            else _fmt_dispatch_reason(outcome)
        ),
        "status": outcome.status.value,
    }


def _fmt_dispatch_reason(outcome: object) -> str:
    """Combine DispatchOutcome.status + .reason into the operator
    string. ``dispatch_failed: <status>`` when no reason is set,
    ``dispatch_failed: <status>: <reason>`` otherwise.
    """
    status = getattr(outcome, "status", None)
    status_val = getattr(status, "value", status)
    reason = getattr(outcome, "reason", None)
    if reason:
        # Truncate long stack-traces to keep the summary readable.
        r = str(reason).strip().splitlines()[0][:180]
        return f"dispatch_failed: {status_val}: {r}"
    return f"dispatch_failed: {status_val}"


async def _ensure_queue_entry_for_grab(
    session: "AsyncSession",
    *,
    game_id: int,
    release_id: int | None,
    candidate_title: str | None,
    client_id: int | None,
    client_native_id: str,
) -> None:
    """Insert a ``queue_entry`` row tying the download-client
    native id back to ``game_id`` (+ ``release_id`` when the
    candidate already had one). Idempotent on
    ``(download_client_id, download_client_native_id)``.

    Why this lives in the auto-grab path and not in
    :func:`dispatch_winner`: the dispatcher is a pure adapter
    between Candidate and DownloadClient. Persistence is the
    caller's concern — the manual grab API does it inline for
    its own grabs, and the auto-grab paths now do it via this
    helper.

    We deliberately DO NOT pre-create a placeholder ``Release``
    row when ``release_id`` is None. The importer's normal flow
    (orchestrator's "slice 369 + 441") resolves the file via DAT
    + name and creates / reuses the right Release authoritatively;
    a synthetic placeholder would just lose the filename-match
    race (the importer matches on ``Release.name == source.stem``
    and the torrent/feed name almost never equals the No-Intro
    DAT name), leaving a stray "unknown" row next to the real
    "imported" one. The queue_entry's ``game_id`` alone is enough
    — the dispatcher threads it to the importer as
    ``pre_matched_game_id`` so DAT runs scoped to that game.
    """
    from sqlalchemy import select as _select

    from romarr.api.models import QueueEntry

    existing = (
        await session.execute(
            _select(QueueEntry).where(
                QueueEntry.download_client_id == client_id,
                QueueEntry.download_client_native_id == client_native_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Reconciler / earlier write already created the row —
        # back-fill the bindings so the importer can identify it
        # next tick. ``state`` / ``progress`` we leave alone
        # because the reconciler owns those.
        if existing.release_id is None and release_id is not None:
            existing.release_id = release_id
        if existing.game_id is None:
            existing.game_id = game_id
        if not existing.title and candidate_title:
            existing.title = candidate_title
    else:
        session.add(
            QueueEntry(
                release_id=release_id,
                game_id=game_id,
                title=candidate_title,
                download_client_id=client_id,
                download_client_native_id=client_native_id,
                state="downloading",
                progress=0.0,
            )
        )
    await session.commit()


__all__ = [
    "build_db_dat_lookup",
    "build_owned_lookup",
    "dispatch_best_for_game",
    "load_min_score_for_game",
    "load_min_scores_by_game",
    "none_dat",
    "none_owned",
]
