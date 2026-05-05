"""CL007 — confidence-threshold boundary at 0.5 (spec 001 FR-029).

The four documented cascade entry points and their expected
confidence vs. the 0.5 routing threshold:

* hash match           → ~1.0 → through (NOT unidentified)
* No-Intro filename    → ~0.85 → through (NOT unidentified)
* header read only     → ~0.6 → through (NOT unidentified)
* bare guess (<0.5)    → unidentified_dump

The merger is the single source of truth for the threshold. These
tests pin the contract so a future tweak to per-source confidence
constants doesn't silently push the bare-guess case above the
parking threshold or the header-only case below it.
"""

from __future__ import annotations

from romarr.identification.merger import (
    UNIDENTIFIED_THRESHOLD,
    IdentificationSource,
    SourceContribution,
    merge,
)


def test_hash_match_confidence_above_threshold() -> None:
    """Hash-match sources contribute confidence ~1.0 → routed through."""
    contrib = SourceContribution(
        source=IdentificationSource.HASH,
        confidence=1.0,
        title="Sonic the Hedgehog",
        platform_slug="megadrive",
    )
    result = merge([contrib])

    assert not result.is_unidentified
    assert result.confidence >= UNIDENTIFIED_THRESHOLD
    assert result.confidence == 1.0


def test_no_intro_filename_confidence_above_threshold() -> None:
    """No-Intro filename parser contributes ~0.85 → routed through."""
    contrib = SourceContribution(
        source=IdentificationSource.FILENAME,
        confidence=0.85,
        title="Sonic the Hedgehog",
        regions=("USA",),
    )
    result = merge([contrib])

    assert not result.is_unidentified
    assert result.confidence >= UNIDENTIFIED_THRESHOLD
    assert result.confidence == 0.85


def test_header_only_confidence_above_threshold() -> None:
    """Header reader alone contributes ~0.6 → routed through."""
    contrib = SourceContribution(
        source=IdentificationSource.HEADER,
        confidence=0.6,
        platform_slug="nes",
    )
    result = merge([contrib])

    assert not result.is_unidentified
    assert result.confidence >= UNIDENTIFIED_THRESHOLD
    assert result.confidence == 0.6


def test_bare_guess_below_threshold_routes_to_unidentified() -> None:
    """A confidence below 0.5 routes the file to unidentified_dump."""
    contrib = SourceContribution(
        source=IdentificationSource.FILENAME,
        confidence=0.3,
        title="ambiguous-rom",
    )
    result = merge([contrib])

    assert result.is_unidentified
    assert result.confidence < UNIDENTIFIED_THRESHOLD


def test_threshold_is_strictly_less_than() -> None:
    """``confidence == 0.5`` is NOT considered unidentified.

    Pinned here so a future ``<=`` regression on the threshold
    boundary is caught alongside the four canonical entry points.
    """
    contrib = SourceContribution(
        source=IdentificationSource.FILENAME,
        confidence=UNIDENTIFIED_THRESHOLD,
        title="boundary-rom",
    )
    result = merge([contrib])

    assert not result.is_unidentified
    assert result.confidence == UNIDENTIFIED_THRESHOLD


def test_multi_source_agreement_above_threshold() -> None:
    """When multiple sources contribute, the max wins → through."""
    contribs = [
        SourceContribution(
            source=IdentificationSource.HASH,
            confidence=1.0,
            title="Sonic the Hedgehog",
        ),
        SourceContribution(
            source=IdentificationSource.FILENAME,
            confidence=0.85,
            title="Sonic the Hedgehog",
            regions=("USA",),
        ),
    ]
    result = merge(contribs)

    assert not result.is_unidentified
    assert result.confidence == 1.0


def test_conflict_penalty_can_drop_below_threshold() -> None:
    """A 0.55 base + conflict penalty → 0.45 → falls below threshold.

    Ensures the threshold check applies AFTER the conflict penalty
    is subtracted (CL004), so a near-boundary identification with
    disagreement still routes to ``unidentified_dump``.
    """
    contribs = [
        SourceContribution(
            source=IdentificationSource.HEADER,
            confidence=0.55,
            platform_slug="nes",
        ),
        SourceContribution(
            source=IdentificationSource.FILENAME,
            confidence=0.55,
            platform_slug="snes",
        ),
    ]
    result = merge(contribs)

    assert result.is_unidentified
    assert result.confidence < UNIDENTIFIED_THRESHOLD
    assert len(result.conflicts) > 0
