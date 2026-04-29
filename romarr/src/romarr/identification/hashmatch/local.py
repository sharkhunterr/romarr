"""Local DAT backend — wraps :class:`DatManager` for the cascade."""

from __future__ import annotations

from typing import TYPE_CHECKING

from romarr.domain.enums import DumpStatus
from romarr.identification.hashmatch.types import (
    BackendName,
    HashLookupResult,
    RemoteHashEntry,
)

if TYPE_CHECKING:
    from romarr.identification.dat.manager import DatManager


class LocalDatBackend:
    """Cascade-shaped wrapper around :class:`DatManager` lookups."""

    name = BackendName.LOCAL

    def __init__(self, manager: DatManager) -> None:
        self._manager = manager

    async def lookup_sha1(self, *, platform_id: int, sha1: str) -> HashLookupResult:
        try:
            entries = await self._manager.lookup_by_sha1(
                platform_id=platform_id, sha1=sha1
            )
        except Exception as exc:  # pragma: no cover — DB errors are tested upstream
            return HashLookupResult(
                backend=BackendName.LOCAL, error=f"db_error:{type(exc).__name__}"
            )

        return HashLookupResult(
            backend=BackendName.LOCAL,
            entries=tuple(
                RemoteHashEntry(
                    source=e.source,
                    name=e.name,
                    crc32=e.crc32,
                    md5=e.md5,
                    sha1=e.sha1,
                    size_bytes=e.size_bytes,
                    status=DumpStatus(e.status) if isinstance(e.status, str) else e.status,
                )
                for e in entries
            ),
        )
