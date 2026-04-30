"""Atomic gamelist.xml writer tests (T058, FR-017, FR-017a)."""

from __future__ import annotations

import multiprocessing
import os
import time
from pathlib import Path

import pytest

from romarr.libraries.exporters.esde import (
    EsdeGame,
    render_gamelist_xml,
    write_gamelist_atomic,
)


def _xml_for(*titles: str) -> bytes:
    games = [EsdeGame(slug=t.lower(), title=t, rom_path=f"./{t}.md") for t in titles]
    return render_gamelist_xml(games)


# ---------------------------------------------------------------------------
# T058 — mid-write crash preserves prior file
# ---------------------------------------------------------------------------


def test_mid_write_crash_preserves_prior_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Simulate an os.replace failure after the .tmp has been written.
    The prior gamelist.xml MUST be untouched and the .tmp MUST be
    cleaned up."""
    # First write — establishes the prior file.
    assert write_gamelist_atomic(tmp_path, _xml_for("Sonic")) is True
    target = tmp_path / "gamelist.xml"
    prior = target.read_bytes()

    # Simulate the second write crashing right at the os.replace step.
    def fail_replace(_src: object, _dst: object) -> None:
        raise OSError("simulated rename failure")

    monkeypatch.setattr(
        "romarr.libraries.exporters.esde.os.replace", fail_replace
    )
    with pytest.raises(OSError):
        write_gamelist_atomic(tmp_path, _xml_for("Streets of Rage"))

    # Prior file is untouched. Partial .tmp is gone.
    assert target.read_bytes() == prior
    assert not (tmp_path / "gamelist.xml.tmp").exists()


def test_first_write_creates_directory(tmp_path: Path) -> None:
    target_dir = tmp_path / "megadrive"
    assert not target_dir.exists()

    assert write_gamelist_atomic(target_dir, _xml_for("Sonic")) is True
    assert (target_dir / "gamelist.xml").exists()


def test_second_write_overwrites_atomically(tmp_path: Path) -> None:
    write_gamelist_atomic(tmp_path, _xml_for("Sonic"))
    write_gamelist_atomic(tmp_path, _xml_for("Streets of Rage"))
    body = (tmp_path / "gamelist.xml").read_text()
    assert "Streets of Rage" in body
    assert "Sonic" not in body  # the second write fully overwrote


# ---------------------------------------------------------------------------
# FR-017a — advisory lock coalesces concurrent writers
# ---------------------------------------------------------------------------


def _hold_lock_then_exit(target_dir: str, hold_seconds: float) -> None:
    """Worker process: open the lock file, acquire the same lock the
    writer uses, hold it for ``hold_seconds``, exit. Mirrors what
    ``write_gamelist_atomic`` does so we can test the contention
    path without spawning two writers (which would race on the file
    system in unpredictable ways)."""
    import fcntl as _fcntl

    target = Path(target_dir)
    target.mkdir(parents=True, exist_ok=True)
    fd = os.open(target / ".gamelist.lock", os.O_CREAT | os.O_RDWR)
    try:
        _fcntl.flock(fd, _fcntl.LOCK_EX)
        time.sleep(hold_seconds)
        _fcntl.flock(fd, _fcntl.LOCK_UN)
    finally:
        os.close(fd)


def test_lock_unavailable_coalesces(tmp_path: Path) -> None:
    """When another process holds the lock, ``write_gamelist_atomic``
    returns ``False`` immediately rather than blocking."""
    ctx = multiprocessing.get_context("fork")
    holder = ctx.Process(
        target=_hold_lock_then_exit,
        args=(str(tmp_path), 1.0),
        daemon=True,
    )
    holder.start()
    try:
        # Give the holder a moment to acquire.
        time.sleep(0.2)
        result = write_gamelist_atomic(tmp_path, _xml_for("Sonic"))
        assert result is False
        # gamelist.xml MUST NOT exist — coalescing means we did
        # nothing.
        assert not (tmp_path / "gamelist.xml").exists()
    finally:
        holder.join(timeout=3)
        if holder.is_alive():
            holder.terminate()
            holder.join(timeout=1)


def test_lock_released_after_successful_write(tmp_path: Path) -> None:
    """After a write completes, a subsequent write succeeds — the
    lock is properly released."""
    assert write_gamelist_atomic(tmp_path, _xml_for("A")) is True
    assert write_gamelist_atomic(tmp_path, _xml_for("B")) is True
    assert (tmp_path / "gamelist.xml").read_text().count("<game>") == 1
