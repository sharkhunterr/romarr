# Implementation Plan: Import Pipeline

**Branch**: `008-import-pipeline` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification at `specs/008-import-pipeline/spec.md`
**Depends on**: `001-foundation`, `005-download-clients`, `006-profiles`,
`007-search-decision-engine`. **Forward-references** the future
`010-library` spec.

## Summary

The Import Pipeline turns a completed download into a properly identified,
DAT-verified, hardlinked Dump in the operator's library. It is **the most
operationally critical pipeline in Romarr** — bugs here corrupt user
collections.

The pipeline runs 13 ordered steps. Most are **compositions of existing
primitives** rather than new logic:

- Step 1 (Watch) is new code (polling loop + webhook handler + lifespan wiring).
- Steps 3-6 (Hash, DATMATCH, IDENTIFY, GAMEMATCH) are thin wrappers around
  `Hasher`, `HashMatchCascade`, `Identifier`, plus a small RapidFuzz-90 game
  resolver.
- Step 8 (PROFILEGATE) re-uses spec 006's `ProfileEvaluator`.
- Step 9 (RENDER) re-uses spec 006's `NamingTemplateEngine`.
- Steps 12-13 (LIFECYCLE, NOTIFY) re-use spec 005's tag operations.

The novel pieces are:

1. **An atomic mover** with hardlink-first + cross-fs fallback +
   idempotency-by-SHA-1 (step 10).
2. **A multi-disc detector** with cue/bin parsing + filename-pattern matching
   (step 7).
3. **An async per-import advisory lock** keyed on `(release_id, source_hash_sha1)`
   to coalesce concurrent imports (FR-033, SC-007).
4. **A webhook endpoint** with constant-time token comparison + rate
   limiting.
5. **An archive extractor** with recursion-depth-3 ceiling, supporting
   `.zip` / `.7z` / `.rar`.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: SQLAlchemy 2.0 (async), Pydantic v2, Alembic,
`py7zr>=0.21` (7-zip support), `rarfile>=4.2` (RAR support; requires the
`unrar` binary in the Docker image), `aiofiles>=23` (async file I/O for the
mover), `rapidfuzz>=3.6` (already a dep from spec 007), structlog. **No new
HTTP client.**
**Storage**: SQLite default / PostgreSQL 15+ optional. One new table
(`import_history`) plus column additions to the existing `unidentified_dump`
(`rejection_reason`, `library_id` FK, `suggested_game_id` FK).
**Testing**: pytest, pytest-asyncio, pytest-cov, hypothesis (multi-disc
detection property tests), respx (download-client mocks), freezegun (5-min
grace + 30-s polling cadence), `tmp_path` + tmpfs mount (cross-fs mover
tests), TestClient (FastAPI endpoints + webhook auth tests).
**Target Platform**: Linux server in the Romarr Docker image. The Docker
image MUST install `unrar` (Debian/Ubuntu package) for `rarfile` to work.
**Project Type**: Backend Python module added under `src/romarr/importer/`.
**Performance Goals**:
- Webhook-triggered import path: < 1 s p95 from webhook receipt to start of
  hashing (excluding hash time on large files; SC-008).
- Cross-filesystem copy of a 1 GB ROM completes in under 30 s on local SSD
  (network-bound otherwise).
- Idempotency check (re-import) returns within 100 ms (it's a single SHA-1
  hash + one indexed DB lookup).
**Constraints**:
- Hardlinks always attempted first (Constitution Article XII; FR-024).
- Imports idempotent (Constitution Article XII / XVII; FR-025, FR-033).
- No automatic deletion of imported files without explicit lifecycle policy
  (Article XII; FR-029).
- Concurrent imports of same release coalesce to one Dump (FR-033).
- Hash mismatches with DAT do NOT auto-reject (FR-011).
**Scale/Scope**:
- Imports per day: tens to hundreds for a power user.
- Lock contention: rare; the lock is a fast in-process advisory primitive.
- `import_history` rows: thousands per year per instance; needs a periodic
  prune from the future Tasks spec.

## Constitution Check

*Gate: must pass before Phase 0 research and again after Phase 1 design.*

| Article | Gate | Status |
|---------|------|--------|
| III — Technology Stack (Locked) | SQLAlchemy 2.0 async, Pydantic v2, Alembic; py7zr + rarfile + aiofiles are well-maintained Python libraries; no custom protocol code. | ✅ Conformant. |
| V — Profile-Driven Decisions | Step 8 delegates to spec 006's `ProfileEvaluator`; step 9 to its `NamingTemplateEngine`. No business-logic duplication. | ✅ Conformant. |
| VI — Identification Cascade | Step 4 uses spec 001's hash-match cascade; step 5 uses the foundation `Identifier`. Authority order preserved. | ✅ Conformant. |
| IX — Metadata Aggregation | Imports do not consume metadata enrichment in this spec — they only consume already-aggregated metadata via Game/Release rows. | ✅ Conformant (no interaction). |
| XII — Library Discipline | Hardlinks default (FR-024); imports idempotent (FR-025 + FR-033); per-Release cutoff respected (Release.status update at FR-027); no auto-delete without explicit lifecycle (FR-029). | ✅ Conformant. |
| XVI — Quality Gates | ≥ 75% coverage on `importer/` (SC-010); 1-second p95 webhook-to-hash (SC-008); zero ruff warnings. | ✅ Conformant. |
| XVII — Idempotency & Safety | Idempotent re-import (FR-025); concurrent imports coalesce (FR-033); failed imports never delete the source (FR-005, edge cases); webhook auth uses constant-time comparison (FR-002). | ✅ Conformant. |

**Result**: GREEN. No constitutional violations; **Complexity Tracking**
stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/008-import-pipeline/
├── plan.md              # this file
├── spec.md              # user-value specification
├── data-model.md        # import_history table + unidentified_dump extensions + value types
├── tasks.md             # 15-phase task list (one per pipeline step + 2 bookends)
└── checklists/
    └── requirements.md  # spec-quality checklist
```

### Source Code (additions to the existing repo)

```text
src/romarr/
├── importer/                            # NEW — top-level module
│   ├── __init__.py                       # public re-exports: ImportEngine, run_import, watcher loop
│   ├── types.py                          # ImportContext, ImportOutcome, MultiDiscGroup, LifecycleAction, RejectionReason
│   ├── errors.py                         # ImporterError, ExtractError, MoveError, GameNotMatched, ProfileRejected, LockTimeout, WebhookAuthError
│   ├── locks.py                          # async in-process advisory lock keyed on (release_id, sha1)
│   ├── steps/                            # one module per pipeline step (FR-001 .. FR-031)
│   │   ├── __init__.py
│   │   ├── watch.py                      # polling loop + webhook handler + signal channel
│   │   ├── extract.py                    # zip/7z/rar with depth limit
│   │   ├── hash_step.py                  # wraps Hasher (foundation)
│   │   ├── dat_match.py                  # wraps HashMatchCascade (foundation)
│   │   ├── identify.py                   # wraps Identifier (foundation)
│   │   ├── game_match.py                 # DAT→IGDB then RapidFuzz at 90
│   │   ├── multi_disc.py                 # cue/bin parser + filename heuristics
│   │   ├── profile_gate.py               # wraps ProfileEvaluator (spec 006)
│   │   ├── render.py                     # wraps NamingTemplateEngine (spec 006)
│   │   ├── move.py                       # hardlink-first atomic mover with cross-fs fallback
│   │   ├── db_update.py                  # Release.status + Dump creation + previous-Dump cleanup
│   │   ├── lifecycle.py                  # async tag + scheduled remove
│   │   └── notify.py                     # OnImport / OnUpgrade event emission
│   ├── orchestrator.py                   # the 13-step driver function: run_import(context) -> ImportOutcome
│   ├── manual.py                         # manual import + unidentified-dump match + retry
│   ├── webhook.py                        # POST /api/v3/webhook/download-complete handler with token auth + rate limit
│   ├── models.py                         # ImportHistory SQLAlchemy 2.0 model + extensions to UnidentifiedDump
│   ├── schemas.py                        # Pydantic *Read/*Create + ImportRequest, RetryRequest, ManualMatchRequest
│   └── api/                              # FastAPI router stubs
│       ├── __init__.py
│       ├── manual.py                     # /api/v3/rom/import/manual*
│       ├── history.py                    # /api/v3/rom/import/history*, /retry/{id}
│       ├── unidentified.py               # /api/v3/rom/unidentified*
│       └── webhook.py                    # /api/v3/webhook/download-complete
└── db/
    └── alembic/
        └── versions/
            └── 0008_import_pipeline.py   # NEW migration

tests/
├── importer/
│   ├── conftest.py                       # respx download-client mocks; tmp_path library; fake DAT entries
│   ├── test_models.py
│   ├── test_migration_0008.py
│   ├── test_locks.py                     # contention + 60-s timeout (FR-034)
│   ├── steps/
│   │   ├── test_watch_polling.py         # 30-s cadence, 'romarr' tag filter
│   │   ├── test_extract.py               # zip/7z/rar + depth-3 ceiling + idempotent re-extract
│   │   ├── test_hash_step.py             # composes foundation hasher
│   │   ├── test_dat_match.py             # composes foundation cascade
│   │   ├── test_identify.py              # composes foundation Identifier
│   │   ├── test_game_match.py            # DAT→IGDB happy path; RapidFuzz threshold 90
│   │   ├── test_multi_disc.py            # cue/bin + 5 filename patterns + property tests
│   │   ├── test_profile_gate.py          # spec 006's evaluator wired
│   │   ├── test_render.py                # spec 006's naming engine wired
│   │   ├── test_move_hardlink.py         # same-fs hardlink (inode equality)
│   │   ├── test_move_crossfs.py          # tmpfs fallback to copy+verify+delete
│   │   ├── test_move_idempotent.py       # re-run no-op (FR-025, SC-002)
│   │   ├── test_move_fault_injection.py  # mid-move crash leaves nothing partial (SC-009)
│   │   ├── test_db_update.py             # previous-Dump cleanup when keep_dump_history=false
│   │   ├── test_lifecycle.py             # 5-min grace; tag application
│   │   └── test_notify.py                # OnImport + OnUpgrade emitted
│   ├── test_orchestrator.py              # 13-step end-to-end with fixture inputs
│   ├── test_concurrent_imports.py        # SC-007: 5 concurrent → 1 Dump
│   ├── test_auto_blocklist_on_failure.py # spec 007 helper invoked
│   ├── test_manual_flow.py               # ?force=true profile warning vs. block
│   ├── test_webhook.py                   # constant-time token; rate limit; HTTP 401
│   └── api/
│       ├── test_manual_endpoints.py
│       ├── test_history_endpoints.py
│       ├── test_unidentified_endpoints.py
│       └── test_webhook_endpoint.py
└── fixtures/
    ├── importer/
    │   ├── archives/
    │   │   ├── good_zip.zip                   # 1 valid ROM inside
    │   │   ├── good_7z.7z                     # 1 valid ROM
    │   │   ├── good_rar.rar                   # 1 valid ROM
    │   │   ├── nested_zip_in_zip.zip          # 2-level nesting
    │   │   ├── too_deep_4_levels.zip          # 4-level → depth-exceeded
    │   │   ├── corrupted.7z                   # extract failure for FR-035
    │   │   └── compilation_pack.zip           # multiple ROMs for edge case
    │   ├── multi_disc/
    │   │   ├── ff9_disc1.cue / .bin
    │   │   ├── ff9_disc2.cue / .bin
    │   │   ├── filename_pattern_disc.bin      # "Game (Disc 2).bin" without parent
    │   │   └── side_a_b/                      # "(Side A)" / "(Side B)" floppy
    │   └── webhook_payloads/
    │       ├── qbit_torrent_finished.json
    │       └── sab_history_complete.json
```

**Structure Decision**: keep the 13 steps as **separate modules** under
`importer/steps/` so each has its own test file and can be exercised in
isolation. The orchestrator is a small driver; the heavy lifting lives in
the steps. The mover (step 10) is the riskiest piece — it gets four
dedicated test files (hardlink, cross-fs, idempotency, fault-injection).

The async lock is a single async primitive at `importer/locks.py`; it is
NOT a database lock (which would couple the lock lifetime to the
transaction). It is an in-process `asyncio.Lock` keyed by
`(release_id, sha1)` via a small registry. For multi-process deployments
(which Romarr does NOT target — see Article I), a future spec could
swap in a Redis-based advisory lock without changing the call sites.

## Phase 0 — Research

Three small research items resolved before code; results captured in
`specs/008-import-pipeline/research.md` if confirmation is needed at code time.

1. **Cross-filesystem detection** — `os.stat(src).st_dev !=
   os.stat(dest_dir).st_dev` is the canonical, reliable signal on Linux. We
   handle the edge case where `dest_dir` does not yet exist by walking up to
   the nearest existing parent and stat-ing that.
2. **Multi-disc cue parser** — the `.cue` file is small ASCII; the parser
   reads the `FILE "<name>" BINARY` lines via a 50-line regex helper. We do
   NOT pull a full `pycdlib`-class dependency for what amounts to a
   one-line-per-bin extraction.
3. **Webhook auth** — constant-time string comparison via `secrets.compare_digest`.
   The expected token is loaded from the download-client config (encrypted
   at rest, decrypted in memory) per spec 005's encryption helper. Rate
   limiting is a 60-second sliding window in-process; persistence is not
   required for MVP.

## Forward Dependency on Library spec (010)

This feature reads three columns from a `library` table that does NOT exist
yet:

- `library.path` — the destination root.
- `library.lifecycle_policy` — the `hardlink_and_seed` /
  `move_and_remove` / `copy_and_keep` selector.
- `library.keep_dump_history` — controls whether previous Dump rows are
  deleted when a Release is re-imported.

The migration `0008_import_pipeline.py` ships a guard:

```python
if op.get_bind().has_table("library"):
    # Library spec landed first → just create the import_history table and the
    # unidentified_dump extension columns.
    ...
else:
    # Library spec hasn't landed yet → still safe to create import_history,
    # but mark library_id columns nullable so they materialize once Library lands.
    ...
```

Either ordering works. The implementation note: **prefer to ship the Library
spec (010) BEFORE coding this Import spec (008)**. The roadmap order has them
the wrong way round; if the operator follows the roadmap as written, they
will be unable to bind a real library to the import flow until they ship 010.
The data-model and the migration are designed to tolerate either order
gracefully, but the **runtime** behaviour requires Library rows to exist
before any import can target them.

## Phase 1 — Design Outputs

- `data-model.md` — DDL for `import_history`; column additions on
  `unidentified_dump`; the value types `ImportContext`, `ImportOutcome`,
  `MultiDiscGroup`, `LifecycleAction`.
- No `contracts/` — endpoint stubs only; full payload schemas live in the
  API spec.
- No `quickstart.md` — a REPL one-liner showing
  `await ImportEngine.run_import(...)` lives in the wrap-up phase of
  `tasks.md`.

### Re-check: Constitution after design

Same table as above; nothing in the design pulls a constraint.
**Result**: GREEN.

## Complexity Tracking

> *Empty.* No constitutional violations. No deviations to justify.

## Clarification Deltas (Session 2026-04-29)

The 5 clarifications recorded in `spec.md` add the following architectural
constraints to this plan:

- **Auto-blocklist taxonomy aligned with spec 007** (FR-035 rewritten +
  FR-035a) — the importer emits failure subreasons in two strict
  categories. Only **content-correctness** subreasons
  (`hash-mismatch`, `dat-rejected`, `format-corrupt`,
  `archive-extraction-failed`) trigger spec 007's blocklist helper.
  **Transient/operational** subreasons (`disk-full`, `permission-denied`,
  `client-unreachable`, `move-failed`, `scan-timeout`) record in
  `import_history` and follow the existing 30 s / 2 min / 5 min
  exponential-backoff retry policy without auto-blocklisting.
- **Webhook auth: bearer in `X-Romarr-Webhook-Token`** (FR-002 rewritten)
  — header name fixed; constant-time comparison via `hmac.compare_digest`;
  rate-limited 10 req/min/source-IP; HTTP 401 with no info disclosure
  on mismatch. No HMAC body signing at MVP.
- **Destination-collision parking** (FR-026a) — automatic-flow encounter
  of an existing destination with different SHA-1 MUST: leave the existing
  file untouched, park the incoming file in `unidentified_dump` with
  `rejection_reason = 'destination_collision'` and `suggested_game_id`
  populated, emit `OnHealthIssue` `category = 'naming-collision'`. No
  numeric-suffix disambiguation EVER (would mask Naming profile bugs).
- **Zip-bomb defense** (FR-004a) — extractor caps total uncompressed
  expansion at `max(4 × archive_compressed_size, 5 GiB)` enforced
  incrementally as bytes are written. Overrun aborts extraction, deletes
  partial files, parks the archive in `unidentified_dump` with
  `rejection_reason = 'extract:bomb-detected'`, emits `OnHealthIssue`
  `category = 'extract-bomb'`.
- **Admin-only mutations; webhook is its own auth** (FR-038a) —
  POST/POST-match/DELETE/POST-retry require admin role. Reads accessible
  to any authenticated user. The webhook endpoint authenticates solely
  via `X-Romarr-Webhook-Token` and does NOT consult the user-session/
  API-key chain.

No new tables. The `unidentified_dump` extension columns (`rejection_reason`,
`library_id` FK, `suggested_game_id` FK) were already in scope for this
spec's data-model.
