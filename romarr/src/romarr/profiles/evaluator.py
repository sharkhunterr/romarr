"""Pure-function profile evaluators (Phase 3 — Article V invariant).

Four evaluators, one per gating profile type — Quality, Region,
Dump, Language. Each takes a profile (ORM row OR Pydantic
``*Create`` shape; only attribute access matters), a
:class:`ReleaseFacts` snapshot, and returns an
:class:`EvaluationResult`.

Constitutional invariants:

  * **Purity** (FR-007 / SC-002). No DB session, no logging, no
    time, no random. Same input ⇒ same output, every time.
  * **Profile-driven decisions** (Article V). Every grab/upgrade/
    import decision the search engine or importer makes flows
    through these functions; no hardcoded gameplay-style policy
    leaks into the consumer specs.

The Custom Format scorer is :func:`romarr.profiles.scoring.compute_custom_format_score`.
"""

from __future__ import annotations

from typing import Any, Protocol

from romarr.domain.enums import DumpStatus
from romarr.profiles.types import (
    Decision,
    EvaluationReason,
    EvaluationResult,
    ReleaseFacts,
)

# ---------------------------------------------------------------------------
# Protocols — duck-typed inputs so the evaluator works against ORM rows
# AND against in-memory Pydantic ``*Create`` shapes during tests / preview.
# ---------------------------------------------------------------------------


class _QualityShape(Protocol):
    allowed_formats: list[str]
    preferred_format: str
    require_dat_verified: bool
    upgrade_until_format: str


class _RegionShape(Protocol):
    priorities: list[str]
    allow_fallback_outside_priorities: bool
    exclude_regions: list[str]


class _DumpShape(Protocol):
    allowed_dump_status: list[str]
    allow_proto_beta: bool
    allow_hacks: bool
    allow_trainers: bool
    allow_translations: bool


class _LanguageShape(Protocol):
    required_languages: list[str]
    preferred_languages: list[str]
    exclude_japanese_only: bool


# ---------------------------------------------------------------------------
# Permissive-flag map for Dump
# ---------------------------------------------------------------------------


_PERMISSIVE_FLAGS: dict[DumpStatus, str] = {
    DumpStatus.HACK: "allow_hacks",
    DumpStatus.TRAINER: "allow_trainers",
    DumpStatus.TRANSLATION: "allow_translations",
    DumpStatus.PROTO: "allow_proto_beta",
    DumpStatus.BETA: "allow_proto_beta",
}


def _accept(code: str, message: str, *, score: int = 0, field: str | None = None) -> EvaluationResult:
    return EvaluationResult(
        decision=Decision.ACCEPT,
        reason=EvaluationReason(field=field, code=code, message=message),
        score=score,
    )


def _reject(code: str, message: str, *, field: str | None = None) -> EvaluationResult:
    return EvaluationResult(
        decision=Decision.REJECT,
        reason=EvaluationReason(field=field, code=code, message=message),
        score=0,
    )


# Slice 403 — archive containers are transparent for the quality
# gate. They wrap the actual ROM dump; the importer extracts them
# and the gate runs again on the inner file format. Rejecting a
# release for being a ``.rar`` would just block content that
# would have passed once unwrapped, which is a footgun (the user's
# PSX ``.rar`` of an ``.iso`` shouldn't fail at search time
# because the profile happened to spell out ``zip + 7z`` only).
_UNIVERSAL_ARCHIVE_CONTAINERS = frozenset(
    {"zip", "rar", "7z", "tar", "gz", "bz2", "xz"}
)


class ProfileEvaluator:
    """Static-method facade for the four pure evaluators.

    Class wrapper rather than module-level functions because the
    consumer specs (search, importer) want a single import surface
    and a stable public API name. Every method MUST stay pure.
    """

    # ---- Quality (FR-009..FR-012) -----------------------------------------

    @staticmethod
    def evaluate_quality(
        profile: _QualityShape, facts: ReleaseFacts
    ) -> EvaluationResult:
        if profile.require_dat_verified and not facts.dat_verified:
            return _reject(
                "dat_required",
                "profile requires DAT verification; release is unverified",
                field="dat_verified",
            )
        # Slice 403 — archive containers (zip / rar / 7z / tar / …)
        # are transparent: pass through regardless of
        # ``allowed_formats`` because the importer extracts them and
        # the gate runs again on the inner file. Avoids the common
        # footgun where a PSX ``.rar`` of an ``.iso`` is rejected
        # at search time despite being fine once unwrapped.
        if (
            facts.file_format
            and facts.file_format.lower() in _UNIVERSAL_ARCHIVE_CONTAINERS
        ):
            return _accept(
                "container_format",
                f"file_format {facts.file_format!r} is a universal "
                "archive container — gate defers to inner format",
                field="file_format",
            )
        if facts.file_format and facts.file_format not in profile.allowed_formats:
            return _reject(
                "format_not_allowed",
                f"file_format {facts.file_format!r} not in allowed_formats",
                field="file_format",
            )
        if facts.file_format == profile.upgrade_until_format:
            return _accept(
                "cutoff_met",
                f"file_format equals upgrade_until_format {profile.upgrade_until_format!r}",
                field="file_format",
            )
        return _accept(
            "format_allowed",
            f"file_format {facts.file_format!r} accepted",
            field="file_format",
        )

    # ---- Region (FR-013..FR-016) ------------------------------------------

    @staticmethod
    def evaluate_region(
        profile: _RegionShape, facts: ReleaseFacts
    ) -> EvaluationResult:
        # Excluded regions are rejected outright (FR-014). If ANY of
        # the release's regions is in the exclude list, reject.
        for region in facts.regions:
            if region in profile.exclude_regions:
                return _reject(
                    "region_excluded",
                    f"region {region!r} is in exclude_regions",
                    field="region",
                )

        # Priority match: pick the BEST score across the release's regions.
        # ``score = len(priorities) - index`` (FR-013 rewritten in the
        # session-2026-04-29 clarifications).
        best_score: int | None = None
        for region in facts.regions:
            if region in profile.priorities:
                idx = profile.priorities.index(region)
                candidate = len(profile.priorities) - idx
                if best_score is None or candidate > best_score:
                    best_score = candidate

        if best_score is not None:
            return _accept(
                "region_priority_match",
                f"matched priority region with score {best_score}",
                score=best_score,
                field="region",
            )

        # No priority match. Fallback path:
        if profile.allow_fallback_outside_priorities:
            return _accept(
                "region_fallback",
                "no priority match; fallback enabled",
                score=0,
                field="region",
            )
        return _reject(
            "region_not_in_priorities",
            "no region in priorities and fallback disabled",
            field="region",
        )

    # ---- Dump (FR-017..FR-019) --------------------------------------------

    @staticmethod
    def evaluate_dump(
        profile: _DumpShape, facts: ReleaseFacts
    ) -> EvaluationResult:
        status_str = facts.dump_status.value
        if status_str in profile.allowed_dump_status:
            return _accept(
                "dump_status_allowed",
                f"dump_status {status_str!r} is allowlisted",
                field="dump_status",
            )
        # Permissive flag map — hacks / trainers / translations / proto-beta.
        flag = _PERMISSIVE_FLAGS.get(facts.dump_status)
        if flag is not None and getattr(profile, flag, False):
            return _accept(
                "dump_status_permissive",
                f"{status_str!r} accepted via {flag}",
                field="dump_status",
            )
        return _reject(
            "dump_status_disallowed",
            f"dump_status {status_str!r} not allowed by profile",
            field="dump_status",
        )

    # ---- Language (FR-020 / FR-022) ---------------------------------------

    @staticmethod
    def evaluate_language(
        profile: _LanguageShape, facts: ReleaseFacts
    ) -> EvaluationResult:
        # Japanese-only exclusion: when the release's languages are
        # exactly ``("ja",)`` and the profile excludes it, reject.
        if (
            profile.exclude_japanese_only
            and len(facts.languages) == 1
            and facts.languages[0] == "ja"
        ):
            return _reject(
                "japanese_only_excluded",
                "release is Japanese-only and profile excludes JA-only",
                field="languages",
            )

        # required_languages is any-of: at least one must be present.
        if profile.required_languages:
            release_langs = set(facts.languages)
            if not release_langs.intersection(profile.required_languages):
                return _reject(
                    "required_language_missing",
                    f"none of required_languages {sorted(profile.required_languages)!r} "
                    f"present in {sorted(release_langs)!r}",
                    field="languages",
                )

        return _accept(
            "language_allowed",
            "release languages satisfy the profile",
            field="languages",
        )


def evaluate_all(
    *,
    quality: _QualityShape,
    region: _RegionShape,
    dump: _DumpShape,
    language: _LanguageShape,
    facts: ReleaseFacts,
) -> dict[str, EvaluationResult]:
    """Run all four evaluators against one release; return their results.

    Convenience for the search engine / importer — keeps each
    evaluator's purity invariant intact since the wrapper itself
    has no side effects. The dict keys are stable: ``"quality"``,
    ``"region"``, ``"dump"``, ``"language"``.
    """
    return {
        "quality": ProfileEvaluator.evaluate_quality(quality, facts),
        "region": ProfileEvaluator.evaluate_region(region, facts),
        "dump": ProfileEvaluator.evaluate_dump(dump, facts),
        "language": ProfileEvaluator.evaluate_language(language, facts),
    }


# Re-export ``Any`` so static checkers don't complain about the protocol attrs
# being declared as plain ``list[str]`` — Pydantic models satisfy these.
_ = Any


__all__ = ["ProfileEvaluator", "evaluate_all"]
