"""Single-pass streaming hasher for ROM files.

Computes CRC32 + MD5 + SHA-1 from one file read (FR-014). SHA-256 is
optional and disabled by default. A configurable buffer size (default
1 MiB, FR-015) keeps memory bounded; running off the asyncio event
loop is the caller's job via ``asyncio.to_thread`` (FR-016).

Performance target: hash a 1 GB ROM on local SSD in under 10 seconds
(SC-002).
"""

from __future__ import annotations

import asyncio
import hashlib
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING, AnyStr

if TYPE_CHECKING:
    from io import BufferedReader
    from os import PathLike

DEFAULT_BUFFER_SIZE = 1 << 20  # 1 MiB
"""Default streaming buffer size — picked to balance throughput and RAM."""


@dataclass(frozen=True, slots=True)
class HashResult:
    """The hashes produced by a single :class:`Hasher` pass.

    All hex digests are lowercase. ``crc32`` is zero-padded to 8 chars
    so it sorts and compares cleanly against DAT-derived strings.
    """

    crc32: str
    md5: str
    sha1: str
    sha256: str | None
    size_bytes: int

    def as_dict(self) -> dict[str, str | int | None]:
        """Serialize to a dict for logging or DB persistence."""
        return {
            "crc32": self.crc32,
            "md5": self.md5,
            "sha1": self.sha1,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


class Hasher:
    """Stream-once-compute-many hasher.

    Use as a one-shot helper:

    >>> hasher = Hasher()
    >>> result = hasher.hash_path(Path("/games/sonic.md"))
    >>> result.sha1
    '1d7e0c1d...'

    Or pass an existing file handle for tests / archive entries:

    >>> with open(path, 'rb') as fh:
    ...     result = hasher.hash_stream(fh)
    """

    def __init__(
        self,
        buffer_size: int = DEFAULT_BUFFER_SIZE,
        compute_sha256: bool = False,
    ) -> None:
        if buffer_size <= 0:
            raise ValueError("buffer_size must be positive")
        self.buffer_size = buffer_size
        self.compute_sha256 = compute_sha256

    def hash_path(self, path: str | PathLike[str]) -> HashResult:
        """Hash the file at ``path``. Blocks; call from a worker thread."""
        with Path(path).open("rb") as fh:
            return self.hash_stream(fh)

    def hash_stream(self, stream: IO[AnyStr] | BufferedReader) -> HashResult:
        """Hash bytes from ``stream`` until EOF.

        The stream MUST be opened in binary mode (returns ``bytes``).
        Position is consumed as the hasher reads; the caller is
        responsible for reset/close semantics.
        """
        crc = 0
        md5 = hashlib.md5(usedforsecurity=False)
        sha1 = hashlib.sha1(usedforsecurity=False)
        sha256 = hashlib.sha256() if self.compute_sha256 else None
        total = 0

        while True:
            chunk = stream.read(self.buffer_size)
            if not chunk:
                break
            assert isinstance(chunk, (bytes, bytearray)), (
                "Hasher requires a binary-mode stream; got "
                f"{type(chunk).__name__}"
            )
            crc = zlib.crc32(chunk, crc)
            md5.update(chunk)
            sha1.update(chunk)
            if sha256 is not None:
                sha256.update(chunk)
            total += len(chunk)

        return HashResult(
            crc32=f"{crc & 0xFFFFFFFF:08x}",
            md5=md5.hexdigest(),
            sha1=sha1.hexdigest(),
            sha256=sha256.hexdigest() if sha256 is not None else None,
            size_bytes=total,
        )


async def hash_file(
    path: str | PathLike[str],
    *,
    buffer_size: int = DEFAULT_BUFFER_SIZE,
    compute_sha256: bool = False,
) -> HashResult:
    """Async-friendly wrapper that runs :class:`Hasher` off the event loop.

    Per FR-016, hashing must NOT block FastAPI's event loop. This
    helper offloads to the default thread pool so callers in async
    handlers can ``await hash_file(...)`` directly.
    """
    hasher = Hasher(buffer_size=buffer_size, compute_sha256=compute_sha256)
    return await asyncio.to_thread(hasher.hash_path, path)
