# Research — Spec 008 Import Pipeline

## Webhook latency (T093 / SC-008)

Budget: webhook-to-202 latency p95 **< 1 s** (SC-008).

Method: 100 trials of POST
``/api/v3/webhook/download-complete`` against a fresh
``httpx.AsyncClient`` over ``ASGITransport`` with a configured
token, no dispatcher attached, rate-limit reset every 10
requests so the burst doesn't trip 429. ``time.perf_counter``
brackets the request. Hardware: developer workstation
(Linux 6.17, Python 3.12), opportunistic measurement with no
isolation.

Result:

```
webhook 202 latency over 100 trials:
  p50 = 0.34 ms
  p95 = 0.66 ms
  max = 0.78 ms
```

**p95 ~ 0.66 ms — ~1500x under the 1 s SC-008 budget.** The
handler runs three trivial checks (token compare, rate-limit
deque scan, Pydantic validation) and returns; the actual import
runs as a fire-and-forget ``asyncio.create_task`` so the
caller's connection isn't held open during the pipeline
(FR-002).

Headroom for the orchestrator integration to take its time
without backpressure on the webhook publisher. The fire-and-
forget pattern already protects the response path from any
import-side stall.

## Bomb-defense cap formula

Per FR-004a the cap is ``max(4 × compressed_size, 5 GiB)``,
enforced incrementally. Two cases the cap protects against:

  * **High-ratio bomb** — a 1 KB compressed bomb that expands
    to gigabytes. The 5 GiB floor catches it.
  * **Large-but-not-bombing archive** — a 50 GB legit ROM
    collection. The ``4 ×`` factor over 50 GB = 200 GB cap;
    legitimate archives have compressed-vs-uncompressed ratios
    well under 4× for ROM data, so the cap doesn't block
    operator workflows.

The 64 KB streaming write loop in ``_stream_with_cap`` checks
the running total against the remaining budget on every chunk;
the moment cumulative output exceeds the cap, the writer
short-circuits with ``ExtractError(EXTRACT_BOMB_DETECTED)`` and
the outer handler cleans up the partial output.

For 7z, py7zr's API doesn't expose per-byte streaming — we
pre-validate against ``info.uncompressed`` sums in the
archive's metadata. A malicious archive that lies about its
metadata would trip the disk-full guard during extractall;
defense-in-depth holds.

## Polling watcher deferral

T014-T016 (poll every 30 s, filter by tag, isolate failing
client) and T020 / T022 (WatcherLoop + lifespan wiring) are
deferred until ``DownloadClient.list_managed_downloads`` lands
on spec 005's ABC. The current set of methods
(``add_torrent``, ``get_status``, ``remove``,
``set_imported_tag``) doesn't expose the bulk listing the
watcher needs.

For MVP, the webhook covers the operator's primary
post-download-complete signal (qBittorrent's ``run external
program`` hook, SAB's post-processing hook). Operators who
prefer polling can run a small cron-style script that calls
the webhook for every download tagged ``romarr`` and not
``romarr-imported``; the watcher loop is a convenience, not a
correctness requirement.

## Manual / retry / match endpoints deferral

The remaining mutating endpoints —
``POST /api/v3/rom/import/manual``,
``POST /api/v3/rom/unidentified/{id}/match``,
``POST /api/v3/rom/import/retry/{import_id}`` — depend on the
orchestrator's ``run_import`` end-to-end. The 12 pipeline
steps and the ``ImportLockManager`` are all in place; the
remaining work is the orchestrator's step-threading driver
that turns an :class:`ImportContext` into an
:class:`ImportOutcome`.

That driver is the single biggest piece of new code in the
follow-up integration slice. It composes:

  1. ``ImportLockManager`` acquisition keyed on (release_id,
     sha1) with the 60 s timeout.
  2. EXTRACT (when source is an archive).
  3. HASH on the extracted directory.
  4. DATMATCH per file.
  5. IDENTIFY to produce the merged identification.
  6. GAMEMATCH to resolve to a Game / Release / suggested
     game.
  7. MULTIDISC if multiple files.
  8. PROFILEGATE (force-aware).
  9. RENDER to compute the dest path.
  10. MOVE to land the file atomically.
  11. DBUPDATE to insert Dump + transition Release.
  12. LIFECYCLE to dispatch the post-import action.
  13. NOTIFY to emit OnImport / OnUpgrade.
  14. ImportHistory row write — at every success and every
      failure, with the structured ``rejection_reason`` for
      the operator.

Plus: auto-blocklist on content-correctness failures (FR-035 —
hash mismatch / DAT-rejected / format-corrupt /
archive-extraction-failed) wired to spec 007's blocklist
helper; transient/operational failures (disk-full,
permission-denied, client-unreachable, move-failed,
scan-timeout) recorded with retry-eligibility but never
blocklisted.
