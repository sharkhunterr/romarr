"""App lifespan bootstrap tests (slice 173).

Covers spec 003 T038 (apply_builtin_pack) + spec 006 T055
(seed_defaults) wired into the FastAPI lifespan. Both are
opt-in via ``app.state._enable_bootstrap = True``.

We use a file-based SQLite per test so the engine the lifespan
builds (via ``_test_database_url``) and the engine the test
reads with both see the same rows — ``:memory:`` doesn't share
across separate ``create_engine`` calls in the same process.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from romarr.api.app import create_app
from romarr.auth.models import SetupToken, User
from romarr.db.session import create_engine
from romarr.domain import Base
from romarr.profiles.models import (
    DumpProfile,
    NamingProfile,
    QualityProfile,
)


async def _seed_schema(db_url: str) -> None:
    """Build the schema once on the file-DB so the lifespan
    finds tables when it runs ``seed_defaults``."""
    engine = create_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()


@pytest.fixture
def file_db_url(tmp_path: Path) -> str:
    return f"sqlite+aiosqlite:///{tmp_path / 'bootstrap.sqlite'}"


@pytest.mark.asyncio
async def test_lifespan_seeds_default_profiles_when_bootstrap_enabled(
    file_db_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """With ``_enable_bootstrap=True`` on app.state, the
    lifespan invokes ``seed_defaults`` and inserts the
    default-profile catalogue."""
    monkeypatch.setenv(
        "ROMARR_AUTH_SECRET_KEY",
        "test-only-secret-key-do-not-use-in-prod",
    )
    await _seed_schema(file_db_url)

    app = create_app()
    app.state._test_database_url = file_db_url
    app.state._enable_bootstrap = True

    async with app.router.lifespan_context(app):
        pass

    # Read back via a fresh engine on the same file.
    engine = create_engine(file_db_url)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        quality = (await session.execute(select(QualityProfile))).scalars().all()
        naming = (await session.execute(select(NamingProfile))).scalars().all()
        dump = (await session.execute(select(DumpProfile))).scalars().all()
    await engine.dispose()

    assert len(quality) > 0, "default quality profiles missing"
    assert len(naming) > 0, "default naming profiles missing"
    assert len(dump) > 0, "default dump profiles missing"


@pytest.mark.asyncio
async def test_lifespan_skips_bootstrap_by_default(
    file_db_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without the opt-in flag, the lifespan does NOT run the
    seeders."""
    monkeypatch.setenv(
        "ROMARR_AUTH_SECRET_KEY",
        "test-only-secret-key-do-not-use-in-prod",
    )
    await _seed_schema(file_db_url)

    app = create_app()
    app.state._test_database_url = file_db_url
    # _enable_bootstrap NOT set — default is False.

    async with app.router.lifespan_context(app):
        pass

    engine = create_engine(file_db_url)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        rows = (await session.execute(select(QualityProfile))).scalars().all()
    await engine.dispose()

    assert rows == [], (
        "lifespan should NOT seed defaults when bootstrap is disabled"
    )


@pytest.mark.asyncio
async def test_lifespan_seed_defaults_idempotent(
    file_db_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-running the bootstrap on an already-seeded DB is a
    no-op (relied on at every app restart in production)."""
    monkeypatch.setenv(
        "ROMARR_AUTH_SECRET_KEY",
        "test-only-secret-key-do-not-use-in-prod",
    )
    await _seed_schema(file_db_url)

    app = create_app()
    app.state._test_database_url = file_db_url
    app.state._enable_bootstrap = True

    # First boot.
    async with app.router.lifespan_context(app):
        pass
    engine = create_engine(file_db_url)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        first = (
            await session.execute(select(QualityProfile))
        ).scalars().all()
    await engine.dispose()
    first_count = len(first)
    assert first_count > 0

    # Second boot on the same DB — count holds, no duplicates.
    async with app.router.lifespan_context(app):
        pass
    engine = create_engine(file_db_url)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        second = (
            await session.execute(select(QualityProfile))
        ).scalars().all()
    await engine.dispose()
    assert len(second) == first_count


@pytest.mark.asyncio
async def test_lifespan_mints_setup_token_on_fresh_boot(
    file_db_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slice 187 wired ``maybe_bootstrap_setup_token`` into the
    bootstrap step. A fresh DB → exactly one ``setup_token`` row
    (the operator captures the plaintext from the WARNING log
    line and uses it to complete /auth/setup)."""
    monkeypatch.setenv(
        "ROMARR_AUTH_SECRET_KEY",
        "test-only-secret-key-do-not-use-in-prod",
    )
    await _seed_schema(file_db_url)

    app = create_app()
    app.state._test_database_url = file_db_url
    app.state._enable_bootstrap = True

    async with app.router.lifespan_context(app):
        pass

    engine = create_engine(file_db_url)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        tokens = (
            await session.execute(select(SetupToken))
        ).scalars().all()
    await engine.dispose()

    assert len(tokens) == 1
    assert tokens[0].consumed_at is None


@pytest.mark.asyncio
async def test_lifespan_does_not_mint_second_token_on_subsequent_boot(
    file_db_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing unconsumed token + still-valid expiry → no
    new mint on the next boot. Tokens persist across restarts
    so the operator's first capture is still authoritative."""
    monkeypatch.setenv(
        "ROMARR_AUTH_SECRET_KEY",
        "test-only-secret-key-do-not-use-in-prod",
    )
    await _seed_schema(file_db_url)

    app = create_app()
    app.state._test_database_url = file_db_url
    app.state._enable_bootstrap = True

    # First boot mints.
    async with app.router.lifespan_context(app):
        pass
    # Second boot with the same DB.
    async with app.router.lifespan_context(app):
        pass

    engine = create_engine(file_db_url)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        tokens = (
            await session.execute(select(SetupToken))
        ).scalars().all()
    await engine.dispose()

    assert len(tokens) == 1, (
        f"expected exactly 1 setup_token row, got {len(tokens)}"
    )


@pytest.mark.asyncio
async def test_lifespan_skips_token_when_active_user_exists(
    file_db_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If an active human admin exists already, the lifespan
    must NOT mint a setup token — the system is past the
    first-boot phase."""
    from romarr.auth.hashing import hash_password

    monkeypatch.setenv(
        "ROMARR_AUTH_SECRET_KEY",
        "test-only-secret-key-do-not-use-in-prod",
    )
    await _seed_schema(file_db_url)

    # Seed an active admin BEFORE the lifespan runs.
    engine = create_engine(file_db_url)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            User(
                username="admin",
                role="admin",
                is_active=True,
                hashed_password=hash_password("hunter2-correct-horse-battery-staple"),
            )
        )
        await session.commit()
    await engine.dispose()

    app = create_app()
    app.state._test_database_url = file_db_url
    app.state._enable_bootstrap = True

    async with app.router.lifespan_context(app):
        pass

    engine = create_engine(file_db_url)
    sm = async_sessionmaker(engine, expire_on_commit=False)
    async with sm() as session:
        tokens = (
            await session.execute(select(SetupToken))
        ).scalars().all()
    await engine.dispose()

    assert tokens == [], (
        "lifespan must skip setup-token mint when an active "
        f"human user already exists, got {len(tokens)} tokens"
    )
