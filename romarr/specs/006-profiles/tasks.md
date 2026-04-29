---

description: "Granular task list for profiles — six profile types, pure evaluator, sandboxed naming engine, full CRUD"
---

# Tasks: Profiles (Quality, Region, Dump, Language, Naming, Custom Format)

**Input**: Design documents from `specs/006-profiles/`
**Prerequisites**: `001-foundation` shipped (Game, Release, Dump, Platform, ParsedFilename, DumpStatus, NamingConvention)
**Tests**: MANDATORY (Constitution Article XVI; SC-007: ≥ 80% on profiles/)

**Organization**: 8 phases. Scaffolding → persistence → pure evaluator + scoring →
sandboxed naming engine → first-boot seeders → API + schema + preview → cascade
protection → hardening.

## Format: `[ID] [P?] [Phase] Description`

- `[P]` = parallelizable with other `[P]` tasks in the same phase.
- Phase tag short codes: `SCAF`, `PERS`, `EVAL`, `NAME`, `SEED`, `API`, `CASCADE`,
  `HARD`.

---

## Phase 1: Scaffolding (`SCAF`)

**Purpose**: bring up the module skeleton, dependencies, types, and shared errors.

- [ ] T001 [SCAF] Update `pyproject.toml` — add runtime dep
      `Jinja2>=3.1` (used in sandboxed mode only).
- [ ] T002 [P] [SCAF] Create `src/romarr/profiles/__init__.py` exposing
      `ProfileEvaluator`, `NamingTemplateEngine`, `seed_defaults`.
- [ ] T003 [P] [SCAF] Create `src/romarr/profiles/errors.py` —
      `ProfileError` (base), `TemplateSyntaxError`,
      `TemplateUnknownTokenError`, `SandboxViolationError`,
      `RegexCompileError`, `ProfileInUseError`.
- [ ] T004 [P] [SCAF] Create `src/romarr/profiles/types.py` —
      `Decision` enum, `EvaluationReason`, `EvaluationResult`,
      `NamingPreviewRequest/Response`, `ForceDeleteResult` Pydantic
      models from `data-model.md`.
- [ ] T005 [SCAF] Extend `tests/conftest.py` with a
      `parsed_filename(name)` fixture loader; create
      `tests/profiles/conftest.py` for module-local fixtures.

**Checkpoint**: imports work; lint+types green; no behaviour added.

---

## Phase 2: Persistence (`PERS`)

**Purpose**: 6 new tables + m2m + Alembic migration + SQLAlchemy models + Pydantic
schemas + idempotent library-FK addition.

### Tests (write first; must fail)

- [ ] T006 [P] [PERS] `tests/profiles/test_models.py` — round-trip one row
      per profile type through the async session; verify CHECK constraints
      on `dump_profile.prefer_revision`, `naming_profile.convention`,
      `custom_format.score` range.
- [ ] T007 [P] [PERS] `tests/profiles/test_models.py::test_unique_name_per_type`
      — second insertion of the same `name` in any profile table raises
      `IntegrityError`.
- [ ] T008 [P] [PERS] `tests/profiles/test_models.py::test_m2m_unique`
      — `(library_id, custom_format_id)` is a composite PK; duplicate insert
      raises (edge case in spec).
- [ ] T009 [P] [PERS] `tests/profiles/test_models.py::test_quality_validators`
      — Pydantic-level: `len(allowed_formats) >= 1`,
      `preferred_format ∈ allowed_formats`,
      `upgrade_until_format ∈ allowed_formats`.
- [ ] T010 [P] [PERS] `tests/profiles/test_models.py::test_region_invariants`
      — empty priorities + fallback=false rejected;
      same-region in priorities AND exclude rejected.
- [ ] T011 [P] [PERS] `tests/profiles/test_models.py::test_custom_format_regex_compile`
      — invalid regex in `matches_regex` rejected at save time
      with `RegexCompileError`.
- [ ] T012 [P] [PERS] `tests/profiles/test_migration_0006.py::test_creates_six_tables_and_m2m`
      — applying the migration creates all six tables + m2m with the
      documented constraints.
- [ ] T013 [P] [PERS] `tests/profiles/test_migration_0006.py::test_library_fk_idempotent`
      — apply the migration twice (with a fake `library` table present);
      the FK columns are added once and the second run is a no-op.

### Implementation

- [ ] T014 [PERS] Create `src/romarr/profiles/models.py` — six SQLAlchemy
      2.0 models matching `data-model.md`, including the
      `library_custom_format` association.
- [ ] T015 [P] [PERS] Create `src/romarr/profiles/schemas.py` — `*Read /
      *Create / *Update` for each profile type.
- [ ] T016 [PERS] Author `src/romarr/db/alembic/versions/0006_profiles.py`
      — DDL for the six tables, the m2m, and the conditional `ADD COLUMN
      IF NOT EXISTS` for the five library FKs (gated by an existence check
      on the `library` table).

**Checkpoint**: `alembic upgrade head` is clean; PERS tests green.

---

## Phase 3: Pure Evaluator + Scoring (`EVAL`)

**Purpose**: pure-function decision engine and Custom Format scorer. No I/O, no
side effects beyond the structured return value.

### Tests

- [ ] T017 [P] [EVAL] `tests/profiles/test_evaluator_quality.py::test_format_filter`
      — release whose detected format is in `allowed_formats` ⇒
      `ACCEPT`; release with disallowed format ⇒ `REJECT` with
      `code = "format_not_allowed"`.
- [ ] T018 [P] [EVAL] `tests/profiles/test_evaluator_quality.py::test_dat_required`
      — `require_dat_verified = true`, `dump.dat_verified = false` ⇒
      `REJECT` with `code = "dat_required"`.
- [ ] T019 [P] [EVAL] `tests/profiles/test_evaluator_quality.py::test_cutoff_met`
      — release format equals `upgrade_until_format` ⇒ `ACCEPT` AND
      reason `code = "cutoff_met"`.
- [ ] T020 [P] [EVAL] `tests/profiles/test_evaluator_region.py::test_priority_score`
      — release region is at index `i` of priorities ⇒ score
      `len(priorities) - i`.
- [ ] T021 [P] [EVAL] `tests/profiles/test_evaluator_region.py::test_excluded_region`
      — region in `exclude_regions` ⇒ `REJECT`.
- [ ] T022 [P] [EVAL] `tests/profiles/test_evaluator_region.py::test_fallback`
      — region outside priorities, `fallback = true` ⇒ `ACCEPT` with
      score below any priority match. `fallback = false` ⇒ `REJECT`.
- [ ] T023 [P] [EVAL] `tests/profiles/test_evaluator_dump.py::test_status_filter`
      — `dump_status` not in `allowed_dump_status` AND no permissive
      flag applies ⇒ `REJECT`.
- [ ] T024 [P] [EVAL] `tests/profiles/test_evaluator_dump.py::test_permissive_flags`
      — table-driven over `allow_proto_beta`, `allow_hacks`,
      `allow_trainers`, `allow_translations`.
- [ ] T025 [P] [EVAL] `tests/profiles/test_evaluator_language.py::test_required_languages`
      — `required_languages = [fr, en]` (any-of); release with
      `[de]` ⇒ `REJECT`; release with `[en, de]` ⇒ `ACCEPT`.
- [ ] T026 [P] [EVAL] `tests/profiles/test_evaluator_language.py::test_japanese_only`
      — `exclude_japanese_only = true`, release languages exactly
      `[ja]` ⇒ `REJECT`.
- [ ] T027 [P] [EVAL] `tests/profiles/test_scoring.py::test_50_release_corpus`
      — fixture `parsed_releases_corpus.json` of 50 mixed releases
      run against the 11 default Custom Formats; assert each release's
      cumulative score matches the documented expected score (SC-003).
- [ ] T028 [P] [EVAL] `tests/profiles/test_scoring.py::test_or_grouping`
      — Custom Format with two conditions in OR group; matches when
      either side matches; contributes 0 when neither matches (FR-021).
- [ ] T029 [P] [EVAL] `tests/profiles/test_scoring.py::test_score_sum`
      — multiple matching Custom Formats ⇒ returned score is the sum.
- [ ] T030 [P] [EVAL] `tests/profiles/test_evaluator_purity.py::test_purity`
      — hypothesis property test: 1 000 randomized
      `(profile, parsed_filename, dump_data)` triples; assert each
      evaluator returns the same output for the same input twice in a
      row AND the database row count is unchanged after the test
      (SC-002).

### Implementation

- [ ] T031 [EVAL] Create `src/romarr/profiles/evaluator.py` — static-method
      `ProfileEvaluator` class with the four boolean evaluators
      (`evaluate_quality`, `evaluate_region`, `evaluate_dump`,
      `evaluate_language`). Every function is pure: no DB session
      argument, no logging side effects.
- [ ] T032 [EVAL] Create `src/romarr/profiles/scoring.py` — pure
      `compute_custom_format_score(formats, parsed, indexer_meta) -> int`
      with the operator dispatch table for `matches_regex`, `equals`,
      `in`, `contains`, `not_in`, `greater_than`, `less_than`. Handles
      OR-grouping per FR-021.

**Checkpoint**: every evaluator test green; the purity invariant
holds; the 50-release scoring corpus exits clean.

---

## Phase 4: Sandboxed Naming Engine (`NAME`)

**Purpose**: Jinja2 sandbox + token whitelist + filter whitelist + post-processing.
The most sensitive piece — operator-supplied templates run inside it.

### Tests

- [ ] T033 [P] [NAME] `tests/profiles/naming/test_engine_sandbox.py::test_class_attribute_blocked`
      — template `{{ Release.__class__ }}` raises
      `SandboxViolationError`.
- [ ] T034 [P] [NAME] `tests/profiles/naming/test_engine_sandbox.py::test_globals_blocked`
      — template `{{ globals() }}` raises.
- [ ] T035 [P] [NAME] `tests/profiles/naming/test_engine_sandbox.py::test_unknown_token`
      — template `{{ Game.SomeForbidden }}` raises
      `TemplateUnknownTokenError` at parse time (save time, FR-028).
- [ ] T036 [P] [NAME] `tests/profiles/naming/test_engine_filters.py::test_only_allowed_filters`
      — table-driven: `lower`, `upper`, `replace`, `truncate(N)` all
      work; any other Jinja built-in (e.g., `length`, `default`)
      raises `SandboxViolationError`.
- [ ] T037 [P] [NAME] `tests/profiles/naming/test_postprocess.py::test_collapse_whitespace`
      — rendered string with consecutive spaces collapses to single
      spaces; trailing whitespace trimmed.
- [ ] T038 [P] [NAME] `tests/profiles/naming/test_postprocess.py::test_drop_empty_groups`
      — empty bracketed groups (`()`, `( )`, `[]`, `[ ]`) are removed
      cleanly when their token is empty (FR-027).
- [ ] T039 [P] [NAME] `tests/profiles/naming/test_postprocess.py::test_replace_illegal_chars`
      — `replace_illegal_chars = true` and Game title contains
      `:`/`/`/`\`/`*`/`?`/`"`/`<`/`>`/`|`; assert each is replaced with
      `_` (FR-026).
- [ ] T040 [P] [NAME] `tests/profiles/naming/test_no_intro_corpus.py`
      — at least 10 fixture pairs (input ParsedFilename + expected
      rendered string) under `tests/fixtures/profiles/naming/nointro/`;
      assert each renders to its golden output (SC-004).
- [ ] T041 [P] [NAME] `tests/profiles/naming/test_redump_corpus.py`
      — same shape, ≥ 10 fixtures.
- [ ] T042 [P] [NAME] `tests/profiles/naming/test_tosec_corpus.py`
      — same shape, ≥ 10 fixtures.
- [ ] T043 [P] [NAME] `tests/profiles/naming/test_esde_corpus.py`
      — same shape, ≥ 10 fixtures.
- [ ] T044 [P] [NAME] `tests/profiles/naming/test_romm_corpus.py`
      — same shape, ≥ 10 fixtures.
- [ ] T045 [P] [NAME] `tests/profiles/naming/test_bad_templates.py`
      — at least 10 deliberately broken templates under
      `tests/fixtures/profiles/bad_templates/`; assert each is rejected
      at save time with the documented structured error (SC-005).

### Implementation

- [ ] T046 [NAME] Create `src/romarr/profiles/naming/tokens.py` — the
      whitelist of allowed token namespaces (`Game`, `Release`, `Dump`,
      `Platform`) and the per-namespace allowed attributes. The Jinja
      env's `is_safe_attribute` consults this whitelist.
- [ ] T047 [NAME] Create `src/romarr/profiles/naming/filters.py` —
      definitions of the four allowed filters (`lower`, `upper`,
      `replace`, `truncate`).
- [ ] T048 [NAME] Create `src/romarr/profiles/naming/postprocess.py`
      — pure `collapse_whitespace`, `drop_empty_bracketed_groups`,
      `replace_illegal_chars`, composed by `postprocess(rendered,
      replace_illegal: bool) -> str`.
- [ ] T049 [NAME] Create `src/romarr/profiles/naming/engine.py` —
      `NamingTemplateEngine` class that wraps an
      `ImmutableSandboxedEnvironment`, registers only the allowed
      filters, sets `is_safe_attribute` to consult the token whitelist,
      and exposes `validate(template_str) -> None` (raises on save) and
      `render(profile, game, release, dump) -> str`.

**Checkpoint**: every naming test green including the ≥ 50 golden
fixture pairs and the ≥ 10 bad-template rejections.

---

## Phase 5: First-Boot Seeders (`SEED`)

**Purpose**: ship default-profile JSON files and an idempotent runner that respects
operator edits.

### Tests

- [ ] T050 [P] [SEED] `tests/profiles/test_seeders.py::test_first_boot_inserts_all`
      — fresh DB; runner invoked; assert the documented counts
      (3/3/3/3/3/11) and that every row has `is_factory_default = true`
      (SC-001).
- [ ] T051 [P] [SEED] `tests/profiles/test_seeders.py::test_idempotent_rerun`
      — runner invoked a second time; row counts unchanged; no
      `updated_at` modified.
- [ ] T052 [P] [SEED] `tests/profiles/test_seeders.py::test_user_edit_preserved`
      — operator updates a default profile (e.g. renames "Preservation"
      → "Archive"); runner invoked again; the renamed row is left
      untouched and `is_factory_default` is now considered "owned by
      the operator" (the seeder uses `created_at != updated_at` as the
      sentinel).

### Implementation

- [ ] T053 [SEED] Author the JSON seed files under
      `src/romarr/profiles/seeders/`:
      `quality.json`, `region.json`, `dump.json`, `language.json`,
      `naming.json`, `custom_formats.json`, `scene_groups.json`. Each
      file mirrors the catalogue tables in `data-model.md`.
- [ ] T054 [SEED] Create `src/romarr/profiles/seeders/runner.py` —
      `seed_defaults(session)` async helper that:
      1. iterates every JSON file;
      2. for each row, checks whether `(name, type)` already exists;
      3. inserts when missing, marking `is_factory_default = true`;
      4. when present and `created_at == updated_at`, **leaves it alone**
         (operator hasn't touched it; in this MVP we don't push schema
         updates onto operator-touched rows even if `is_factory_default`
         is true);
      5. when present and `created_at != updated_at`, the operator has
         edited it — leave alone unconditionally.
- [ ] T055 [SEED] Wire `seed_defaults(session)` into the application
      bootstrap so first-boot is automatic. The wiring lives in
      `src/romarr/app/lifespan.py` (a placeholder for now; the API spec
      formalises it).

**Checkpoint**: seeders tests green; an empty database has the catalog
ready after a single startup; restarting touches nothing.

---

## Phase 6: API + Schema + Preview (`API`)

**Purpose**: CRUD endpoints for the six profile types, JSON Schema endpoints, and
the naming-template preview endpoint.

### Tests

- [ ] T056 [P] [API] `tests/profiles/api/test_quality_endpoints.py`
      — full CRUD round-trip; POST then GET then PUT then DELETE.
- [ ] T057 [P] [API] `tests/profiles/api/test_region_endpoints.py`
      — same shape.
- [ ] T058 [P] [API] `tests/profiles/api/test_dump_endpoints.py`
      — same.
- [ ] T059 [P] [API] `tests/profiles/api/test_language_endpoints.py`
      — same.
- [ ] T060 [P] [API] `tests/profiles/api/test_naming_endpoints.py`
      — same; PUT with a bad template returns HTTP 400 with the
      structured error (FR-028).
- [ ] T061 [P] [API] `tests/profiles/api/test_custom_format_endpoints.py`
      — same; POST with an invalid regex returns HTTP 400.
- [ ] T062 [P] [API] `tests/profiles/api/test_schema_endpoints.py`
      — `GET /api/v3/qualityprofile/schema` (and the five other
      `/schema` endpoints) returns a valid JSON Schema document
      describing every documented field (FR-030).
- [ ] T063 [P] [API] `tests/profiles/api/test_naming_preview.py`
      — `POST /api/v3/rom/namingprofile/preview` with a candidate
      profile + an existing release id; assert the response body's
      `rendered` matches an offline render of the same template
      against the same release (FR-031). DB unchanged after.

### Implementation

- [ ] T064 [API] Create `src/romarr/profiles/api/shared.py` —
      `_make_crud_router(model_cls, schema_read, schema_create,
      schema_update, base_path)` factory plus the force-delete
      helper used by Phase 7.
- [ ] T065 [P] [API] Create `src/romarr/profiles/api/quality.py` —
      uses the factory to expose `/api/v3/qualityprofile*` and
      `/schema`.
- [ ] T066 [P] [API] Create `src/romarr/profiles/api/region.py` —
      `/api/v3/rom/regionprofile*` + `/schema`.
- [ ] T067 [P] [API] Create `src/romarr/profiles/api/dump.py` —
      `/api/v3/rom/dumpprofile*` + `/schema`.
- [ ] T068 [P] [API] Create `src/romarr/profiles/api/language.py`
      — `/api/v3/rom/languageprofile*` + `/schema`.
- [ ] T069 [P] [API] Create `src/romarr/profiles/api/naming.py` —
      `/api/v3/rom/namingprofile*` + `/schema` + `/preview`.
- [ ] T070 [P] [API] Create `src/romarr/profiles/api/custom_format.py`
      — `/api/v3/customformat*` + `/schema`.
- [ ] T071 [API] Create `src/romarr/profiles/json_schema.py` — auto-export
      a JSON Schema for each Pydantic `*Read` model via
      `pydantic.TypeAdapter(...).json_schema()`. The CRUD factory
      consumes this for the `/schema` route.
- [ ] T072 [API] Wire all six routers into the application factory
      under their documented paths. Authentication continues to use
      the development-only no-op admin dependency until the Auth spec
      lands.

**Checkpoint**: every endpoint exercised; the JSON Schema endpoints
return documents that validate every existing default-seeded row.

---

## Phase 7: Cascade Protection (`CASCADE`)

**Purpose**: deleting a profile bound to a library returns HTTP 409. A
`?force=true` query parameter unbinds the profile from libraries (FK to NULL)
before the delete.

### Tests

- [ ] T073 [P] [CASCADE] `tests/profiles/api/test_force_delete.py::test_blocked_when_bound`
      — bind a Quality profile to a synthetic library row; DELETE
      returns HTTP 409 with the affected library names listed in
      the response body (SC-006).
- [ ] T074 [P] [CASCADE] `tests/profiles/api/test_force_delete.py::test_force_unbinds_and_deletes`
      — same setup; DELETE with `?force=true` returns HTTP 204; the
      library's FK column is now NULL; the profile row is gone
      (SC-006).
- [ ] T075 [P] [CASCADE] `tests/profiles/api/test_force_delete.py::test_unbound_delete_works`
      — profile not bound; DELETE returns HTTP 204 directly.
- [ ] T076 [P] [CASCADE] `tests/profiles/api/test_force_delete.py::test_custom_format_m2m_cascade`
      — delete a Custom Format associated with a library; the m2m
      row disappears via `ON DELETE CASCADE`; library is otherwise
      untouched.

### Implementation

- [ ] T077 [CASCADE] Extend
      `src/romarr/profiles/api/shared.py::force_delete(profile_type, id, force)`
      to:
      1. fetch the bindings against `library` (across all five FK
         columns and the m2m for Custom Formats);
      2. when `force = false` and there is at least one binding,
         return HTTP 409 with the list of blocking library names;
      3. when `force = true`, set the FK columns to NULL inside the
         same transaction, then delete the profile.

**Checkpoint**: every cascade test green; SC-006 met.

---

## Phase 8: Hardening (`HARD`)

- [ ] T078 [HARD] Run `pytest --cov=romarr.profiles` — verify
      ≥ 80% coverage (SC-007). Add targeted tests for any uncovered
      branch.
- [ ] T079 [HARD] Run `ruff check .` — zero warnings on
      `src/romarr/profiles/`.
- [ ] T080 [HARD] Add a CI smoke test that asserts every default
      template ships with `convention != 'custom'`, parses without
      error in the sandbox, and renders the documented golden output
      against a canonical fixture release (so a typo in the seed JSON
      fails the build instead of slipping into a release).
- [ ] T081 [HARD] Manual perf check — render a single naming template
      against a fixture release in < 1 ms; full evaluator pipeline in
      < 5 ms. Record the median over 100 trials in
      `specs/006-profiles/research.md`.
- [ ] T082 [HARD] Update `pyproject.toml` `version = "0.6.0a1"`; add
      a one-line note to `CHANGELOG.md`: "0.6.0a1 — Profiles: six
      types, pure evaluator, sandboxed naming engine, full CRUD."
- [ ] T083 [HARD] Final review: open `specs/006-profiles/spec.md`
      and tick every Functional Requirement (FR-001 → FR-032) against
      a task ID; record gaps as follow-up items.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (SCAF)**: foundation merged.
- **Phase 2 (PERS)**: depends on Phase 1.
- **Phase 3 (EVAL)**: depends on Phase 2 for the model classes; the
  evaluator functions are pure but they accept the model objects.
- **Phase 4 (NAME)**: depends on Phase 1 only — pure functions
  consuming the foundation's domain objects.
- **Phase 5 (SEED)**: depends on Phase 2 + Phase 4 (the seeder
  validates each seeded naming template through the engine).
- **Phase 6 (API)**: depends on Phases 2, 3, 4, 5.
- **Phase 7 (CASCADE)**: depends on Phase 6.
- **Phase 8 (HARD)**: depends on Phase 7.

### Within-Phase Parallelism

- Phase 1: T002–T004 in parallel.
- Phase 2: T006–T013 (tests) in parallel; T014 + T015 in parallel.
- Phase 3: T017–T030 (tests) in parallel; T031 + T032 in parallel.
- Phase 4: T033–T045 (tests) in parallel; T046–T048 (helpers)
  in parallel; T049 last.
- Phase 5: T050–T052 in parallel.
- Phase 6: T056–T063 (tests) in parallel; T065–T070 (routers) in
  parallel; T071 + T072 sequential at the end.
- Phase 7: T073–T076 in parallel.

### Critical Path

`SCAF → PERS → (EVAL || NAME) → SEED → API → CASCADE → HARD`. EVAL
and NAME are independent; they can run in parallel by two
contributors.

### Implementation Strategy

- **Day 1**: Phases 1–2 (scaffolding + persistence + migration).
- **Day 2**: Phase 3 (evaluator + scoring) + Phase 4 (naming
  engine) split across two contributors. Single contributor: Phase
  3 first, Phase 4 second.
- **Day 3**: Phase 4 (naming engine) wrap-up + the per-convention
  fixture corpus.
- **Day 4**: Phase 5 (seeders) + Phase 7 (cascade) in parallel.
- **Day 5**: Phase 6 (API + JSON Schema + preview).
- **Day 6**: Phase 8 (hardening).

This sizing assumes one developer working full-time. With two,
EVAL and NAME split cleanly.

---

## Notes

- `[P]` tasks change different files only.
- Tests are written BEFORE implementation in every phase.
- Stop at any phase checkpoint — the profiles layer is delivered
  incrementally; each phase is independently shippable.
- Avoid: pulling search-engine logic (Search & Decision Engine
  spec); implementing the importer's file-mover (Importer spec);
  building UI forms (UI spec); doing profile recommendation
  (deferred to v1+); doing profile sharing/export (deferred to
  v1+).
- Constitutional invariants under test:
  - **Article V (Profile-Driven Decisions)** — every grab/upgrade/
    import decision flows from declarative profiles. T030 (purity)
    + T027 (50-release scoring corpus) gate this.
  - **Article XI (Naming Discipline)** — naming conventions are
    first-class objects with a sandboxed engine. T040–T044 (per-
    convention golden corpora) + T045 (bad-template rejection) are
    the gate.
  - **Article XVI (Quality Gates)** — ≥ 80% coverage. SC-007 +
    Hardening phase.
  - **Article XVII (Idempotency & Safety)** — pure evaluators,
    idempotent seeder, protected deletion. T030, T051, T052,
    T073–T076.

## Phase: Clarification Tasks (Session 2026-04-29)

- [ ] CL001 [P] [US4] Implement Custom Format adversarial-input regex validator in `src/romarr/profiles/validators/regex_safety.py` — at save time, compile + run against 256-byte adversarial input on a worker thread bounded by 50 ms; reject Custom Format with HTTP 400 + offending condition's index. Mirrors spec 003 FR-005a (FR-023a)
- [ ] CL002 Migration `0006_profiles.py` adds two columns to **every** profile table (`quality_profile`, `region_profile`, `dump_profile`, `language_profile`, `naming_profile`, `custom_format`): `seed_key VARCHAR NULL` and `is_user_modified BOOLEAN NOT NULL DEFAULT false`, plus a partial unique index on `seed_key WHERE seed_key IS NOT NULL` (FR-003a)
- [ ] CL003 [P] Update profile seeders in `src/romarr/profiles/seeds/` to populate `seed_key` on every default row (e.g., `seed_key = "default-preservation"` for the seeded "Preservation" Quality profile)
- [ ] CL004 [P] Implement `is_user_modified` flip-on-write in `src/romarr/profiles/repository.py` — every UPDATE that mutates a non-FK column flips the flag in the same transaction
- [ ] CL005 [P] Update seeder logic to upsert by `seed_key` ONLY when `is_user_modified = false`; rows where the operator made any change are left alone (FR-003)
- [ ] CL006 [US2] Implement Region scoring formula `score = len(priorities) − index` (0-based) in `src/romarr/profiles/evaluators/region_evaluator.py`; fallback releases score 0; excluded regions reject outright (FR-013, FR-015)
- [ ] CL007 [P] [Admin] Wire admin-role gate on every mutating profile endpoint AND on the naming-preview endpoint in `src/romarr/profiles/api.py` (FR-032a)
- [ ] CL008 [P] Add tests in `tests/profiles/test_seed_key_invariant.py` covering: fresh DB seed → all defaults present with `seed_key` set; UPDATE one default → flag flips; subsequent seed run → modified row preserved, missing row re-created
- [ ] CL009 [P] Add tests in `tests/profiles/test_region_scoring.py` covering: priority-0 → score = len; priority-last → score = 1; outside-priorities + fallback enabled → score 0; excluded → reject
- [ ] CL010 [P] Add tests in `tests/profiles/test_custom_format_regex_safety.py` covering catastrophic-backtracking pattern rejected at save time
- [ ] CL011 **Note**: this spec does NOT add Library FK columns or the `library_id` FK on `library_custom_format`. Spec 009's migration owns those. The `library_custom_format` table here is created with `custom_format_id` FK only; the unique constraint `(library_id, custom_format_id)` ships in `0009_library.py` after `library_id` is added (FR-004 rewritten)
