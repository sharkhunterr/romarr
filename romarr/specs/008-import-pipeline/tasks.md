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
      *(Deferred — DownloadClient ABC needs a
      ``list_managed_downloads`` method that doesn't exist yet
      on spec 005's surface. The polling watcher lands once
      that method is added; for now the webhook covers the
      operator's primary post-download-complete signal.)*
- [ ] T015 [P] [WATCH] `tests/importer/steps/test_watch_polling.py::test_filters_by_tag`
      *(Deferred with T014.)*
- [ ] T016 [P] [WATCH] `tests/importer/steps/test_watch_polling.py::test_isolates_failing_client`
      *(Deferred with T014.)*
- [X] T017 [P] [WATCH] `tests/importer/test_webhook.py::test_invalid_token_returns_401`
      — bad token returns HTTP 401 with structured
      ``errorCode='invalid_token'``; the comparison runs in
      constant time via :func:`secrets.compare_digest` so the
      response time doesn't leak the expected value. Plus
      ``test_missing_token_returns_401`` and
      ``test_disabled_webhook_returns_401`` (no-token-configured
      defensive case).
- [X] T018 [P] [WATCH] `tests/importer/test_webhook.py::test_rate_limit_returns_429_after_burst`
      — 10 valid requests in <60 s succeed; the 11th returns
      HTTP 429 with ``errorCode='rate_limited'``. Sliding-window
      counter per source IP via
      :class:`SlidingWindowLimiter`, in-process (the threat
      model is the operator's own qBit on their own network).
- [X] T019 [P] [WATCH] `tests/importer/test_webhook.py::test_valid_token_returns_202_and_dispatches`
      — happy path: 202 ACCEPTED with the request's
      ``download_client_native_id`` echoed back; the configured
      dispatcher fires asynchronously after the response
      publishes (FR-002 / SC-008). Plus
      ``test_no_dispatcher_configured_still_returns_202`` and
      ``test_missing_native_id_returns_422``.

### Implementation

- [ ] T020 [WATCH] Create `src/romarr/importer/steps/watch.py` — async
      ``WatcherLoop`` that runs every 30 s, iterates configured
      clients, and enqueues ``(client_id, native_id)`` candidates
      onto an internal ``asyncio.Queue`` consumed by the
      orchestrator. *(Deferred with T014-T016 — needs
      ``DownloadClient.list_managed_downloads``.)*
- [X] T021 [WATCH] Create `src/romarr/importer/webhook.py` — FastAPI
      handler at ``/api/v3/webhook/download-complete``.
      Constant-time token comparison via
      :func:`secrets.compare_digest`, sliding-window 60-s rate
      limit (10 req/IP) via
      :class:`romarr.importer._rate_limit.SlidingWindowLimiter`,
      schema validation via :class:`WebhookPayload`. Returns
      202 ACCEPTED immediately and dispatches the actual import
      via a fire-and-forget ``asyncio.create_task`` (held in
      ``_inflight`` so the loop doesn't garbage-collect it
      mid-import). ``configure_dispatcher(callable | None)``
      injects the dispatcher (tests pass a recorder; production
      wires the orchestrator's ``run_import``).
      Wired into the application factory in ``api/app.py``.
      Settings: new ``importer_webhook_token`` field on
      :class:`Settings` (empty = webhook closed).
- [ ] T022 [WATCH] Wire ``WatcherLoop.start()`` into the application
      lifespan startup. *(Deferred with T014-T016, T020.)*

**Checkpoint**: WATCH tests green; the watcher loop runs as a background
task and the webhook returns within the 1 s p95 budget.

---

## Phase 3: Extract (`EXTRACT`) — Pipeline step 2

### Tests

- [X] T023 [P] [EXTRACT] `tests/importer/steps/test_extract.py::test_zip_extracts_cleanly`
      — programmatically-built zip extracts cleanly; sentinel
      file ``.romarr-extracted-from-<sha1[:16]>`` written.
- [X] T024 [P] [EXTRACT] `tests/importer/steps/test_extract.py::test_7z_extracts_cleanly`
      — py7zr round-trip. The extractor chmods extracted files
      to ensure owner-read because py7zr propagates restrictive
      modes from ``writestr``-built archives.
- [X] T025 [P] [EXTRACT] `tests/importer/steps/test_extract.py::test_rar_extracts_cleanly`
      — rarfile round-trip; skipped automatically when neither
      ``unrar`` nor ``unar`` is on PATH.
- [X] T026 [P] [EXTRACT] `tests/importer/steps/test_extract.py::test_recursive_zip_in_zip`
      — outer.zip whose only member is inner.zip extracts both
      levels in one ``extract`` call (depth=0 -> depth=1).
- [X] T027 [P] [EXTRACT] `tests/importer/steps/test_extract.py::test_depth_exceeded_raises`
      — 3-level chain with ``max_depth=1`` raises
      ``extract:depth-exceeded`` on the third recursion (FR-004).
- [X] T028 [P] [EXTRACT] `tests/importer/steps/test_extract.py::test_idempotent_re_extract_skips`
      — second ``extract`` call against the same dest finds the
      sentinel and returns ``archive_was_processed=False`` /
      ``bytes_written=0`` (FR-006).
- [X] T029 [P] [EXTRACT] `tests/importer/steps/test_extract.py::test_corrupted_archive_raises`
      — non-archive bytes saved with a ``.7z`` extension raise
      ``ExtractError(EXTRACT_BAD_ARCHIVE)``. Plus
      ``test_unsupported_format_raises`` covering the unknown-
      extension path,
      ``test_bomb_detected_when_expansion_exceeds_cap`` proving
      the FR-004a cap aborts cleanly with leftover files
      removed, and
      ``test_zip_with_path_traversal_member_raises`` rejecting
      ``../../etc/passwd``-style members before any bytes land.
- [ ] T030 [P] [EXTRACT] `tests/importer/steps/test_extract.py::test_preserve_archive_flag`
      — when ``preserve_archive=false`` the archive is deleted
      after a successful import; when ``true``, kept (FR-005).
      *(Deferred to the orchestrator slice — FR-005 is a
      lifecycle decision the orchestrator owns; ``extract``
      itself never touches the source archive.)*

### Implementation

- [X] T031 [EXTRACT] Create `src/romarr/importer/steps/extract.py` —
      async ``extract(*, archive_path, dest_dir, depth=0,
      max_depth=3) -> ExtractResult``. Three independent
      defenses:
        1. **Depth limit (FR-004)**: ``depth > max_depth`` =>
           ``ExtractError(EXTRACT_DEPTH_EXCEEDED)``.
        2. **Bomb defense (FR-004a)**: cumulative output capped
           at ``max(4 x compressed_size, 5 GiB)``, enforced
           **incrementally** on zip / rar via a 64 KB streaming
           writer; pre-validated against archive metadata for
           7z (py7zr's API doesn't expose per-byte streaming).
           Overrun => partial files cleaned up,
           ``ExtractError(EXTRACT_BOMB_DETECTED)``.
        3. **Idempotent skip (FR-006)**: sentinel file
           ``.romarr-extracted-from-<sha1[:16]>`` carries the
           source archive's SHA-1; a subsequent extract finds
           the sentinel and short-circuits.
      Path-traversal members are pre-rejected via ``_safe_join``
      before any bytes hit disk, regardless of format.
      Format-specific work runs inside ``asyncio.to_thread``.
      ``rarfile`` shells out to ``unrar`` / ``unar`` — production
      Docker images include the binary; tests skip when absent.

**Checkpoint**: EXTRACT tests green; the depth-3 limit holds; idempotent
re-extract skips.

---

## Phase 4: Hash (`HASH`) — Pipeline step 3

### Tests

- [X] T032 [P] [HASH] `tests/importer/steps/test_hash_step.py` —
      6 tests covering the walker: filters by extension (case-
      insensitive, leading-dot-tolerant), honours
      ``min_size_bytes`` floor (FR-008 small-file skip), recurses
      through nested directories, skips unknown extensions,
      ``FormatRule.normalised_extension`` round-trips both
      ``"md"`` and ``".MD"``.
- [X] T033 [P] [HASH] `tests/importer/steps/test_hash_step.py::test_uses_foundation_hasher`
      — output of ``hash_candidates`` matches a direct
      ``Hasher().hash_path`` call (sha1 / crc32 / md5 /
      size_bytes), proving the step delegates to spec 001's
      foundation Hasher rather than re-implementing.

### Implementation

- [X] T034 [HASH] Create `src/romarr/importer/steps/hash_step.py` —
      ``FormatRule(extension, min_size_bytes)`` value type plus
      async ``hash_candidates(*, directory, rules, hasher)
      -> dict[Path, HashResult]``. Walks ``directory.rglob("*")``
      sorted for determinism; hashes through
      ``asyncio.to_thread(hasher.hash_path, ...)`` so the event
      loop stays responsive during multi-MB CD images.

**Checkpoint**: HASH tests green; the small-file skip rule honours
`platform_format.min_size_bytes`.

---

## Phase 5: DAT match (`DATMATCH`) — Pipeline step 4

### Tests

- [X] T035 [P] [DATMATCH] `tests/importer/steps/test_dat_match.py::test_local_dat_hit_populates_verified_source_entry`
      — composes foundation's `HashMatchCascade`; the cascade
      winner's source / entry / VERIFIED status flow into the
      ``DatMatchResult`` (``dat_verified=True``, ``dat_source``
      populated, ``entry`` is the winner).
- [X] T036 [P] [DATMATCH] `tests/importer/steps/test_dat_match.py::test_no_dat_match_returns_unverified`
      — no entry on any backend ⇒ ``dat_verified=False`` /
      ``dump_status=UNKNOWN`` / ``entry=None`` (FR-011 — pipeline
      doesn't block). Plus
      ``test_backend_error_surfaces_in_status`` covering the
      circuit-open case.
- [X] T037 [P] [DATMATCH] `tests/importer/steps/test_dat_match.py::test_baddump_propagates_status_and_flips_verified`
      — DAT entry's ``status=BADDUMP`` propagates as
      ``dump_status=BADDUMP``; ``dat_verified`` flips to False
      so the audit row records the file as unverified (US5.3).

### Implementation

- [X] T038 [DATMATCH] Create `src/romarr/importer/steps/dat_match.py` —
      ``DatMatchResult`` (dat_verified, dat_source, entry,
      dump_status, backend_status) frozen dataclass. Async
      ``match_dat(*, cascade, platform_id, sha1) -> DatMatchResult``
      wraps ``cascade.lookup_sha1``. Lower-cases the SHA-1
      defensively. Surfaces the per-backend status dict so the
      audit row can show which backend(s) hit.

**Checkpoint**: DATMATCH tests green; "no DAT match" never blocks.

---

## Phase 6: Identify (`IDENTIFY`) — Pipeline step 5

### Tests

- [X] T039 [P] [IDENTIFY] `tests/importer/steps/test_identify.py::test_full_cascade_returns_identify_outcome`
      — composes foundation's ``Identifier.identify``; the
      resulting :class:`IdentifyOutcome` carries the merged
      identification + hashes. Without a configured cascade /
      parser dispatcher / header readers, every layer
      short-circuits cleanly; the wrapper itself proves the
      composition rather than the underlying cascade behaviour
      (which spec 001 owns).
- [X] T040 [P] [IDENTIFY] `tests/importer/steps/test_identify.py::test_with_grab_record_torznab_attrs`
      — Torznab extended attrs from a prior grab record are
      passed through; the merged identification preserves the
      contribution. Plus
      ``test_precomputed_hashes_bypasses_rehashing`` so the
      orchestrator's hash-once invariant holds (the HASH step's
      output is reused, not recomputed).

### Implementation

- [X] T041 [IDENTIFY] Create `src/romarr/importer/steps/identify.py` —
      async ``identify_file(*, identifier, path, platform_id,
      torznab_attrs, precomputed_hashes) -> IdentifyOutcome``.
      Always passes ``compute_hashes=False`` when
      ``precomputed_hashes`` is provided (the HASH step's result
      is canonical). ``platform_id=None`` skips the cascade so
      the orchestrator can route to GAMEMATCH for fuzzy
      resolution when the platform isn't yet known.

**Checkpoint**: IDENTIFY tests green; provenance preserved in the merge.

---

## Phase 7: Game match (`GAMEMATCH`) — Pipeline step 6

### Tests

- [X] T042 [P] [GAMEMATCH] `tests/importer/steps/test_game_match.py::test_exact_match_short_circuits`
      — case-insensitive exact title match against monitored Games
      short-circuits at confidence 1.0. The DAT-to-IGDB lookup
      lands when the cascade exposes IGDB IDs on
      ``RemoteHashEntry``; today the matcher consumes whichever
      titles the cascade + identifier produced (FR-013 — title
      authority is the canonical signal).
- [X] T043 [P] [GAMEMATCH] `tests/importer/steps/test_game_match.py::test_rapidfuzz_threshold_90_accepts_close_match`
      — typo'd title ``"Sonic the hedge hog"`` matches
      ``Sonic the Hedgehog`` at the 90 threshold (FR-014). Plus
      ``test_rapidfuzz_below_threshold_returns_no_match`` and
      ``test_threshold_can_be_relaxed_at_call_site`` proving the
      threshold is the gate.
- [X] T044 [P] [GAMEMATCH] `tests/importer/steps/test_game_match.py::test_fuzzy_tiebreak_lower_id_wins`
      — two candidates with the same fuzzy score ⇒ lower
      ``Game.id`` wins (FR-015 minimal version). The
      profile-region overlap tiebreak (full FR-015) lives in the
      orchestrator: it ranks the matcher's returned candidates
      using the preloaded library bindings.
- [X] T045 [P] [GAMEMATCH] `tests/importer/steps/test_game_match.py::test_unmatched_with_suggested_game`
      — no monitored match ⇒ retry against unmonitored Games at
      stricter 95 threshold; a hit populates
      ``suggested_game_id`` so the ``unidentified_dump`` row
      carries the operator-actionable hint (FR-016). Plus
      ``test_no_match_when_neither_pool_hits``,
      ``test_empty_titles_returns_no_match``, and 2 async DB-backed
      tests for the convenience wrapper.

### Implementation

- [X] T046 [GAMEMATCH] Create `src/romarr/importer/steps/game_match.py` —
      ``GameCandidate`` (id, title, sort_title, monitored) +
      ``GameMatchResult`` (game_id, confidence, signal,
      suggested_game_id, candidates_considered). Pure
      ``match_candidates(*, titles, monitored, unmonitored,
      monitored_threshold=90, suggested_threshold=95)`` runs
      exact → fuzzy → unmonitored-suggested in that order; ties
      resolved by lower id (sorted_pool insertion). Async
      ``match_to_game(...)`` wraps a DB query for callers that
      don't preload candidates. The pure core stays unit-testable
      in isolation.

  Slice produced one bug-fix on the multi-disc detector: the
  hypothesis property test caught a case where two files sharing
  the same prefix and disc number ([3, 3, 4]) violated the
  unique-disc-number invariant. Fixed by collapsing
  ``(prefix, disc_number) → first path`` so duplicate-disc paths
  become a single member.

**Checkpoint**: GAMEMATCH tests green; threshold 90 is stricter than
search engine's 85 (intentional asymmetry).

---

## Phase 8: Multi-disc (`MULTIDISC`) — Pipeline step 7

### Tests

- [X] T047 [P] [MULTIDISC] `tests/importer/steps/test_multi_disc.py::test_cue_bin_parent_child`
      — two cue/bin pairs ⇒ ``MultiDiscGroup(detection_signal='cue_bin')``
      with 2 members; each member ships both files; ``primary_file``
      is the ``.bin`` (FR-017, FR-018, FR-019). The
      orchestrator-level transition to ``parent_release_id`` is the
      DBUPDATE step's concern.
- [X] T048 [P] [MULTIDISC] `tests/importer/steps/test_multi_disc.py::test_filename_pattern_disc_n`
      — three ``Game (Disc N).iso`` files ⇒
      ``detection_signal='filename_pattern'`` with 3 members. Plus
      ``test_filename_pattern_single_disc_returns_none`` covering
      the single ``(Disc 1)`` no-siblings case (returns None; the
      orchestrator imports as a single-disc release).
- [X] T049 [P] [MULTIDISC] `tests/importer/steps/test_multi_disc.py::test_side_a_b_floppy`
      — ``(Side A)`` / ``(Side B)`` mapped to disc_number 1 / 2 with
      ``detection_signal='side_a_b'``.
- [X] T050 [P] [MULTIDISC] `tests/importer/steps/test_multi_disc.py::test_hash_the_bin_not_the_cue`
      — every member's ``primary_file`` is the ``.bin`` (FR-019).
      Plus 3 cue-parser tests: extracts referenced files, gracefully
      handles missing files, parses multi-track cues.
- [X] T051 [P] [MULTIDISC] `tests/importer/steps/test_multi_disc.py::test_property_random_disc_layouts_never_produce_invalid_trees`
      — hypothesis: 200 random combinations of disc-style and
      unrelated filenames; the detector never produces an invalid
      tree (members sorted by disc_number, no duplicate disc
      numbers, ≥ 2 members in any returned group). Plus
      ``test_irrelevant_files_dont_trigger_detection`` covering
      the no-disc-signal happy path.

### Implementation

- [X] T052 [MULTIDISC] Create `src/romarr/importer/steps/multi_disc.py`
      — pure ``detect_multi_disc(files) -> MultiDiscGroup | None``
      consuming a list of paths. Three detection signals (cue_bin
      > filename_pattern > side_a_b) tried in priority order;
      ``parse_cue_referenced_files(cue_path)`` exposed as a public
      helper. ``DiscMember`` carries ``files`` (every file
      constituting the member) and ``primary_file`` (the canonical
      bytestream the orchestrator hashes).

**Checkpoint**: MULTIDISC tests green; the property test runs 1000
random layouts without producing invalid trees.

---

## Phase 9: Profile gate (`PROFILEGATE`) — Pipeline step 8

### Tests

- [X] T053 [P] [PROFILEGATE] `tests/importer/steps/test_profile_gate.py`
      — 6 tests cover the spec 006 ``evaluate_all`` composition: all
      gates accept ⇒ passed; quality / region / dump / language each
      reject with their structured ``RejectionReason``; multi-gate
      rejection always surfaces the first failing gate in fixed
      Q→R→D→L order (deterministic across reruns).
- [X] T054 [P] [PROFILEGATE] `tests/importer/steps/test_profile_gate.py::test_force_overrides_rejection_into_warning`
      — ``force=True`` flips a rejection into a passing result with
      ``warning='force_overrode:<reason>'`` and the structured
      ``rejection_reason`` populated for the audit trail (FR-021,
      US4.2). Plus ``test_force_on_passing_gate_is_no_op`` so a
      force-import that wouldn't have been rejected anyway produces
      a clean pass without spurious warnings.

### Implementation

- [X] T055 [PROFILEGATE] Create
      `src/romarr/importer/steps/profile_gate.py` — pure
      ``apply_profile_gate(*, quality, region, dump, language,
      facts, force) -> ProfileGateResult`` composing spec 006's
      ``evaluate_all``. ``ProfileGateResult`` carries ``passed``,
      ``rejection_reason`` (always populated when a profile said
      NO), ``warning`` (force-pass only), and ``failing_gate``
      (deterministic via the fixed Q→R→D→L order).

**Checkpoint**: PROFILEGATE tests green; spec 006's evaluator wired with
no business-logic duplication.

---

## Phase 10: Render (`RENDER`) — Pipeline step 9

### Tests

- [X] T056 [P] [RENDER] `tests/importer/steps/test_render.py::test_uses_spec_006_engine`
      — composes ``NamingTemplateEngine.render(profile, game,
      release, dump, platform)``; the rendered basename + extension
      surface on :class:`RenderedDestination` for the MOVE step.
- [X] T057 [P] [RENDER] `tests/importer/steps/test_render.py::test_platform_subfolder_when_enabled`
      — rendered path begins with
      ``<library_root>/<platform_slug>/...`` when the Naming
      profile's ``platform_subfolder=True``. Plus the symmetric
      ``test_no_platform_subfolder_when_disabled``.
- [X] T058 [P] [RENDER] `tests/importer/steps/test_render.py::test_multi_disc_subfolder_groups_discs`
      — for multi-disc games with ``multi_disc_subfolder=True`` and
      ``multi_disc_total > 1``, both discs land in
      ``<library_root>/<platform_slug>/<game_subfolder>/``. Plus
      ``test_no_multi_disc_subfolder_for_single_disc`` (no spurious
      grouping when ``multi_disc_total == 1``) and
      ``test_render_is_deterministic`` (purity).

### Implementation

- [X] T059 [RENDER] Create `src/romarr/importer/steps/render.py` —
      pure ``render_destination(*, engine, profile, library_root,
      game, release, dump, platform, multi_disc_total)
      -> RenderedDestination`` composing spec 006's engine. Path
      composition: ``library_root [/ platform_slug [/ game_subfolder]]
      / basename.ext``. ``_safe_dirname`` sanitises the multi-disc
      subfolder name (built outside the engine).

**Checkpoint**: RENDER tests green; rendered paths are deterministic
across reruns.

---

## Phase 11: Move (`MOVE`) — Pipeline step 10

**Purpose**: the riskiest piece. Hardlink-first atomic mover with cross-fs
fallback, idempotency-by-SHA-1, and fault-injection resilience.

### Tests

- [X] T060 [P] [MOVE] `tests/importer/steps/test_move.py::test_same_fs_hardlink`
      — same-fs ``os.link`` ⇒ ``MoveResult(used_hardlink=True,
      coalesced=False, bytes_copied=0)``; source and dest share an
      inode (Constitution Article XII; SC-003).
- [X] T061 [P] [MOVE] `tests/importer/steps/test_move.py::test_cross_fs_fallback_copy_verify`
      — monkeypatch ``os.link`` to raise ``EXDEV``; the mover falls
      back to ``shutil.copy2`` (mtime preserved) + SHA-1 verify +
      ``os.replace``. ``MoveResult.bytes_copied`` reports the
      copied size; no leftover ``.tmp`` (FR-024, US2.1).
- [X] T062 [P] [MOVE] `tests/importer/steps/test_move.py::test_copy_hash_mismatch_keeps_source`
      — corrupt the copy after ``shutil.copy2``; ``move_atomic``
      raises ``MoveError(rejection_reason=
      MOVE_HASH_MISMATCH)``; source survives untouched, no
      partial dest, no ``.tmp`` artefact (US2.2).
- [X] T063 [P] [MOVE] `tests/importer/steps/test_move.py::test_existing_dest_matching_sha1_coalesces`
      — destination already exists with matching SHA-1 ⇒
      ``MoveResult(coalesced=True)``; both files preserved
      (FR-025, SC-002).
- [X] T064 [P] [MOVE] `tests/importer/steps/test_move.py::test_existing_dest_mismatching_sha1_no_force_raises`
      — dest exists with different SHA-1 and ``force=False`` ⇒
      ``MoveError(rejection_reason=DESTINATION_COLLISION)``; both
      files survive (FR-026). Plus
      ``test_existing_dest_mismatching_sha1_with_force_overwrites``
      proving ``force=True`` overwrites cleanly.
- [X] T065 [P] [MOVE] `tests/importer/steps/test_move.py::test_crash_mid_copy_no_partial_dest`
      — monkeypatch ``shutil.copy2`` to raise ``OSError(EIO)``
      mid-write; assert no file at the canonical destination, no
      ``.tmp`` artefact left, source preserved (SC-009).
- [X] T066 [P] [MOVE] `tests/importer/steps/test_move.py::test_disk_full_preserves_source`
      — simulate ``OSError(ENOSPC)`` ⇒
      ``MoveError(rejection_reason=MOVE_DISK_FULL)``; source
      preserved. Plus
      ``test_permission_denied_maps_to_permission_error`` so
      ``EACCES`` / ``EPERM`` map to the right structured reason.
      (``OnHealthIssue`` emission lives in spec 011's notification
      consumer.)

### Implementation

- [X] T067 [MOVE] Create `src/romarr/importer/steps/move.py` — async
      ``move_atomic(*, source, dest, expected_sha1, force=False)
      -> MoveResult``. Strict ordering:
        1. Idempotent check: dest exists with matching sha1 ⇒
           coalesced no-op.
        2. Collision check: dest exists with different sha1 ⇒
           MoveError(DESTINATION_COLLISION) when force=False;
           overwrite when force=True.
        3. Hardlink attempt via ``os.link`` (in
           ``asyncio.to_thread``). EXDEV ⇒ step 4. Other
           OSError wraps to MoveError with the right rejection
           reason (ENOSPC → MOVE_DISK_FULL,
           EACCES/EPERM → MOVE_PERMISSION_ERROR, default →
           MOVE_FAILED).
        4. Cross-fs: ``shutil.copy2`` source → dest.tmp; verify
           SHA-1 (``Hasher().hash_path(dest.tmp).sha1``);
           mismatch ⇒ unlink + raise. The copy uses sync
           ``shutil.copy2`` inside ``asyncio.to_thread`` rather
           than aiofiles because aiofiles' streaming benefits
           don't apply to a one-shot copy and the synchronous
           path is simpler to reason about.
        5. ``os.replace(dest.tmp, dest)`` atomic rename.
      Source deletion (``move_and_remove`` lifecycle policy)
      lives with the LIFECYCLE step — this step focuses on
      landing dest correctly.

**Checkpoint**: every MOVE test green; the fault-injection suite passes
in 100% of trials (SC-009).

---

## Phase 12: DB update (`DBUPDATE`) — Pipeline step 11

### Tests

- [X] T068 [P] [DBUPDATE] `tests/importer/steps/test_db_update.py::test_creates_dump_with_all_hashes`
      — Dump row carries CRC32 / MD5 / SHA-1 / size_bytes / format /
      path / original_filename / dat_verified / dat_source /
      imported_at / imported_via / imported_by (FR-027).
- [X] T069 [P] [DBUPDATE] `tests/importer/steps/test_db_update.py::test_release_status_flips_to_imported`
      — ``Release.status`` flips from ``wanted`` to ``imported``
      after a successful import; ``cutoff_met`` clears so the
      search engine re-evaluates against the current Quality
      profile.
- [X] T070 [P] [DBUPDATE] `tests/importer/steps/test_db_update.py::test_keep_dump_history_false_replaces_old_dump`
      — ``keep_dump_history=False``; the prior Dump row for the
      same Release is deleted by the same transaction so only
      the fresh Dump survives (FR-028). On-disk file deletion
      lives with the LIFECYCLE step when the lifecycle policy
      requires it; this step focuses on DB state.
- [X] T071 [P] [DBUPDATE] `tests/importer/steps/test_db_update.py::test_keep_dump_history_true_appends`
      — ``keep_dump_history=True``; both Dumps coexist on the
      Release (the historical one + the fresh one).

### Implementation

- [X] T072 [DBUPDATE] Create `src/romarr/importer/steps/db_update.py` —
      async ``persist_dump(*, session, release_id, dump_path,
      original_filename, hashes, file_format, dat_verified,
      dat_source, dat_entry_id, imported_via, imported_by,
      keep_dump_history) -> Dump``. Steps in order: retire prior
      Dumps when history is disabled, insert the fresh Dump,
      transition Release status. ``await session.flush()``
      populates ``Dump.id`` so the caller can record it on the
      audit row; the orchestrator owns the commit so the whole
      pipeline lands in a single transaction.

**Checkpoint**: DBUPDATE tests green; the keep-history toggle works both
ways.

---

## Phase 13: Lifecycle (`LIFECYCLE`) — Pipeline step 12

### Tests

- [X] T073 [P] [LIFECYCLE] `tests/importer/steps/test_lifecycle.py::test_tag_imported_tags_only`
      — tags the download via ``client.set_imported_tag``;
      ``apply_lifecycle`` returns ``None`` (no scheduled task);
      no remove is called (FR-029, hardlink_and_seed policy).
- [X] T074 [P] [LIFECYCLE] `tests/importer/steps/test_lifecycle.py::test_schedule_remove_fires_after_grace`
      — tags synchronously, returns an :class:`asyncio.Task` that
      sleeps the grace window then calls
      ``client.remove(native_id, delete_files=True)``. Test uses
      a 50 ms grace + ``await task`` rather than freezegun
      because asyncio.sleep doesn't honour frozen clocks.
- [X] T075 [P] [LIFECYCLE] `tests/importer/steps/test_lifecycle.py::test_noop_neither_tags_nor_removes`
      — copy_and_keep policy maps to ``LifecycleAction(kind="noop")``;
      neither tag nor remove fires.
- [X] T076 [P] [LIFECYCLE] `tests/importer/steps/test_lifecycle.py::test_schedule_remove_does_not_block_completion`
      — FR-030: ``apply_lifecycle`` with a 10 s grace window
      returns in < 1 s; the scheduled task carries the work
      asynchronously so the orchestrator publishes
      ``ImportOutcome`` before the removal fires. Plus
      ``test_unknown_action_kind_raises`` so an unhandled kind
      surfaces a ``ValueError`` rather than silently noop'ing.

### Implementation

- [X] T077 [LIFECYCLE] Create `src/romarr/importer/steps/lifecycle.py`
      — async ``apply_lifecycle(*, action, client, grace_seconds)
      -> asyncio.Task | None`` that dispatches the
      :class:`LifecycleAction`'s kind. Both ``tag_imported`` and
      ``schedule_remove`` start by tagging via
      ``client.set_imported_tag``; ``schedule_remove`` then spawns
      a fire-and-forget ``asyncio.create_task`` that sleeps the
      grace window before calling ``client.remove(native_id,
      delete_files=True)``. The Task is returned so tests can
      ``await`` it; production callers never await — the task
      lives until the grace window completes or the loop shuts
      down.

**Checkpoint**: LIFECYCLE tests green; the 5-minute grace is honoured.

---

## Phase 14: Notify (`NOTIFY`) — Pipeline step 13

### Tests

- [X] T078 [P] [NOTIFY] `tests/importer/steps/test_notify.py::test_on_import_emitted_on_success`
      — successful import emits an ``OnImport`` event on the
      in-process pub/sub channel (FR-031). Plus
      ``test_on_import_carries_coalesced_and_warning`` proving
      the payload threads coalesced + warning fields so the
      consumer can render "5 callers, 1 imported, 4 coalesced"-
      style notifications.
- [X] T079 [P] [NOTIFY] `tests/importer/steps/test_notify.py::test_on_upgrade_emitted_in_addition_to_on_import`
      — import with ``upgraded_from_dump_id`` set emits BOTH
      ``OnImport`` and ``OnUpgrade`` (FR-032). Plus
      ``test_on_upgrade_not_emitted_when_no_prior_dump`` so
      first-time imports stay quiet on the upgrade channel.

### Implementation

- [X] T080 [NOTIFY] Create `src/romarr/importer/steps/notify.py` —
      ``ImporterEventBus`` (in-process pub/sub) +
      ``OnImportEvent`` / ``OnUpgradeEvent`` frozen value types +
      async ``emit_import_events(*, bus, correlation_id,
      library_id, game_id, release_id, dump_id, dump_path,
      imported_via, coalesced, warning, upgraded_from_dump_id)``.
      The bus dispatches sequentially and propagates subscriber
      failures (no swallowing — silent failures hide real
      notification bugs). Plus 3 mechanic tests covering multiple
      subscribers, no-subscribers no-op, and subscriber-failure
      propagation. Spec 011's notification subsystem will
      register the actual Apprise / WebSocket / library-exporter
      consumers on top of this primitive.

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
