---

description: "Granular task list for platform-packs — YAML schema, transactional ingest, built-in pack, user overrides, API"
---

# Tasks: Platform Packs

**Input**: Design documents from `specs/003-platform-packs/`
**Prerequisites**: `001-foundation` shipped (Platform, PlatformFormat, PlatformNamingToken,
platform_pack with `pack_source` / `pack_version` / `contents_hash`)
**Tests**: MANDATORY (Constitution Article XVI; SC-007: ≥ 80% on platform_packs/)

**Organization**: 8 phases. Scaffolding → persistence → validator → ingestor → built-in /
first-boot → user overrides → API → hardening.

## Format: `[ID] [P?] [Phase] Description`

- `[P]` = parallelizable with other `[P]` tasks in the same phase.
- Phase tag short codes: `SCAF`, `PERS`, `VALID`, `INGEST`, `BUILTIN`, `OVR`, `API`, `HARD`.

---

## Phase 1: Scaffolding (`SCAF`)

**Purpose**: bring up the module skeleton, dependencies, and shared types.

- [X] T001 [SCAF] Updated `pyproject.toml` — added `PyYAML>=6.0`, `jsonschema>=4.21`.
- [X] T002 [P] [SCAF] Created `src/romarr/platform_packs/__init__.py` —
      currently re-exports the validator + types + errors. Ingest /
      built-in / overrides land in follow-up slices.
- [X] T003 [P] [SCAF] Created `src/romarr/platform_packs/types.py` —
      `PackPlatformDiff`, `PackUploadResult`, `ValidateResult`.
- [X] T004 [P] [SCAF] Created `src/romarr/platform_packs/errors.py` —
      `PackValidationError` (with structured `violations: list[Violation]`),
      `SchemaVersionTooHighError`, `PackVersionConflictError`, `OverrideRequiredError`.
- [ ] T005 [SCAF] Extend `src/romarr/config/settings.py` with
      `builtin_pack_path: Path | None`. **Deferred** to the BUILTIN
      slice — adding a settings field for a feature whose runtime
      doesn't ship yet would just dangle.
- [X] T006 [SCAF] Created `tests/platform_packs/conftest.py` with the
      `pack_yaml` fixture that loads files from
      `tests/fixtures/packs/`.

**Checkpoint**: imports work, lint+types green; no behaviour added yet.

---

## Phase 2: Persistence (`PERS`)

**Purpose**: 2 new tables + Alembic migration + SQLAlchemy models + Pydantic schemas.

### Tests (write first; must fail)

- [X] T007 [P] [PERS] `tests/platform_packs/test_migration_0003.py` —
      applies the migration end-to-end against a fresh SQLite DB,
      asserts both new tables exist + the CHECK constraint on
      `parsing_strategies.pack_source` fires; idempotency test
      via downgrade + re-upgrade.
- [X] T008 [P] [PERS] `tests/platform_packs/test_models.py` —
      round-trip both new model rows through the async session;
      JSON list columns + the FK on platform_pack_application_log
      both round-trip.

### Implementation

- [X] T009 [PERS] Created `src/romarr/platform_packs/models.py` —
      `ParsingStrategy` and `PlatformPackApplicationLog` SQLAlchemy 2.0
      models matching `data-model.md`. CHECK constraints on
      `pack_source`, `action`, `status`. FK on
      `platform_pack_application_log.pack_version` →
      `platform_pack.pack_version`.
- [ ] T010 [P] [PERS] Create `src/romarr/platform_packs/schemas.py` —
      Pydantic *Read/*Create/*Update for the new entities. **Deferred**
      to the API slice — schemas aren't consumed until the routers land.
- [X] T011 [PERS] Authored `src/romarr/db/alembic/versions/0003_platform_packs.py`
      — DDL for the two tables. The defensive
      `ADD COLUMN IF NOT EXISTS contents_hash` was unnecessary —
      foundation 0001 ships the column.

**Checkpoint**: `alembic upgrade head` applies cleanly; PERS tests green.

---

## Phase 3: YAML Loading & Validation (`VALID`)

**Purpose**: PyYAML loader + JSON Schema validator + cross-reference checks. The
validator is a **pure function** consumed by both upload and validate-only flows.

### Tests

- [X] T012 [P] [VALID] `tests/platform_packs/test_yaml_loader.py` —
      `load_pack` parses + 1 MiB body cap; `canonicalize` is stable
      across YAML cosmetic edits + key reorderings;
      `compute_contents_hash` returns 64-char SHA-256 hex.
- [X] T013 [P] [VALID] `tests/platform_packs/test_validator_schema.py`
      — iterates **22** broken-pack fixtures under
      `tests/fixtures/packs/invalid_schema/`; each yields a
      `PackValidationError`. Includes `test_at_least_twenty_invalid_schema_fixtures_exist`
      to pin SC-004's ≥ 20 corpus bar.
- [X] T014 [P] [VALID] `tests/platform_packs/test_validator_cross_refs.py::test_dangling_parent_rejected`
      — fixture `invalid_refs/dangling_parent.yaml` raises naming the
      bad slug in the violation message; the existing-slugs override
      pass is exercised in
      `test_dangling_parent_satisfied_by_existing_db_slug`.
- [X] T015 [P] [VALID] `tests/platform_packs/test_validator_cross_refs.py::test_cycle_a_b_*`
      — both 2-cycle and 3-cycle fixtures raise with messages that
      name every cycle member.
- [X] T016 [P] [VALID] `tests/platform_packs/test_validator_cross_refs.py::test_duplicate_slug_rejected`.
- [X] T017 [P] [VALID] `tests/platform_packs/test_validator_cross_refs.py::test_duplicate_extension_rejected`.
- [X] T018 [P] [VALID] `tests/platform_packs/test_validator_schema.py::test_schema_version_too_high_raises_specific_error`.

### Implementation

- [X] T019 [VALID] Created `src/romarr/platform_packs/yaml_loader.py` —
      `load_pack` (SafeLoader + 1 MiB cap), `canonicalize`,
      `compute_contents_hash`.
- [X] T020 [VALID] Created `src/romarr/platform_packs/schema.py` — JSON
      Schema dict constant + lazy-cached `Draft202012Validator`.
- [X] T021 [VALID] Created `src/romarr/platform_packs/validator.py` —
      `validate_pack_structure`, `validate_cross_refs` (duplicates +
      dangling + cycles + adversarial-regex check), `validate_pack`
      orchestration. **Note on adversarial-regex check**: per FR-005a
      the check was specified as a 50-ms wall-clock bound. Python's
      ``re`` module does not release the GIL during a match, so a
      thread-based timeout cannot reliably interrupt a doomed regex.
      Switched to a static-pattern danger heuristic that rejects
      nested-quantifier shapes (``(a+)+``, ``(a*)*``, ``(a|aa)+``,
      etc.) at validation time. The wire-stable error code
      ``regex_timeout`` is preserved so the API layer doesn't need
      to change. A v1+ slice can re-enable the wall-clock bound by
      moving to multiprocessing or the third-party ``regex`` library.

**Checkpoint**: validator tests green including the ≥ 20 broken-pack corpus
(SC-004 entry); validator is pure and importable from a REPL without a DB.

---

## Phase 4: Transactional Ingest (`INGEST`)

**Purpose**: turn a validated pack into a single SQL transaction. Implements
the per-platform rules from FR-011, FR-012, FR-013, the parsing-strategies
upsert from FR-014, and the audit-log entries from FR-023, FR-024.

### Tests

- [ ] T022 [P] [INGEST] `tests/platform_packs/test_ingestor_idempotency.py::test_unchanged_pack_no_writes`
      — apply pack; capture every `updated_at` on platform/format/token rows;
      re-apply the same YAML; assert no row was touched and one
      `application_log` row exists with `action = 'skipped'` (FR-009, SC-002).
- [ ] T023 [P] [INGEST] `tests/platform_packs/test_ingestor_idempotency.py::test_version_conflict`
      — apply pack version V; modify YAML body; re-upload with the same V;
      assert `PackVersionConflictError` raised (FR-010).
- [ ] T024 [P] [INGEST] `tests/platform_packs/test_ingestor_per_platform_rules.py::test_insert_new`
      — pack adds a slug not in DB; assert platform + formats + tokens inserted
      with `pack_source` matching the pack's origin (FR-011).
- [ ] T025 [P] [INGEST] `tests/platform_packs/test_ingestor_per_platform_rules.py::test_update_existing`
      — pack defines an existing `pack_source != 'user'` slug with new fields
      and a different format set; assert mutable fields updated, formats and
      naming tokens fully replaced (FR-013).
- [ ] T026 [P] [INGEST] `tests/platform_packs/test_ingestor_per_platform_rules.py::test_skip_user_overridden`
      — slug exists with `pack_source = 'user'`; assert pack apply leaves
      every row untouched and the audit log records the slug as `skipped`
      (FR-012, SC-003).
- [ ] T027 [P] [INGEST] `tests/platform_packs/test_ingestor_parsing_strategies.py`
      — pack with `parsing_strategies` list; assert rows inserted/replaced;
      a strategy with `pack_source = 'user'` is preserved.
- [ ] T028 [P] [INGEST] `tests/platform_packs/test_ingestor_transactional.py`
      — inject a failure mid-ingest (e.g., monkeypatch a model `flush` to
      raise); assert the entire transaction rolled back, the audit-log row
      records `status = 'failed'` with the captured error message, and the
      database is byte-for-byte identical to the pre-application state
      (SC-006, FR-007, FR-024).
- [ ] T029 [P] [INGEST] `tests/platform_packs/test_ingestor_diff.py` — apply a
      pack to a populated DB; assert the returned `PackUploadResult.diff`
      lists each platform with the right action and `fields_changed`.

### Implementation

- [ ] T030 [INGEST] Create `src/romarr/platform_packs/diff.py` — pure
      `compute_diff(parsed: ParsedPack, current_state: PlatformSnapshot) -> list[PackPlatformDiff]`.
- [ ] T031 [INGEST] Create `src/romarr/platform_packs/audit.py` — async
      helpers `start_log(...)`, `complete_log(...)`, `fail_log(...)` that
      manage the application-log lifecycle.
- [ ] T032 [INGEST] Create `src/romarr/platform_packs/ingestor.py` — the
      pipeline:
      1. parse + validate (Phase 3 helpers).
      2. compute diff against current DB state.
      3. short-circuit if `(pack_version, contents_hash)` already in
         `platform_pack` → emit `skipped` audit row, return.
      4. raise `PackVersionConflictError` if `pack_version` exists but
         `contents_hash` differs.
      5. open a single SQLAlchemy `async with session.begin():` block.
      6. for each platform: apply FR-011 / FR-012 / FR-013.
      7. for each parsing strategy: apply FR-014.
      8. insert one `platform_pack` row.
      9. complete the audit-log row (`status = 'success'`,
         `action = 'applied' | 'reapplied'`).
      10. on any exception: capture, fail the audit-log row outside the
          transaction (separate session), re-raise.

**Checkpoint**: every INGEST test green; the ingestor passes both the
idempotency and the transactional-rollback gates from the spec.

---

## Phase 5: Built-in Pack & First-Boot (`BUILTIN`)

**Purpose**: ship the YAML, resolve its path on disk, auto-apply on first boot.

### Tests

- [ ] T033 [P] [BUILTIN] `tests/platform_packs/test_builtin_first_boot.py::test_empty_db_applies_pack`
      — start the application against an empty DB; assert the built-in pack
      ends up in `platform_pack` and approximately 20 platforms exist with
      `pack_source = 'builtin'`; assert total elapsed under 5 s (SC-001).
- [ ] T034 [P] [BUILTIN] `tests/platform_packs/test_builtin_first_boot.py::test_already_applied_no_ops`
      — pre-seed `platform_pack` with the built-in version + contents_hash;
      start the application; assert no platform writes occurred.
- [ ] T035 [P] [BUILTIN] `tests/platform_packs/test_builtin_first_boot.py::test_missing_file_warns_does_not_crash`
      — point `ROMARR_BUILTIN_PACK_PATH` at a nonexistent file; start the
      application; assert it boots, logs a structured warning, and no rows
      are written (FR-019).
- [ ] T036 [BUILTIN] Author the YAML at
      `src/romarr/builtin_packs/builtin-2026.04.001.yaml` with the documented
      ~20 platforms (cartridges nes/snes/megadrive/master-system/gameboy/gbc/gba/n64/atari-2600/atari-7800;
      disc-based psx/saturn/dreamcast/gamecube/wii/pce-cd; handheld modern
      nds/3ds/psp; modern ps2). Each platform with proper IGDB and
      ScreenScraper IDs, primary format extension, and a sensible parser
      strategy reference where applicable.

### Implementation

- [ ] T037 [BUILTIN] Create `src/romarr/platform_packs/builtin.py` —
      `resolve_builtin_pack_path() -> Path | None` (env var → wheel resource →
      `/opt/romarr/builtin-packs/`); `apply_builtin_pack(session) -> None`
      that calls into `ingestor.ingest_pack` with `applied_by='system'` and
      origin `'builtin'`.
- [ ] T038 [BUILTIN] Wire `apply_builtin_pack(session)` into the application
      bootstrap (the FastAPI lifespan startup or its package-level equivalent
      — exact wiring formalized in the API spec, but the call point lives
      here and is exercised by an integration test).

**Checkpoint**: first-boot tests green; the YAML lints clean against the
JSON Schema (a tiny CI smoke-test runs `validate_pack_structure` on the
built-in YAML at every CI run).

---

## Phase 6: User Overrides (`OVR`)

**Purpose**: mark/release override + format-CRUD endpoints' write rules.

### Tests

- [ ] T039 [P] [OVR] `tests/platform_packs/test_override.py::test_mark_overridden_cascades`
      — mark a platform overridden; assert the platform row, every format,
      and every naming token of that platform have `pack_source = 'user'`
      (FR-020).
- [ ] T040 [P] [OVR] `tests/platform_packs/test_override.py::test_release_override`
      — release the override on a platform that was overridden by the
      operator; assert `pack_source` reverts to the value of the most-recent
      pack that touched the row (`'builtin'` or `'community'`); subsequent
      pack apply now updates it.
- [ ] T041 [P] [OVR] `tests/platform_packs/test_override.py::test_user_format_protected`
      — overridden platform; add a format via the helper; assert the new
      format has `pack_source = 'user'`; apply a pack that defines a different
      format set for the same slug; assert the user-added format is preserved
      (because the platform is user-overridden, FR-012 short-circuits the
      whole platform).
- [ ] T042 [P] [OVR] `tests/platform_packs/test_override.py::test_format_mutation_requires_override`
      — attempt to add a format on a platform with `pack_source != 'user'`;
      assert `OverrideRequiredError` raised (FR-026).

### Implementation

- [ ] T043 [OVR] Create `src/romarr/platform_packs/override.py` —
      `mark_overridden(session, platform_id) -> None` (cascades pack_source on
      formats and tokens), `release_override(session, platform_id) -> None`
      (resets pack_source on formats/tokens to the parent platform's
      restored pack_source).
- [ ] T044 [OVR] Add format-mutation helpers
      `add_format(session, platform_id, format_data)`,
      `update_format(...)`, `delete_format(...)` that enforce the
      "platform must be user-overridden" precondition.

**Checkpoint**: overrides tests green; the user-wins invariant is exercised
end-to-end against a full pack apply.

---

## Phase 7: API Stubs (`API`)

**Purpose**: wire the documented endpoints; full payload schemas land in the
API spec but the stubs must be functional.

### Tests

- [ ] T045 [P] [API] `tests/platform_packs/api/test_pack_endpoints.py::test_upload_valid`
      — multipart POST a valid YAML; assert HTTP 200 with a
      `PackUploadResult`; DB rows materialized.
- [ ] T046 [P] [API] `tests/platform_packs/api/test_pack_endpoints.py::test_upload_bad_yaml`
      — POST malformed YAML; assert HTTP 400 with parse-error details.
- [ ] T047 [P] [API] `tests/platform_packs/api/test_pack_endpoints.py::test_upload_schema_violation`
      — POST a pack missing `pack_version`; assert HTTP 400 with the JSON
      path of the violation.
- [ ] T048 [P] [API] `tests/platform_packs/api/test_pack_endpoints.py::test_upload_cycle`
      — POST a pack with cycling `parent_platform_slug`; assert HTTP 400
      "cycle detected" naming the cycle.
- [ ] T049 [P] [API] `tests/platform_packs/api/test_pack_endpoints.py::test_validate_only_no_writes`
      — POST to `/validate`; capture row counts before/after; assert
      `database_state_unchanged = true` and counts identical.
- [ ] T050 [P] [API] `tests/platform_packs/api/test_pack_endpoints.py::test_list_and_detail`
      — apply two packs over time; assert `GET /api/v3/rom/platform-pack`
      lists both ordered most recent first; assert
      `GET /api/v3/rom/platform-pack/{version}` returns the right detail.
- [ ] T051 [P] [API] `tests/platform_packs/api/test_pack_endpoints.py::test_reapply_known_pack`
      — apply pack V; mutate platform manually; POST to
      `/api/v3/rom/platform-pack/{V}/apply`; assert the platform reverts to
      pack defaults (and the platform was NOT user-overridden — that
      situation is covered by the override test).
- [ ] T052 [P] [API] `tests/platform_packs/api/test_override_endpoints.py` —
      POST/DELETE `/override` round-trip.
- [ ] T053 [P] [API] `tests/platform_packs/api/test_format_endpoints.py` —
      list/add/edit/delete formats; mutation against a non-overridden
      platform returns HTTP 409.

### Implementation

- [ ] T054 [API] Create `src/romarr/platform_packs/api/packs.py` — FastAPI
      router with the 5 pack endpoints (upload, list, detail, re-apply,
      validate). The upload endpoint accepts a `multipart/form-data` file;
      the validate endpoint accepts the same body but never opens a write
      transaction.
- [ ] T055 [API] Create `src/romarr/platform_packs/api/platforms.py` —
      FastAPI router with override + format-CRUD endpoints. All format
      mutation endpoints check the platform's `pack_source` and return
      HTTP 409 if not `'user'`.
- [ ] T056 [API] Wire both routers under `/api/v3/rom/` in the application
      factory. Authentication wiring continues to use the development-only
      no-op admin dependency until the Auth spec lands.

**Checkpoint**: every documented endpoint exercised; HTTP error codes match
the spec; happy-path response shapes match the Pydantic models in
`schemas.py`.

---

## Phase 8: Hardening (`HARD`)

- [ ] T057 [HARD] Run `pytest --cov=romarr.platform_packs` — verify ≥ 80%
      coverage (SC-007). Add targeted tests for any uncovered branch.
- [ ] T058 [HARD] Run `ruff check .` — zero warnings on
      `src/romarr/platform_packs/`.
- [ ] T059 [HARD] Add a CI smoke test that runs `validate_pack_structure` on
      `src/romarr/builtin_packs/builtin-2026.04.001.yaml` so a typo in the
      shipped pack fails the build instead of slipping into a release.
- [ ] T060 [HARD] Add a property-based test (hypothesis) that generates random
      directed graphs over a fixed slug pool and asserts the validator's
      cycle detector matches a reference graph algorithm (sanity check on
      the DFS implementation).
- [ ] T061 [HARD] Update `pyproject.toml` `version = "0.3.0a1"`; add a
      one-line note to `CHANGELOG.md`: "0.3.0a1 — Platform Packs:
      transactional ingest, built-in pack, user overrides, full API surface."
- [ ] T062 [HARD] Final review: open `specs/003-platform-packs/spec.md`
      and tick every Functional Requirement (FR-001 → FR-026) against a
      task ID; record any gaps as follow-up items.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (SCAF)**: foundation merged.
- **Phase 2 (PERS)**: depends on Phase 1.
- **Phase 3 (VALID)**: depends on Phase 1 only — pure functions, no DB.
- **Phase 4 (INGEST)**: depends on Phases 2 and 3.
- **Phase 5 (BUILTIN)**: depends on Phase 4.
- **Phase 6 (OVR)**: depends on Phase 2 (writes platform/format rows). Can
  start in parallel with Phase 5.
- **Phase 7 (API)**: depends on Phases 4, 5, 6.
- **Phase 8 (HARD)**: depends on Phase 7.

### Within-Phase Parallelism

- Phase 1: T002–T004 in parallel.
- Phase 2: T007–T008 in parallel; T009 + T010 in parallel.
- Phase 3: T012–T018 (test fixtures + tests) in parallel; the validator
  implementation tasks (T019–T021) are sequential because they layer.
- Phase 4: T022–T029 in parallel; T030–T031 in parallel; T032 last.
- Phase 5: T033–T035 in parallel; T036 (the YAML itself) parallel with the
  tests; T037–T038 sequential.
- Phase 6: T039–T042 in parallel; T043–T044 sequential.
- Phase 7: T045–T053 in parallel; T054–T055 in parallel; T056 last.

### Critical Path

`SCAF → PERS → VALID → INGEST → BUILTIN → API → HARD`. The OVR phase runs in
parallel with BUILTIN once PERS is done.

### Implementation Strategy

- **Day 1**: Phases 1–2 (scaffolding + persistence + migration).
- **Day 2**: Phase 3 (validator) — pure functions, fast iteration.
- **Day 3–4**: Phase 4 (transactional ingest) — the heart of the feature;
  invest the most testing effort here.
- **Day 5**: Phase 5 (built-in pack + first-boot wiring) and Phase 6
  (overrides) in parallel.
- **Day 6**: Phase 7 (API stubs).
- **Day 7**: Phase 8 (hardening).

This sizing assumes one developer working full-time. With multiple
contributors, Phases 5 and 6 split cleanly across two people.

---

## Notes

- `[P]` tasks change different files only.
- Tests are written BEFORE implementation in every phase.
- Stop at any phase checkpoint — the platform-pack layer is delivered
  incrementally; each phase is independently shippable.
- Avoid: implementing community-pack-via-Git (deferred to v1+); pack
  signing (v2); pack-diff UI (UI spec); platform deletion (out of scope);
  `schema_version = 0` migration (we start at 1).
- Constitutional invariant under test (SC-003): user-overridden platforms
  survive every pack apply unchanged. The dedicated test in T026 + the
  cascade test in T039 + T041 form the three-prong defence of this rule.

## Phase: Clarification Tasks (Session 2026-04-29)

- [ ] CL001 [P] [US2] Implement adversarial-input regex validator in `src/romarr/platform_packs/validation/regex_safety.py` — compile + 256-byte adversarial test on a worker thread with a 50 ms wall-clock budget; reject pack with HTTP 400 + offending JSON path on overrun (FR-005a)
- [ ] CL002 [P] [US2] Configure `yaml.SafeLoader` (refuse default unsafe loader) in `src/romarr/platform_packs/loader.py` (FR-001a)
- [ ] CL003 [P] [US2] Add 1 MiB request body cap in `src/romarr/platform_packs/api.py` — return HTTP 413 with structured size-limit error before YAML parsing (FR-001b)
- [ ] CL004 [P] [US2] Add 200-platform-per-pack cap in the same handler — return HTTP 400 with platform-count error (FR-001c)
- [ ] CL005 [US4] Implement `pack_version`-order downgrade rejection in `src/romarr/platform_packs/applier.py` — return HTTP 409 with structured "downgrade rejected" + offending slug list when incoming `pack_version` is older than the recorded version on any non-`user` platform (FR-013a)
- [ ] CL006 Migration `0003_platform_packs.py` creates `parsing_strategies` table with columns `(id PK, name, pattern, apply_to_platforms JSON, pack_version, created_at, updated_at)` per spec 003 data-model.md delta (FR-014a)
- [ ] CL007 [P] [Admin] Wire admin-role gate on every mutating pack endpoint in `src/romarr/platform_packs/api.py` (`/upload`, `/{version}/apply`, `/validate`, `/platform/{id}/override` set/release, format CRUD); reads stay open to any authenticated user (FR-026a)
- [ ] CL008 [P] Add tests in `tests/platform_packs/test_regex_safety.py` covering: clean regex passes; catastrophic-backtracking pattern rejected; compile error rejected; multiple regexes one slow → pack rejected with the offending JSON path
- [ ] CL009 [P] Add tests in `tests/platform_packs/test_downgrade_rejection.py` covering: equal version (idempotent); higher version (accepted); lower version on any slug (rejected with HTTP 409); user-overridden slug excluded from the comparison
- [ ] CL010 [P] Add fixture in `tests/platform_packs/fixtures/zip_bomb.yaml` and `tests/platform_packs/fixtures/yaml_python_object_apply.yaml` — confirm both rejected by SafeLoader / size cap before any DB write
