"""Apprise wrapper tests (T017, T018, FR-002, FR-004)."""

from __future__ import annotations

from typing import Any

import pytest

from romarr.config.settings import get_settings
from romarr.metadata.encryption import encrypt
from romarr.notifications.apprise_wrapper import send
from romarr.notifications.errors import AppriseInvalidUrl
from romarr.notifications.models import Notification


@pytest.fixture(autouse=True)
def _patch_secret(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setenv("ROMARR_AUTH_SECRET_KEY", "test-only-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _notification(*, plaintext_url: str, scheme: str) -> Notification:
    """Build an in-memory Notification ORM object with a Fernet-
    encrypted URL ready for the wrapper. The DB persistence path
    is unrelated; the wrapper only needs the row's encrypted blob
    and its scheme prefix."""
    return Notification(
        name="test",
        apprise_url_encrypted=encrypt(plaintext_url.encode("utf-8")),
        apprise_url_scheme=scheme,
    )


# ---------------------------------------------------------------------------
# T018 — invalid URL raises AppriseInvalidUrl
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_apprise_url_raises() -> None:
    """A scheme Apprise can't parse rejects at validation time
    (FR-004)."""
    notif = _notification(
        plaintext_url="not-a-real-scheme://nonsense",
        scheme="not-a-real-scheme",
    )
    with pytest.raises(AppriseInvalidUrl):
        await send(notification=notif, title="hi", body="message")


# ---------------------------------------------------------------------------
# T017 — happy path delivery (5 service families)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scheme,plaintext_url",
    [
        # Apprise stub URLs: every scheme below is recognised by
        # apprise; the wrapper validates without making real
        # network calls because we monkeypatch ``apobj.notify``
        # to return True.
        ("discord", "discord://1234567890/abcdefghijklmnop"),
        ("tgram", "tgram://12345:abcde/-100123456"),
        ("ntfys", "ntfys://username@ntfy.sh/topic"),
        ("slack", "slack://TokenA/TokenB/TokenC/Channel"),
        ("gotify", "gotify://localhost/abcdefghijklmnop"),
    ],
)
async def test_happy_path_returns_success(
    scheme: str,
    plaintext_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock ``Apprise.notify`` to return True; the wrapper returns
    ``AppriseSendResult(success=True, error_message=None)``."""
    notif = _notification(plaintext_url=plaintext_url, scheme=scheme)

    async def fake_to_thread(func, *args, **kwargs):  # type: ignore[no-untyped-def]
        return True

    monkeypatch.setattr(
        "romarr.notifications.apprise_wrapper.asyncio.to_thread",
        fake_to_thread,
    )
    result = await send(
        notification=notif, title="t", body="b", notify_type="success"
    )
    assert result.success is True
    assert result.error_message is None


@pytest.mark.asyncio
async def test_apprise_returns_false_surfaces_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    notif = _notification(
        plaintext_url="discord://1234567890/abcdefghijklmnop",
        scheme="discord",
    )

    async def fake_to_thread(func, *args, **kwargs):  # type: ignore[no-untyped-def]
        return False

    monkeypatch.setattr(
        "romarr.notifications.apprise_wrapper.asyncio.to_thread",
        fake_to_thread,
    )
    result = await send(notification=notif, title="t", body="b")
    assert result.success is False
    assert result.error_message is not None
    assert "non-success" in result.error_message


@pytest.mark.asyncio
async def test_apprise_raises_surfaces_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Apprise can raise on transport errors. The wrapper
    catches the exception and surfaces it as
    ``AppriseSendResult(success=False, error_message=...)``."""
    notif = _notification(
        plaintext_url="discord://1234567890/abcdefghijklmnop",
        scheme="discord",
    )

    async def fake_to_thread(func, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise ConnectionError("dns failure")

    monkeypatch.setattr(
        "romarr.notifications.apprise_wrapper.asyncio.to_thread",
        fake_to_thread,
    )
    result = await send(notification=notif, title="t", body="b")
    assert result.success is False
    assert "ConnectionError" in (result.error_message or "")


# ---------------------------------------------------------------------------
# Encryption path — plaintext is decrypted on every call
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_url_decrypted_per_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The wrapper calls Fernet.decrypt every send. We verify by
    counting calls to the encryption module's ``decrypt``."""
    notif = _notification(
        plaintext_url="discord://1234567890/abcdefghijklmnop",
        scheme="discord",
    )

    call_count = 0
    real_decrypt = __import__(
        "romarr.metadata.encryption", fromlist=["decrypt"]
    ).decrypt

    def counting_decrypt(blob: bytes) -> bytes:
        nonlocal call_count
        call_count += 1
        return real_decrypt(blob)

    async def fake_to_thread(func, *args, **kwargs):  # type: ignore[no-untyped-def]
        return True

    monkeypatch.setattr(
        "romarr.notifications.apprise_wrapper.decrypt", counting_decrypt
    )
    monkeypatch.setattr(
        "romarr.notifications.apprise_wrapper.asyncio.to_thread",
        fake_to_thread,
    )

    for _ in range(3):
        await send(notification=notif, title="t", body="b")

    assert call_count == 3
