"""Notification + HealthCheck model tests (T006-T010)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.notifications.models import HealthCheck, Notification
from romarr.notifications.schemas import NotificationCreate


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# T006 — Notification + HealthCheck round-trip + CHECK constraints
# ---------------------------------------------------------------------------


async def test_notification_round_trip(async_session: AsyncSession) -> None:
    notification = Notification(
        name="my-discord",
        apprise_url_encrypted=b"\x01\x02\x03\x04",
        apprise_url_scheme="discord",
    )
    async_session.add(notification)
    await async_session.commit()

    row = (
        await async_session.execute(
            select(Notification).where(Notification.name == "my-discord")
        )
    ).scalar_one()
    assert row.on_import is True  # default
    assert row.on_grab is False  # default
    assert row.tags == []
    assert row.enabled is True
    assert row.last_status is None


async def test_notification_last_status_check_rejects_unknown(
    async_session: AsyncSession,
) -> None:
    notification = Notification(
        name="bad",
        apprise_url_encrypted=b"\x01",
        apprise_url_scheme="discord",
        last_status="weird",
    )
    async_session.add(notification)
    with pytest.raises(IntegrityError):
        await async_session.commit()


async def test_health_check_round_trip(
    async_session: AsyncSession,
) -> None:
    now = _now()
    check = HealthCheck(
        component="indexer:MyIndexer",
        status="warning",
        message="last poll returned 503",
        severity_changed_at=now,
        last_checked_at=now,
        first_seen_at=now,
        last_seen_at=now,
        last_emitted_state="warning",
        last_emitted_at=now,
    )
    async_session.add(check)
    await async_session.commit()

    row = (
        await async_session.execute(
            select(HealthCheck).where(
                HealthCheck.component == "indexer:MyIndexer"
            )
        )
    ).scalar_one()
    assert row.status == "warning"
    assert row.last_emitted_state == "warning"


async def test_health_check_status_check_rejects_unknown(
    async_session: AsyncSession,
) -> None:
    now = _now()
    check = HealthCheck(
        component="indexer:Foo",
        status="degraded",  # not in CHECK list
        severity_changed_at=now,
        last_checked_at=now,
        first_seen_at=now,
        last_seen_at=now,
    )
    async_session.add(check)
    with pytest.raises(IntegrityError):
        await async_session.commit()


# ---------------------------------------------------------------------------
# T007 — duplicate notification name rejected
# ---------------------------------------------------------------------------


async def test_notification_unique_name(async_session: AsyncSession) -> None:
    async_session.add(
        Notification(
            name="my-discord",
            apprise_url_encrypted=b"\x01",
            apprise_url_scheme="discord",
        )
    )
    await async_session.commit()

    async_session.add(
        Notification(
            name="my-discord",
            apprise_url_encrypted=b"\x02",
            apprise_url_scheme="discord",
        )
    )
    with pytest.raises(IntegrityError):
        await async_session.commit()


# ---------------------------------------------------------------------------
# T008 — duplicate health-check component rejected
# ---------------------------------------------------------------------------


async def test_health_check_unique_component(
    async_session: AsyncSession,
) -> None:
    now = _now()

    def _check(component: str) -> HealthCheck:
        return HealthCheck(
            component=component,
            status="ok",
            severity_changed_at=now,
            last_checked_at=now,
            first_seen_at=now,
            last_seen_at=now,
        )

    async_session.add(_check("db"))
    await async_session.commit()

    async_session.add(_check("db"))  # duplicate
    with pytest.raises(IntegrityError):
        await async_session.commit()


# ---------------------------------------------------------------------------
# T009 — Pydantic validator: at least one event subscribed
# ---------------------------------------------------------------------------


def test_notification_create_requires_at_least_one_event() -> None:
    with pytest.raises(ValidationError) as exc:
        NotificationCreate(
            name="silent",
            apprise_url="discord://abc",
            on_grab=False,
            on_import=False,
            on_upgrade=False,
            on_fail=False,
            on_health_issue=False,
            on_dat_update=False,
            on_game_added=False,
        )
    assert "at least one event" in str(exc.value)


def test_notification_create_with_one_flag_succeeds() -> None:
    notif = NotificationCreate(
        name="grab-only",
        apprise_url="discord://abc",
        on_grab=True,
        on_import=False,
        on_upgrade=False,
        on_fail=False,
        on_health_issue=False,
        on_dat_update=False,
        on_game_added=False,
    )
    assert notif.on_grab is True
    assert notif.apprise_url.get_secret_value() == "discord://abc"


# ---------------------------------------------------------------------------
# Notification format columns round-trip
# ---------------------------------------------------------------------------


async def test_notification_template_overrides_persist(
    async_session: AsyncSession,
) -> None:
    """The seven nullable ``*_format`` columns persist correctly so
    the dispatcher can read them back at render time."""
    notification = Notification(
        name="custom-templates",
        apprise_url_encrypted=b"\x01",
        apprise_url_scheme="discord",
        on_import_format="🎉 {{ game.title }}!",
        on_health_issue_format="alarm: {{ component }}",
    )
    async_session.add(notification)
    await async_session.commit()

    row = (
        await async_session.execute(
            select(Notification).where(
                Notification.name == "custom-templates"
            )
        )
    ).scalar_one()
    assert row.on_import_format == "🎉 {{ game.title }}!"
    assert row.on_grab_format is None
    assert row.on_health_issue_format == "alarm: {{ component }}"
