"""WindowedDebouncer primitive tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from romarr.libraries._debounce import WindowedDebouncer


def _at(seconds: int) -> datetime:
    return datetime(2026, 4, 30, tzinfo=UTC) + timedelta(seconds=seconds)


def test_first_emit_succeeds() -> None:
    deb: WindowedDebouncer[str] = WindowedDebouncer(window=timedelta(minutes=5))
    assert deb.should_emit(key="lib1:unavailable", now=_at(0)) is True


def test_second_emit_within_window_suppressed() -> None:
    deb: WindowedDebouncer[str] = WindowedDebouncer(window=timedelta(minutes=5))
    assert deb.should_emit(key="k", now=_at(0)) is True
    assert deb.should_emit(key="k", now=_at(60)) is False  # 1 min in
    assert deb.should_emit(key="k", now=_at(299)) is False  # 4:59 in


def test_emit_after_window_succeeds() -> None:
    deb: WindowedDebouncer[str] = WindowedDebouncer(window=timedelta(minutes=5))
    assert deb.should_emit(key="k", now=_at(0)) is True
    assert deb.should_emit(key="k", now=_at(300)) is True  # exactly at boundary


def test_distinct_keys_are_independent() -> None:
    deb: WindowedDebouncer[str] = WindowedDebouncer(window=timedelta(minutes=5))
    assert deb.should_emit(key="k1", now=_at(0)) is True
    assert deb.should_emit(key="k2", now=_at(0)) is True  # different key
    assert deb.should_emit(key="k1", now=_at(10)) is False  # within k1's window


def test_reset_clears_suppression() -> None:
    deb: WindowedDebouncer[str] = WindowedDebouncer(window=timedelta(minutes=5))
    deb.should_emit(key="k", now=_at(0))
    deb.reset(key="k")
    assert deb.should_emit(key="k", now=_at(10)) is True
