"""DownloadClient model + Pydantic-validator tests (T007-T011)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.downloaders.models import DownloadClient
from romarr.downloaders.schemas import DownloadClientCreate
from romarr.downloaders.types import ClientType


def _qbit_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "Local qBit",
        "type": ClientType.QBITTORRENT,
        "host": "127.0.0.1",
        "port": 8080,
        "username": "admin",
        "password": "adminadmin",
        "enable_for_torrents": True,
    }
    base.update(overrides)
    return base


def _sab_payload(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "name": "SAB",
        "type": ClientType.SABNZBD,
        "host": "sab.local",
        "port": 8080,
        "api_key": "sab-key",
        "enable_for_usenet": True,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# T007 — round-trip + CHECK constraints
# ---------------------------------------------------------------------------


async def test_download_client_round_trip(async_session: AsyncSession) -> None:
    async_session.add(
        DownloadClient(
            name="Local qBit",
            type="qbittorrent",
            host="127.0.0.1",
            port=8080,
            username="admin",
            password_encrypted=b"ciphertext",
            enable_for_torrents=True,
        )
    )
    await async_session.commit()

    row = (
        await async_session.execute(
            select(DownloadClient).where(DownloadClient.name == "Local qBit")
        )
    ).scalar_one()
    assert row.type == "qbittorrent"
    assert row.port == 8080
    assert row.priority == 1  # default
    assert row.category_default == "romarr"
    assert row.ssl_cert_validation == "enabled"


async def test_check_constraint_on_type(async_session: AsyncSession) -> None:
    async_session.add(
        DownloadClient(
            name="Bad",
            type="not-a-real-impl",
            host="x.test",
            port=1,
            enable_for_torrents=True,
        )
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


async def test_check_constraint_on_port(async_session: AsyncSession) -> None:
    async_session.add(
        DownloadClient(
            name="Out of range",
            type="qbittorrent",
            host="x.test",
            port=99999,
            enable_for_torrents=True,
        )
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


async def test_check_constraint_on_ssl_validation(
    async_session: AsyncSession,
) -> None:
    async_session.add(
        DownloadClient(
            name="Bad SSL",
            type="qbittorrent",
            host="x.test",
            port=8080,
            ssl_cert_validation="bogus",
            enable_for_torrents=True,
        )
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


# ---------------------------------------------------------------------------
# T008 — UNIQUE on (type, host, port)
# ---------------------------------------------------------------------------


async def test_unique_type_host_port(async_session: AsyncSession) -> None:
    async_session.add(
        DownloadClient(
            name="A",
            type="qbittorrent",
            host="qbit.local",
            port=8080,
            enable_for_torrents=True,
        )
    )
    await async_session.commit()

    async_session.add(
        DownloadClient(
            name="B",
            type="qbittorrent",
            host="qbit.local",
            port=8080,  # collision
            enable_for_torrents=True,
        )
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()
    await async_session.rollback()


# ---------------------------------------------------------------------------
# T009 — qBit requires password
# ---------------------------------------------------------------------------


def test_qbit_requires_password() -> None:
    with pytest.raises(ValidationError) as exc:
        DownloadClientCreate(**_qbit_payload(password=None))
    assert "qbittorrent requires a password" in str(exc.value)


def test_qbit_requires_username() -> None:
    with pytest.raises(ValidationError) as exc:
        DownloadClientCreate(**_qbit_payload(username=None))
    assert "qbittorrent requires a username" in str(exc.value)


def test_qbit_rejects_api_key() -> None:
    with pytest.raises(ValidationError) as exc:
        DownloadClientCreate(**_qbit_payload(api_key="should-not-have-this"))
    assert "qbittorrent must not carry an api_key" in str(exc.value)


# ---------------------------------------------------------------------------
# T010 — SAB rejects username + password
# ---------------------------------------------------------------------------


def test_sab_rejects_username() -> None:
    with pytest.raises(ValidationError) as exc:
        DownloadClientCreate(**_sab_payload(username="not-allowed"))
    assert "sabnzbd must not carry a username" in str(exc.value)


def test_sab_rejects_password() -> None:
    with pytest.raises(ValidationError) as exc:
        DownloadClientCreate(**_sab_payload(password="not-allowed"))
    assert "sabnzbd must not carry a password" in str(exc.value)


def test_sab_requires_api_key() -> None:
    with pytest.raises(ValidationError) as exc:
        DownloadClientCreate(**_sab_payload(api_key=None))
    assert "sabnzbd requires an api_key" in str(exc.value)


# ---------------------------------------------------------------------------
# T011 — at least one source type enabled (FR-023)
# ---------------------------------------------------------------------------


def test_at_least_one_source_type_enabled() -> None:
    with pytest.raises(ValidationError) as exc:
        DownloadClientCreate(
            **_qbit_payload(
                enable_for_torrents=False, enable_for_usenet=False
            )
        )
    assert "at least one of enable_for_torrents" in str(exc.value)
