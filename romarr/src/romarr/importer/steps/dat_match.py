"""DAT-match step (FR-011 / pipeline step 4).

Thin wrapper around foundation's
:class:`HashMatchCascade.lookup_sha1`. Returns a structured
:class:`DatMatchResult` carrying:

  * ``dat_verified``: True iff the cascade found a known-good
    entry (status VERIFIED). A non-verified entry (BADDUMP, HACK,
    OVERDUMP, etc.) propagates its ``dump_status`` to the
    importer's working state but flips ``dat_verified`` to False
    so the audit row records the file as unverified (US5.3).
  * ``dat_source``: the cascade winner's ``source`` string
    (``"no-intro"`` / ``"redump"`` / ``"hasheous"`` etc.) — fed
    into the Dump row's ``dat_source`` column.
  * ``entry``: the full :class:`RemoteHashEntry` so the orchestrator
    can copy ``name`` / ``crc32`` / ``size_bytes`` into a freshly
    created Dump row when needed.
  * ``dump_status``: the parsed status the orchestrator threads
    into :class:`ReleaseFacts.dump_status` for the profile gate.

A miss (no entry on any backend) is **not** a failure — the
pipeline continues to identification (FR-011). The orchestrator
records ``dat_verified=False`` on the Dump and proceeds.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from romarr.domain.enums import DumpStatus

if TYPE_CHECKING:
    from romarr.identification.hashmatch.cascade import HashMatchCascade
    from romarr.identification.hashmatch.types import RemoteHashEntry


@dataclass(frozen=True)
class DatMatchResult:
    """Outcome of one DAT-match step invocation."""

    dat_verified: bool
    dat_source: str | None
    entry: RemoteHashEntry | None
    dump_status: DumpStatus
    backend_status: dict[str, str]
    """Per-backend outcome string (``"ok"``/``"empty"``/``"<error>"``/
    ``"circuit_open"``) — copied verbatim from the cascade. The
    audit row stores the dict so the operator can see which
    backend(s) hit and which short-circuited."""


async def match_dat(
    *,
    cascade: HashMatchCascade,
    platform_id: int,
    sha1: str,
) -> DatMatchResult:
    """Look up ``sha1`` in the cascade for ``platform_id``.

    Returns a :class:`DatMatchResult`. Never raises; backend
    failures surface in ``backend_status`` and the result reflects
    whatever entries did make it through.
    """
    cascade_match = await cascade.lookup_sha1(
        platform_id=platform_id, sha1=sha1.lower()
    )
    winner = cascade_match.winner

    if winner is None:
        return DatMatchResult(
            dat_verified=False,
            dat_source=None,
            entry=None,
            dump_status=DumpStatus.UNKNOWN,
            backend_status={
                str(k): v for k, v in cascade_match.backend_status.items()
            },
        )

    return DatMatchResult(
        dat_verified=winner.status is DumpStatus.VERIFIED,
        dat_source=winner.source,
        entry=winner,
        dump_status=winner.status,
        backend_status={
            str(k): v for k, v in cascade_match.backend_status.items()
        },
    )


__all__ = ["DatMatchResult", "match_dat"]
