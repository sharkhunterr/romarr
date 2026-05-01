"""Identify-step (FR-013 / pipeline step 5).

Thin wrapper around foundation's :meth:`Identifier.identify`.
The importer's working state already carries the file's hashes
(produced by HASH) and a Torznab-attrs payload (when the import
came from a grab). This step just composes the foundation
cascade with those preloaded inputs so the orchestrator doesn't
re-hash and so provenance from the originating grab record
flows through to the merged identification.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from romarr.identification.hasher import HashResult
    from romarr.identification.identifier import (
        Identifier,
        IdentifyOutcome,
        TorznabAttrs,
    )


async def identify_file(
    *,
    identifier: Identifier,
    path: Path,
    platform_id: int | None = None,
    torznab_attrs: TorznabAttrs | None = None,
    precomputed_hashes: HashResult | None = None,
) -> IdentifyOutcome:
    """Run the foundation identification cascade against ``path``.

    Always passes ``compute_hashes=False`` when
    ``precomputed_hashes`` is provided — the importer hashed the
    file in the previous step and that result is the canonical
    one for the pipeline. ``platform_id=None`` skips the
    hash-match cascade (the orchestrator routes to GAMEMATCH for
    fuzzy resolution when the platform isn't yet known).
    """
    return await identifier.identify(
        path=path,
        platform_id=platform_id,
        torznab_attrs=torznab_attrs,
        compute_hashes=precomputed_hashes is None,
        precomputed_hashes=precomputed_hashes,
    )


__all__ = ["identify_file"]
