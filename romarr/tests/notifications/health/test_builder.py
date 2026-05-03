"""HealthEngine builder tests (spec 011 T057)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.indexers.models import Indexer
from romarr.libraries.models import Library
from romarr.notifications.health.builder import build_health_engine
from romarr.profiles.models import (
    DumpProfile,
    LanguageProfile,
    NamingProfile,
    QualityProfile,
    RegionProfile,
)


async def _seed_default_profiles(
    sm: async_sessionmaker[AsyncSession],
) -> dict[str, int]:
    async with sm() as session:
        quality = QualityProfile(
            name="quality-default",
            allowed_formats=["raw"],
            preferred_format="raw",
            require_dat_verified=False,
            upgrade_until_format="raw",
        )
        region = RegionProfile(
            name="region-default",
            priorities=["USA"],
            allow_fallback_outside_priorities=True,
            exclude_regions=[],
        )
        dump = DumpProfile(
            name="dump-default",
            allowed_dump_status=["verified"],
            allow_proto_beta=False,
            allow_hacks=False,
            allow_trainers=False,
            allow_translations=False,
        )
        language = LanguageProfile(
            name="language-default",
            required_languages=[],
            preferred_languages=["en"],
            exclude_japanese_only=False,
        )
        naming = NamingProfile(
            name="naming-default",
            convention="no-intro",
            template="{{ game.title }}",
        )
        session.add_all([quality, region, dump, language, naming])
        await session.commit()
        return {
            "quality_profile_id": quality.id,
            "region_profile_id": region.id,
            "dump_profile_id": dump.id,
            "language_profile_id": language.id,
            "naming_profile_id": naming.id,
        }
from romarr.notifications.health.checks.db import DbHealthCheck
from romarr.notifications.health.checks.disk_space import (
    DiskSpaceHealthCheck,
)
from romarr.notifications.health.checks.indexer import IndexerHealthCheck
from romarr.notifications.health.checks.library_path import (
    LibraryPathHealthCheck,
)
from romarr.metadata.health import MetadataCacheSizeHealthCheck


@pytest.mark.asyncio
async def test_empty_config_yields_db_and_cache_checks_only(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Fresh DB → only the always-on infrastructure checks."""
    engine = await build_health_engine(async_sessionmaker_factory)
    types = {type(c) for c in engine._checks}
    assert DbHealthCheck in types
    assert MetadataCacheSizeHealthCheck in types
    # No libraries / indexers / etc. seeded.
    assert IndexerHealthCheck not in types
    assert LibraryPathHealthCheck not in types


@pytest.mark.asyncio
async def test_seeded_library_yields_path_and_disk_checks(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    tmp_path,
) -> None:
    """One Library row → a path check + a disk-space check
    using its ``min_disk_free_gb``."""
    sm = async_sessionmaker_factory
    profile_ids = await _seed_default_profiles(sm)
    async with sm() as session:
        session.add(
            Library(
                name="My Library",
                path=str(tmp_path),
                lifecycle_policy="hardlink_and_seed",
                min_disk_free_gb=10,
                **profile_ids,
            )
        )
        await session.commit()

    engine = await build_health_engine(sm)
    library_checks = [
        c for c in engine._checks
        if isinstance(c, LibraryPathHealthCheck)
    ]
    disk_checks = [
        c for c in engine._checks
        if isinstance(c, DiskSpaceHealthCheck)
    ]
    assert len(library_checks) == 1
    assert len(disk_checks) == 1
    assert disk_checks[0].min_free_gb == 10


@pytest.mark.asyncio
async def test_seeded_indexer_yields_indexer_check(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Every configured Indexer row → one IndexerHealthCheck.
    The Indexer model splits the "enabled" flag into per-flow
    booleans (enable_rss / enable_automatic_search /
    enable_interactive_search); a configured row gets a probe
    regardless so the operator sees reachability problems."""
    sm = async_sessionmaker_factory
    async with sm() as session:
        session.add(
            Indexer(
                name="A",
                implementation="newznab",
                url="https://idx.test/api",
                categories=[1060],
                source="manual",
            )
        )
        session.add(
            Indexer(
                name="B",
                implementation="newznab",
                url="https://idx2.test/api",
                categories=[1060],
                source="manual",
            )
        )
        await session.commit()

    engine = await build_health_engine(sm)
    indexer_checks = [
        c for c in engine._checks
        if isinstance(c, IndexerHealthCheck)
    ]
    assert len(indexer_checks) == 2


@pytest.mark.asyncio
async def test_engine_runs_returns_a_snapshot(
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The built engine actually refresh()es — the always-on
    DB check probes ``SELECT 1`` against the same session
    factory so the snapshot reports at least one OK
    component."""
    engine = await build_health_engine(async_sessionmaker_factory)
    snapshot = await engine.refresh()
    all_results = [
        r
        for results in snapshot.by_category.values()
        for r in results
    ]
    components = [r.component for r in all_results]
    assert "db" in components
    # The DB component MUST resolve to OK (we just did a
    # round-trip into it via `_seed`-like queries).
    db_result = next(r for r in all_results if r.component == "db")
    assert db_result.status.value == "ok"
