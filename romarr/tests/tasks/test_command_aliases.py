"""Sonarr-command-name mapping tests (T058, T059, FR-016)."""

from __future__ import annotations

import pytest

from romarr.tasks.command_aliases import (
    COMMAND_ALIASES,
    UnknownCommand,
    known_command_names,
    resolve_command,
)

# ---------------------------------------------------------------------------
# T058 — every documented command name maps cleanly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sonarr_name, expected_job_id",
    [
        ("MissingSearch", "MissingSearch"),
        ("CutoffSearch", "CutoffSearch"),
        ("RssSync", "RssSync"),
        ("RefreshGame", "RefreshGameMetadata"),
        ("RescanLibrary", "LibraryScan"),
        ("DownloadDats", "DatUpdate"),
        ("IndexerSearch", "RssSync"),
        ("Backup", "Backup"),
        ("HealthCheck", "HealthCheck"),
        ("RefreshGameMetadata", "RefreshGameMetadata"),
    ],
)
def test_known_names_map_to_expected_jobs(
    sonarr_name: str, expected_job_id: str
) -> None:
    job_id, _params = resolve_command(name=sonarr_name)
    assert job_id == expected_job_id


def test_at_least_eight_documented_commands() -> None:
    """SC-008 mandates ≥ 8 Sonarr-compat names. Catch removals."""
    names = known_command_names()
    assert len(names) >= 8
    # Sanity — the documented FR-016 minimum set is present.
    minimum_set = {
        "MissingSearch",
        "CutoffSearch",
        "RssSync",
        "RefreshGame",
        "RescanLibrary",
        "DownloadDats",
        "IndexerSearch",
        "Backup",
    }
    assert minimum_set.issubset(set(names))


# ---------------------------------------------------------------------------
# T059 — unknown command raises
# ---------------------------------------------------------------------------


def test_unknown_command_raises() -> None:
    with pytest.raises(UnknownCommand) as exc_info:
        resolve_command(name="Foo")
    assert "Foo" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Kwargs flow / whitelist
# ---------------------------------------------------------------------------


def test_refresh_game_forwards_game_id() -> None:
    """``RefreshGame`` declares ``gameId`` in
    ``allowed_kwargs``; the value flows through verbatim."""
    job_id, params = resolve_command(
        name="RefreshGame", payload={"name": "RefreshGame", "gameId": 42}
    )
    assert job_id == "RefreshGameMetadata"
    assert params == {"gameId": 42}


def test_rescan_library_forwards_library_id() -> None:
    job_id, params = resolve_command(
        name="RescanLibrary",
        payload={"name": "RescanLibrary", "libraryId": 7},
    )
    assert job_id == "LibraryScan"
    assert params == {"libraryId": 7}


def test_unknown_kwargs_silently_dropped() -> None:
    """Sonarr's permissive behaviour: unknown payload keys are
    ignored rather than 400-ing. We mirror that so older
    Notifiarr clients adding fields don't break."""
    _job_id, params = resolve_command(
        name="RefreshGame",
        payload={
            "name": "RefreshGame",
            "gameId": 42,
            "someUnknownField": "ignored",
        },
    )
    assert params == {"gameId": 42}


def test_no_payload_is_fine_for_kwargless_command() -> None:
    """``MissingSearch`` declares no allowed_kwargs;
    ``parameters`` is empty regardless of payload."""
    _job_id, params = resolve_command(
        name="MissingSearch",
        payload={"name": "MissingSearch", "extraField": "x"},
    )
    assert params == {}


# ---------------------------------------------------------------------------
# Drift guard — every alias references a real Romarr job
# ---------------------------------------------------------------------------


def test_every_alias_targets_a_seeded_job() -> None:
    """Every alias's ``job_id`` must match a SEED catalogue
    entry; otherwise the API would 404 at trigger time."""
    from romarr.tasks.seeder import DEFAULT_CATALOGUE

    seed_ids = {default.job_id for default in DEFAULT_CATALOGUE}
    for alias in COMMAND_ALIASES:
        assert alias.job_id in seed_ids, (
            f"alias {alias.sonarr_name} → {alias.job_id} doesn't "
            f"match any SEED catalogue entry"
        )
