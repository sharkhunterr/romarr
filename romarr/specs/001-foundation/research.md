# Spec 001 — Research notes

Notes captured during implementation that don't fit cleanly in
the spec or plan but matter for the next maintainer.

## lxml `iterparse` cleanup pattern (FR-017)

A real Logiqx DAT can be ~200 MiB (No-Intro full pack). The naive
`etree.parse()` would allocate a tree the same size as the file —
unworkable inside an async lifespan that has to ingest several
DATs concurrently.

The canonical streaming pattern:

```python
context = etree.iterparse(stream, events=("end",), tag="game")
for event, elem in context:
    # ... extract <rom> rows ...
    elem.clear()
    for ancestor in elem.xpath("ancestor-or-self::*"):
        while ancestor.getprevious() is not None:
            parent = ancestor.getparent()
            if parent is None:
                break
            del parent[0]
```

Two crucial details:

1. `elem.clear()` alone is NOT enough — lxml retains references to
   already-yielded siblings on the parent. The inner while-loop walks
   up the ancestor chain and deletes preceding siblings as it goes,
   which lets the GC actually reclaim the memory.
2. The `del context` in a `finally` block is needed because lxml's
   `iterparse` holds a C-level reference to the file stream;
   forgetting the cleanup leaks the file handle on Python 3.12.

Profiling (informal, on a 100 MiB synthetic DAT): peak RSS stays
under 50 MiB throughout the parse, vs ~600 MiB without the
ancestor cleanup. The behaviour is exercised by
`tests/identification/test_dat_manager.py::test_dat_manager_batches_large_ingest`
(2500-row synthetic DAT, slice 177).

## Hash performance (SC-002)

The 1 GiB single-pass hash budget (CRC32 + MD5 + SHA-1 in one
read) is implemented in `src/romarr/identification/hasher.py`. The
single-pass approach uses three running hashers + a 64 KiB read
buffer; the bottleneck is `read()`, not the hashes themselves.
The 1 GiB SC-002 perf check is gated on a real-corpus release-cut
verification — see T085 in `tasks.md`.

## Identifier authority cascade (FR-022)

The cascade lives at `src/romarr/identification/identifier.py`
and merges signals from the four subsystems in priority order:

1. Hash match (highest authority — exact byte equivalence)
2. Header read (detects platform-specific magic numbers)
3. Filename parser (No-Intro / TOSEC / GoodTools / Scene)
4. Torznab extended attributes (lowest, indexer-asserted)

Conflicts resolve to the higher-authority source; the merger
records every contribution with provenance so the audit trail
shows why a given Game / Release was picked.

## Why DAT remote services are out-of-process

Hasheous + PlayMatch + Datomatic-API style services are remote
HTTPS endpoints. Romarr never self-hosts them — those are
RomM/community-operated public services. The `hashmatch/remote.py`
client speaks the documented public protocols and treats the
service as fallible (timeouts + circuit breaker + per-service
backoff). When all three fail, identification falls back to the
local DAT cache + filename parser; a no-match doesn't block the
import, it just lands the file in `unidentified_dump` per FR-029.
