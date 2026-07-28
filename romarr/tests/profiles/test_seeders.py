"""First-boot seeder tests (T050-T052)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.profiles.models import (
    CustomFormat,
    DumpProfile,
    LanguageProfile,
    NamingProfile,
    QualityProfile,
    RegionProfile,
)
from romarr.profiles.seeders import SCENE_GROUPS, seed_defaults

# ---------------------------------------------------------------------------
# T050 — first boot inserts every documented row
# ---------------------------------------------------------------------------


async def test_first_boot_inserts_all_defaults(
    async_session: AsyncSession,
) -> None:
    counts = await seed_defaults(async_session)

    assert counts == {
        "quality.json": 3,
        "region.json": 3,
        "dump.json": 3,
        "language.json": 3,
        "naming.json": 3,
        "custom_formats.json": 18,
    }

    quality_count = (
        await async_session.execute(select(QualityProfile))
    ).scalars().all()
    assert len(quality_count) == 3

    region_count = (
        await async_session.execute(select(RegionProfile))
    ).scalars().all()
    assert len(region_count) == 3

    dump_count = (
        await async_session.execute(select(DumpProfile))
    ).scalars().all()
    assert len(dump_count) == 3

    language_count = (
        await async_session.execute(select(LanguageProfile))
    ).scalars().all()
    assert len(language_count) == 3

    naming_count = (
        await async_session.execute(select(NamingProfile))
    ).scalars().all()
    assert len(naming_count) == 3

    custom_format_count = (
        await async_session.execute(select(CustomFormat))
    ).scalars().all()
    assert len(custom_format_count) == 18


async def test_seeded_rows_are_factory_default_and_carry_seed_key(
    async_session: AsyncSession,
) -> None:
    await seed_defaults(async_session)

    quality_rows = (
        (await async_session.execute(select(QualityProfile))).scalars().all()
    )
    for row in quality_rows:
        assert row.is_factory_default is True
        assert row.is_user_modified is False
        assert row.seed_key  # non-empty


async def test_documented_seed_keys_present(
    async_session: AsyncSession,
) -> None:
    """Spot-check the data-model.md catalogue names."""
    await seed_defaults(async_session)

    seed_keys_by_table = {}
    for cls in (
        QualityProfile,
        RegionProfile,
        DumpProfile,
        LanguageProfile,
        NamingProfile,
        CustomFormat,
    ):
        rows = (await async_session.execute(select(cls))).scalars().all()
        seed_keys_by_table[cls.__tablename__] = {r.seed_key for r in rows}

    assert "preservation" in seed_keys_by_table["quality_profile"]
    assert "usa-first" in seed_keys_by_table["region_profile"]
    assert "preservation-strict" in seed_keys_by_table["dump_profile"]
    assert "fr-or-en" in seed_keys_by_table["language_profile"]
    assert "no-intro-standard" in seed_keys_by_table["naming_profile"]
    assert "verified-dump" in seed_keys_by_table["custom_format"]
    assert "hack" in seed_keys_by_table["custom_format"]


# ---------------------------------------------------------------------------
# T051 — idempotent rerun
# ---------------------------------------------------------------------------


async def test_idempotent_rerun_does_not_change_rows(
    async_session: AsyncSession,
) -> None:
    """Second invocation must report 0 changes per table."""
    first = await seed_defaults(async_session)
    # 3+3+3+3+3 profiles + 18 custom formats
    assert sum(first.values()) == 33

    second = await seed_defaults(async_session)
    assert all(count == 0 for count in second.values())


async def test_idempotent_rerun_preserves_updated_at(
    async_session: AsyncSession,
) -> None:
    """Second invocation MUST NOT bump ``updated_at`` since no values
    actually changed (T051)."""
    await seed_defaults(async_session)
    rows_before = (
        (await async_session.execute(select(QualityProfile))).scalars().all()
    )
    timestamps_before = {r.seed_key: r.updated_at for r in rows_before}

    await seed_defaults(async_session)

    rows_after = (
        (await async_session.execute(select(QualityProfile))).scalars().all()
    )
    timestamps_after = {r.seed_key: r.updated_at for r in rows_after}

    assert timestamps_before == timestamps_after


# ---------------------------------------------------------------------------
# T052 — operator edits are preserved (FR-003a)
# ---------------------------------------------------------------------------


async def test_user_edit_preserved_on_rerun(
    async_session: AsyncSession,
) -> None:
    """An operator-edited row stays untouched even when the seed JSON
    would otherwise change it."""
    await seed_defaults(async_session)

    pres = (
        await async_session.execute(
            select(QualityProfile).where(QualityProfile.seed_key == "preservation")
        )
    ).scalar_one()

    # Operator renames the profile + flips is_user_modified (the API
    # layer flips this in slice 5; the test simulates that here).
    pres.name = "Archive"
    pres.is_user_modified = True
    await async_session.commit()

    second = await seed_defaults(async_session)
    assert second["quality.json"] == 0

    refreshed = (
        await async_session.execute(
            select(QualityProfile).where(QualityProfile.seed_key == "preservation")
        )
    ).scalar_one()
    assert refreshed.name == "Archive"  # operator edit survived
    assert refreshed.is_user_modified is True


async def test_user_edit_is_factory_default_unchanged(
    async_session: AsyncSession,
) -> None:
    """is_factory_default tracks 'this row started life as a default',
    which is true forever once seeded — operator edits don't reset it."""
    await seed_defaults(async_session)

    pres = (
        await async_session.execute(
            select(QualityProfile).where(QualityProfile.seed_key == "preservation")
        )
    ).scalar_one()
    pres.is_user_modified = True
    pres.name = "Renamed"
    await async_session.commit()

    await seed_defaults(async_session)

    refreshed = (
        await async_session.execute(
            select(QualityProfile).where(QualityProfile.seed_key == "preservation")
        )
    ).scalar_one()
    assert refreshed.is_factory_default is True


# ---------------------------------------------------------------------------
# Drift handling — non-edited rows refresh when JSON values diverge
# ---------------------------------------------------------------------------


async def test_drift_in_factory_row_is_refreshed(
    async_session: AsyncSession,
) -> None:
    """A non-edited row whose values drift from the JSON gets refreshed
    on next boot — covers the 'release evolves the default' path."""
    await seed_defaults(async_session)

    pres = (
        await async_session.execute(
            select(QualityProfile).where(QualityProfile.seed_key == "preservation")
        )
    ).scalar_one()
    # Simulate a stale value (as if a prior release seeded the wrong format).
    # The runner will not touch is_user_modified, so it remains false.
    pres.preferred_format = "raw"  # actual JSON ships "7z"
    await async_session.commit()

    counts = await seed_defaults(async_session)
    assert counts["quality.json"] == 1

    refreshed = (
        await async_session.execute(
            select(QualityProfile).where(QualityProfile.seed_key == "preservation")
        )
    ).scalar_one()
    assert refreshed.preferred_format == "7z"


# ---------------------------------------------------------------------------
# Scene groups list is loadable
# ---------------------------------------------------------------------------


def test_scene_groups_loaded_at_import_time() -> None:
    assert isinstance(SCENE_GROUPS, list)
    assert all(isinstance(g, str) for g in SCENE_GROUPS)
    assert len(SCENE_GROUPS) >= 3
    # spot-check a documented entry
    assert "DEMENT" in SCENE_GROUPS


# ---------------------------------------------------------------------------
# Naming profile templates round-trip through the sandbox engine
# ---------------------------------------------------------------------------


async def test_seeded_naming_templates_validate_in_sandbox(
    async_session: AsyncSession,
) -> None:
    """Every seeded naming template parses cleanly under the engine —
    catches a typo in naming.json before it lands in a release.
    """
    from romarr.profiles.naming import NamingTemplateEngine

    await seed_defaults(async_session)
    engine = NamingTemplateEngine()
    rows = (
        (await async_session.execute(select(NamingProfile))).scalars().all()
    )
    for row in rows:
        engine.validate(row.template)


# ---------------------------------------------------------------------------
# Future-time guarantee — older + newer seed_at don't matter
# ---------------------------------------------------------------------------


async def test_seed_runs_clean_when_factory_row_freshly_inserted(
    async_session: AsyncSession,
) -> None:
    """Edge case: a row inserted with non-default timestamps must not
    trip the seeder into thinking it's been edited."""
    now = datetime.now(UTC) - timedelta(days=30)
    # Slice 403 — broader allowed_formats list in the seeded
    # JSON. Pre-populate the row with the exact same list so the
    # pre-existing branch (no update) still exercises here; the
    # other two seeded rows are still missing → +2 inserts.
    async_session.add(
        QualityProfile(
            seed_key="preservation",
            name="Preservation",
            allowed_formats=[
                "raw", "zip", "7z", "rar",
                "iso", "cue", "bin", "img", "gdi", "mdf", "nrg",
                "chd", "rvz", "wbfs", "wia", "nkit", "ciso", "cso", "pbp",
            ],
            preferred_format="7z",
            require_dat_verified=False,
            allow_archive_double_compression=False,
            upgrade_until_format="7z",
            is_factory_default=True,
            is_user_modified=False,
            created_at=now,
            updated_at=now,
        )
    )
    await async_session.commit()

    counts = await seed_defaults(async_session)
    # The pre-existing row already matches the JSON, so it isn't
    # updated; the other two missing rows ARE inserted (= 2 changes).
    assert counts["quality.json"] == 2

    pres = (
        await async_session.execute(
            select(QualityProfile).where(QualityProfile.seed_key == "preservation")
        )
    ).scalar_one()
    # SQLite doesn't preserve tzinfo on round-trip — compare bare values.
    assert pres.updated_at.replace(tzinfo=UTC) == now  # untouched
