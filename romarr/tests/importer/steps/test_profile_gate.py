"""Profile-gate step tests (T053, T054)."""

from __future__ import annotations

from dataclasses import dataclass, field

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.importer.steps.profile_gate import apply_profile_gate
from romarr.importer.types import RejectionReason
from romarr.profiles.types import ReleaseFacts

# ---------------------------------------------------------------------------
# Duck-typed profile shapes (the evaluators don't care whether they
# come from ORM rows, Pydantic schemas, or plain dataclasses).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Quality:
    allowed_formats: list[str] = field(default_factory=lambda: ["7z"])
    preferred_format: str = "7z"
    require_dat_verified: bool = False
    upgrade_until_format: str = "7z"


@dataclass(frozen=True)
class _Region:
    priorities: list[str] = field(default_factory=lambda: ["USA"])
    allow_fallback_outside_priorities: bool = True
    exclude_regions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Dump:
    allowed_dump_status: list[str] = field(
        default_factory=lambda: ["verified"]
    )
    allow_proto_beta: bool = False
    allow_hacks: bool = False
    allow_trainers: bool = False
    allow_translations: bool = False


@dataclass(frozen=True)
class _Language:
    required_languages: list[str] = field(default_factory=list)
    preferred_languages: list[str] = field(default_factory=lambda: ["en"])
    exclude_japanese_only: bool = False


def _facts(**overrides: object) -> ReleaseFacts:
    base: dict[str, object] = {
        "title": "Sonic the Hedgehog",
        "regions": ("USA",),
        "languages": ("en",),
        "dump_status": DumpStatus.VERIFIED,
        "tags": (),
        "naming_convention": NamingConvention.NO_INTRO,
        "file_format": "7z",
        "dat_verified": True,
        "indexer_source": None,
        "release_size": 1024,
    }
    base.update(overrides)
    return ReleaseFacts(**base)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# T053 — every gate ACCEPTs ⇒ passed
# ---------------------------------------------------------------------------


def test_all_gates_accept() -> None:
    result = apply_profile_gate(
        quality=_Quality(),
        region=_Region(),
        dump=_Dump(),
        language=_Language(),
        facts=_facts(),
    )
    assert result.passed is True
    assert result.rejection_reason is None
    assert result.warning is None


def test_quality_reject_returns_structured_reason() -> None:
    # Slice 403 made archive containers (zip / 7z / rar / …)
    # transparent in the quality gate. Use a non-container family
    # (chd) so the reject path still fires.
    result = apply_profile_gate(
        quality=_Quality(allowed_formats=["raw"]),  # chd not allowed
        region=_Region(),
        dump=_Dump(),
        language=_Language(),
        facts=_facts(file_format="chd"),
    )
    assert result.passed is False
    assert result.rejection_reason is RejectionReason.PROFILE_QUALITY_REJECT
    assert result.failing_gate == "quality"


def test_region_reject_returns_structured_reason() -> None:
    result = apply_profile_gate(
        quality=_Quality(),
        region=_Region(exclude_regions=["JPN"]),
        dump=_Dump(),
        language=_Language(),
        facts=_facts(regions=("JPN",)),
    )
    assert result.passed is False
    assert result.rejection_reason is RejectionReason.PROFILE_REGION_REJECT
    assert result.failing_gate == "region"


def test_dump_reject_returns_structured_reason() -> None:
    result = apply_profile_gate(
        quality=_Quality(),
        region=_Region(),
        dump=_Dump(),  # only verified allowed
        language=_Language(),
        facts=_facts(
            dump_status=DumpStatus.HACK,
            tags=("[h]",),
        ),
    )
    assert result.passed is False
    assert result.rejection_reason is RejectionReason.PROFILE_DUMP_REJECT


def test_language_reject_returns_structured_reason() -> None:
    result = apply_profile_gate(
        quality=_Quality(),
        region=_Region(),
        dump=_Dump(),
        language=_Language(required_languages=["fr"]),
        facts=_facts(languages=("en",)),
    )
    assert result.passed is False
    assert result.rejection_reason is RejectionReason.PROFILE_LANGUAGE_REJECT


def test_first_failing_gate_in_fixed_order() -> None:
    """When multiple gates would reject, the first-rejecting gate
    in the fixed Q→R→D→L order surfaces — deterministic across
    reruns."""
    result = apply_profile_gate(
        quality=_Quality(allowed_formats=["raw"]),  # rejects chd
        region=_Region(exclude_regions=["USA"]),  # would reject too
        dump=_Dump(),
        language=_Language(),
        facts=_facts(file_format="chd"),
    )
    assert result.failing_gate == "quality"


# ---------------------------------------------------------------------------
# T054 — force=True converts rejection into a warning
# ---------------------------------------------------------------------------


def test_force_overrides_rejection_into_warning() -> None:
    # Slice 403 — use ``chd`` (not an archive container) so the
    # quality gate actually fires the reject branch ``force``
    # is meant to override.
    result = apply_profile_gate(
        quality=_Quality(allowed_formats=["raw"]),
        region=_Region(),
        dump=_Dump(),
        language=_Language(),
        facts=_facts(file_format="chd"),
        force=True,
    )
    assert result.passed is True
    assert result.rejection_reason is RejectionReason.PROFILE_QUALITY_REJECT
    assert result.warning is not None
    assert "force_overrode" in result.warning
    assert result.failing_gate == "quality"


def test_force_on_passing_gate_is_no_op() -> None:
    """A force-import that wouldn't have been rejected anyway
    produces a clean pass — no spurious warning."""
    result = apply_profile_gate(
        quality=_Quality(),
        region=_Region(),
        dump=_Dump(),
        language=_Language(),
        facts=_facts(),
        force=True,
    )
    assert result.passed is True
    assert result.warning is None
