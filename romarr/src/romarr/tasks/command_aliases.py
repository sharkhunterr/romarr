"""Sonarr-command-name → Romarr job_id mapping (T062, FR-016).

Notifiarr / Homepage / Tautulli drive Sonarr clones via
``POST /api/v3/command`` with payloads like
``{"name": "MissingSearch"}`` or
``{"name": "RefreshGame", "gameId": 42}``. Romarr accepts the
same payload shape so those tools work transparently.

The mapping is one-way (Sonarr → Romarr) and pure: no I/O, no
side effects. The endpoint layer composes this with the
:class:`SchedulerService` to fire the corresponding runner.

The mapping table also documents the kwargs key transformations
— Sonarr uses camelCase (``gameId``, ``libraryId``) while
Romarr's runner adapters can accept either form (the
:class:`JobContext.parameters` dict is opaque). We pass through
camelCase verbatim — the spec 002 layer normalises if needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from romarr.tasks.errors import TaskError


class UnknownCommand(TaskError):  # noqa: N818
    """Raised when a Sonarr command name doesn't map to any
    Romarr job. The endpoint layer maps this to HTTP 400 with
    ``errorCode = "unknown_command"``."""


@dataclass(frozen=True)
class CommandAlias:
    """One Sonarr-command-name → Romarr-job binding.

    ``allowed_kwargs`` documents which payload keys are
    forwarded as ``JobContext.parameters``; unknown keys are
    silently dropped (matches Sonarr's behaviour — it ignores
    unknown payload fields rather than 400-ing).
    """

    sonarr_name: str
    job_id: str
    allowed_kwargs: tuple[str, ...] = ()


# The 8 documented commands per FR-016 + spec.md SC-008. Add
# new aliases here when shipping new runners — the registry
# in :mod:`romarr.tasks.runner_protocol` must already carry
# the corresponding adapter.
COMMAND_ALIASES: tuple[CommandAlias, ...] = (
    CommandAlias(
        sonarr_name="MissingSearch",
        job_id="MissingSearch",
    ),
    CommandAlias(
        sonarr_name="CutoffSearch",
        job_id="CutoffSearch",
    ),
    CommandAlias(
        sonarr_name="RssSync",
        job_id="RssSync",
    ),
    CommandAlias(
        sonarr_name="RefreshGame",
        job_id="RefreshGameMetadata",
        allowed_kwargs=("gameId",),
    ),
    CommandAlias(
        sonarr_name="RescanLibrary",
        job_id="LibraryScan",
        allowed_kwargs=("libraryId",),
    ),
    CommandAlias(
        sonarr_name="DownloadDats",
        job_id="DatUpdate",
    ),
    CommandAlias(
        sonarr_name="IndexerSearch",
        # Sonarr's ``IndexerSearch`` triggers the same RSS sync
        # cycle Romarr's RSS job already drives — until a
        # dedicated ``IndexerSearch`` runner ships, alias it.
        job_id="RssSync",
    ),
    CommandAlias(
        sonarr_name="Backup",
        job_id="Backup",
    ),
    CommandAlias(
        sonarr_name="HealthCheck",
        job_id="HealthCheck",
    ),
    CommandAlias(
        sonarr_name="RefreshGameMetadata",
        # Sonarr-style "refresh all games" alias — same runner
        # as the per-game ``RefreshGame`` but with no gameId.
        job_id="RefreshGameMetadata",
    ),
)


_BY_NAME: dict[str, CommandAlias] = {
    alias.sonarr_name: alias for alias in COMMAND_ALIASES
}


def resolve_command(
    *,
    name: str,
    payload: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Resolve a Sonarr command name to ``(job_id, parameters)``.

    Raises :class:`UnknownCommand` when the name isn't in
    :data:`COMMAND_ALIASES`. Unknown payload keys are dropped
    (matching Sonarr's permissive behaviour); known keys
    forward verbatim into ``parameters``.
    """
    alias = _BY_NAME.get(name)
    if alias is None:
        raise UnknownCommand(f"unknown Sonarr command: {name}")

    parameters: dict[str, Any] = {}
    if payload:
        for key in alias.allowed_kwargs:
            if key in payload:
                parameters[key] = payload[key]
    return alias.job_id, parameters


def known_command_names() -> tuple[str, ...]:
    """Return the documented Sonarr command names — used by
    the API surface schema."""
    return tuple(alias.sonarr_name for alias in COMMAND_ALIASES)


__all__ = [
    "COMMAND_ALIASES",
    "CommandAlias",
    "UnknownCommand",
    "known_command_names",
    "resolve_command",
]
