"""Profile force-delete cascade tests (spec 006 T073/T074/T076).

The DELETE handler walks ``library.{type}_profile_id`` for each
of the five profile types and surfaces a 409 with the blocking
library names when the profile is still bound. CustomFormat is
bound via the ``library_custom_format`` m2m which has
``ondelete=CASCADE`` on the FK, so the DELETE just works there.

The current cascade implementation always 409s on bound NOT NULL
FKs; ``?force=true`` is accepted on the surface for forward-
compatibility but doesn't change the behaviour today (a
substitute-rebind semantic would require either making the FKs
nullable or reading a "factory default" id).
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

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
from tests.profiles.api.conftest import seed_user_and_login


async def _seed_one_of_each_profile(
    engine: AsyncEngine,
) -> dict[str, int]:
    """Seed one row of each of the five profile types so a Library
    has valid FKs to bind. Returns the ids by short label."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        q = QualityProfile(
            name="Q-Test",
            allowed_formats=["raw"],
            preferred_format="raw",
            upgrade_until_format="raw",
        )
        r = RegionProfile(name="R-Test", priorities=["USA"])
        d = DumpProfile(name="D-Test")
        l_ = LanguageProfile(
            name="L-Test", required_languages=["en"], preferred_languages=["en"]
        )
        n = NamingProfile(
            name="N-Test", convention="no-intro", template="{Title}"
        )
        for obj in (q, r, d, l_, n):
            session.add(obj)
        await session.commit()
        for obj in (q, r, d, l_, n):
            await session.refresh(obj)
        return {
            "quality": q.id,
            "region": r.id,
            "dump": d.id,
            "language": l_.id,
            "naming": n.id,
        }


async def _seed_library_with_profiles(
    engine: AsyncEngine,
    *,
    name: str,
    profile_ids: dict[str, int],
) -> int:
    """Seed a Library row binding the supplied profile ids.
    Returns the library id."""
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        lib = Library(
            name=name,
            path=f"/srv/library-{name}",
            quality_profile_id=profile_ids["quality"],
            region_profile_id=profile_ids["region"],
            dump_profile_id=profile_ids["dump"],
            language_profile_id=profile_ids["language"],
            naming_profile_id=profile_ids["naming"],
        )
        session.add(lib)
        await session.commit()
        await session.refresh(lib)
        return lib.id


# ---------------------------------------------------------------------------
# T073 — DELETE blocked-when-bound returns 409 with blocking library names
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quality_delete_blocked_when_bound(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """A QualityProfile bound by a Library cannot be deleted —
    the cascade query returns 409 with ``in_use`` errorCode +
    the blocking library name in ``blocking_libraries``."""
    await seed_user_and_login(api_engine, api_client)
    profile_ids = await _seed_one_of_each_profile(api_engine)
    await _seed_library_with_profiles(
        api_engine, name="LibA", profile_ids=profile_ids
    )

    resp = await api_client.delete(
        f"/api/v3/qualityprofile/{profile_ids['quality']}"
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["errorCode"] == "in_use"
    assert "LibA" in body["blocking_libraries"]


@pytest.mark.asyncio
async def test_region_delete_blocked_when_bound(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """RegionProfile cascade detection."""
    await seed_user_and_login(api_engine, api_client)
    profile_ids = await _seed_one_of_each_profile(api_engine)
    await _seed_library_with_profiles(
        api_engine, name="LibR", profile_ids=profile_ids
    )

    resp = await api_client.delete(
        f"/api/v3/rom/regionprofile/{profile_ids['region']}"
    )
    assert resp.status_code == 409
    assert resp.json()["blocking_libraries"] == ["LibR"]


@pytest.mark.asyncio
async def test_naming_delete_blocked_lists_multiple_libraries(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """When two libraries bind the same profile, the 409 detail
    surfaces both names."""
    await seed_user_and_login(api_engine, api_client)
    profile_ids = await _seed_one_of_each_profile(api_engine)
    await _seed_library_with_profiles(
        api_engine, name="Lib-1", profile_ids=profile_ids
    )
    await _seed_library_with_profiles(
        api_engine, name="Lib-2", profile_ids=profile_ids
    )

    resp = await api_client.delete(
        f"/api/v3/rom/namingprofile/{profile_ids['naming']}"
    )
    assert resp.status_code == 409
    blocking = resp.json()["blocking_libraries"]
    assert set(blocking) == {"Lib-1", "Lib-2"}


# ---------------------------------------------------------------------------
# T074 — DELETE-with-force still 409s when bound
#
# The current implementation accepts ``?force=true`` on the surface but
# returns the same 409 because the library.*_profile_id columns are NOT
# NULL — a force-unbind would need a substitute-rebind semantic that
# isn't part of MVP. The test pins this contract.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_quality_delete_with_force_still_409s_when_bound(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """``?force=true`` is accepted but is currently a no-op — the
    behaviour matches ``force=false`` until a substitute-rebind
    semantic ships."""
    await seed_user_and_login(api_engine, api_client)
    profile_ids = await _seed_one_of_each_profile(api_engine)
    await _seed_library_with_profiles(
        api_engine, name="LibForce", profile_ids=profile_ids
    )

    resp = await api_client.delete(
        f"/api/v3/qualityprofile/{profile_ids['quality']}?force=true"
    )
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# T076 — CustomFormat m2m cascade: DELETE on bound CF removes m2m rows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_custom_format_delete_cascades_via_m2m(
    api_client: httpx.AsyncClient, api_engine: AsyncEngine
) -> None:
    """CustomFormat is bound to libraries through
    ``library_custom_format`` with ``ondelete=CASCADE`` on the FK.
    Deleting the CF auto-removes the binding rows; the DELETE
    succeeds without an explicit unbind step.

    The ``CustomFormat`` model also carries ``is_factory_default``
    — non-default rows are deletable; the
    ``test_unbound_delete_works`` parent test already covers the
    happy path. This test pins the cascade specifically."""
    await seed_user_and_login(api_engine, api_client)
    sm = async_sessionmaker(api_engine, expire_on_commit=False)

    profile_ids = await _seed_one_of_each_profile(api_engine)
    library_id = await _seed_library_with_profiles(
        api_engine, name="LibCf", profile_ids=profile_ids
    )

    async with sm() as session:
        cf = CustomFormat(name="CF-Test", score=10, conditions=[])
        session.add(cf)
        await session.commit()
        await session.refresh(cf)
        bind = LibraryCustomFormat(
            library_id=library_id,
            custom_format_id=cf.id,
            created_at=__import__("datetime").datetime.now(
                __import__("datetime").UTC
            ),
        )
        session.add(bind)
        await session.commit()
        cf_id = cf.id

    resp = await api_client.delete(f"/api/v3/customformat/{cf_id}")
    assert resp.status_code == 204

    # m2m row gone — cascade auto-removed it.
    async with sm() as session:
        rows = (
            await session.execute(
                select(LibraryCustomFormat).where(
                    LibraryCustomFormat.custom_format_id == cf_id
                )
            )
        ).scalars().all()
        assert rows == []
