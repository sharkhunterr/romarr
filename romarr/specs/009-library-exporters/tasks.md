---

description: "Granular task list for library management & exporters"
---

# Tasks: Library Management & Exporters

**Input**: Design documents from `specs/009-library-exporters/`
**Prerequisites**: `001-foundation`, `002-metadata-aggregation`, `006-profiles`,
`008-import-pipeline` shipped.
**Tests**: MANDATORY (Constitution Article XVI; SC-010: ≥ 75% on libraries/)

**Organization**: 14 phases. Scaffolding → persistence → routing → heartbeat →
disk-space → full scan → incremental scan → 4 exporter phases (RomM, ES-DE,
Pegasus, LaunchBox) → manual import → API → hardening.

## Format: `[ID] [P?] [Phase] Description`

- `[P]` = parallelizable with other `[P]` tasks in the same phase.
- Phase tag short codes: `SCAF`, `PERS`, `ROUTE`, `HEART`, `DISK`,
  `SCAN-FULL`, `SCAN-INC`, `EXP-ROMM`, `EXP-ESDE`, `EXP-PEGASUS`,
  `EXP-LAUNCHBOX`, `MANUAL`, `API`, `HARD`.

---

## Phase 1: Scaffolding (`SCAF`)

- [ ] T001 [SCAF] Update `pyproject.toml` — add runtime dep
      `watchdog>=4.0` (inotify on Linux + polling fallback).
- [ ] T002 [P] [SCAF] Create `src/romarr/libraries/__init__.py` exposing
      `LibraryRegistry`, `route_to_library`, `scan_full`,
      `scan_incremental`, `ExporterRegistry`.
- [ ] T003 [P] [SCAF] Create `src/romarr/libraries/errors.py` —
      `LibraryError`, `PathUnwritable`, `NoEligibleLibrary`,
      `LibraryUnavailable`, `DiskFullError`, `ExporterError`.
- [ ] T004 [P] [SCAF] Create `src/romarr/libraries/types.py` — every
      Pydantic / StrEnum from `data-model.md`'s Value Types section.
- [ ] T005 [SCAF] Extend `tests/conftest.py` with `tmp_library(tmp_path)`
      fixture that returns a `LibrarySnapshot` pointing at a fresh tmp
      directory; create `tests/libraries/conftest.py` for module-local
      fixtures (mock RomM via respx, sample profile rows, fixture
      gamelist.xml from a known-good ES-DE installation).

**Checkpoint**: imports work; lint+types green; no behaviour added.

---

## Phase 2: Persistence (`PERS`)

### Tests (write first; must fail)

- [ ] T006 [P] [PERS] `tests/libraries/test_models.py` — round-trip a
      `Library` row + a `LibraryPlatform` row through the async session;
      verify CHECK constraints on `lifecycle_policy` and `status`.
- [ ] T007 [P] [PERS] `tests/libraries/test_models.py::test_unique_name`
      — second insertion with the same `name` raises `IntegrityError`.
- [ ] T008 [P] [PERS] `tests/libraries/test_models.py::test_path_validator`
      — Pydantic-level: non-existent path rejected; non-writable path
      rejected; relative path rejected (FR-004).
- [ ] T009 [P] [PERS] `tests/libraries/test_models.py::test_restricted_requires_platforms`
      — `platforms_restricted=true` AND empty m2m ⇒ rejected at
      validation (FR-005).
- [ ] T010 [P] [PERS] `tests/libraries/test_models.py::test_romm_requires_url_and_key`
      — `exporter_romm_enabled=true` without URL OR without API key ⇒
      rejected.
- [ ] T011 [P] [PERS] `tests/libraries/test_migration_0009.py::test_creates_table_and_release_fk`
      — applying the migration creates `library` + m2m + adds
      `release.library_id` with FK to `library(id) ON DELETE SET NULL`.
- [ ] T012 [P] [PERS] `tests/libraries/test_migration_0009.py::test_finalises_unidentified_dump_fk`
      — applying after spec-008's gated migration finalises
      `fk_unidentified_dump_library` (idempotent — runs without error
      either way).

### Implementation

- [ ] T013 [PERS] Create `src/romarr/libraries/models.py` — `Library`
      and `LibraryPlatform` SQLAlchemy 2.0 models matching
      `data-model.md`.
- [ ] T014 [P] [PERS] Create `src/romarr/libraries/schemas.py` —
      `LibraryRead/Create/Update`, `LibraryPlatformRead`, `ScanResult`,
      `ManualImportListing`, `ManualImportRequest`,
      `ManualImportResult`. `LibraryRead` MUST omit
      `exporter_romm_api_key_encrypted` and expose
      `is_romm_configured: bool`.
- [ ] T015 [PERS] Modify `src/romarr/domain/models/release.py` to add
      `library_id: Mapped[int | None]` with the FK relationship and
      `back_populates`.
- [ ] T016 [PERS] Author `src/romarr/db/alembic/versions/0009_libraries.py`
      — DDL for the table + m2m + the `release.library_id` FK addition;
      finalise the gated FK on `unidentified_dump.library_id` if not
      already present.

**Checkpoint**: `alembic upgrade head` is clean against any of {fresh
DB, post-spec-008-only DB}; PERS tests green.

---

## Phase 3: Routing (`ROUTE`)

**Purpose**: pure-function library router consumed by spec 008.

### Tests

- [ ] T017 [P] [ROUTE] `tests/libraries/test_routing.py::test_only_eligible_wins`
      — three libraries; only one accepts the inferred platform;
      `chosen_via='only_eligible'`.
- [ ] T018 [P] [ROUTE] `tests/libraries/test_routing.py::test_unrestricted_library_accepts_all`
      — library with `platforms_restricted=false` accepts every
      platform.
- [ ] T019 [P] [ROUTE] `tests/libraries/test_routing.py::test_profile_match_breaks_tie`
      — two libraries both accept the platform; the one whose Quality
      + Region profile match the parsed file better wins.
- [ ] T020 [P] [ROUTE] `tests/libraries/test_routing.py::test_lower_id_final_tiebreak`
      — both libraries match equally on profiles; lower `id` wins
      (FR-006).
- [ ] T021 [P] [ROUTE] `tests/libraries/test_routing.py::test_unavailable_skipped`
      — eligible library is `status='unavailable'` ⇒ skipped; routing
      falls through (FR-008).
- [ ] T022 [P] [ROUTE] `tests/libraries/test_routing.py::test_no_eligible_library`
      — no library accepts the platform ⇒
      `chosen_via='no_eligible_library'`,
      `rejection_reason='routing:no_library_for_platform'` (FR-007).
- [ ] T023 [P] [ROUTE] `tests/libraries/test_routing.py::test_30_release_corpus`
      — fixture `routing_corpus_30_releases.jsonl` of 30 mixed
      releases (NES / SNES / Mega Drive / PSX / 3DS / etc.) plus 3
      pre-defined libraries; assert each release routes to the
      documented library (SC-002).

### Implementation

- [ ] T024 [ROUTE] Create `src/romarr/libraries/routing.py` — pure
      `route_to_library(parsed_filename, libraries: list[LibrarySnapshot]) -> RoutingChoice`.
      Order: filter unavailable → filter by platform allowlist →
      score remaining by profile match → pick the lowest-id of the
      best-scored. No I/O.

**Checkpoint**: routing tests green; the 30-release fixture corpus
hits 100%.

---

## Phase 4: Heartbeat (`HEART`)

**Purpose**: detect path unavailability, emit `OnHealthIssue`, restore
on recovery, debounce events.

### Tests

- [ ] T025 [P] [HEART] `tests/libraries/test_heartbeat.py::test_unavailable_emits_event`
      — remove the library path; one heartbeat cycle; assert
      `status='unavailable'` and one `OnHealthIssue` event.
- [ ] T026 [P] [HEART] `tests/libraries/test_heartbeat.py::test_recovery_emits_event`
      — restore the path; next heartbeat; status returns to `'ok'` and
      one recovery event emitted.
- [ ] T027 [P] [HEART] `tests/libraries/test_heartbeat.py::test_debounce_5min_window`
      — flap (down → up → down → up) within 5 minutes; only the first
      down + first recovery emit; no event storm (FR-029).
- [ ] T028 [P] [HEART] `tests/libraries/test_heartbeat.py::test_per_library_cadence`
      — two libraries with different `heartbeat_seconds`; freezegun
      asserts each fires at its own cadence.

### Implementation

- [ ] T029 [HEART] Create `src/romarr/libraries/heartbeat.py` — async
      `HeartbeatLoop` that iterates configured libraries, calls
      `os.stat(library.path)`, transitions status, emits debounced
      events on the in-process pub/sub channel.
- [ ] T030 [HEART] Wire `HeartbeatLoop.start()` into the application
      lifespan startup so the loop runs as a background task; cancel
      on shutdown.

**Checkpoint**: heartbeat tests green; debouncing prevents event
storms.

---

## Phase 5: Disk Space (`DISK`)

### Tests

- [ ] T031 [P] [DISK] `tests/libraries/test_disk_space.py::test_above_threshold_passes`
      — synthesise a path with > `min_disk_free_gb` available; the
      checker returns OK.
- [ ] T032 [P] [DISK] `tests/libraries/test_disk_space.py::test_below_threshold_fails`
      — monkeypatch `shutil.disk_usage` to return < threshold; the
      checker raises `DiskFullError` (FR-030).

### Implementation

- [ ] T033 [DISK] Create `src/romarr/libraries/disk_space.py` — pure
      `check_min_disk_free(path: Path, min_gb: int) -> None`. Used by
      spec 008's import pipeline before each move (consumed via
      explicit dependency injection so spec 008 doesn't need to
      reference this module by import).

**Checkpoint**: DISK tests green; spec 008 can import the helper from
`romarr.libraries.disk_space`.

---

## Phase 6: Full Scan (`SCAN-FULL`)

### Tests

- [ ] T034 [P] [SCAN-FULL] `tests/libraries/scanner/test_full_scan.py::test_100_files_under_5s`
      — fixture `full_scan_100_files/` with 100 small ROMs; assert
      scan completes in < 5 s (SC-003 first leg).
- [ ] T035 [P] [SCAN-FULL] `tests/libraries/scanner/test_full_scan.py::test_10k_files_under_5min`
      — generate 10 000 tiny synthetic files at test time; assert scan
      < 5 min (SC-003 second leg). Parallelise hashing across a
      threadpool.
- [ ] T036 [P] [SCAN-FULL] `tests/libraries/scanner/test_full_scan.py::test_links_existing_releases`
      — pre-populate Releases with known DAT-matching hashes; scan
      links each file to its existing Release without creating a
      duplicate.
- [ ] T037 [P] [SCAN-FULL] `tests/libraries/scanner/test_full_scan_idempotent.py::test_skip_known_path_size_mtime`
      — re-scan after a clean scan; files whose `(path, size, mtime)`
      already match a Dump are skipped (FR-010).
- [ ] T038 [P] [SCAN-FULL] `tests/libraries/scanner/test_full_scan_orphan.py::test_missing_file_marks_release_wanted`
      — delete a file on disk; scan; orphaned Dump detected; parent
      Release transitions to `status='wanted'`; structured warning
      emitted (FR-011).
- [ ] T039 [P] [SCAN-FULL] `tests/libraries/scanner/test_progress_events.py::test_emits_every_100_files`
      — scan 250 files; assert 3 progress events emitted on the
      pub/sub channel (FR-012).
- [ ] T040 [P] [SCAN-FULL] `tests/libraries/scanner/test_full_scan.py::test_new_file_creates_release`
      — file not matching any Release ⇒ runs identification cascade;
      passes profile gate ⇒ new Release created; fails ⇒ parked in
      `unidentified_dump` with `library_id` set (FR-014).

### Implementation

- [ ] T041 [SCAN-FULL] Create `src/romarr/libraries/scanner/progress.py`
      — `ScanProgressEmitter` that publishes events every N files.
- [ ] T042 [SCAN-FULL] Create `src/romarr/libraries/scanner/full.py` —
      async `full_scan(library: Library) -> ScanProgress`. Walks the
      path with `os.scandir`, hashes via spec 001's `Hasher` in a
      threadpool (`asyncio.to_thread`), identifies via spec 001's
      `Identifier`, links/creates Releases.

**Checkpoint**: full-scan tests green including the 10k perf budget.

---

## Phase 7: Incremental Scan (`SCAN-INC`)

### Tests

- [ ] T043 [P] [SCAN-INC] `tests/libraries/scanner/test_incremental.py::test_inotify_detects_new_file`
      — start the watcher; copy a known ROM into the path; assert
      Dump created in < 5 s (SC-004).
- [ ] T044 [P] [SCAN-INC] `tests/libraries/scanner/test_incremental.py::test_rename_updates_path_no_rehash`
      — rename a file inside the library; the existing Dump's `path`
      column updates without re-hashing.
- [ ] T045 [P] [SCAN-INC] `tests/libraries/scanner/test_incremental.py::test_rename_outside_library_orphans`
      — move a file outside the library path; the Dump becomes
      orphaned (FR-011) on the next event.
- [ ] T046 [P] [SCAN-INC] `tests/libraries/scanner/test_incremental_polling.py::test_polling_fallback`
      — disable inotify (force `watchdog`'s polling observer); a new
      file is detected within `scan_poll_seconds` (test with reduced
      interval).

### Implementation

- [ ] T047 [SCAN-INC] Create `src/romarr/libraries/scanner/incremental.py`
      — async `IncrementalScanner` wrapping a `watchdog.observers.Observer`.
      `start(library)` chooses `Observer` (inotify) or
      `PollingObserver` based on `WATCHDOG_OBSERVER_TYPE` env or auto-
      detect. Events are debounced with a 500 ms quiet period before
      processing.

**Checkpoint**: incremental-scan tests green on both inotify and
polling paths.

---

## Phase 8: Exporter — RomM (`EXP-ROMM`)

### Tests

- [ ] T048 [P] [EXP-ROMM] `tests/libraries/exporters/test_romm.py::test_happy_path`
      — respx-mocked RomM; import succeeds; the exporter POSTs to
      `<romm_url>/api/platforms/<id>/scan` with the `Authorization:
      Bearer <key>` header.
- [ ] T049 [P] [EXP-ROMM] `tests/libraries/exporters/test_romm.py::test_503_does_not_block_import`
      — RomM returns 503; import is recorded as `success=true` with
      `warning='romm_export_failed'` (FR-015, US9).
- [ ] T050 [P] [EXP-ROMM] `tests/libraries/exporters/test_romm.py::test_three_failures_emit_health_event`
      — 3 sustained failures; one `OnHealthIssue` event emitted (no
      duplicate within 5-min debounce).

### Implementation

- [ ] T051 [EXP-ROMM] Create `src/romarr/libraries/exporters/__init__.py`
      with the `ExporterBase` ABC and `ExporterRegistry`.
- [ ] T052 [EXP-ROMM] Create `src/romarr/libraries/exporters/romm.py`
      — `RommExporter` implementing the ABC. Uses httpx async with
      tenacity (3 attempts, exponential backoff) and decrypts the API
      key on each call via spec 002's helper.

**Checkpoint**: RomM exporter tests green; failure paths surface
warnings without blocking imports.

---

## Phase 9: Exporter — ES-DE (`EXP-ESDE`)

### Tests

- [ ] T053 [P] [EXP-ESDE] `tests/libraries/exporters/test_esde_gamelist.py::test_emits_well_formed_xml`
      — emit gamelist.xml for 5 fixture games; parse with `lxml.etree`
      and assert it matches the structure of the known-good ES-DE
      fixture (SC-005).
- [ ] T054 [P] [EXP-ESDE] `tests/libraries/exporters/test_esde_gamelist.py::test_relative_image_path`
      — emitted `<image>` value is `./media/covers/<slug>.<ext>`
      (FR-018).
- [ ] T055 [P] [EXP-ESDE] `tests/libraries/exporters/test_esde_media_mirror.py::test_hardlink_when_same_fs`
      — covers under `data/covers/` are hardlinked to
      `<lib>/<platform>/media/covers/<slug>.<ext>` when same fs.
- [ ] T056 [P] [EXP-ESDE] `tests/libraries/exporters/test_esde_media_mirror.py::test_copy_fallback_cross_fs`
      — when `EXDEV` raised, fall back to `shutil.copy2` with mtime
      preservation.
- [ ] T057 [P] [EXP-ESDE] `tests/libraries/exporters/test_esde_media_mirror.py::test_refresh_on_metadata_update`
      — cover changes in `data/covers/`; the exporter detects the
      mtime change and refreshes the mirror.
- [ ] T058 [P] [EXP-ESDE] `tests/libraries/exporters/test_esde_atomic_rewrite.py::test_mid_write_crash_preserves_prior_file`
      — fault-inject mid-XML-write; assert the existing gamelist.xml
      is untouched (FR-017).
- [ ] T059 [P] [EXP-ESDE] `tests/libraries/exporters/test_esde_gamelist.py::test_disabled_emits_nothing`
      — `exporter_esde_enabled=false`; no gamelist.xml created on
      import.

### Implementation

- [ ] T060 [EXP-ESDE] Create `src/romarr/libraries/exporters/esde.py`
      — `EsdeExporter` implementing the ABC. Builds the XML via
      `lxml.etree` from a streaming query of all Imported Releases on
      the platform. Writes to `gamelist.xml.tmp` then `os.replace`.
      Materialises media via `os.link` (hardlink) with `EXDEV`
      fallback to `shutil.copy2`.

**Checkpoint**: ES-DE exporter tests green; SC-005 fixture parses
correctly.

---

## Phase 10: Exporter — Pegasus (`EXP-PEGASUS`)

### Tests

- [ ] T061 [P] [EXP-PEGASUS] `tests/libraries/exporters/test_pegasus.py::test_emits_well_formed_text`
      — `metadata.txt` contains the documented fields per game.
- [ ] T062 [P] [EXP-PEGASUS] `tests/libraries/exporters/test_pegasus.py::test_atomic_rewrite`
      — same temp+replace pattern as ES-DE; mid-write crash preserves
      prior file.

### Implementation

- [ ] T063 [EXP-PEGASUS] Create `src/romarr/libraries/exporters/pegasus.py`
      — `PegasusExporter` implementing the ABC.

**Checkpoint**: Pegasus exporter tests green.

---

## Phase 11: Exporter — LaunchBox (`EXP-LAUNCHBOX`)

### Tests

- [ ] T064 [P] [EXP-LAUNCHBOX] `tests/libraries/exporters/test_launchbox.py::test_per_platform_default`
      — emits one `launchbox-export.xml` per platform under
      `<lib>/<platform_slug>/`.
- [ ] T065 [P] [EXP-LAUNCHBOX] `tests/libraries/exporters/test_launchbox.py::test_global_when_disabled_per_platform`
      — `exporter_launchbox_per_platform=false`; emits a single global
      file at `<lib>/launchbox-export.xml`.

### Implementation

- [ ] T066 [EXP-LAUNCHBOX] Create
      `src/romarr/libraries/exporters/launchbox.py` —
      `LaunchBoxExporter` implementing the ABC.

**Checkpoint**: LaunchBox exporter tests green.

---

## Phase 12: Manual Import (`MANUAL`)

### Tests

- [ ] T067 [P] [MANUAL] `tests/libraries/test_manual_import_listing.py::test_listing_no_db_modification`
      — drop 50 fixture files in a folder; GET endpoint returns
      candidates; assert the database row counts are unchanged after.
- [ ] T068 [P] [MANUAL] `tests/libraries/test_manual_import_bulk.py::test_bulk_under_30s`
      — 50 fixture files; POST bulk; assert completion in < 30 s
      (SC-008).
- [ ] T069 [P] [MANUAL] `tests/libraries/test_manual_import_bulk.py::test_skip_action_recorded`
      — entries with `action='skip'` are recorded in `import_history`
      with the skip outcome (no failure).
- [ ] T070 [P] [MANUAL] `tests/libraries/test_manual_import_bulk.py::test_routing_check_per_entry`
      — entry whose `library_id` doesn't accept the platform fails
      per-entry with `routing:platform_not_in_library_allowlist`
      (FR-024).

### Implementation

- [ ] T071 [MANUAL] Create `src/romarr/libraries/manual_import.py` —
      `list_candidates(folder: Path) -> list[ManualImportListing]` (no
      DB write) and async `bulk_import(entries: list[ManualImportRequest])
      -> list[ManualImportResult]` that delegates per-entry to spec
      008's `run_import`.

**Checkpoint**: manual-import tests green; 50-file bulk under 30 s.

---

## Phase 13: API (`API`)

### Tests

- [ ] T072 [P] [API] `tests/libraries/api/test_library_endpoints.py::test_full_crud`
      — POST/GET/PUT/DELETE round-trip.
- [ ] T073 [P] [API] `tests/libraries/api/test_library_endpoints.py::test_path_validation_400`
      — POST with non-existent path ⇒ HTTP 400 (FR-004).
- [ ] T074 [P] [API] `tests/libraries/api/test_library_endpoints.py::test_force_delete_blocks_when_history_present`
      — `keep_dump_history=true` AND historical Dumps reference the
      library ⇒ even `?force=true` returns HTTP 409 (FR-027, US6.3).
- [ ] T075 [P] [API] `tests/libraries/api/test_library_endpoints.py::test_force_delete_succeeds_no_history`
      — Releases attached but no historical Dumps ⇒ `?force=true`
      removes the library row, sets Releases' `library_id` to NULL,
      keeps files on disk (FR-026, SC-006).
- [ ] T076 [P] [API] `tests/libraries/api/test_scan_endpoints.py`
      — POST scan + scan/incremental return command IDs; full + incr
      scans run.
- [ ] T077 [P] [API] `tests/libraries/api/test_exporter_endpoints.py::test_list_returns_status`
      — GET exporter status; per-exporter last-run + count.
- [ ] T078 [P] [API] `tests/libraries/api/test_exporter_endpoints.py::test_run_on_demand`
      — POST `/exporters/{name}/run`; the named exporter executes.
- [ ] T079 [P] [API] `tests/libraries/api/test_manual_import_endpoints.py`
      — GET listing + POST bulk happy paths.

### Implementation

- [ ] T080 [API] Create `src/romarr/libraries/api/libraries.py` —
      FastAPI router for `/api/v3/rom/library*` (CRUD).
- [ ] T081 [P] [API] Create `src/romarr/libraries/api/scan.py` —
      scan trigger endpoints.
- [ ] T082 [P] [API] Create `src/romarr/libraries/api/exporters.py`
      — exporter status + manual-run endpoints.
- [ ] T083 [P] [API] Create `src/romarr/libraries/api/manual_import.py`
      — `/api/v3/rom/manual-import*` endpoints.
- [ ] T084 [API] Wire all four routers into the application factory.

**Checkpoint**: every endpoint exercised; HTTP status codes match the
spec.

---

## Phase 14: Hardening (`HARD`)

- [ ] T085 [HARD] Run `pytest --cov=romarr.libraries` — verify ≥ 75%
      coverage (SC-010). Add targeted tests for any uncovered branch.
- [ ] T086 [HARD] Run `ruff check .` — zero warnings on
      `src/romarr/libraries/`.
- [ ] T087 [HARD] Add a CI smoke test that asserts the routing module
      has no I/O imports (no `httpx`, no `sqlalchemy.session`).
- [ ] T088 [HARD] Manual perf check — record full-scan time on
      10 000 files in `specs/009-library-exporters/research.md` (SC-003).
- [ ] T089 [HARD] Update `pyproject.toml` `version = "0.9.0a1"`; add
      a one-line note to `CHANGELOG.md`: "0.9.0a1 — Library Management
      & Exporters: multi-library routing, full+incremental scanner,
      RomM/ES-DE/Pegasus/LaunchBox exporters, manual import."
- [ ] T090 [HARD] Final review: open `specs/009-library-exporters/spec.md`
      and tick every Functional Requirement (FR-001 → FR-034) against
      a task ID; record gaps as follow-up items.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (SCAF)**: prerequisite specs merged.
- **Phase 2 (PERS)**: depends on Phase 1.
- **Phase 3 (ROUTE)**: depends on Phase 2 (LibrarySnapshot built from
  Library rows) but routing itself is pure.
- **Phase 4 (HEART)**: depends on Phase 2.
- **Phase 5 (DISK)**: depends on Phase 1 only — pure helper.
- **Phase 6 (SCAN-FULL)**: depends on Phases 2 + 3 + 5.
- **Phase 7 (SCAN-INC)**: depends on Phase 6 (shares helpers).
- **Phases 8–11 (exporters)**: depend on Phase 2; can run in parallel.
- **Phase 12 (MANUAL)**: depends on Phase 8 of spec 008 (run_import).
- **Phase 13 (API)**: depends on Phases 6, 7, 8, 11, 12.
- **Phase 14 (HARD)**: depends on Phase 13.

### Within-Phase Parallelism

- Phase 1: T002–T004 in parallel.
- Phase 2: T006–T012 in parallel; T013 + T014 in parallel.
- Phase 3: T017–T023 in parallel.
- Phase 4: T025–T028 in parallel.
- Phase 5: T031 + T032 in parallel.
- Phase 6: T034–T040 in parallel.
- Phase 7: T043–T046 in parallel.
- Phases 8–11: each phase's tests in parallel; the four exporters
  themselves run on independent contributors.
- Phase 12: T067–T070 in parallel.
- Phase 13: T072–T079 in parallel; T080–T083 in parallel.

### Critical Path

`SCAF → PERS → ROUTE → SCAN-FULL → API → HARD`. Heartbeat, disk-space,
incremental scan, and the four exporters can develop in parallel
once PERS is done.

### Implementation Strategy

- **Day 1**: Phase 1 (SCAF) + Phase 2 (PERS) + Phase 3 (ROUTE).
- **Day 2**: Phase 4 (HEART) + Phase 5 (DISK) + Phase 6 (SCAN-FULL).
- **Day 3**: Phase 7 (SCAN-INC) + Phases 8 + 9 (RomM + ES-DE) in
  parallel.
- **Day 4**: Phases 10 + 11 (Pegasus + LaunchBox) + Phase 12
  (MANUAL).
- **Day 5**: Phase 13 (API).
- **Day 6**: Phase 14 (HARD).

This sizing assumes one developer working full-time. With two
contributors, the four exporter phases split cleanly across them.

---

## Notes

- `[P]` tasks change different files only.
- Tests are written BEFORE implementation in every phase.
- Stop at any phase checkpoint — the libraries layer is delivered
  incrementally; each phase is independently shippable.
- Avoid: building UI (UI spec); implementing bidirectional RomM sync
  (only push in MVP); save data migration (firm out per Constitution);
  library splitting/merging (deferred to v1+); per-game library moves
  (v1+); duplicating profile evaluation (use spec 006); duplicating
  the import pipeline (use spec 008's `run_import` from
  `manual_import.py`).
- Constitutional invariants under test:
  - **Article XII (Library Discipline)** — hardlinks default for
    media mirror (T055); deletion never cascades to files (T075,
    SC-006); per-Release status updates on orphan detection
    (T038); idempotent re-scan via `(path, size, mtime)` (T037).
  - **Article XVII (Idempotency & Safety)** — atomic gamelist.xml
    rewrite (T058); deletion blocked by HTTP 409 (T074, T075);
    heartbeat debounced (T027).
  - **Article V (Profile-Driven Decisions)** — profile evaluator
    determines whether new files become Releases or unidentified
    dumps during scan (T040).
  - **Article XVI (Quality Gates)** — ≥ 75% coverage (T085); 10 000
    files < 5 min (T035 + T088); 50-file manual import < 30 s
    (T068).

## Phase: Clarification Tasks (Session 2026-04-29)

- [ ] CL001 Migration `0009_library.py` is the **integrating migration** for spec 006 forward references plus library-owned schema. In one transaction:
  - (a) Create `library` table per data-model.md
  - (b) Create `library_platform` m2m
  - (c) Add `Release.library_id INTEGER NULLABLE` FK with `ON DELETE SET NULL`
  - (d) Add the **five Library → Profile FKs** to `library` (`quality_profile_id`, `region_profile_id`, `dump_profile_id`, `language_profile_id`, `naming_profile_id`) all with `ON DELETE SET NULL` (FR-004 in spec 006)
  - (e) Add `library_id` FK on the existing `library_custom_format` m2m (which spec 006 created with `custom_format_id` only) AND the unique constraint `(library_id, custom_format_id)` (FR-005 in spec 006)
- [ ] CL002 Within the same migration's `upgrade()` body, after the table DDL settles, run the one-shot `Release.library_id` backfill: for each newly-created library, UPDATE Release rows whose Dump path is under that library's canonicalized `path` (string-prefix match) and whose current `library_id IS NULL` (FR-003a)
- [ ] CL003 [P] Post-migration hook: count Release rows where `library_id IS NULL` AFTER the backfill loop completes; if > 0, emit a single `OnHealthIssue` event with `category = 'orphan-releases'` and the count in the payload (FR-003a)
- [ ] CL004 [P] [US2] Implement multi-library routing tie-breaker in `src/romarr/library/routing.py` — `routing_score = region_score (per spec 006 FR-013, len(priorities) − index) + (1 if Quality=ACCEPT else 0)`; higher wins; ties → lower `library.id`; Custom Format scores explicitly NOT included (FR-006 rewritten)
- [ ] CL005 [P] [US3] Implement gamelist.xml absent-cover handling in `src/romarr/library/exporters/esde.py` — omit `<image>` element entirely when `data/covers/<game_id>.<ext>` doesn't exist; same rule for `<thumbnail>` and `<marquee>`; `<game>` element still emitted with all other fields (FR-018a)
- [ ] CL006 [P] [US3] Implement filesystem-based advisory lock for emitters in `src/romarr/library/exporters/lock.py` — `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on `<library_path>/<platform_slug>/.gamelist.lock`; lock unavailable → coalesce (skip; in-flight emission covers latest state); same lock pattern for Pegasus `metadata.txt` and LaunchBox XML, each with its own lock file (FR-017a)
- [ ] CL007 [P] [Admin] Wire admin-role gate on every mutating library endpoint AND on `GET /api/v3/rom/manual-import?folder=…` (path-traversal surface) in `src/romarr/library/api.py`. Other reads accessible to any authenticated user (FR-033a)
- [ ] CL008 [P] Add tests in `tests/library/test_backfill.py` covering: fresh DB + library creation → orphan Releases bound by path prefix; remaining orphans → OnHealthIssue emitted once with the count
- [ ] CL009 [P] Add tests in `tests/library/test_routing_tiebreaker.py` covering: 2 eligible libraries, different Region profiles → higher region_score wins; same region_score, different Quality outcomes → ACCEPT wins; full tie → lower id wins
- [ ] CL010 [P] Add tests in `tests/library/test_emitter_lock.py` covering: 2 concurrent imports targeting same (lib, platform) → exactly one emission fires; second import sees the lock and coalesces (no second emission)
- [ ] CL011 [P] Add tests in `tests/library/test_gamelist_no_cover.py` covering: Game with cover → `<image>` present; Game without cover → `<image>` element absent (NOT empty); other fields still present
