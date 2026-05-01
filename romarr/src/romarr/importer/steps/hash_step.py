"""Hash-step (FR-008 / pipeline step 3).

Walks a directory of extracted files, filters by platform-format
extension + min_size_bytes, and hashes the survivors via spec 001's
:class:`Hasher`. Hashing runs off the asyncio event loop in a
threadpool — large CD images or 10s-of-MB ROMs would otherwise
block the orchestrator while the WATCH step queues fresh imports.

The step is **pure-ish**: side effects are the file reads + the
hasher's CPU work. No DB access, no logging side effects, no
network I/O.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING

from romarr.identification.hasher import Hasher

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from pathlib import Path

    from romarr.identification.hasher import HashResult


@dataclass(frozen=True)
class FormatRule:
    """One ``(extension, min_size_bytes)`` rule the hash step
    consults to decide whether a file is a hashable ROM.

    ``extension`` is matched case-insensitively and the leading dot
    is optional (``".md"`` and ``"md"`` are equivalent).
    ``min_size_bytes`` lets the importer skip readme.txt-style noise
    files that share an extension with a ROM (FR-008).
    """

    extension: str
    min_size_bytes: int = 0

    @property
    def normalised_extension(self) -> str:
        return self.extension.lstrip(".").lower()


def _candidate_files(
    directory: Path, rules: Sequence[FormatRule]
) -> Iterable[tuple[Path, FormatRule]]:
    """Yield every file under ``directory`` whose extension matches
    one of ``rules`` and whose size meets the rule's
    ``min_size_bytes`` floor.

    The traversal uses ``Path.rglob`` (sorted for determinism). The
    returned rule is the matching one — useful when the caller wants
    to record which rule applied.
    """
    by_ext = {rule.normalised_extension: rule for rule in rules}
    for entry in sorted(directory.rglob("*")):
        if not entry.is_file():
            continue
        ext = entry.suffix.lstrip(".").lower()
        rule = by_ext.get(ext)
        if rule is None:
            continue
        try:
            size = entry.stat().st_size
        except OSError:
            continue
        if size < rule.min_size_bytes:
            continue
        yield entry, rule


async def hash_candidates(
    *,
    directory: Path,
    rules: Sequence[FormatRule],
    hasher: Hasher | None = None,
) -> dict[Path, HashResult]:
    """Hash every candidate file under ``directory``.

    Returns a dict keyed by the absolute file path; the value is the
    foundation's :class:`HashResult` (CRC32 / MD5 / SHA-1, all
    populated from the same streaming pass). Hashing runs in a
    threadpool via :func:`asyncio.to_thread`.

    Files that fail to open are silently skipped — the orchestrator
    surfaces the failure via the empty result (the file is missing
    from the returned dict). This matches the behaviour of spec
    009's full scanner.
    """
    if hasher is None:
        hasher = Hasher()

    results: dict[Path, HashResult] = {}
    for path, _rule in _candidate_files(directory, rules):
        try:
            results[path] = await asyncio.to_thread(hasher.hash_path, path)
        except OSError:
            continue
    return results


__all__ = ["FormatRule", "hash_candidates"]
