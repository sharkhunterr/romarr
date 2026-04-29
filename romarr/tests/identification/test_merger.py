"""Identification merger tests — FR-010 / FR-011 / FR-012 / FR-013 / FR-029.

Spec 001 acceptance scenarios (User Story 5):
1. filename = USA + DAT = EUR → EUR wins, conflict logged, confidence -10%
2. filename has [h] but DAT verified → DAT wins, discrepancy logged
3. all four sources agree → confidence = max, no penalty
"""

from __future__ import annotations

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.identification.merger import (
    CONFLICT_PENALTY,
    UNIDENTIFIED_THRESHOLD,
    IdentificationSource,
    SourceContribution,
    merge,
)


def test_merge_no_contributions_returns_unidentified() -> None:
    result = merge([])
    assert result.confidence == 0.0
    assert result.is_unidentified
    assert result.dump_status == DumpStatus.UNKNOWN


def test_merge_single_filename_source() -> None:
    contrib = SourceContribution(
        source=IdentificationSource.FILENAME,
        confidence=0.85,
        title="Sonic the Hedgehog",
        regions=("US",),
        naming_convention=NamingConvention.NO_INTRO,
    )
    result = merge([contrib])
    assert result.title == "Sonic the Hedgehog"
    assert result.regions == ("US",)
    assert result.confidence == 0.85
    assert result.conflicts == ()
    assert not result.is_unidentified


def test_merge_filename_usa_vs_dat_eur_eur_wins(
) -> None:
    """Acceptance scenario 5.1 — DAT (hash) outranks filename for region."""
    filename = SourceContribution(
        source=IdentificationSource.FILENAME,
        confidence=0.85,
        title="Sonic the Hedgehog",
        regions=("US",),
        naming_convention=NamingConvention.NO_INTRO,
    )
    dat_via_hash = SourceContribution(
        source=IdentificationSource.HASH,
        confidence=1.0,
        title="Sonic the Hedgehog",
        regions=("EU",),
        dump_status=DumpStatus.VERIFIED,
    )

    result = merge([filename, dat_via_hash])
    # Hash authority wins on region.
    assert result.regions == ("EU",)
    # One conflict was recorded → flat 10% reduction (CL004).
    assert len(result.conflicts) == 1
    assert result.conflicts[0].field == "regions"
    assert result.conflicts[0].winner_source == IdentificationSource.HASH
    assert result.conflicts[0].loser_source == IdentificationSource.FILENAME
    # Base = max(1.0, 0.85) = 1.0; penalty = 0.10 → 0.90.
    assert abs(result.confidence - 0.90) < 1e-6


def test_merge_filename_hack_vs_dat_verified_dat_wins() -> None:
    """Acceptance scenario 5.2 / FR-013 — DAT verified beats filename [h]."""
    filename = SourceContribution(
        source=IdentificationSource.FILENAME,
        confidence=0.85,
        title="Sonic the Hedgehog",
        dump_status=DumpStatus.HACK,
    )
    dat = SourceContribution(
        source=IdentificationSource.HASH,
        confidence=1.0,
        title="Sonic the Hedgehog",
        dump_status=DumpStatus.VERIFIED,
    )
    result = merge([filename, dat])
    assert result.dump_status == DumpStatus.VERIFIED
    assert any(c.field == "dump_status" for c in result.conflicts)


def test_merge_all_sources_agree_no_penalty() -> None:
    """Acceptance scenario 5.3 — agreement → max confidence, no penalty."""
    common = {
        "title": "Sonic the Hedgehog",
        "regions": ("US",),
        "dump_status": DumpStatus.VERIFIED,
    }
    contrib = [
        SourceContribution(source=IdentificationSource.HASH, confidence=1.0, **common),
        SourceContribution(source=IdentificationSource.TORZNAB, confidence=0.9, **common),
        SourceContribution(source=IdentificationSource.HEADER, confidence=0.8, **common),
        SourceContribution(source=IdentificationSource.FILENAME, confidence=0.85, **common),
    ]
    result = merge(contrib)
    assert result.conflicts == ()
    assert result.confidence == 1.0


def test_merge_conflict_penalty_does_not_stack(
) -> None:
    """CL004: regardless of conflict count, penalty is a flat 10%."""
    filename = SourceContribution(
        source=IdentificationSource.FILENAME,
        confidence=0.85,
        title="Sonic Hedgehog Different",
        regions=("US",),
        languages=("en",),
        dump_status=DumpStatus.HACK,
    )
    dat = SourceContribution(
        source=IdentificationSource.HASH,
        confidence=1.0,
        title="Sonic the Hedgehog",
        regions=("EU",),
        languages=("fr",),
        dump_status=DumpStatus.VERIFIED,
    )
    result = merge([filename, dat])
    # Multiple conflicts (title + regions + languages + dump_status) but
    # the penalty is applied ONCE.
    assert len(result.conflicts) >= 3
    assert abs(result.confidence - (1.0 - CONFLICT_PENALTY)) < 1e-6


def test_merge_threshold_routes_low_confidence_to_unidentified() -> None:
    """CL007 / FR-029 — confidence < 0.5 → ``is_unidentified``."""
    only = SourceContribution(
        source=IdentificationSource.FILENAME,
        confidence=0.4,
        title="??? something",
    )
    result = merge([only])
    assert result.is_unidentified
    assert result.confidence < UNIDENTIFIED_THRESHOLD


def test_merge_threshold_boundary_at_0_5_inclusive() -> None:
    """``confidence == 0.5`` is NOT treated as unidentified (FR-029 says ``< 0.5``)."""
    contrib = SourceContribution(
        source=IdentificationSource.FILENAME, confidence=0.5, title="x"
    )
    result = merge([contrib])
    assert not result.is_unidentified


def test_merge_authority_order_torznab_beats_header() -> None:
    """FR-011: TORZNAB > HEADER for any disagreement."""
    header = SourceContribution(
        source=IdentificationSource.HEADER,
        confidence=0.7,
        platform_slug="megacd",
    )
    torznab = SourceContribution(
        source=IdentificationSource.TORZNAB,
        confidence=0.6,
        platform_slug="megadrive",
    )
    result = merge([header, torznab])
    assert result.platform_slug == "megadrive"  # TORZNAB authority wins
    assert any(c.field == "platform_slug" for c in result.conflicts)


def test_merge_extra_fields_higher_authority_overrides() -> None:
    filename = SourceContribution(
        source=IdentificationSource.FILENAME,
        confidence=0.8,
        extra={"year": "1991", "publisher": "Sega"},
    )
    dat = SourceContribution(
        source=IdentificationSource.HASH,
        confidence=1.0,
        extra={"year": "1992"},
    )
    result = merge([filename, dat])
    assert result.extra["year"] == "1992"  # hash overrides
    assert result.extra["publisher"] == "Sega"  # only filename had it


def test_merge_purity_invariant() -> None:
    """Identical inputs → byte-for-byte identical outputs."""
    contributions = [
        SourceContribution(
            source=IdentificationSource.HASH,
            confidence=1.0,
            title="Sonic",
            regions=("US",),
        ),
        SourceContribution(
            source=IdentificationSource.FILENAME,
            confidence=0.85,
            title="Sonic",
            regions=("EU",),
        ),
    ]
    a = merge(contributions)
    b = merge(contributions)
    assert a == b
