"""Built-in pack first-boot tests (T033, T034, T035)."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from romarr.domain.models import Platform, PlatformPack
from romarr.platform_packs import apply_builtin_pack
from romarr.platform_packs.builtin import (
    _BUILTIN_PACK_VERSION,
    resolve_builtin_pack_path,
)


@pytest.mark.asyncio
async def test_empty_db_applies_built_in_pack(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SC-001: starting against an empty DB lands the bundled built-in
    pack with ~20 platforms in `pack_source = 'builtin'`."""
    monkeypatch.delenv("ROMARR_BUILTIN_PACK_PATH", raising=False)
    sm = async_sessionmaker_factory

    async with sm() as s:
        result = await apply_builtin_pack(s, sessionmaker=sm)
    assert result is not None
    assert result.action == "applied"
    assert result.pack_version == _BUILTIN_PACK_VERSION

    async with sm() as s:
        platforms = (await s.execute(select(Platform))).scalars().all()

    assert len(platforms) >= 18  # 20 platforms shipped, ≥ 18 is the SC-001 floor
    assert all(p.pack_source == "builtin" for p in platforms)
    # Sample a few canonical ones.
    slugs = {p.slug for p in platforms}
    for required in ("nes", "snes", "megadrive", "psx", "gba"):
        assert required in slugs


@pytest.mark.asyncio
async def test_already_applied_pack_is_idempotent_skip(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ROMARR_BUILTIN_PACK_PATH", raising=False)
    sm = async_sessionmaker_factory
    async with sm() as s:
        first = await apply_builtin_pack(s, sessionmaker=sm)
    assert first is not None and first.action == "applied"

    async with sm() as s:
        second = await apply_builtin_pack(s, sessionmaker=sm)
    assert second is not None and second.action == "skipped"

    # platform_pack table holds exactly ONE row.
    async with sm() as s:
        packs = (
            (await s.execute(select(PlatformPack)))
            .scalars()
            .all()
        )
    assert len(packs) == 1


@pytest.mark.asyncio
async def test_missing_builtin_pack_logs_warning_does_not_crash(
    async_session: AsyncSession,
    async_sessionmaker_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """FR-019: pointing ROMARR_BUILTIN_PACK_PATH at a nonexistent file
    boots normally and writes nothing.

    We patch the module logger directly because caplog can be flaky
    across the full suite if an earlier test mucked with logging
    handlers / propagation.
    """
    import logging
    from unittest.mock import MagicMock

    monkeypatch.setenv(
        "ROMARR_BUILTIN_PACK_PATH", str(tmp_path / "does-not-exist.yaml")
    )
    sm = async_sessionmaker_factory

    builtin_logger = logging.getLogger("romarr.platform_packs.builtin")
    spy = MagicMock(wraps=builtin_logger.warning)
    monkeypatch.setattr(builtin_logger, "warning", spy)

    async with sm() as s:
        result = await apply_builtin_pack(s, sessionmaker=sm)

    assert result is None

    async with sm() as s:
        platforms = (await s.execute(select(Platform))).scalars().all()
    assert platforms == []

    # The structured-warning call was issued exactly once with the
    # documented event key.
    assert spy.call_count == 1
    args, _kwargs = spy.call_args
    assert args[0] == "platform_packs.builtin.missing"


def test_resolve_path_honors_env_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ROMARR_BUILTIN_PACK_PATH wins over the wheel resource."""
    fake = tmp_path / "operator-builtin.yaml"
    fake.write_text("pack_version: '2026.04.001'\nschema_version: 1\nplatforms: []\n")
    monkeypatch.setenv("ROMARR_BUILTIN_PACK_PATH", str(fake))
    # Settings cache may already be primed by another test; clear
    # it so the env override is picked up.
    from romarr.config.settings import get_settings

    get_settings.cache_clear()
    try:
        assert resolve_builtin_pack_path() == fake
    finally:
        get_settings.cache_clear()


def test_resolve_path_honors_typed_settings_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T005 / slice 174: the typed ``Settings.builtin_pack_path``
    field — populated from ``ROMARR_BUILTIN_PACK_PATH`` via the
    Pydantic Settings env-prefix — is consulted before the
    wheel-resource fallback."""
    fake = tmp_path / "from-settings.yaml"
    fake.write_text(
        "pack_version: '2026.04.001'\nschema_version: 1\nplatforms: []\n"
    )
    monkeypatch.setenv("ROMARR_BUILTIN_PACK_PATH", str(fake))
    monkeypatch.setenv(
        "ROMARR_AUTH_SECRET_KEY",
        "test-only-secret-key-do-not-use-in-prod",
    )
    from romarr.config.settings import get_settings

    get_settings.cache_clear()
    try:
        # Sanity-check the typed field actually surfaces.
        assert get_settings().builtin_pack_path == str(fake)
        assert resolve_builtin_pack_path() == fake
    finally:
        get_settings.cache_clear()


def test_resolve_path_returns_wheel_resource_when_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ROMARR_BUILTIN_PACK_PATH", raising=False)
    path = resolve_builtin_pack_path()
    assert path is not None
    assert path.name == f"builtin-{_BUILTIN_PACK_VERSION}.yaml"


def test_builtin_pack_lints_clean_against_schema() -> None:
    """A typo in the shipped YAML must fail the build, not slip into a
    release. This is the smoke-test referenced from Phase 8 T059."""
    from romarr.platform_packs.validator import validate_pack

    path = resolve_builtin_pack_path()
    assert path is not None, "built-in pack must resolve from the wheel"
    parsed = validate_pack(path.read_bytes())
    assert parsed.pack_version == _BUILTIN_PACK_VERSION
    assert len(parsed.parsed["platforms"]) >= 18
