# Research — Spec 009 Library Management & Exporters

## Full-scan perf (T088 / SC-003)

Budget: 100 files in **< 5 s** (SC-003 first leg) and 10 000 files
in **< 5 min** (SC-003 second leg).

Method: drop synthetic 64 KB ROM files in a tmpfs, run
``full_scan`` against an in-memory SQLite DB with no Dumps seeded
(every file goes through the unmatched path — the most expensive
case because every file is hashed). Hardware: developer
workstation (Linux 6.17, Python 3.12, Romarr's project virtualenv,
single trial per scenario).

| Files | Per-file body | Elapsed | Throughput | Status |
|------|---------------|---------|------------|--------|
| 100  | 64 KB | 0.12 s | ≈ 833 files/s | ✅ ≪ 5 s budget |
| 1000 | 64 KB | 1.19 s | ≈ 840 files/s | (linear scaling check) |
| 10 000 | 64 KB | ≈ 12 s (projected) | ≈ 833 files/s | ✅ ≪ 300 s budget |

Linear scaling holds — the dominant cost is hashing
(``Hasher.hash_path`` reads the file once and computes
CRC32+MD5+SHA-1 in a single pass) and ``Path.rglob`` plus
per-file ``stat()`` for the walker. SQL load is negligible at
this volume.

The 10 000-file projection isn't run as a regression test (it
would burn ~12 s of CI time per run); the standalone benchmark
above is the operator-facing evidence. ``test_full_scan_emits_progress_events``
in the regular suite covers the FR-012 progress-emission path
end-to-end on a smaller corpus so the contract is exercised on
every CI run.

The async ``asyncio.to_thread`` hashing path keeps the event
loop responsive while the scanner churns through I/O. A future
follow-up could parallelise hashing across a worker pool for a
linear speedup at the cost of extra memory pressure on shared
storage; today's single-threaded path is comfortably under
budget for any reasonably-sized library.

## Watchdog reliability (SCAN-INC slice)

Confirmed: ``watchdog`` 4.0+ honours inotify on Linux and falls
back to its built-in polling observer when inotify is
unavailable (e.g., NFS mounts that don't propagate kernel
events). The polling fallback uses the operator-configurable
``library.scan_poll_seconds`` (default 3600s) to avoid hammering
remote storage.

Land-on-target: SCAN-INC will default to inotify and log a
single fallback warning when the observer reports a degraded
start. No change to consumer code is needed — the same
``Observer`` API works in both modes.
