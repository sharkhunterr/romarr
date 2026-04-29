"""Multi-source identification merger.

Combines up to four sources per FR-010:
    1. ``hash`` — DAT-cache / Hasheous / PlayMatch lookup (highest authority)
    2. ``torznab`` — extended Torznab attributes from the indexer
    3. ``header`` — header reader output (iNES / Mega Drive / ISO9660)
    4. ``filename`` — filename parser output (No-Intro / Redump / TOSEC / GoodTools / Scene)

Per FR-011, when sources disagree on a field, the highest-authority
source wins. Per FR-012 (clarified to a flat cap, CL004), the merged
confidence MUST be reduced by exactly **10%** when one or more
conflicts fire, regardless of conflict count. Per FR-029 (CL007),
a merged confidence below 0.5 routes the file to ``unidentified_dump``.

The merger is a pure function: identical inputs ⇒ identical outputs;
no I/O; no logging side effects beyond the structured ``Conflict``
record list returned alongside the result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from romarr.domain.enums import DumpStatus, NamingConvention

# ---------------------------------------------------------------------------
# Source taxonomy + threshold constants
# ---------------------------------------------------------------------------


class IdentificationSource(StrEnum):
    """Authority order for FR-011 conflict resolution.

    Order matters: ``HASH`` wins over ``TORZNAB`` wins over ``HEADER``
    wins over ``FILENAME``.
    """

    HASH = "hash"
    TORZNAB = "torznab"
    HEADER = "header"
    FILENAME = "filename"


_AUTHORITY_RANK: dict[IdentificationSource, int] = {
    IdentificationSource.HASH: 0,
    IdentificationSource.TORZNAB: 1,
    IdentificationSource.HEADER: 2,
    IdentificationSource.FILENAME: 3,
}


CONFLICT_PENALTY = 0.10
"""Flat confidence reduction when one or more conflicts fire (CL004 / FR-012)."""

UNIDENTIFIED_THRESHOLD = 0.5
"""Files below this merged confidence route to ``unidentified_dump`` (CL007 / FR-029)."""


# ---------------------------------------------------------------------------
# Per-source contribution shape
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class SourceContribution:
    """One source's offer to the merger.

    ``confidence`` is the source's own confidence in its findings; the
    merger uses it both for the per-field winner and for the merged
    overall confidence (which is the max across contributing sources,
    minus the conflict penalty).
    """

    source: IdentificationSource
    confidence: float
    title: str | None = None
    platform_slug: str | None = None
    regions: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    revision: str | None = None
    dump_status: DumpStatus | None = None
    naming_convention: NamingConvention | None = None
    serial: str | None = None
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Conflict:
    """A single field-level disagreement between sources.

    Stored on the merged result so the operator (or a UI) can see why
    the confidence was penalised.
    """

    field: str
    winner_source: IdentificationSource
    winner_value: object
    loser_source: IdentificationSource
    loser_value: object


@dataclass(frozen=True, slots=True)
class MergedIdentification:
    """The structured output of :func:`merge`."""

    title: str | None
    platform_slug: str | None
    regions: tuple[str, ...]
    languages: tuple[str, ...]
    revision: str | None
    dump_status: DumpStatus
    naming_convention: NamingConvention
    serial: str | None
    confidence: float
    contributing_sources: tuple[IdentificationSource, ...]
    conflicts: tuple[Conflict, ...]
    extra: dict[str, str]

    @property
    def is_unidentified(self) -> bool:
        """``True`` when confidence falls below the FR-029 threshold."""
        return self.confidence < UNIDENTIFIED_THRESHOLD


# ---------------------------------------------------------------------------
# Merge implementation
# ---------------------------------------------------------------------------


def merge(contributions: list[SourceContribution]) -> MergedIdentification:
    """Merge multiple :class:`SourceContribution` values into one result.

    Pure function. ``contributions`` is the union of every source that
    actually had something to say (callers should drop sources that
    found nothing rather than passing zero-confidence shapes).

    The merger:
      1. Sorts contributions by FR-011 authority rank.
      2. For each canonical field, walks contributions in authority
         order and adopts the first non-empty value as the winner.
      3. Records every loser → winner disagreement as a :class:`Conflict`.
      4. Sets merged ``confidence = max(c.confidence for c in contributions)``,
         then subtracts a flat ``CONFLICT_PENALTY`` if any conflicts
         fired (FR-012 / CL004 — never stacked).
    """
    if not contributions:
        return MergedIdentification(
            title=None,
            platform_slug=None,
            regions=(),
            languages=(),
            revision=None,
            dump_status=DumpStatus.UNKNOWN,
            naming_convention=NamingConvention.UNKNOWN,
            serial=None,
            confidence=0.0,
            contributing_sources=(),
            conflicts=(),
            extra={},
        )

    # Sort once — every per-field walk uses this canonical order.
    ordered = sorted(contributions, key=lambda c: _AUTHORITY_RANK[c.source])

    conflicts: list[Conflict] = []
    extra: dict[str, str] = {}

    title = _pick_scalar(ordered, "title", conflicts)
    platform_slug = _pick_scalar(ordered, "platform_slug", conflicts)
    revision = _pick_scalar(ordered, "revision", conflicts)
    serial = _pick_scalar(ordered, "serial", conflicts)
    dump_status = _pick_dump_status(ordered, conflicts)
    naming_convention = _pick_naming_convention(ordered, conflicts)

    regions = _pick_tuple(ordered, "regions", conflicts)
    languages = _pick_tuple(ordered, "languages", conflicts)

    # Merge ``extra`` dicts in reverse authority order so higher
    # sources overwrite lower ones for any shared key.
    for c in reversed(ordered):
        for k, v in c.extra.items():
            extra[k] = v

    # Confidence: max across contributors, minus a flat 10% if any
    # conflict fired (CL004).
    base_confidence = max(c.confidence for c in ordered)
    if conflicts:
        merged_confidence = max(0.0, base_confidence - CONFLICT_PENALTY)
    else:
        merged_confidence = base_confidence

    return MergedIdentification(
        title=title,
        platform_slug=platform_slug,
        regions=regions,
        languages=languages,
        revision=revision,
        dump_status=dump_status or DumpStatus.UNKNOWN,
        naming_convention=naming_convention or NamingConvention.UNKNOWN,
        serial=serial,
        confidence=merged_confidence,
        contributing_sources=tuple(c.source for c in ordered),
        conflicts=tuple(conflicts),
        extra=extra,
    )


# ---------------------------------------------------------------------------
# Per-field pickers
# ---------------------------------------------------------------------------


def _pick_scalar(
    ordered: list[SourceContribution],
    field_name: str,
    conflicts: list[Conflict],
) -> str | None:
    """Pick a scalar field from the highest-authority non-empty source.

    A "loser" disagreement is recorded for every other source that
    proposed a different (non-empty) value. Per FR-013 a special-case
    is also captured here: filename ``[h]`` (hack) overruled by a DAT
    ``verified`` is a recordable conflict even though the merger
    already picked the DAT value.
    """
    winner: SourceContribution | None = None
    winner_value: str | None = None
    for c in ordered:
        v = getattr(c, field_name)
        if v in (None, ""):
            continue
        if winner is None:
            winner = c
            winner_value = v
        elif v != winner_value:
            conflicts.append(
                Conflict(
                    field=field_name,
                    winner_source=winner.source,
                    winner_value=winner_value,
                    loser_source=c.source,
                    loser_value=v,
                )
            )
    return winner_value


def _pick_tuple(
    ordered: list[SourceContribution],
    field_name: str,
    conflicts: list[Conflict],
) -> tuple[str, ...]:
    """Pick a tuple-valued field (regions / languages).

    Higher authority wins outright when non-empty. Lower-authority
    sources whose set differs from the winner generate a conflict
    record.
    """
    winner: SourceContribution | None = None
    winner_value: tuple[str, ...] = ()
    for c in ordered:
        v: tuple[str, ...] = getattr(c, field_name)
        if not v:
            continue
        if winner is None:
            winner = c
            winner_value = v
        elif set(v) != set(winner_value):
            conflicts.append(
                Conflict(
                    field=field_name,
                    winner_source=winner.source,
                    winner_value=winner_value,
                    loser_source=c.source,
                    loser_value=v,
                )
            )
    return winner_value


def _pick_dump_status(
    ordered: list[SourceContribution], conflicts: list[Conflict]
) -> DumpStatus | None:
    """Specialised picker for ``dump_status`` to encode FR-013.

    FR-013: when filename indicates ``[h]`` (hack) but DAT match
    reports verified, the DAT MUST win and the discrepancy MUST be
    logged. The standard authority order already produces the right
    winner; we just need to record the conflict.
    """
    winner_source: IdentificationSource | None = None
    winner_value: DumpStatus | None = None
    for c in ordered:
        if c.dump_status is None or c.dump_status == DumpStatus.UNKNOWN:
            continue
        if winner_source is None:
            winner_source = c.source
            winner_value = c.dump_status
        elif c.dump_status != winner_value:
            conflicts.append(
                Conflict(
                    field="dump_status",
                    winner_source=winner_source,
                    winner_value=winner_value,
                    loser_source=c.source,
                    loser_value=c.dump_status,
                )
            )
    return winner_value


def _pick_naming_convention(
    ordered: list[SourceContribution], conflicts: list[Conflict]
) -> NamingConvention | None:
    winner_source: IdentificationSource | None = None
    winner_value: NamingConvention | None = None
    for c in ordered:
        if c.naming_convention is None or c.naming_convention == NamingConvention.UNKNOWN:
            continue
        if winner_source is None:
            winner_source = c.source
            winner_value = c.naming_convention
        elif c.naming_convention != winner_value:
            conflicts.append(
                Conflict(
                    field="naming_convention",
                    winner_source=winner_source,
                    winner_value=winner_value,
                    loser_source=c.source,
                    loser_value=c.naming_convention,
                )
            )
    return winner_value
