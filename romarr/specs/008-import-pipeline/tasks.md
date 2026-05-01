---

description: "Granular task list for import pipeline — 13 pipeline steps + scaffolding + hardening"
---

# Tasks: Import Pipeline

**Input**: Design documents from `specs/008-import-pipeline/`
**Prerequisites**: `001-foundation`, `005-download-clients`, `006-profiles`,
`007-search-decision-engine` shipped. Forward-references `010-library`.
**Tests**: MANDATORY (Constitution Article XVI; SC-010: ≥ 75% on importer/)

**Organization**: 15 phases — one phase per pipeline step (13) plus 2 bookend
phases (`SCAF`, `HARD`).

## Format: `[ID] [P?] [Phase] Description`

- `[P]` = parallelizable with other `[P]` tasks in the same phase.
- Phase tag short codes: `SCAF`, `WATCH`, `EXTRACT`, `HASH`, `DATMATCH`,
  `IDENTIFY`, `GAMEMATCH`, `MULTIDISC`, `PROFILEGATE`, `RENDER`, `MOVE`,
  `DBUPDATE`, `LIFECYCLE`, `NOTIFY`, `HARD`.

---

## Phase 1: Scaffolding (`SCAF`)

**Purpose**: bring up the module skeleton, dependencies, types, locks,
errors, persistence, and orchestrator shell.

- [X] T001 [SCAF] Update `pyproject.toml` — add runtime dep
      `aiofiles>=23` (`py7zr>=0.21` and `rarfile>=4.1` already
      shipped with foundation). Docker `unrar` apt-get dependency
      documented in plan.md.
- [X] T002 [P] [SCAF] Create `src/romarr/importer/__init__.py`
      exposing the slice-1 surface (errors + types + lock manager
      + orchestrator stubs). The full ``ImportEngine`` symbol
      lands with the WATCH slice once polling + webhook + lifecycle
      compose into a single managed object.
- [X] T003 [P] [SCAF] Create `src/romarr/importer/errors.py` —
      `ImporterError`, `ExtractError`, `MoveError`, `GameNotMatched`,
      `ProfileRejected`, `LockTimeout`, `WebhookAuthError`.
- [X] T004 [P] [SCAF] Create `src/romarr/importer/types.py` —
      `RejectionReason` StrEnum + `ImportContext` /
      `MultiDiscGroup` / `LifecycleAction` / `ImportOutcome`
      frozen Pydantic models matching `data-model.md`.
- [X] T005 [P] [SCAF] Create `src/romarr/importer/locks.py` — async
      `ImportLockManager` with per-(release_id, sha1)
      :class:`asyncio.Lock` registry, 60-s default timeout
      (FR-033, FR-034). 4 tests cover distinct keys parallel,
      same-key serialisation, timeout raises ``LockTimeout``,
      lock released on exception.
- [X] T006 [P] [SCAF] Create `src/romarr/importer/models.py` —
      `ImportHistory` SQLAlchemy 2.0 model with the documented
      indices (started_at, release_started, correlation,
      native_id, success). The `UnidentifiedDump` extension
      columns (`rejection_reason`, `library_id`,
      `suggested_game_id`) live on the foundation ORM class so
      every consumer sees the same schema; only the FK target on
      `library_id` is gated by the migration.
- [X] T007 [P] [SCAF] Create `src/romarr/importer/schemas.py` —
      `ImportHistoryRead`, `ManualImportEntry` /
      `ManualImportRequest`, `ManualMatchRequest`,
      `RetryResponse`, `UnidentifiedDumpRead`. The
      `WebhookPayload` discriminated union lands with the WATCH
      slice once the per-client variants are needed.
- [X] T008 [SCAF] Author `src/romarr/db/alembic/versions/0008_import_pipeline.py`
      — DDL for `import_history` + `unidentified_dump`
      extensions with the gated FK pattern. Since spec 009
      (Library) shipped first, the ``library`` table exists when
      0008 runs and the FK on
      ``unidentified_dump.library_id`` is finalised here directly.
      ``down_revision = '0009_libraries'``.
- [X] T009 [SCAF] Create `src/romarr/importer/orchestrator.py` —
      `run_import(context) -> ImportOutcome`, `start_watcher()`,
      `stop_watcher()` stubs. Each raises `NotImplementedError`
      with a message naming the slice that fills it in.
- [X] T010 [SCAF] Extend `tests/conftest.py` to register
      `romarr.importer.models`; create `tests/importer/conftest.py`
      with `correlation_id`, `base_context`, `now` fixtures.
      Synthetic-ROM / fake-DAT / mock-client fixtures land
      with the slices that need them.
- [X] T011 [P] [SCAF] `tests/importer/test_models.py` — 5 tests:
      round-trip with all populated fields, CHECK constraint on
      `imported_via`, nullable FKs accept NULL on a failure row,
      coalesced marker round-trips, ``UnidentifiedDump`` extension
      columns persist through the foundation ORM class.
- [X] T012 [P] [SCAF] `tests/importer/test_locks.py` — 4 tests
      (see T005). Timeout test uses real ``asyncio.wait_for`` with
      a 100 ms timeout instead of freezegun — the lock manager
      uses ``asyncio`` internals which freezegun doesn't reach.
- [X] T013 [P] [SCAF] `tests/importer/test_migration_0008.py` —
      3 tests: import_history table + every nullable FK created;
      unidentified_dump extension columns + both FKs (game,
      library) finalised at head; downgrade reverses cleanly.
      Plus update to `test_migration_0009` so its
      ``test_migration_unidentified_dump_finalisation_gate_no_ops_at_0009``
      stops at 0009 (where the column doesn't exist) before
      rolling forward to head (where 0008 adds the column + FK).

**Checkpoint**: `alembic upgrade head` is clean; locks + models + types
+ scaffolding tests green; orchestrator imports cleanly.

---

## Phase 2: Watch (`WATCH`) — Pipeline step 1

**Purpose**: poll download clients + accept webhooks; emit "ready to import"
signals to the orchestrator.

### Tests

- [ ] T014 [P] [WATCH] `tests/importer/steps/test_watch_polling.py::test_polls_every_30s`
      — freezegun-advance time; assert one poll per configured client per
      30 seconds (FR-001).
- [ ] T015 [P] [WATCH] `tests/importer/steps/test_watch_polling.py::test_filters_by_tag`
      — only downloads tagged `romarr` AND missing `romarr-imported` are
      surfaced (FR-001).
- [ ] T016 [P] [WATCH] `tests/importer/steps/test_watch_polling.py::test_isolates_failing_client`
      — one client raises ConnectionError; others still polled; failure
      persisting > 10 minutes emits `OnHealthIssue` (FR-003).
- [ ] T017 [P] [WATCH] `tests/importer/test_webhook.py::test_constant_time_token`
      — bad token returns HTTP 401 with no log entry exposing the expected
      token (FR-002, edge case).
- [ ] T018 [P] [WATCH] `tests/importer/test_webhook.py::test_rate_limit`
      — 11 requests in 60 seconds from one source IP ⇒ the 11th gets
      HTTP 429.
- [ ] T019 [P] [WATCH] `tests/importer/test_webhook.py::test_immediate_import`
      — valid token; assert the import for the documented download_id
      starts within 1 second (SC-008).

### Implementation

- [ ] T020 [WATCH] Create `src/romarr/importer/steps/watch.py` — async
      `WatcherLoop` that runs every 30 s, iterates configured clients, and
      enqueues `(client_id, native_id)` candidates onto an internal
      asyncio.Queue consumed by the orchestrator.
- [ ] T021 [WATCH] Create `src/romarr/importer/webhook.py` — FastAPI
      handler at `/api/v3/webhook/download-complete` performing
      constant-time token comparison via `secrets.compare_digest` and
      sliding-window 60-s rate limit per source IP.
- [ ] T022 [WATCH] Wire `WatcherLoop.start()` into the application
      lifespan startup (the lifespan helper from spec 006). The loop is
      cancelable on shutdown.

**Checkpoint**: WATCH tests green; the watcher loop runs as a background
task and the webhook returns within the 1 s p95 budget.

---

## Phase 3: Extract (`EXTRACT`) — Pipeline step 2

### Tests

- [ ] T023 [P] [EXTRACT] `tests/importer/steps/test_extract.py::test_zip`
      — fixture `archives/good_zip.zip` extracts cleanly to a tmpdir.
- [ ] T024 [P] [EXTRACT] `tests/importer/steps/test_extract.py::test_7z`
      — fixture `archives/good_7z.7z` via `py7zr`.
- [ ] T025 [P] [EXTRACT] `tests/importer/steps/test_extract.py::test_rar`
      — fixture `archives/good_rar.rar` via `rarfile` (skip on systems
      without `unrar`).
- [ ] T026 [P] [EXTRACT] `tests/importer/steps/test_extract.py::test_recursive_two_levels`
      — `nested_zip_in_zip.zip` extracts at level 1 then level 2.
- [ ] T027 [P] [EXTRACT] `tests/importer/steps/test_extract.py::test_depth_exceeded`
      — `too_deep_4_levels.zip` raises with reason
      `extract:depth-exceeded` (FR-004).
- [ ] T028 [P] [EXTRACT] `tests/importer/steps/test_extract.py::test_idempotent_skip`
      — pre-existing extracted folder with matching content hash → no
      double-extract (FR-006).
- [ ] T029 [P] [EXTRACT] `tests/importer/steps/test_extract.py::test_corrupted_archive`
      — fixture `archives/corrupted.7z` raises `ExtractError`.
- [ ] T030 [P] [EXTRACT] `tests/importer/steps/test_extract.py::test_preserve_archive_flag`
      — when `preserve_archive = false` (default), the archive is deleted
      after a successful import; when `true`, kept (FR-005).

### Implementation

- [ ] T031 [EXTRACT] Create `src/romarr/importer/steps/extract.py` —
      `extract(archive_path: Path, dest_dir: Path, depth: int = 0) -> list[Path]`
      with the depth-3 ceiling, supporting `.zip` (stdlib `zipfile`),
      `.7z` (`py7zr`), `.rar` (`rarfile`).

**Checkpoint**: EXTRACT tests green; the depth-3 limit holds; idempotent
re-extract skips.

---

## Phase 4: Hash (`HASH`) — Pipeline step 3

### Tests

- [ ] T032 [P] [HASH] `tests/importer/steps/test_hash_step.py::test_walks_extracted_dir`
      — given a directory containing one ROM + one `readme.txt` smaller
      than `min_size_bytes`, the hasher hashes only the ROM (FR-008).
- [ ] T033 [P] [HASH] `tests/importer/steps/test_hash_step.py::test_streams_via_foundation_hasher`
      — calls go through `src/romarr/identification/hasher.py` (mock-and-
      assert).

### Implementation

- [ ] T034 [HASH] Create `src/romarr/importer/steps/hash_step.py` —
      `hash_candidates(directory, platform_formats) -> dict[Path, Hashes]`
      using foundation's `Hasher.async_hash_file`.

**Checkpoint**: HASH tests green; the small-file skip rule honours
`platform_format.min_size_bytes`.

---

## Phase 5: DAT match (`DATMATCH`) — Pipeline step 4

### Tests

- [ ] T035 [P] [DATMATCH] `tests/importer/steps/test_dat_match.py::test_local_dat_hit`
      — composes foundation's `HashMatchCascade`; first authoritative
      match populates `dat_verified=true, dat_source, dat_entry_id`.
- [ ] T036 [P] [DATMATCH] `tests/importer/steps/test_dat_match.py::test_no_dat_continues`
      — no match → `dat_verified=false`; pipeline does NOT block (FR-011).
- [ ] T037 [P] [DATMATCH] `tests/importer/steps/test_dat_match.py::test_baddump_status_propagated`
      — DAT entry's `status='baddump'` propagates as parsed
      `dump_status='baddump'`; `dat_verified` is set to false (US5.3).

### Implementation

- [ ] T038 [DATMATCH] Create `src/romarr/importer/steps/dat_match.py` —
      thin wrapper around `HashMatchCascade.lookup(...)`.

**Checkpoint**: DATMATCH tests green; "no DAT match" never blocks.

---

## Phase 6: Identify (`IDENTIFY`) — Pipeline step 5

### Tests

- [ ] T039 [P] [IDENTIFY] `tests/importer/steps/test_identify.py::test_full_cascade`
      — composes foundation's `Identifier.identify(path, filename,
      torznab_attrs)`; resulting `Identification` has `confidence` set.
- [ ] T040 [P] [IDENTIFY] `tests/importer/steps/test_identify.py::test_with_grab_record_attrs`
      — Torznab extended attrs from a prior grab record are passed
      through; the merged identification carries provenance.

### Implementation

- [ ] T041 [IDENTIFY] Create `src/romarr/importer/steps/identify.py` —
      thin wrapper around `Identifier.identify(...)`.

**Checkpoint**: IDENTIFY tests green; provenance preserved in the merge.

---

## Phase 7: Game match (`GAMEMATCH`) — Pipeline step 6

### Tests

- [ ] T042 [P] [GAMEMATCH] `tests/importer/steps/test_game_match.py::test_dat_to_igdb_lookup`
      — DAT hit with known IGDB ID resolves Game by `(platform_id,
      igdb_id)` (FR-013).
- [ ] T043 [P] [GAMEMATCH] `tests/importer/steps/test_game_match.py::test_rapidfuzz_threshold_90`
      — typo'd title `"Sonic the hedge hog"` matches `Sonic the Hedgehog`
      at threshold 90; below-threshold returns no match (FR-014).
- [ ] T044 [P] [GAMEMATCH] `tests/importer/steps/test_game_match.py::test_tiebreak_by_profile_then_id`
      — multiple candidates: prefer one whose monitoring library's region
      profile intersects parsed regions; tie-broken by lower `id`
      (FR-015).
- [ ] T045 [P] [GAMEMATCH] `tests/importer/steps/test_game_match.py::test_unmatched_with_suggested_game`
      — DAT entry knows IGDB ID for an unmonitored Game; result populates
      `unidentified_dump.suggested_game_id` (FR-016).

### Implementation

- [ ] T046 [GAMEMATCH] Create `src/romarr/importer/steps/game_match.py` —
      hash-first then RapidFuzz at threshold 90 with case-insensitive
      processor; tie-breaker function pure.

**Checkpoint**: GAMEMATCH tests green; threshold 90 is stricter than
search engine's 85 (intentional asymmetry).

---

## Phase 8: Multi-disc (`MULTIDISC`) — Pipeline step 7

### Tests

- [ ] T047 [P] [MULTIDISC] `tests/importer/steps/test_multi_disc.py::test_cue_bin_parent_child`
      — `Final Fantasy IX (USA) (Disc 1).cue/.bin` +
      `Final Fantasy IX (USA) (Disc 2).cue/.bin` ⇒ exactly 1 parent
      Release with `disc_number=1, disc_total=2` and 1 child with
      `parent_release_id = parent.id` (FR-017, FR-018, SC-004).
- [ ] T048 [P] [MULTIDISC] `tests/importer/steps/test_multi_disc.py::test_filename_pattern_disc_n`
      — `Game (Disc 2).bin` without `(Disc 1)` sibling ⇒ create child
      Release with `parent_release_id` referring to the existing parent if
      present, otherwise pseudo-parent created with disc_total inferred.
- [ ] T049 [P] [MULTIDISC] `tests/importer/steps/test_multi_disc.py::test_side_a_b_floppy`
      — `Title (Side A).adf / (Side B).adf` ⇒ multi-side handled like
      multi-disc.
- [ ] T050 [P] [MULTIDISC] `tests/importer/steps/test_multi_disc.py::test_hash_the_bin_not_cue`
      — for cue/bin pairs, the DAT lookup uses the `.bin` hash (FR-019,
      US3.3).
- [ ] T051 [P] [MULTIDISC] `tests/importer/steps/test_multi_disc.py::test_property_random_disc_layouts`
      — hypothesis property test: random combinations of cue/bin and
      filename-pattern entries; the detector never produces an invalid
      tree (no orphan child without a known parent slot).

### Implementation

- [ ] T052 [MULTIDISC] Create `src/romarr/importer/steps/multi_disc.py`
      — `detect_multi_disc(files: list[Path]) -> list[MultiDiscGroup]`
      pure function consuming a list of paths, plus a small `.cue` parser
      that extracts `FILE "<name>" BINARY` lines.

**Checkpoint**: MULTIDISC tests green; the property test runs 1000
random layouts without producing invalid trees.

---

## Phase 9: Profile gate (`PROFILEGATE`) — Pipeline step 8

### Tests

- [ ] T053 [P] [PROFILEGATE] `tests/importer/steps/test_profile_gate.py::test_uses_spec_006_evaluator`
      — composes `ProfileEvaluator.evaluate_quality/region/dump/language`;
      a rejecting profile parks the file in `unidentified_dump` with the
      structured reason.
- [ ] T054 [P] [PROFILEGATE] `tests/importer/steps/test_profile_gate.py::test_force_warning_only`
      — `ImportContext.force = true` (manual flow) ⇒ rejection becomes a
      `warning` field on `ImportOutcome`, not a halt (FR-021, US4.2).

### Implementation

- [ ] T055 [PROFILEGATE] Create
      `src/romarr/importer/steps/profile_gate.py` — composes the four
      evaluators and produces a `Decision` + structured rejection reason.

**Checkpoint**: PROFILEGATE tests green; spec 006's evaluator wired with
no business-logic duplication.

---

## Phase 10: Render (`RENDER`) — Pipeline step 9

### Tests

- [ ] T056 [P] [RENDER] `tests/importer/steps/test_render.py::test_uses_spec_006_engine`
      — composes `NamingTemplateEngine.render(profile, game, release,
      dump)`.
- [ ] T057 [P] [RENDER] `tests/importer/steps/test_render.py::test_platform_subfolder`
      — rendered path begins with `<library_root>/<platform_slug>/...` when
      the Naming profile has `platform_subfolder=true`.
- [ ] T058 [P] [RENDER] `tests/importer/steps/test_render.py::test_multi_disc_subfolder`
      — for multi-disc games with `multi_disc_subfolder=true`, both discs
      land in `<library_root>/<platform_slug>/<game_subfolder>/`.

### Implementation

- [ ] T059 [RENDER] Create `src/romarr/importer/steps/render.py` —
      composes the engine; resolves the full destination path including
      `library.path`, `platform_subfolder`, `multi_disc_subfolder`.

**Checkpoint**: RENDER tests green; rendered paths are deterministic
across reruns.

---

## Phase 11: Move (`MOVE`) — Pipeline step 10

**Purpose**: the riskiest piece. Hardlink-first atomic mover with cross-fs
fallback, idempotency-by-SHA-1, and fault-injection resilience.

### Tests

- [ ] T060 [P] [MOVE] `tests/importer/steps/test_move_hardlink.py::test_same_fs_hardlink`
      — `os.stat(dest).st_ino == os.stat(source).st_ino` after move
      (Constitution Article XII; SC-003).
- [ ] T061 [P] [MOVE] `tests/importer/steps/test_move_crossfs.py::test_tmpfs_fallback_copy_verify_delete`
      — mount tmpfs at a fixture path; mover detects different `st_dev`
      and falls back to copy + verify SHA-1 + delete + atomic rename
      (FR-024, US2.1).
- [ ] T062 [P] [MOVE] `tests/importer/steps/test_move_crossfs.py::test_copy_hash_mismatch_keeps_source`
      — inject a hash mismatch (truncated copy); the temp file is deleted,
      `MoveError(reason='copy_hash_mismatch')` raised, source intact
      (US2.2).
- [ ] T063 [P] [MOVE] `tests/importer/steps/test_move_idempotent.py::test_existing_dest_matching_sha1`
      — destination already exists with matching SHA-1; mover returns
      no-op success (FR-025, SC-002).
- [ ] T064 [P] [MOVE] `tests/importer/steps/test_move_idempotent.py::test_existing_dest_mismatching_sha1_no_force`
      — destination exists with different SHA-1 and `force=false` ⇒
      `MoveError(reason='dest_exists')` raised; nothing written
      (FR-026).
- [ ] T065 [P] [MOVE] `tests/importer/steps/test_move_fault_injection.py::test_crash_mid_copy_no_partial_dest`
      — monkeypatch `aiofiles` to raise mid-write; assert no file at the
      canonical destination, no `*.tmp` artefact left (SC-009).
- [ ] T066 [P] [MOVE] `tests/importer/steps/test_move_fault_injection.py::test_disk_full_no_source_delete`
      — simulate `OSError(ENOSPC)`; the source is preserved; `OnHealthIssue`
      is emitted (edge case).

### Implementation

- [ ] T067 [MOVE] Create `src/romarr/importer/steps/move.py` —
      `move_atomic(source, dest, *, expected_sha1, force=False) -> MoveResult`:
      1. Pre-flight: if `dest` exists and `sha1(dest) == expected_sha1`,
         return no-op.
      2. Pre-flight: if `dest` exists and SHA-1 differs and `force=false`,
         raise.
      3. Try `os.link(source, dest)` (hardlink). On `OSError(EXDEV)`,
         fall back to step 4.
      4. Cross-fs path: copy source → `dest.tmp` via aiofiles; compute
         `sha1(dest.tmp)`; if mismatch, delete `dest.tmp` and raise.
      5. `os.replace(dest.tmp, dest)` (atomic).
      6. Per the library's lifecycle policy, optionally delete the
         source (move_and_remove path; copy_and_keep keeps it).

**Checkpoint**: every MOVE test green; the fault-injection suite passes
in 100% of trials (SC-009).

---

## Phase 12: DB update (`DBUPDATE`) — Pipeline step 11

### Tests

- [ ] T068 [P] [DBUPDATE] `tests/importer/steps/test_db_update.py::test_creates_dump_with_all_hashes`
      — Dump row carries CRC32, MD5, SHA-1, format, path, dat_verified,
      dat_source, dat_entry_id, original_filename, imported_at,
      imported_via (FR-027).
- [ ] T069 [P] [DBUPDATE] `tests/importer/steps/test_db_update.py::test_release_status_imported`
      — `Release.status` flips to `'imported'` after a successful import.
- [ ] T070 [P] [DBUPDATE] `tests/importer/steps/test_db_update.py::test_keep_dump_history_false_deletes_old`
      — `library.keep_dump_history = false`; existing Dump for the same
      Release is deleted along with its file (FR-028).
- [ ] T071 [P] [DBUPDATE] `tests/importer/steps/test_db_update.py::test_keep_dump_history_true_appends`
      — `library.keep_dump_history = true`; both Dumps coexist.

### Implementation

- [ ] T072 [DBUPDATE] Create `src/romarr/importer/steps/db_update.py` —
      async `persist_dump(session, identification, dump_path,
      lifecycle_outcome) -> Dump`. The whole operation runs in a single
      `async with session.begin()` to be transactional.

**Checkpoint**: DBUPDATE tests green; the keep-history toggle works both
ways.

---

## Phase 13: Lifecycle (`LIFECYCLE`) — Pipeline step 12

### Tests

- [ ] T073 [P] [LIFECYCLE] `tests/importer/steps/test_lifecycle.py::test_hardlink_and_seed`
      — tags the download `romarr-imported`; does not remove (FR-029).
- [ ] T074 [P] [LIFECYCLE] `tests/importer/steps/test_lifecycle.py::test_move_and_remove_grace`
      — tags then schedules `client.remove(client_id)` for 5 min later;
      assert via freezegun that removal fires after the grace period.
- [ ] T075 [P] [LIFECYCLE] `tests/importer/steps/test_lifecycle.py::test_copy_and_keep_noop`
      — only tags; no removal scheduled.
- [ ] T076 [P] [LIFECYCLE] `tests/importer/steps/test_lifecycle.py::test_async_does_not_block_completion`
      — the orchestrator returns the `ImportOutcome` before the
      lifecycle action fires (FR-030).

### Implementation

- [ ] T077 [LIFECYCLE] Create `src/romarr/importer/steps/lifecycle.py`
      — async `apply_lifecycle(action: LifecycleAction)` that re-uses
      spec 005's qBittorrent / SAB tag operations. Schedule-remove uses
      an `asyncio.create_task(asyncio.sleep(grace_seconds) + client.remove)`
      pattern.

**Checkpoint**: LIFECYCLE tests green; the 5-minute grace is honoured.

---

## Phase 14: Notify (`NOTIFY`) — Pipeline step 13

### Tests

- [ ] T078 [P] [NOTIFY] `tests/importer/steps/test_notify.py::test_on_import_emitted`
      — successful import emits an `OnImport` event on the in-process
      pub/sub channel (FR-031).
- [ ] T079 [P] [NOTIFY] `tests/importer/steps/test_notify.py::test_on_upgrade_emitted`
      — import that replaces an existing Dump emits `OnUpgrade` IN
      ADDITION to `OnImport` (FR-032).

### Implementation

- [ ] T080 [NOTIFY] Create `src/romarr/importer/steps/notify.py` —
      `emit(event_name, payload)` writing onto the in-process channel
      that the future Notifications spec consumes. Library exporters
      (RomM push, gamelist.xml) are stubbed at this point — the channel
      delivers the event; the consumer wiring lands in Library spec.

**Checkpoint**: NOTIFY tests green; the channel emits both event types
when applicable.

---

## Phase 15: Hardening (`HARD`)

**Purpose**: orchestrator end-to-end, concurrency, manual flow, retry,
auto-blocklist, perf, coverage, ruff.

### Tests

- [ ] T081 [P] [HARD] `tests/importer/test_orchestrator.py::test_end_to_end_torrent`
      — fixture import of a known DAT-matching ROM; verify Dump,
      destination file, qBit tag, OnImport event (US1, SC-001).
- [ ] T082 [P] [HARD] `tests/importer/test_concurrent_imports.py::test_5_concurrent_one_dump`
      — `asyncio.gather(*5×run_import(...))` for the same release;
      assert exactly 1 Dump, exactly 1 destination file, 4 history rows
      with `coalesced=true` (FR-033, SC-007).
- [ ] T083 [P] [HARD] `tests/importer/test_auto_blocklist_on_failure.py`
      — fault-injected extract failure; assert blocklist row created via
      spec 007 helper with `added_by='system'` and the documented reason
      (FR-035, SC-006).
- [ ] T084 [P] [HARD] `tests/importer/test_manual_flow.py::test_force_overrides_profile`
      — manual flow with `force=true`; profile rejection becomes warning
      (FR-021, US4.2).
- [ ] T085 [P] [HARD] `tests/importer/test_manual_flow.py::test_unidentified_match_endpoint`
      — POST `/api/v3/rom/unidentified/{id}/match`; importer runs from
      step 9 (render); destination materialises; unidentified row deleted
      (US8).
- [ ] T086 [P] [HARD] `tests/importer/test_manual_flow.py::test_unidentified_delete_keeps_file`
      — DELETE on unidentified row removes DB row but NOT the source file
      (US8.2, FR-038).
- [ ] T087 [P] [HARD] `tests/importer/test_manual_flow.py::test_retry_creates_new_history_row`
      — POST retry on a failed import; new history row is created; the
      original row is preserved.
- [ ] T088 [P] [HARD] `tests/importer/api/test_manual_endpoints.py` —
      full CRUD-style round trip on the manual import endpoints.
- [ ] T089 [P] [HARD] `tests/importer/api/test_history_endpoints.py` —
      pagination + filter on `/api/v3/rom/import/history`.
- [ ] T090 [P] [HARD] `tests/importer/api/test_unidentified_endpoints.py`
      — list + match + delete.
- [ ] T091 [HARD] Run `pytest --cov=romarr.importer` — verify ≥ 75%
      coverage (SC-010). Add targeted tests for any uncovered branch.
- [ ] T092 [HARD] Run `ruff check .` — zero warnings on
      `src/romarr/importer/`.
- [ ] T093 [HARD] Manual perf check — webhook-to-hash-start latency p95
      < 1 s on a healthy local mock; record median over 100 trials in
      `specs/008-import-pipeline/research.md`.
- [ ] T094 [HARD] Update `pyproject.toml` `version = "0.8.0a1"`; add a
      one-line note to `CHANGELOG.md`: "0.8.0a1 — Import Pipeline:
      13-step pipeline, atomic mover, multi-disc, webhook + polling,
      auto-blocklist on failure."
- [ ] T095 [HARD] Final review: open `specs/008-import-pipeline/spec.md`
      and tick every Functional Requirement (FR-001 → FR-038) against a
      task ID; record gaps as follow-up items.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (SCAF)**: prerequisite specs merged; foundation hasher,
  spec 005 download clients, spec 006 evaluator + naming engine, spec 007
  blocklist helper available.
- **Phases 2–14 (one per pipeline step)**: each depends on Phase 1; the
  orchestrator's stub raises `NotImplementedError` for unimplemented
  steps so phases can be developed in any order.
- **Phase 15 (HARD)**: depends on Phases 2–14.

### Within-Phase Parallelism

- Phase 1: T002–T007 in parallel; T011–T013 in parallel.
- Each pipeline phase: every `[P]` task in that phase is independent.
- Phase 15: T081–T090 in parallel.

### Critical Path

The riskiest module is the **mover** (Phase 11) — invest the most testing
effort here. Beyond that, the orchestrator end-to-end test (T081) and the
concurrency test (T082) gate the whole feature's correctness.

### Implementation Strategy

- **Day 1**: Phase 1 (SCAF) — scaffolding + locks + migration + types.
- **Day 2-3**: Phase 2 (WATCH) + Phase 3 (EXTRACT) — entry-side I/O.
- **Day 4**: Phase 4 (HASH) + Phase 5 (DATMATCH) + Phase 6 (IDENTIFY) —
  thin compositions of foundation primitives.
- **Day 5**: Phase 7 (GAMEMATCH) + Phase 8 (MULTIDISC) — domain-heavy.
- **Day 6**: Phase 9 (PROFILEGATE) + Phase 10 (RENDER) + Phase 11 (MOVE)
  — the riskiest day; invest most testing effort on the mover.
- **Day 7**: Phase 12 (DBUPDATE) + Phase 13 (LIFECYCLE) + Phase 14
  (NOTIFY).
- **Day 8**: Phase 15 (HARD) — concurrency, perf, coverage, ruff.

This sizing assumes one developer working full-time. With two
contributors, the WATCH and EXTRACT phases (Day 2-3) split cleanly.

---

## Notes

- `[P]` tasks change different files only.
- Tests are written BEFORE implementation in every phase.
- Stop at any phase checkpoint — the importer is delivered incrementally;
  each phase is independently shippable (the orchestrator's
  `NotImplementedError` stubs make partial deployments safe).
- Avoid: building patch application (PatchManager spec, v1+); building
  format conversion (Converter spec, v1+); writing the actual library
  exporters (Library spec, scheduled as 010); duplicating profile
  evaluation logic (use spec 006); duplicating the blocklist code (use
  spec 007).
- Constitutional invariants under test:
  - **Article XII (Library Discipline)** — hardlinks default (T060);
    imports idempotent (T063, SC-002); per-Release cutoff
    (Release.status update at T069); no auto-delete without explicit
    lifecycle (T073-T076).
  - **Article XVII (Idempotency & Safety)** — re-import no-op (T063);
    concurrent imports coalesce (T082); webhook auth constant-time
    (T017); hash mismatch with DAT does NOT auto-reject (T036).
  - **Article V (Profile-Driven Decisions)** — profile gate uses
    spec 006's evaluator (T053); manual flow turns rejection into
    warning, never bypasses the engine.
  - **Article XVI (Quality Gates)** — ≥ 75% coverage (T091);
    perf budgets met (T093).

## Phase: Clarification Tasks (Session 2026-04-29)

- [ ] CL001 [P] [US6] Implement subreason-aware auto-blocklist in `src/romarr/importer/steps/lifecycle/blocklist_emitter.py` — call spec 007's helper ONLY for content-correctness subreasons (`hash-mismatch`, `dat-rejected`, `format-corrupt`, `archive-extraction-failed`); transient subreasons (`disk-full`, `permission-denied`, `client-unreachable`, `move-failed`, `scan-timeout`) record in `import_history` only, with the existing 30s/2m/5m exponential-backoff retry policy (FR-035 rewritten + FR-035a)
- [ ] CL002 [P] [US9] Implement webhook bearer-token validator in `src/romarr/importer/api/webhook.py` — read `X-Romarr-Webhook-Token` header; constant-time compare via `hmac.compare_digest` against the configured per-download-client secret; HTTP 401 with no token-disclosing error body on mismatch; 10 req/min/source-IP rate limit (FR-002)
- [ ] CL003 [P] [US1] Implement destination-collision parking in `src/romarr/importer/steps/move/dest_collision.py` — when automatic-flow encounters an existing destination with different SHA-1: leave existing file untouched, park incoming file in `unidentified_dump` with `rejection_reason = 'destination_collision'` and `suggested_game_id` populated, emit `OnHealthIssue` with `category = 'naming-collision'`. NO numeric-suffix disambiguation EVER (FR-026a)
- [ ] CL004 [P] [US1] Implement zip-bomb defense in `src/romarr/importer/steps/extract/expansion_cap.py` — cap uncompressed total expansion at `max(4 × archive_compressed_size, 5 GiB)`; check incrementally as bytes are written; abort on overrun; delete partial files; park archive in `unidentified_dump` with `rejection_reason = 'extract:bomb-detected'`; emit `OnHealthIssue` with `category = 'extract-bomb'` (FR-004a)
- [ ] CL005 [P] [Admin] Wire admin-role gate on `POST /api/v3/rom/import/manual`, `POST /api/v3/rom/unidentified/{id}/match`, `DELETE /api/v3/rom/unidentified/{id}`, `POST /api/v3/rom/import/retry/{import_id}` in `src/romarr/importer/api/__init__.py` (FR-038a)
- [ ] CL006 [P] **Note**: webhook endpoint `POST /api/v3/webhook/download-complete` does NOT consult the user-session/API-key auth chain. It uses solely `X-Romarr-Webhook-Token`. Confirm absence of `require_role` annotation on its handler
- [ ] CL007 [P] Add tests in `tests/importer/test_subreason_taxonomy.py` covering: each content-correctness subreason → blocklist row created; each transient subreason → no blocklist row, retry-eligible
- [ ] CL008 [P] Add tests in `tests/importer/test_dest_collision.py` covering: same SHA-1 → idempotent no-op; different SHA-1 → parked + OnHealthIssue + existing file untouched; manual-flow with `?force=true` → overwrite allowed
- [ ] CL009 [P] Add tests in `tests/importer/test_zip_bomb.py` covering: 4× ratio archive → extracts; 100× ratio at 5 GiB+ → aborts; small-but-shallow nested → depth check applies first
- [ ] CL010 [P] Add tests in `tests/importer/test_webhook_auth.py` covering: valid token → 200 + import fires; missing header → 401 + no log disclosure; mismatched token → 401 with constant-time comparison; 11 req in 60 s → 429
