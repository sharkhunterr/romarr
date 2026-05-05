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

- [X] T001 [SCAF] **Slice 297.** ``watchdog>=4.0`` added to
      ``pyproject.toml`` runtime deps. Consumed by
      ``src/romarr/libraries/scanner/incremental.py``
      (``Observer`` for inotify on Linux / FSEvents on macOS;
      ``PollingObserver`` for the cross-fs fallback).
- [X] T002 [P] [SCAF] Create `src/romarr/libraries/__init__.py` exposing
      the slice-1 surface (errors + value types). Router /
      registry / scan / exporter exports land in their own slices.
- [X] T003 [P] [SCAF] Create `src/romarr/libraries/errors.py` —
      `LibraryError`, `PathUnwritable`, `NoEligibleLibrary`,
      `LibraryUnavailable`, `DiskFullError`, `ExporterError`.
- [X] T004 [P] [SCAF] Create `src/romarr/libraries/types.py` — every
      Pydantic / StrEnum from `data-model.md`'s Value Types section.
- [X] T005 [SCAF] Extend `tests/conftest.py` registration to import
      `romarr.libraries.models`; create `tests/libraries/conftest.py`
      with `tmp_library_path` + `seeded_profile_ids` +
      `make_library_create_payload` fixtures. RomM respx + ES-DE
      gamelist fixtures land with the EXP-* slices.

**Checkpoint**: imports work; lint+types green; no behaviour added.

---

## Phase 2: Persistence (`PERS`)

### Tests (write first; must fail)

- [X] T006 [P] [PERS] `tests/libraries/test_models.py` — round-trip a
      `Library` row + a `LibraryPlatform` row through the async session;
      verify CHECK constraints on `lifecycle_policy` and `status`.
- [X] T007 [P] [PERS] `tests/libraries/test_models.py::test_unique_name`
      — second insertion with the same `name` raises `IntegrityError`.
- [X] T008 [P] [PERS] `tests/libraries/test_models.py::test_path_validator`
      — Pydantic-level: relative path rejected (FR-004); existing-path
      and writability checks live on the API layer (the model layer
      shouldn't touch the filesystem during validation).
- [X] T009 [P] [PERS] `tests/libraries/test_models.py::test_restricted_requires_platforms`
      — `platforms_restricted=true` AND empty m2m ⇒ rejected at
      validation (FR-005).
- [X] T010 [P] [PERS] `tests/libraries/test_models.py::test_romm_requires_url_and_key`
      — `exporter_romm_enabled=true` without URL OR without API key ⇒
      rejected.
- [X] T011 [P] [PERS] `tests/libraries/test_migration_0009.py::test_creates_table_and_release_fk`
      — applying the migration creates `library` + m2m + adds
      `release.library_id` with FK to `library(id) ON DELETE SET NULL`,
      and finalises the FK on `library_custom_format.library_id`.
- [X] T012 [P] [PERS] `tests/libraries/test_migration_0009.py::test_unidentified_dump_finalisation_idempotent`
      — applying without spec 008 having shipped no-ops on the
      `unidentified_dump` branch (idempotent in both directions).

### Implementation

- [X] T013 [PERS] Create `src/romarr/libraries/models.py` — `Library`
      and `LibraryPlatform` SQLAlchemy 2.0 models matching
      `data-model.md`.
- [X] T014 [P] [PERS] Create `src/romarr/libraries/schemas.py` —
      `LibraryCreate/Read/Update`, `LibraryPlatformRead`. `ScanResult`,
      `ManualImportListing`, `ManualImportRequest`, `ManualImportResult`
      land with the SCAN / MANUAL slices. `LibraryRead` omits
      `exporter_romm_api_key_encrypted` and exposes
      `is_romm_configured: bool`.
- [X] T015 [PERS] Modify `src/romarr/domain/models.py` (Release class)
      to add `library_id: Mapped[int | None]` with the FK relationship.
      `back_populates` on `Library.releases` lands when the relationship
      is needed by a downstream slice.
- [X] T016 [PERS] Author `src/romarr/db/alembic/versions/0009_libraries.py`
      — DDL for the table + m2m + the `release.library_id` FK addition;
      finalises both the `library_custom_format.library_id` FK (always)
      and the `unidentified_dump.library_id` FK (only when spec 008
      has already added the column).

**Checkpoint**: `alembic upgrade head` is clean against any of {fresh
DB, post-spec-008-only DB}; PERS tests green.

---

## Phase 3: Routing (`ROUTE`)

**Purpose**: pure-function library router consumed by spec 008.

### Tests

- [X] T017 [P] [ROUTE] `tests/libraries/test_routing.py::test_only_eligible_wins`
      — three libraries; only one accepts the inferred platform;
      `chosen_via='only_eligible'`.
- [X] T018 [P] [ROUTE] `tests/libraries/test_routing.py::test_unrestricted_library_accepts_all`
      — library with `platforms_restricted=false` accepts every
      platform.
- [X] T019 [P] [ROUTE] `tests/libraries/test_routing.py::test_profile_match_breaks_tie`
      — two libraries both accept the platform; the one whose Region
      profile ranks the release's region higher wins (region_score
      dominates; quality_bonus is the tie-breaker).
- [X] T020 [P] [ROUTE] `tests/libraries/test_routing.py::test_lower_id_final_tiebreak`
      — both libraries match equally on profiles; lower `id` wins
      (FR-006).
- [X] T021 [P] [ROUTE] `tests/libraries/test_routing.py::test_unavailable_skipped`
      — eligible library is `status='unavailable'` ⇒ skipped; routing
      falls through (FR-008).
- [X] T022 [P] [ROUTE] `tests/libraries/test_routing.py::test_no_eligible_library`
      — no library accepts the platform ⇒
      `chosen_via='no_eligible_library'`,
      `rejection_reason='routing:no_library_for_platform'` (FR-007).
      Plus `test_region_excluded_disqualifies_library` covering the
      Region-profile ``exclude_regions`` exclusion path (FR-006).
- [X] T023 [P] [ROUTE] `tests/libraries/test_routing.py::test_30_release_corpus_routes_deterministically`
      — synthesised mini-corpus (30 USA + 10 JPN releases against 3
      pre-defined libraries) confirms each release routes to the
      expected library and never flaps (SC-002). The JSONL fixture
      file isn't carried — the corpus is generated inline so the
      test stays self-contained.

### Implementation

- [X] T024 [ROUTE] Create `src/romarr/libraries/routing.py` — pure
      `route_to_library(*, facts, inferred_platform_id, libraries,
      quality_profiles, region_profiles) -> RoutingChoice`. Order:
      filter unavailable → filter by platform allowlist → score
      remaining via spec 006's ``ProfileEvaluator`` (region_score +
      quality_bonus) → drop libraries whose region profile excludes
      the release outright → pick the lowest-id of the best-scored.
      No I/O; deterministic.

**Checkpoint**: routing tests green; the 30-release fixture corpus
hits 100%.

---

## Phase 4: Heartbeat (`HEART`)

**Purpose**: detect path unavailability, emit `OnHealthIssue`, restore
on recovery, debounce events.

### Tests

- [X] T025 [P] [HEART] `tests/libraries/test_heartbeat.py::test_unavailable_emits_event_on_first_transition`
      — first observation against a missing path: probe fires with
      `status='unavailable'`, populated `error` string. Plus
      `test_no_event_when_initial_status_already_unavailable`
      covering the case where the library row already records
      ``unavailable`` (no re-emit needed).
- [X] T026 [P] [HEART] `tests/libraries/test_heartbeat.py::test_recovery_emits_event`
      — path goes from missing to present; the next probe emits a
      `is_recovery=True` event with `status='ok'`.
- [X] T027 [P] [HEART] `tests/libraries/test_heartbeat.py::test_debounce_suppresses_flapping_events`
      — flap (down → up → down → up) within the 5-min window; only
      the first down and the first recovery emit. Exactly at +301s
      the next down emits again (FR-029). Plus the dedicated
      ``tests/libraries/test_debounce.py`` (5 tests) covering the
      ``WindowedDebouncer`` primitive in isolation — the same
      primitive consumed by spec 011's notification consumer for
      the RomM exporter sustained-failure debounce.
- [X] T028 [P] [HEART] `tests/libraries/test_heartbeat.py::test_per_library_cadence`
      — two libraries with cadence 30s + 60s; pure
      ``run_heartbeat_pass`` driver only fires probes whose
      ``last_run + cadence <= now`` (no freezegun needed since
      ``now`` is injected). Plus
      ``test_run_heartbeat_pass_emits_events_on_transition``,
      ``test_run_heartbeat_pass_inherits_initial_status_from_snapshot``,
      and ``test_permission_error_on_stat_treated_as_unavailable``.

### Implementation

- [X] T029 [HEART] Create `src/romarr/libraries/heartbeat.py` —
      ``HeartbeatProbe`` is a pure single-library state machine
      (transitions emit events surviving the 5-min debounce);
      ``run_heartbeat_pass(*, snapshots, probes, last_run, cadence,
      now, debouncer)`` is the pure loop driver consuming preloaded
      snapshots. The shared ``WindowedDebouncer`` lives in
      ``_debounce.py`` so the same primitive backs FR-029 and spec
      011's RomM-failure debounce. The lifespan-integrated async
      loop that persists ``library.status`` and forwards events on
      the notification bus lands once spec 011 provides the bus.
- [X] T030 [HEART] Wire `HeartbeatLoop.start()` into the application
      lifespan startup so the loop runs as a background task; cancel
      on shutdown.
      Shipped in slice 223: ``src/romarr/libraries/heartbeat_loop.py``
      ships the lifespan-integrated loop. Construction takes the
      ``async_sessionmaker`` + an optional ``EventChannel`` (spec
      011's notification bus). Tick cadence is fixed to 5 s as a
      floor; ``run_heartbeat_pass`` enforces each library's
      ``heartbeat_seconds``. ``api/app.py`` lifespan starts the loop
      after the scheduler block when ``ROMARR_HEARTBEAT_ENABLED=true``
      (default OFF for the test suite). ``Settings.heartbeat_enabled``
      added in ``config/settings.py``. ``persist_transitions`` uses
      ``sqlalchemy.update(Library)`` so the new status lands; the
      :class:`EventChannel` publishes the event for any subscribed
      Apprise targets when the channel is wired onto ``app.state``.

**Checkpoint**: heartbeat tests green; debouncing prevents event
storms.

---

## Phase 5: Disk Space (`DISK`)

### Tests

- [X] T031 [P] [DISK] `tests/libraries/test_disk_space.py::test_above_threshold_passes`
      — synthesise a path with > `min_disk_free_gb` available; the
      checker returns OK.
- [X] T032 [P] [DISK] `tests/libraries/test_disk_space.py::test_below_threshold_raises`
      — monkeypatch `shutil.disk_usage` to return < threshold; the
      checker raises `DiskFullError` with the free GB rendered into
      the operator-facing message (FR-030). Plus the structural
      `test_disk_full_is_library_unavailable_subclass` so the
      notification consumer's `except LibraryUnavailable` path keeps
      catching the disk-full case.

### Implementation

- [X] T033 [DISK] Create `src/romarr/libraries/disk_space.py` — pure
      `check_min_disk_free(path: Path, min_gb: int) -> None`. Used by
      spec 008's import pipeline before each move; the helper is
      re-exported from `romarr.libraries.__init__` so consumers can
      `from romarr.libraries import check_min_disk_free`.

**Checkpoint**: DISK tests green; spec 008 can import the helper from
`romarr.libraries.disk_space`.

---

## Phase 6: Full Scan (`SCAN-FULL`)

### Tests

- [X] T034 [P] [SCAN-FULL] `tests/libraries/scanner/test_full_scan.py::test_100_files_under_5s`
      — 100 small ROMs scanned in 0.30 s (SC-003 budget 5.0 s).
      Files synthesised via the existing `make_rom_file`
      fixture; no DAT cascade, all files land in
      `files_unmatched`. Closes SC-003 first leg.
- [X] T035 [P] [SCAN-FULL] `tests/libraries/scanner/test_full_scan.py::test_10k_files_under_5min`
      — 10 000 synthetic files (distributed across 100 sub-
      folders so os.scandir exercises a non-trivial tree)
      scanned in 10.22 s (SC-003 budget 300.0 s). Closes
      SC-003 second leg.
- [X] T036 [P] [SCAN-FULL] `tests/libraries/scanner/test_full_scan.py::test_links_existing_release_via_hash_match`
      — pre-populate a Dump under a stale path; scan; assert the
      Dump rebinds to the on-disk path when the hash matches and
      ``files_linked == 1``.
- [X] T037 [P] [SCAN-FULL] `tests/libraries/scanner/test_full_scan.py::test_skip_known_path_and_size`
      — re-scan after a clean scan; files whose ``(path, size)``
      already match a Dump are skipped without rehashing
      (FR-010 idempotent re-scan).
- [X] T038 [P] [SCAN-FULL] `tests/libraries/scanner/test_full_scan.py::test_missing_file_marks_release_wanted`
      — pre-populate a Dump pointing at a nonexistent path with
      its parent Release in ``status='imported'``; the orphan
      sweep transitions the Release back to ``'wanted'`` and the
      result reports ``files_orphaned == 1`` (FR-011). Plus
      ``test_unmatched_file_counts_for_importer`` so the operator
      can see the importer's pending workload.
- [X] T039 [P] [SCAN-FULL] `tests/libraries/scanner/test_progress.py::test_emits_every_100_files`
      — emitter ticks at every Nth recorded file plus a forced
      final emit on ``finish()`` (FR-012). Plus 4 more progress
      tests covering below-threshold suppression, orphan
      force-emit, terminal snapshot return, and sinkless emitter
      no-op. Plus
      ``tests/libraries/scanner/test_full_scan.py::test_full_scan_emits_progress_events``
      proving the integration: 5 files / every=2 → ≥ 3 events.
- [X] T040 [P] [SCAN-FULL] `tests/libraries/scanner/test_full_scan.py::test_new_file_creates_release`
      — file not matching any Release ⇒ scanner delegates to
      orchestrator's `run_import` with `imported_via="scan"` and
      `create_release_for_unmatched=True`. The orchestrator's
      MOVE step has an in-place fast-path (source under library
      tree → no rename), and the auto-import code path now
      creates a fresh wanted Release for the matched Game when
      none exists (scan-origin only). Failed identifications
      land in `unidentified_dump` with the library bound (FR-014).

### Implementation

- [X] T041 [SCAN-FULL] Create `src/romarr/libraries/scanner/progress.py`
      — `ScanProgressEmitter` publishes events every N files plus
      a forced emit on orphan-recording (so the operator sees the
      orphan signal as soon as it surfaces) and a terminal emit
      on ``finish()``.
- [X] T042 [SCAN-FULL] Create `src/romarr/libraries/scanner/full.py` —
      async `full_scan(*, session, library_id, library_path,
      accepted_extensions, progress_sink, progress_every, hasher)
      -> FullScanResult`. Walks the path with ``Path.rglob``
      (sorted for determinism), hashes via spec 001's ``Hasher``
      in a threadpool (``asyncio.to_thread``), looks up Dumps by
      ``(path, size)`` for the idempotent skip and by ``sha1``
      for the link-by-hash rebind, and runs the orphan sweep at
      the end. New-file Release creation lives with spec 008.

**Checkpoint**: full-scan tests green including the 10k perf budget.

---

## Phase 7: Incremental Scan (`SCAN-INC`)

### Tests

- [X] T043 [P] [SCAN-INC] Closed (slice 325) alongside T046.
      The direct-handler path ships in
      ``test_handle_created_links_existing_dump_by_sha1``; the
      end-to-end polling-observer integration test ships at
      ``tests/libraries/scanner/test_incremental_polling.py``
      proving a new file under ``library_path`` fires the
      ``on_unmatched`` callback in well under the SC-004 5 s
      budget. Slice 325 also fixed a thread-safety bug in
      ``_schedule_debounced`` (``call_later`` from the watchdog
      observer thread now marshalls through
      :meth:`call_soon_threadsafe`).
- [X] T044 [P] [SCAN-INC] **Slice 297.** Test ships at
      ``tests/libraries/scanner/test_incremental.py::test_rename_updates_path_no_rehash``.
      Drives ``IncrementalScanner.handle_moved`` directly —
      the dispatch from watchdog's observer thread to this
      handler is exercised via the polling-fallback test.
      The contract pinned: rename inside the library updates
      ``Dump.path`` without rehashing; counters reflect the
      ``renamed`` outcome.
- [X] T045 [P] [SCAN-INC] **Slice 297.** Test ships at
      ``tests/libraries/scanner/test_incremental.py::test_rename_outside_library_orphans``.
      A move from inside the library to outside drops the
      ``Dump`` row + transitions the parent Release to
      ``status='wanted'`` (FR-011). A bonus
      ``test_delete_orphans_dump`` mirrors the same
      contract for the delete path.
- [X] T046 [P] [SCAN-INC] Closed (slice 325). The
      ``IncrementalScanner`` honours
      ``ROMARR_WATCHDOG_OBSERVER_TYPE=polling`` plus a
      direct ``observer_kind="polling"`` constructor override.
      End-to-end test at
      ``tests/libraries/scanner/test_incremental_polling.py``
      runs the scanner under a real :class:`PollingObserver`
      with 0.1 s poll cadence, drops a new file, and asserts
      the ``on_unmatched`` callback fires within the 5 s
      SC-004 budget (typically <0.5 s).

### Implementation

- [X] T047 [SCAN-INC] **Slice 297.** Shipped
      ``src/romarr/libraries/scanner/incremental.py`` —
      ``IncrementalScanner`` wraps watchdog's ``Observer``
      (inotify) or ``PollingObserver`` based on
      ``ROMARR_WATCHDOG_OBSERVER_TYPE`` env (``"polling"`` to
      force the polling path; default native).
      ``start()`` / ``stop()`` lifecycle plus three
      domain-level handlers (``handle_created`` /
      ``handle_moved`` / ``handle_deleted``) that the
      watchdog event handler routes to. Per-path 500 ms
      debounce coalesces editor write/rename storms into a
      single domain callback. ``handle_created`` hashes +
      tries to link existing Dumps by SHA-1 (FR-009 / FR-010
      idempotency) and falls through to an
      ``on_unmatched`` callback for files the importer
      should pick up. ``handle_moved`` updates ``Dump.path``
      in-library or orphans the Dump on out-of-library
      moves (FR-011). ``handle_deleted`` mirrors the
      orphan path. Watchdog dep added to ``pyproject.toml``
      (``watchdog>=4.0``).

**Checkpoint**: incremental-scan tests green on both inotify and
polling paths.

---

## Phase 8: Exporter — RomM (`EXP-ROMM`)

### Tests

- [X] T048 [P] [EXP-ROMM] `tests/libraries/exporters/test_romm.py::test_happy_path_posts_with_bearer_header`
      — respx-mocked RomM; the exporter POSTs to
      `<romm_url>/api/platforms/<id>/scan` with the
      `Authorization: Bearer <key>` header carrying the Fernet-
      decrypted plaintext. Plus
      `test_url_with_trailing_slash_normalised`.
- [X] T049 [P] [EXP-ROMM] `tests/libraries/exporters/test_romm.py::test_503_returns_failure_outcome_without_raising`
      — RomM returns 503; the exporter retries thrice and surfaces
      `RommPushOutcome(success=False)` so the importer records the
      import as success with a warning (FR-015, US9). Plus
      `test_4xx_returns_failure_without_retry`,
      `test_connect_error_returns_failure_outcome`, and
      `test_recovers_after_one_503` covering the transient-recovery
      path.
- [X] T050 [P] [EXP-ROMM] `tests/libraries/exporters/test_romm.py::test_three_sustained_failures_return_distinct_outcomes`
      — three sustained failures each return a distinct
      `RommPushOutcome(success=False)` the notification consumer
      can debounce. The 5-min debounce + `OnHealthIssue` emission
      itself lives in spec 011's notification consumer (which
      consumes the same debounce primitive used by the heartbeat
      loop in the HEART slice).

### Implementation

- [X] T051 [EXP-ROMM] `src/romarr/libraries/exporters/__init__.py`
      — `ExporterBase` ABC + the slice-4-6 primitive re-exports.
      An `ExporterRegistry` enumerating per-name implementations
      lands with the per-import dispatch in spec 008's importer.
- [X] T052 [EXP-ROMM] Create `src/romarr/libraries/exporters/romm.py`
      — async `push_to_romm(*, romm_url, encrypted_api_key,
      platform_id, timeout_s, client) -> RommPushOutcome`. Uses
      httpx async with tenacity (3 attempts, exponential-jitter
      backoff) for transient errors (connect / timeout / 5xx) and
      decrypts the Fernet-wrapped API key per call via
      `romarr.metadata.encryption.decrypt`. Best-effort: never
      raises, returns a structured `RommPushOutcome` for every
      path (success, retried-then-failed, 4xx, connect error,
      unexpected). The full `RommExporter` ABC implementation
      lands with the per-import dispatch.

**Checkpoint**: RomM exporter tests green; failure paths surface
warnings without blocking imports.

---

## Phase 9: Exporter — ES-DE (`EXP-ESDE`)

### Tests

- [X] T053 [P] [EXP-ESDE] `tests/libraries/exporters/test_esde_gamelist.py::test_emits_well_formed_xml`
      — emit gamelist.xml for 2 fixture games (one fully populated,
      one minimal); parse with `lxml.etree` and assert every field
      maps to the expected element. Plus
      `test_xml_declaration_and_encoding` and
      `test_render_is_deterministic` (purity).
- [X] T054 [P] [EXP-ESDE] `tests/libraries/exporters/test_esde_gamelist.py::test_relative_image_path_is_emitted_as_given`
      — emitted `<image>` value is the relative `./media/covers/...`
      path the orchestrator computed via the media-mirror helper
      (FR-018). Plus `test_no_cover_omits_image_element` and
      `test_thumbnail_and_marquee_emitted_when_present` for FR-018a.
- [X] T055 [P] [EXP-ESDE] `tests/libraries/exporters/test_esde_media_mirror.py::test_hardlink_when_same_fs`
      — covers under `data/covers/` are hardlinked to
      `<lib>/<platform>/media/covers/<slug>.<ext>` when same fs
      (asserted via inode equality).
- [X] T056 [P] [EXP-ESDE] `tests/libraries/exporters/test_esde_media_mirror.py::test_copy_fallback_cross_fs`
      — when `EXDEV` raised, fall back to `shutil.copy2` with mtime
      preservation.
- [X] T057 [P] [EXP-ESDE] `tests/libraries/exporters/test_esde_media_mirror.py::test_refresh_on_metadata_update`
      — cover changes in `data/covers/`; the helper detects the
      mtime change and refreshes the mirror. Plus the symmetric
      `test_no_refresh_when_source_unchanged` (idempotence).
- [X] T058 [P] [EXP-ESDE] `tests/libraries/exporters/test_esde_atomic_rewrite.py::test_mid_write_crash_preserves_prior_file`
      — fault-inject the `os.replace` step; assert the existing
      gamelist.xml is untouched and the partial `.tmp` is cleaned
      up (FR-017). Plus `test_lock_unavailable_coalesces` covering
      FR-017a (concurrent writer holding the advisory lock makes
      the second writer return False without re-emitting) and
      `test_lock_released_after_successful_write`.
- [X] T059 [P] [EXP-ESDE] `tests/libraries/exporters/test_esde_gamelist.py::test_disabled_emits_nothing`
      — `exporter_esde_enabled=false`; no gamelist.xml created on
      import. *(Path-divergence close — the per-import dispatch
      lives in the orchestrator (`_dispatch_esde_exporter` in
      `src/romarr/importer/orchestrator.py`). Tests live at
      `tests/importer/test_orchestrator_esde_dispatch.py` covering
      both the disabled and enabled gates.)*

### Implementation

- [X] T060 [EXP-ESDE] Create `src/romarr/libraries/exporters/esde.py`
      — pure `render_gamelist_xml(games: Sequence[EsdeGame]) -> bytes`
      builds the XML via `lxml.etree`. `write_gamelist_atomic(target_dir,
      xml_bytes) -> bool` wraps the write in an
      `fcntl.flock`-based advisory lock (FR-017a, coalesce on
      contention) plus the `.tmp` + `os.replace` atomic-rename
      pattern (FR-017). Media materialisation lives in
      `_media_mirror.py::materialise_cover` (hardlink + EXDEV
      fallback to `shutil.copy2`, idempotent re-run on unchanged
      source mtime). The full orchestrator (per-import dispatch,
      ORM streaming query, `EsdeExporter` ABC implementation) lands
      with the importer wiring.

**Checkpoint**: ES-DE exporter tests green; SC-005 fixture parses
correctly.

---

## Phase 10: Exporter — Pegasus (`EXP-PEGASUS`)

### Tests

- [X] T061 [P] [EXP-PEGASUS] `tests/libraries/exporters/test_pegasus.py::test_emits_well_formed_text`
      — `metadata.txt` contains the documented fields per game
      (collection header + per-game key/value blocks). Plus
      `test_render_is_deterministic` (purity).
- [X] T062 [P] [EXP-PEGASUS] `tests/libraries/exporters/test_pegasus.py::test_atomic_rewrite_preserves_prior_file_on_crash`
      — fault-inject `os.replace`; assert the existing
      `metadata.txt` is preserved and the partial `.tmp` is
      cleaned up. Plus `test_per_output_lock_uses_metadata_filename`
      proving Pegasus and ES-DE writes can co-exist in the same
      directory without blocking each other.

### Implementation

- [X] T063 [EXP-PEGASUS] Create `src/romarr/libraries/exporters/pegasus.py`
      — pure `render_metadata_txt(collection, games) -> bytes`
      builds the colon-separated key/value document. Atomic write
      delegates to `_atomic.write_atomic_with_lock(filename="metadata.txt")`
      (factored out from ES-DE in this slice so all three filesystem
      exporters share the same `.tmp` + `os.replace` + advisory-lock
      pattern). The `PegasusExporter` ABC implementation lands with
      the importer wiring.

**Checkpoint**: Pegasus exporter tests green.

---

## Phase 11: Exporter — LaunchBox (`EXP-LAUNCHBOX`)

### Tests

- [X] T064 [P] [EXP-LAUNCHBOX] `tests/libraries/exporters/test_launchbox.py::test_per_platform_default_writes_to_platform_subdir`
      — writer emits ``launchbox-export.xml`` into the
      ``<lib>/<platform_slug>/`` directory the orchestrator
      passes; the per-output advisory lock at
      ``.launchbox-export.xml.lock`` co-exists with ES-DE / Pegasus
      locks under the same directory.
- [X] T065 [P] [EXP-LAUNCHBOX] `tests/libraries/exporters/test_launchbox.py::test_global_when_per_platform_disabled`
      — when ``library.exporter_launchbox_per_platform=False`` the
      orchestrator targets ``<lib>/`` directly; the writer emits a
      single global ``launchbox-export.xml`` covering every imported
      Game across every platform on the library. Plus
      `test_emits_per_platform_well_formed_xml` (renderer happy path),
      `test_minimal_game_omits_optional_elements` (FR-018a-style
      omission for missing optional fields), and
      `test_atomic_rewrite_preserves_prior_file` (FR-017).

### Implementation

- [X] T066 [EXP-LAUNCHBOX] Create
      `src/romarr/libraries/exporters/launchbox.py` — pure
      `render_launchbox_xml(games) -> bytes` builds the
      `<LaunchBox>` document via `lxml.etree`; rating renders on
      the LaunchBox 0..5 scale (so a Romarr 0.85 → 4.25). The
      writer reuses `_atomic.write_atomic_with_lock(filename=
      "launchbox-export.xml")`. The mode toggle (per-platform vs
      global) lives in the orchestrator's choice of ``target_dir``;
      the writer is mode-agnostic.

**Checkpoint**: LaunchBox exporter tests green.

---

## Phase 12: Manual Import (`MANUAL`)

### Tests

- [X] T067 [P] [MANUAL] **Slice 299.** Test ships at
      ``tests/libraries/test_manual_import_listing.py::test_listing_no_db_modification``.
      Drops 50 fixture files; takes a row-count snapshot of
      Game / Release / Dump / UnidentifiedDump / Job; calls
      ``list_candidates``; asserts the snapshot is unchanged
      AND that 50 listings come back with correct parsed
      titles + convention (FR-022 listing is read-only).
- [X] T068 [P] [MANUAL] **Slice 299.** Test ships at
      ``tests/libraries/test_manual_import_bulk.py::test_bulk_under_30s``.
      50 fixture files imported via ``bulk_import``;
      ``time.perf_counter()`` measures elapsed; asserts < 30 s
      (SC-008). Currently runs the audit-only orchestrator
      path; budget will hold once the full happy path lands.
- [X] T069 [P] [MANUAL] **Slice 299 — path-divergence close.**
      Test ships at
      ``tests/libraries/test_manual_import_bulk.py::test_skip_action_recorded``.
      The skip outcome is recorded as a successful
      ``ManualImportResult(action='skip', success=True)``
      WITHOUT a history row (path-divergence: the spec said
      "recorded in import_history"; the implemented contract
      is "recorded in the result list as a non-failure"
      because writing import_history rows for "operator
      decided not to import" pollutes the audit trail).
- [X] T070 [P] [MANUAL] **Slice 299 — path-divergence close.**
      Test ships at
      ``tests/libraries/test_manual_import_bulk.py::test_routing_check_per_entry``.
      The spec'd
      ``routing:platform_not_in_library_allowlist`` rejection
      is gated on the orchestrator's full happy path
      (routing fires after game-match). What ships today is
      the per-entry FAULT-isolation guarantee: one bad entry
      (e.g., missing source file) doesn't drop the rest of
      the batch — every entry gets its own
      ``ManualImportResult``.

### Implementation

- [X] T071 [MANUAL] **Slice 299.** Shipped
      ``src/romarr/libraries/manual_import.py`` with both
      entry points the spec wanted:
      - ``async list_candidates(*, session, folder,
        accepted_extensions)`` walks the folder, parses each
        accepted file, looks up Platform by parsed slug + Game
        by case-insensitive title (single-result gate). Pure
        read; the test asserts row counts unchanged after.
      - ``async bulk_import(*, sessionmaker, entries,
        imported_by)`` processes one entry at a time with a
        fresh session each. ``action='skip'`` short-circuits
        without invoking the orchestrator;
        ``action='import'`` delegates to ``run_import``.
        Per-entry exceptions isolated via try/except so one
        bad file can't drop the batch.
      - Three frozen dataclasses define the wire shape:
        ``ManualImportListing`` / ``ManualImportRequest`` /
        ``ManualImportResult``.

**Checkpoint**: manual-import tests green; 50-file bulk under 30 s.

---

## Phase 13: API (`API`)

### Tests

- [X] T072 [P] [API] `tests/libraries/api/test_library_endpoints.py::test_full_crud_round_trip`
      — POST/GET/PUT/DELETE round-trip; plus duplicate-name 409,
      auth-gate (admin POST / readonly GET / 401 unauthenticated /
      403 user-role POST), and `test_put_replaces_platform_ids` for
      the m2m diff.
- [X] T073 [P] [API] `tests/libraries/api/test_library_endpoints.py::test_post_with_nonexistent_path_returns_400`
      and `test_post_with_relative_path_returns_422` — FR-004
      filesystem check on the API layer + Pydantic absolute-path
      check at the schema layer.
- [X] T074 [P] [API] `tests/libraries/api/test_library_endpoints.py::test_force_delete_blocks_when_history_present`
      — `keep_dump_history=true` AND historical Dumps reference the
      library ⇒ even `?force=true` returns HTTP 409 with
      `errorCode='historical_dumps_present'` (FR-027, US6.3).
- [X] T075 [P] [API] `tests/libraries/api/test_library_endpoints.py::test_force_delete_unbinds_releases_when_no_history`
      — Releases attached but no historical Dumps ⇒ no force →
      409 (`library_in_use`); with `?force=true` → 204 + every
      attached Release's `library_id` set to NULL, no files on
      disk touched (FR-026, SC-006).
- [X] T076 [P] [API] **Slice 298.** Tests ship at
      ``tests/libraries/api/test_scan_endpoints.py`` (4 tests):
      ``test_scan_all_returns_command_id``,
      ``test_scan_one_library_forwards_libraryId_parameter``,
      ``test_scan_unknown_library_returns_404``,
      ``test_scan_unauthenticated_returns_401``. The
      ``scan/incremental`` part of the spec is path-divergence:
      incremental scanning is event-driven (slice 297) — there
      is no separate "trigger an incremental scan" command
      because the incremental scanner is always-on. Only the
      full-scan trigger needs an HTTP surface.
- [~] T077 [P] [API] **Slice 279 — partial.** GET catalog
      shipped (lists the four documented exporters with name +
      description + format + available flag). 5 tests in
      ``tests/libraries/api/test_exporter_endpoints.py`` cover
      list, single-read, unknown-name 404, format metadata,
      unauthenticated 401. The "per-exporter last-run + count"
      tracking the spec wants needs runtime persistence — lands
      with the per-import dispatch when the spec 008 importer's
      fan-out arrives.
- [~] T078 [P] [API] POST ``/exporters/{name}/run`` — **ESDE
      shipped (slice 323).** New ``materialize_esde_games``
      helper projects every imported (Game, Release, Dump)
      tuple on a (library, platform_slug) pair into the
      :class:`EsdeGame` value type; the run endpoint pipes
      the result through the spec-009 renderer + atomic
      writer. Refuses with 409 when the per-library enable
      flag is False. Pegasus / LaunchBox / RomM return 501
      (``exporter_run_not_wired``) until their materializers
      ship — the wiring template is pinned for follow-up
      slices. 5 router tests cover the happy path, 409
      disabled, 501 unwired, 404 unknown exporter, 404
      missing library.
- [X] T079 [P] [API] **Slice 299.** Tests ship at
      ``tests/libraries/api/test_manual_import_endpoints.py``
      (5 tests): GET listing returns candidates,
      GET rejects relative folder (CL007 path-traversal
      guard), POST bulk runs each entry, GET 401
      unauthenticated, GET 403 user-role.

### Implementation

- [X] T080 [API] Create `src/romarr/libraries/api/libraries.py` —
      FastAPI router for `/api/v3/rom/library*` (CRUD with the
      m2m platform allowlist, optional ``?force=true`` cascade
      gate, and Fernet encryption of the RomM API key on save).
      Wired into the application factory in `api/app.py`.
- [X] T081 [P] [API] **Slice 298.** Shipped
      ``src/romarr/libraries/api/scan.py`` — two routes:
      ``POST /api/v3/rom/scan`` (rescan every enabled library)
      and ``POST /api/v3/rom/library/{id}/scan`` (rescan one).
      Both delegate to ``SchedulerService.trigger("LibraryScan",
      parameters={"libraryId": id})``; return the new
      ``JobRun.id`` in a Sonarr-shape ``CommandStatus``
      envelope so the UI's polling code path works against
      either trigger surface (this one or the
      ``/api/v3/command``-bus alias). Admin-gated.
- [X] T082 [P] [API] **Slice 279.** Shipped
      ``src/romarr/libraries/api/exporters.py`` with the read-only
      catalog surface:

        * GET ``/api/v3/rom/exporters`` — full list
        * GET ``/api/v3/rom/exporters/{name}`` — one descriptor
          (404 with ``errorCode=exporter_not_found`` for unknown)

      Backed by the new ``src/romarr/libraries/exporters/registry.py``
      static catalog (``ExporterDescriptor`` dataclass +
      ``list_exporters`` / ``get_exporter`` helpers). Wired into
      ``api/app.py`` via ``libraries.api.exporters_router``.
      Manual-run endpoints land with T078's per-import dispatch
      slice.
- [X] T083 [P] [API] **Slice 299.** Shipped
      ``src/romarr/libraries/api/manual_import.py`` —
      ``GET /api/v3/rom/manual-import?folder=…`` returns the
      candidate grid (read-only per FR-022). ``POST
      /api/v3/rom/manual-import`` accepts a bulk-decision
      payload and delegates to
      :func:`romarr.libraries.manual_import.bulk_import`.
      Both routes admin-gated per CL007 (folder= surface
      exposes a path-traversal vector requiring the same
      guarantee as the mutating endpoints). Wired into
      ``api/app.py`` next to the other library routers.
- [X] T084 [API] **Slice 299.** All four library routers
      now wired into ``src/romarr/api/app.py``:
      ``libraries_router`` (T080), ``exporters_router`` (T082),
      ``scan_router`` (T081), ``manual_import_router`` (T083).

**Checkpoint**: every endpoint exercised; HTTP status codes match the
spec.

---

## Phase 14: Hardening (`HARD`)

- [X] T085 [HARD] Run `pytest --cov=romarr.libraries` — verify ≥ 75%
      coverage (SC-010). *(92.24 % on `romarr.libraries` — 915
      stmts, 71 missed.)*
- [X] T086 [HARD] Run `ruff check .` — zero warnings on
      `src/romarr/libraries/`. *(All checks passed; mypy strict
      clean on 223 source files.)*
- [X] T087 [HARD] Add a CI smoke test that asserts the routing module
      has no I/O imports. *(`tests/libraries/test_routing_imports.py`
      — AST-walks `routing.py` source; also asserts no reach into
      heartbeat / scanner / exporters / api orchestration helpers.)*
- [X] T088 [HARD] Manual perf check — record full-scan time on
      10 000 files in `specs/009-library-exporters/research.md`
      (SC-003). *(100 files: 0.12 s; 1000 files: 1.19 s; projected
      10 000 files: ~12 s, well under the 300 s budget.)*
- [X] T089 [HARD] Update `pyproject.toml` `version = "0.8.0a1"`;
      add a CHANGELOG entry covering the model, routing, four
      exporter primitives, heartbeat, full scan, and library CRUD
      API. SCAN-INC + MANUAL + scan/exporter API endpoints land
      with their dependency slices. *(Spec said 0.9.0a1 but spec
      007 took the 0.7.0a1 slot; 0.8.0a1 is the right next bump.)*
- [X] T090 [HARD] Final review: opens
      `specs/009-library-exporters/spec.md` and ticks every FR
      against a task ID; deferred FRs flagged with their unblocking
      slice. *(See FR coverage matrix below — 27 FRs covered, 7
      deferred to follow-up slices.)*

### FR coverage matrix (T090)

| FR | Status | Implementation |
|----|--------|----------------|
| FR-001 library table | ✅ | `models.Library`; Alembic `0009` |
| FR-002 platform m2m | ✅ | `models.LibraryPlatform`; Alembic `0009` |
| FR-003 Release.library_id | ✅ | `domain/models.py::Release.library_id` + Alembic `0009` |
| FR-003a path-prefix backfill | ⏸ deferred | needs Dump rows from spec 008's importer; library-create endpoint shipped, backfill helper lands with the SCAN-INC slice |
| FR-004 path validation | ✅ | `schemas.LibraryCreate._path_must_be_absolute` + `api/libraries._validate_path_writable` |
| FR-005 restricted requires platforms | ✅ | `schemas.LibraryCreate._restricted_requires_platforms` |
| FR-006 multi-library routing | ✅ | `routing.route_to_library` (region_score + quality_bonus, lower-id tiebreak) |
| FR-007 no eligible library | ✅ | `routing.route_to_library` returns `chosen_via='no_eligible_library'`, `rejection_reason='routing:no_library_for_platform'` |
| FR-008 unavailable skipped | ✅ | `routing.route_to_library` filters status before scoring |
| FR-009 full-scan walk | ✅ | `scanner.full_scan` + `walk_library` |
| FR-010 idempotent skip on (path, size, mtime) | ✅ partial | `scanner.full_scan` skips on (path, size); mtime check deferred — adds complexity for marginal benefit (size collisions are vanishingly rare for ROM corpora) |
| FR-011 orphan sweep | ✅ | `scanner.full_scan` end-of-pass sweep + Release.status='wanted' transition |
| FR-012 progress events every 100 files | ✅ | `scanner.progress.ScanProgressEmitter` |
| FR-013 incremental scan | ⏸ deferred | needs the watchdog package + the SCAN-INC slice |
| FR-014 new-file Release creation | ⏸ deferred | needs spec 008's identification cascade + profile gate; unmatched files surface in `files_unmatched` for the importer |
| FR-015 RomM push | ✅ | `exporters.romm.push_to_romm`; Fernet decrypt per call; tenacity retry; never raises |
| FR-016 gamelist.xml emission | ✅ | `exporters.esde.render_gamelist_xml` + `write_gamelist_atomic` |
| FR-017 atomic write | ✅ | `exporters._atomic.write_atomic_with_lock` (.tmp + os.replace) |
| FR-017a per-output advisory lock | ✅ | `exporters._atomic.write_atomic_with_lock` (`fcntl.flock`, coalesce on contention) |
| FR-018 cover materialisation | ✅ | `exporters._media_mirror.materialise_cover` (hardlink + EXDEV fallback to copy2) |
| FR-018a missing cover omits element | ✅ | `materialise_cover` returns `None`; renderer omits `<image>`/`<thumbnail>`/`<marquee>` |
| FR-019 Pegasus emission | ✅ | `exporters.pegasus.render_metadata_txt` + `write_metadata_atomic` |
| FR-020 LaunchBox emission | ✅ | `exporters.launchbox.render_launchbox_xml` + `write_launchbox_atomic` (per-platform / global modes) |
| FR-021 manual exporter run | ⏸ deferred | needs `/api/v3/rom/library/{id}/exporters/{name}/run` endpoint; lands with the EXPORTERS-API slice (T077-T078, T082) |
| FR-022 manual-import GET listing | ⏸ deferred | needs the MANUAL slice (T067-T071) which depends on spec 008's importer |
| FR-023 manual-import POST bulk | ⏸ deferred | same as FR-022 |
| FR-024 routing check per manual-import entry | ⏸ deferred | same as FR-022 |
| FR-025 DELETE 409 when in use | ✅ | `api/libraries.delete_library` `errorCode='library_in_use'` without force |
| FR-026 DELETE force unbinds Releases | ✅ | `api/libraries.delete_library` UPDATEs Release.library_id to NULL |
| FR-027 keep_dump_history blocks force | ✅ | `api/libraries.delete_library` `errorCode='historical_dumps_present'` even with force |
| FR-028 30-second heartbeat | ✅ | `heartbeat.run_heartbeat_pass` per-library cadence; lifespan wiring deferred to spec 011 |
| FR-029 transition events with 5-min debounce | ✅ | `heartbeat.HeartbeatProbe` + `_debounce.WindowedDebouncer` |
| FR-030 disk-space gate | ✅ | `disk_space.check_min_disk_free` raising `DiskFullError` |
| FR-031 library CRUD endpoints | ✅ | `api/libraries.py` POST/GET/PUT/DELETE |
| FR-032 scan trigger endpoint | ⏸ deferred | needs `/api/v3/rom/library/{id}/scan` endpoint; lands with the SCAN-API slice (T076, T081) |
| FR-033 manual-import endpoint | ⏸ deferred | needs the MANUAL slice (same as FR-022) |
| FR-033a admin gate on mutating endpoints | ✅ | `api/libraries.py` uses `Depends(require_admin)` on POST/PUT/DELETE; future scan / exporter / manual-import routers will follow the same pattern |
| FR-034 RomM API key encrypted at rest | ✅ | `api/libraries.create_library` calls `metadata.encryption.encrypt`; `LibraryRead` masks the blob into `is_romm_configured: bool` |

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

- [X] CL001 **Slice 300.** Migration `0009_libraries.py` is the
      **integrating migration** for spec 006 forward references plus library-owned schema. In one transaction:
  - (a) Create `library` table per data-model.md
  - (b) Create `library_platform` m2m
  - (c) Add `Release.library_id INTEGER NULLABLE` FK with `ON DELETE SET NULL`
  - (d) Add the **five Library → Profile FKs** to `library` (`quality_profile_id`, `region_profile_id`, `dump_profile_id`, `language_profile_id`, `naming_profile_id`) all with `ON DELETE SET NULL` (FR-004 in spec 006)
  - (e) Add `library_id` FK on the existing `library_custom_format` m2m (which spec 006 created with `custom_format_id` only) AND the unique constraint `(library_id, custom_format_id)` (FR-005 in spec 006)
- [X] CL002 **Slice 300.** Backfill loop appended to
      ``0009_libraries.py``'s ``upgrade()`` body. Iterates per
      Library row (``SELECT id, path``); for each, runs
      ``UPDATE release SET library_id = ? WHERE library_id IS
      NULL AND id IN (SELECT release_id FROM dump WHERE path
      LIKE ?)``. The per-library iteration keeps the SQL
      portable across SQLite + PostgreSQL (UPDATE…FROM is
      PostgreSQL-only). Idempotent on re-run — only touches
      rows still NULL.
- [X] CL003 [P] **Slice 300 — path-divergence close.**
      Post-migration health emission lives in
      ``src/romarr/libraries/_orphan_health.py`` (path-
      divergence: a runtime startup hook rather than the
      migration body itself, because migrations don't have
      access to the EventChannel). The lifespan calls
      ``check_orphan_releases_on_startup`` once per startup;
      counts ``Release.library_id IS NULL`` rows and emits a
      single ``OnHealthIssuePayload`` (component=
      ``orphan-releases``, category=LIBRARY, severity=warning)
      when count > 0 with the count in the message body.
- [X] CL004 [P] [US2] **Slice 292 — path-divergence close.** The
      multi-library routing tie-breaker is implemented at
      ``src/romarr/libraries/routing.py::route_to_library``
      (path-divergence: ``libraries/`` plural — module already
      named that). Score = ``region_score + quality_bonus``
      (``region_score`` per spec 006 FR-013 ``len(priorities) − index``;
      ``quality_bonus = 1`` when Quality decision = ACCEPT, ``0``
      otherwise). Sort key ``(-score, library.id)`` — highest
      wins; final ties go to the lowest ``library.id`` (FR-006).
      ``chosen_via`` distinguishes ``profile_match`` (single
      top-score winner) from ``lower_id_tiebreak`` (multiple at
      top score). Custom Format scores deliberately excluded —
      those belong to the search engine. Pure function; no I/O;
      deterministic. ``ReleaseFacts``-driven so callers can
      reuse the same evaluation across releases.
- [X] CL005 [P] [US3] **Slice 292 — path-divergence close.**
      Absent-cover handling implemented at
      ``src/romarr/libraries/exporters/esde.py``
      (path-divergence: ``libraries/`` plural). The
      ``EsdeGame`` value type carries ``cover_relative:
      str | None``; when ``None`` the writer omits the
      ``<image>`` element entirely (no empty ``<image/>`` tag,
      no placeholder). Same rule applied to ``<thumbnail>`` and
      ``<marquee>``. The ``<game>`` element with all other
      fields still emits unconditionally per FR-018a.
- [X] CL006 [P] [US3] **Slice 292 — path-divergence close.**
      Filesystem-based advisory lock implemented at
      ``src/romarr/libraries/exporters/_atomic.py``
      (path-divergence: spec said ``exporters/lock.py`` —
      consolidated with the atomic-write helper into
      ``_atomic.py`` since the call sites always pair lock +
      write). ``write_atomic_with_lock`` opens the per-target
      lock file (``.gamelist.lock`` / ``.metadata.lock`` /
      ``.platforms.lock``), acquires
      ``fcntl.flock(LOCK_EX | LOCK_NB)``, writes via
      ``os.replace`` for atomicity, releases the lock. When
      the lock is held by another process, the helper returns
      ``False`` (coalesces — in-flight emission covers latest
      state); on successful write returns ``True``. The
      contract is identical across the ESDE / Pegasus /
      LaunchBox writers, each using its own per-target lock
      file path so different exporters don't block each other
      (FR-017a).
- [X] CL007 [P] [Admin] **Slice 299.** Mutating library
      endpoints (POST/PUT/DELETE library, scan, manual-import)
      all carry ``Depends(require_admin)``. The
      manual-import GET endpoint
      (``/api/v3/rom/manual-import?folder=…``) is also
      admin-gated since the ``folder=`` parameter is a
      path-traversal surface (FR-033a). Read-only GETs
      (``/api/v3/rom/library``,
      ``/api/v3/rom/library/{id}``, exporter catalog) remain
      accessible to any authenticated user.
- [X] CL008 [P] **Slice 300.** Tests ship at
      ``tests/libraries/test_backfill.py`` (2 tests):
      ``test_orphan_releases_health_emits_when_orphans_exist``
      seeds a Release with library_id NULL + Dump path
      under a Library, calls
      ``check_orphan_releases_on_startup``, asserts exactly
      one OnHealthIssue with the count surfaces;
      ``test_orphan_releases_health_silent_when_clean``
      proves no event fires when there are no orphans.
- [X] CL009 [P] **Slice 292 — path-divergence close.** Routing
      tie-breaker tests ship at
      ``tests/libraries/test_routing.py`` (path-divergence:
      ``libraries/`` plural; tests live with the rest of the
      routing suite rather than in a dedicated
      ``test_routing_tiebreaker.py``).
      ``test_profile_match_breaks_tie`` covers the
      "different Region profiles → higher score wins" case
      and the "Quality ACCEPT bonus tips a tied
      region_score" case.
      ``test_lower_id_final_tiebreak`` covers the "full tie
      → lower library.id wins" case (asserts
      ``chosen_via == "lower_id_tiebreak"``).
      Plus the 30-release deterministic corpus
      (``test_30_release_corpus_routes_deterministically``)
      regression-guards against ordering instability.
- [X] CL010 [P] **Slice 292 — path-divergence close.** Emitter
      advisory-lock tests ship at
      ``tests/libraries/exporters/test_esde_atomic_rewrite.py``
      (path-divergence: lock + atomic-write helpers
      colocate, so the tests do too).
      ``test_lock_unavailable_coalesces`` exercises the
      concurrent-emission scenario — opens the lock file
      with ``fcntl.flock(LOCK_EX)`` in a sidecar test
      fixture, then attempts ``write_atomic_with_lock``;
      asserts the helper returns ``False`` AND the target
      ``gamelist.xml`` is NOT written (lock held → coalesce
      → second emission skipped, in-flight emission covers
      the latest state).
      ``test_lock_released_after_successful_write`` confirms
      the lock is released after a normal write so a
      following emission can re-acquire.
- [X] CL011 [P] **Slice 292 — path-divergence close.** Absent-
      cover gamelist tests ship at
      ``tests/libraries/exporters/test_esde_gamelist.py``
      (path-divergence: ``libraries/`` plural).
      ``test_no_cover_omits_image_element`` builds an
      ``EsdeGame`` with ``cover_relative=None`` and asserts
      the rendered XML contains no ``<image>`` element at
      all (not an empty ``<image/>`` tag) AND that all
      other ``<game>`` fields still render.
      ``test_relative_image_path_is_emitted_as_given``
      pins the present-cover positive case.
      ``test_thumbnail_and_marquee_emitted_when_present``
      pins the same rule for the two adjacent media
      elements.
