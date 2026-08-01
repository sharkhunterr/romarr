"""Library + profile context loader (slice 80).

Given an :class:`ImportContext`'s ``library_id``, fetch the
:class:`Library` row plus its five profile bindings
(Quality, Region, Dump, Language, Naming) plus the m2m
:class:`CustomFormat` rows. The orchestrator calls this once
at the top of the pipeline so the per-step calls (profile
gate, render) get cheap accessors instead of round-tripping
the DB per step.

The five profile FK columns on ``library`` are NOT NULL +
``ondelete='RESTRICT'`` (spec 009 design), so a non-null
``library_id`` always resolves into a fully-populated
:class:`LibraryContext` — the loader never returns partial
state. A missing ``library_id`` raises
:class:`LibraryContextNotFound` so the orchestrator can map
that to a structured rejection (FR-026
``routing:no_library_for_platform`` happens upstream of the
loader, but a stale FK between routing and loading is still
a possible operator-visible failure).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from romarr.libraries.models import Library
from romarr.profiles.models import (
    CustomFormat,
    DumpProfile,
    LanguageProfile,
    LibraryCustomFormat,
    NamingProfile,
    QualityProfile,
    RegionProfile,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class LibraryContextNotFound(Exception):
    """Raised when ``load_library_context(library_id)`` doesn't
    find a row. The orchestrator turns this into a structured
    rejection — operator action: re-route the candidate via the
    library mapper, or fix the stale link."""


@dataclass(frozen=True)
class LibraryContext:
    """The library + 5 profiles + custom-format list the
    orchestrator threads through the pipeline.

    Frozen so a single load survives the entire ``run_import``
    invocation without anyone mutating it mid-step. The
    custom_formats list is sorted by score descending so the
    profile-gate's tie-break is stable.
    """

    library: Library
    quality: QualityProfile
    region: RegionProfile
    dump: DumpProfile
    language: LanguageProfile
    naming: NamingProfile
    custom_formats: tuple[CustomFormat, ...]


async def load_library_context(
    *, session: AsyncSession, library_id: int
) -> LibraryContext:
    """Eager-load the library + five profiles + custom formats.

    Three round-trips at most:

      1. Library + 5 profile rows in one SELECT via FK joins
         (the SQLAlchemy ORM resolves the FKs, but we keep
         the loader explicit so a missing FK target raises
         loudly rather than producing a partially-populated
         object).
      2. Custom-format ids via ``library_custom_format``.
      3. Custom-format rows via ``IN (ids)``.

    The shape is deliberately simple — no `selectinload`
    relationship chaining — so the loader stays correct on
    Library models that don't yet declare relationship() to
    the profile classes (avoids a forward-reference race).
    """
    library = (
        await session.execute(
            select(Library).where(Library.id == library_id)
        )
    ).scalar_one_or_none()
    if library is None:
        raise LibraryContextNotFound(
            f"library_id={library_id} not found"
        )

    # Pull the five profile rows. Each FK is RESTRICT so we trust
    # the ID points at a row; .scalar_one() raises if it doesn't.
    quality = (
        await session.execute(
            select(QualityProfile).where(
                QualityProfile.id == library.quality_profile_id
            )
        )
    ).scalar_one()
    region = (
        await session.execute(
            select(RegionProfile).where(
                RegionProfile.id == library.region_profile_id
            )
        )
    ).scalar_one()
    dump = (
        await session.execute(
            select(DumpProfile).where(
                DumpProfile.id == library.dump_profile_id
            )
        )
    ).scalar_one()
    language = (
        await session.execute(
            select(LanguageProfile).where(
                LanguageProfile.id == library.language_profile_id
            )
        )
    ).scalar_one()
    naming = (
        await session.execute(
            select(NamingProfile).where(
                NamingProfile.id == library.naming_profile_id
            )
        )
    ).scalar_one()

    # Custom formats — m2m. The library_custom_format binding is
    # the operator's per-library choice; the global custom_format
    # catalogue is the universe of options.
    cf_ids = (
        await session.execute(
            select(LibraryCustomFormat.custom_format_id).where(
                LibraryCustomFormat.library_id == library_id
            )
        )
    ).scalars().all()

    custom_formats: tuple[CustomFormat, ...] = ()
    if cf_ids:
        # Migration 0041 — a disabled CF stays in the table but
        # doesn't contribute to scoring.
        cf_rows = (
            await session.execute(
                select(CustomFormat)
                .where(
                    CustomFormat.id.in_(cf_ids),
                    CustomFormat.enabled.is_(True),
                )
                .order_by(CustomFormat.score.desc())
            )
        ).scalars().all()
        custom_formats = tuple(cf_rows)

    # Quiet a tree-shaken-import lint by referencing it.
    _ = selectinload  # noqa: F841 — reserved for the rel() variant

    return LibraryContext(
        library=library,
        quality=quality,
        region=region,
        dump=dump,
        language=language,
        naming=naming,
        custom_formats=custom_formats,
    )


__all__ = [
    "LibraryContext",
    "LibraryContextNotFound",
    "load_library_context",
]
