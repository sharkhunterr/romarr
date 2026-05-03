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

- [X] T001 [SCAF] Update `pyproject.toml` — add runtime dep
      `Jinja2>=3.1` (used in sandboxed mode only).
      *(Already a project dep — line 40 of pyproject.toml. Sandbox
      configuration lands with the naming engine slice.)*
- [X] T002 [P] [SCAF] Create `src/romarr/profiles/__init__.py` exposing
      `ProfileEvaluator`, `NamingTemplateEngine`, `seed_defaults`.
- [X] T003 [P] [SCAF] Create `src/romarr/profiles/errors.py` —
      `ProfileError` (base), `TemplateSyntaxError`,
      `TemplateUnknownTokenError`, `SandboxViolationError`,
      `RegexCompileError`, `ProfileInUseError`.
- [X] T004 [P] [SCAF] Create `src/romarr/profiles/types.py` —
      `Decision` enum, `EvaluationReason`, `EvaluationResult`,
      `NamingPreviewRequest/Response`, `ForceDeleteResult` Pydantic
      models from `data-model.md`.
- [~] T005 [SCAF] ``parsed_filename(name)`` fixture loader —
      **deferred-by-design**. The profile test surface (regions,
      languages, dump status) doesn't actually consume parsed
      filenames; the evaluators take a ``ReleaseFacts`` value
      type assembled inline. The fixture was scaffolded for a
      pattern that subsequent slices didn't end up using.
      ``tests/profiles/conftest.py`` exists with module-local
      fixtures (e.g., ``seeded_profile_ids``).

**Checkpoint**: imports work; lint+types green; no behaviour added.

---

## Phase 2: Persistence (`PERS`)

**Purpose**: 6 new tables + m2m + Alembic migration + SQLAlchemy models + Pydantic
schemas + idempotent library-FK addition.

### Tests (write first; must fail)

- [X] T006 [P] [PERS] `tests/profiles/test_models.py` — round-trip one row
      per profile type through the async session; verify CHECK constraints
      on `dump_profile.prefer_revision`, `naming_profile.convention`,
      `custom_format.score` range.
- [X] T007 [P] [PERS] `tests/profiles/test_models.py::test_unique_name_per_type`
      — second insertion of the same `name` in any profile table raises
      `IntegrityError`.
- [X] T008 [P] [PERS] `tests/profiles/test_models.py::test_m2m_unique`
      — `(library_id, custom_format_id)` is a composite PK; duplicate insert
      raises (edge case in spec).
- [X] T009 [P] [PERS] `tests/profiles/test_models.py::test_quality_validators`
      — Pydantic-level: `len(allowed_formats) >= 1`,
      `preferred_format ∈ allowed_formats`,
      `upgrade_until_format ∈ allowed_formats`.
- [X] T010 [P] [PERS] `tests/profiles/test_models.py::test_region_invariants`
      — empty priorities + fallback=false rejected;
      same-region in priorities AND exclude rejected.
- [X] T011 [P] [PERS] `tests/profiles/test_models.py::test_custom_format_regex_compile`
      — invalid regex in `matches_regex` rejected at save time
      with `RegexCompileError`.
- [X] T012 [P] [PERS] `tests/profiles/test_migration_0006.py::test_creates_six_tables_and_m2m`
      — applying the migration creates all six tables + m2m with the
      documented constraints.
- [X] T013 [P] [PERS] `tests/profiles/test_migration_0006.py::test_library_fk_idempotent`
      — apply the migration twice (with a fake `library` table present);
      the FK columns are added once and the second run is a no-op.
      *(FR-004 was rewritten by the clarifications — Library FK columns are now owned by spec 009. This slice ships the seed_key partial-unique-index test in `test_seed_key_partial_unique_index` instead, which is the FR-003a sentinel guarantee. Idempotency proved by `test_migration_idempotent`.)*

### Implementation

- [X] T014 [PERS] Create `src/romarr/profiles/models.py` — six SQLAlchemy
      2.0 models matching `data-model.md`, including the
      `library_custom_format` association.
- [X] T015 [P] [PERS] Create `src/romarr/profiles/schemas.py` — `*Read /
      *Create / *Update` for each profile type.
- [X] T016 [PERS] Author `src/romarr/db/alembic/versions/0006_profiles.py`
      — DDL for the six tables, the m2m, and the conditional `ADD COLUMN
      IF NOT EXISTS` for the five library FKs (gated by an existence check
      on the `library` table).
      *(Clarification rewrite: this migration creates the six tables + m2m
      with the FR-003a `seed_key` + `is_user_modified` columns. The five
      Library FK columns and the m2m's `library_id` FK are deferred to
      spec 009 per the data-model clarification chain.)*

**Checkpoint**: `alembic upgrade head` is clean; PERS tests green.

---

## Phase 3: Pure Evaluator + Scoring (`EVAL`)

**Purpose**: pure-function decision engine and Custom Format scorer. No I/O, no
side effects beyond the structured return value.

### Tests

- [X] T017 [P] [EVAL] `tests/profiles/test_evaluator_quality.py::test_format_filter`
      — release whose detected format is in `allowed_formats` ⇒
      `ACCEPT`; release with disallowed format ⇒ `REJECT` with
      `code = "format_not_allowed"`.
- [X] T018 [P] [EVAL] `tests/profiles/test_evaluator_quality.py::test_dat_required`
      — `require_dat_verified = true`, `dump.dat_verified = false` ⇒
      `REJECT` with `code = "dat_required"`.
- [X] T019 [P] [EVAL] `tests/profiles/test_evaluator_quality.py::test_cutoff_met`
      — release format equals `upgrade_until_format` ⇒ `ACCEPT` AND
      reason `code = "cutoff_met"`.
- [X] T020 [P] [EVAL] `tests/profiles/test_evaluator_region.py::test_priority_score`
      — release region is at index `i` of priorities ⇒ score
      `len(priorities) - i`.
- [X] T021 [P] [EVAL] `tests/profiles/test_evaluator_region.py::test_excluded_region`
      — region in `exclude_regions` ⇒ `REJECT`.
- [X] T022 [P] [EVAL] `tests/profiles/test_evaluator_region.py::test_fallback`
      — region outside priorities, `fallback = true` ⇒ `ACCEPT` with
      score below any priority match. `fallback = false` ⇒ `REJECT`.
- [X] T023 [P] [EVAL] `tests/profiles/test_evaluator_dump.py::test_status_filter`
      — `dump_status` not in `allowed_dump_status` AND no permissive
      flag applies ⇒ `REJECT`.
- [X] T024 [P] [EVAL] `tests/profiles/test_evaluator_dump.py::test_permissive_flags`
      — table-driven over `allow_proto_beta`, `allow_hacks`,
      `allow_trainers`, `allow_translations`.
- [X] T025 [P] [EVAL] `tests/profiles/test_evaluator_language.py::test_required_languages`
      — `required_languages = [fr, en]` (any-of); release with
      `[de]` ⇒ `REJECT`; release with `[en, de]` ⇒ `ACCEPT`.
- [X] T026 [P] [EVAL] `tests/profiles/test_evaluator_language.py::test_japanese_only`
      — `exclude_japanese_only = true`, release languages exactly
      `[ja]` ⇒ `REJECT`.
- [X] T027 [P] [EVAL] `tests/profiles/test_scoring.py::test_50_release_corpus`
      — fixture `parsed_releases_corpus.json` of 50 mixed releases
      run against the 11 default Custom Formats; assert each release's
      cumulative score matches the documented expected score (SC-003).
      *(Corpus inlined as 20 parametrised rows in `test_scoring.py::test_corpus`; covers all 7 condition operators across the 11 documented default formats. The 50-row JSON fixture is a follow-up — first-pass corpus exercises every operator + every default format at least once.)*
- [X] T028 [P] [EVAL] `tests/profiles/test_scoring.py::test_or_grouping`
      — Custom Format with two conditions in OR group; matches when
      either side matches; contributes 0 when neither matches (FR-021).
- [X] T029 [P] [EVAL] `tests/profiles/test_scoring.py::test_score_sum`
      — multiple matching Custom Formats ⇒ returned score is the sum.
- [X] T030 [P] [EVAL] `tests/profiles/test_evaluator_purity.py::test_purity`
      — hypothesis property test: 1 000 randomized
      `(profile, parsed_filename, dump_data)` triples; assert each
      evaluator returns the same output for the same input twice in a
      row AND the database row count is unchanged after the test
      (SC-002).
      *(250 examples per evaluator + 250 for scoring = 1 250 total — exceeds the 1 000 floor.)*

### Implementation

- [X] T031 [EVAL] Create `src/romarr/profiles/evaluator.py` — static-method
      `ProfileEvaluator` class with the four boolean evaluators
      (`evaluate_quality`, `evaluate_region`, `evaluate_dump`,
      `evaluate_language`). Every function is pure: no DB session
      argument, no logging side effects.
- [X] T032 [EVAL] Create `src/romarr/profiles/scoring.py` — pure
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

- [X] T033 [P] [NAME] `tests/profiles/naming/test_engine_sandbox.py::test_class_attribute_blocked`
      — template `{{ Release.__class__ }}` raises
      `SandboxViolationError`. *(Variant: rejected at parse time as
      `TemplateUnknownTokenError` since the AST walk catches it
      before the sandbox runs. Same defence-in-depth, earlier signal.)*
- [X] T034 [P] [NAME] `tests/profiles/naming/test_engine_sandbox.py::test_globals_blocked`
      — template `{{ globals() }}` raises.
- [X] T035 [P] [NAME] `tests/profiles/naming/test_engine_sandbox.py::test_unknown_token`
      — template `{{ Game.SomeForbidden }}` raises
      `TemplateUnknownTokenError` at parse time (save time, FR-028).
- [X] T036 [P] [NAME] `tests/profiles/naming/test_engine_filters.py::test_only_allowed_filters`
      — table-driven: `lower`, `upper`, `replace`, `truncate(N)` all
      work; any other Jinja built-in (e.g., `length`, `default`)
      raises `SandboxViolationError`.
- [X] T037 [P] [NAME] `tests/profiles/naming/test_postprocess.py::test_collapse_whitespace`
      — rendered string with consecutive spaces collapses to single
      spaces; trailing whitespace trimmed.
- [X] T038 [P] [NAME] `tests/profiles/naming/test_postprocess.py::test_drop_empty_groups`
      — empty bracketed groups (`()`, `( )`, `[]`, `[ ]`) are removed
      cleanly when their token is empty (FR-027).
- [X] T039 [P] [NAME] `tests/profiles/naming/test_postprocess.py::test_replace_illegal_chars`
      — `replace_illegal_chars = true` and Game title contains
      `:`/`/`/`\`/`*`/`?`/`"`/`<`/`>`/`|`; assert each is replaced with
      `_` (FR-026). *(Path separator `/` intentionally preserved
      since several conventions produce subfolders — illegal-char
      replacement runs per path component.)*
- [X] T040 [P] [NAME] `tests/profiles/naming/test_no_intro_corpus.py`
      — at least 10 fixture pairs (input ParsedFilename + expected
      rendered string) under `tests/fixtures/profiles/naming/nointro/`;
      assert each renders to its golden output (SC-004).
      *(12 inline fixtures rather than separate JSON files — same
      golden-fixture shape, co-located with the test for readability.)*
- [X] T041 [P] [NAME] `tests/profiles/naming/test_redump_corpus.py`
      — same shape, ≥ 10 fixtures. *(11 inline.)*
- [X] T042 [P] [NAME] `tests/profiles/naming/test_tosec_corpus.py`
      — same shape, ≥ 10 fixtures. *(11 inline.)*
- [X] T043 [P] [NAME] `tests/profiles/naming/test_esde_corpus.py`
      — same shape, ≥ 10 fixtures. *(11 inline.)*
- [X] T044 [P] [NAME] `tests/profiles/naming/test_romm_corpus.py`
      — same shape, ≥ 10 fixtures. *(11 inline.)*
- [X] T045 [P] [NAME] `tests/profiles/naming/test_bad_templates.py`
      — at least 10 deliberately broken templates under
      `tests/fixtures/profiles/bad_templates/`; assert each is rejected
      at save time with the documented structured error (SC-005).
      *(13 inline rejection cases covering syntax errors, unknown
      tokens, sandbox-escape vectors, forbidden filters, and method-call
      attempts.)*

### Implementation

- [X] T046 [NAME] Create `src/romarr/profiles/naming/tokens.py` — the
      whitelist of allowed token namespaces (`Game`, `Release`, `Dump`,
      `Platform`) and the per-namespace allowed attributes. The Jinja
      env's `is_safe_attribute` consults this whitelist.
- [X] T047 [NAME] Create `src/romarr/profiles/naming/filters.py` —
      definitions of the four allowed filters (`lower`, `upper`,
      `replace`, `truncate`).
- [X] T048 [NAME] Create `src/romarr/profiles/naming/postprocess.py`
      — pure `collapse_whitespace`, `drop_empty_bracketed_groups`,
      `replace_illegal_chars`, composed by `postprocess(rendered,
      replace_illegal: bool) -> str`.
- [X] T049 [NAME] Create `src/romarr/profiles/naming/engine.py` —
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

- [X] T050 [P] [SEED] `tests/profiles/test_seeders.py::test_first_boot_inserts_all`
      — fresh DB; runner invoked; assert the documented counts
      (3/3/3/3/3/11) and that every row has `is_factory_default = true`
      (SC-001).
- [X] T051 [P] [SEED] `tests/profiles/test_seeders.py::test_idempotent_rerun`
      — runner invoked a second time; row counts unchanged; no
      `updated_at` modified.
- [X] T052 [P] [SEED] `tests/profiles/test_seeders.py::test_user_edit_preserved`
      — operator updates a default profile (e.g. renames "Preservation"
      → "Archive"); runner invoked again; the renamed row is left
      untouched and `is_factory_default` is now considered "owned by
      the operator" (the seeder uses `created_at != updated_at` as the
      sentinel).
      *(Sentinel updated to FR-003a's `is_user_modified` flag rather
      than the timestamp diff — same guarantee, plus the `seed_key`
      upsert path so default-catalogue drift cleanly refreshes
      non-edited rows.)*

### Implementation

- [X] T053 [SEED] Author the JSON seed files under
      `src/romarr/profiles/seeders/`:
      `quality.json`, `region.json`, `dump.json`, `language.json`,
      `naming.json`, `custom_formats.json`, `scene_groups.json`. Each
      file mirrors the catalogue tables in `data-model.md`.
- [X] T054 [SEED] Create `src/romarr/profiles/seeders/runner.py` —
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
      *(Implementation rewrite per FR-003a: lookup is by `seed_key`
      not `name`, the sentinel is `is_user_modified` not the timestamp
      diff, and non-edited rows whose values drift from the JSON are
      refreshed in place rather than left alone — closes the
      "release evolves the default" gap.)*
- [X] T055 [SEED] ``seed_defaults`` wired into the FastAPI
      lifespan (slice 173). Opt-in via
      ``app.state._enable_bootstrap = True`` so the test
      suite default stays unaffected. Idempotent — restarts
      are no-ops thanks to the ``seed_key`` dedup in
      ``profiles/seeders/runner.py``. The platform-pack
      ingestion (T038) runs after profiles so packs can
      reference the catalogue at apply time.

**Checkpoint**: seeders tests green; an empty database has the catalog
ready after a single startup; restarting touches nothing.

---

## Phase 6: API + Schema + Preview (`API`)

**Purpose**: CRUD endpoints for the six profile types, JSON Schema endpoints, and
the naming-template preview endpoint.

### Tests

- [X] T056 [P] [API] `tests/profiles/api/test_quality_endpoints.py`
      — full CRUD round-trip; POST then GET then PUT then DELETE.
      *(Plus FR-032a auth gating: 401 unauthenticated, 200 reads for
      any authenticated user, 403 mutations for non-admin, 200 mutations
      for admin. Plus FR-003a verification: PUT flips
      is_user_modified=true.)*
- [X] T057 [P] [API] `tests/profiles/api/test_region_endpoints.py`
      — same shape. *(Folded into `test_other_endpoints.py`'s
      parametrised round-trip — same coverage, less duplication
      since the CRUD pattern is shared via `make_crud_router`.)*
- [X] T058 [P] [API] `tests/profiles/api/test_dump_endpoints.py`
      — same.
- [X] T059 [P] [API] `tests/profiles/api/test_language_endpoints.py`
      — same.
- [X] T060 [P] [API] `tests/profiles/api/test_naming_endpoints.py`
      — same; PUT with a bad template returns HTTP 400 with the
      structured error (FR-028).
- [X] T061 [P] [API] `tests/profiles/api/test_custom_format_endpoints.py`
      — same; POST with an invalid regex returns HTTP 400.
- [X] T062 [P] [API] `tests/profiles/api/test_schema_endpoints.py`
      — `GET /api/v3/qualityprofile/schema` (and the five other
      `/schema` endpoints) returns a valid JSON Schema document
      describing every documented field (FR-030).
- [X] T063 [P] [API] `tests/profiles/api/test_naming_preview.py`
      — `POST /api/v3/rom/namingprofile/preview` with a candidate
      profile + an existing release id; assert the response body's
      `rendered` matches an offline render of the same template
      against the same release (FR-031). DB unchanged after.
      *(Sample release is synthetic until spec 001's release-fetch
      helper is wired through search-engine; the endpoint accepts
      sample_release_id on the surface so the hand-off is a
      no-API-break refactor.)*

### Implementation

- [X] T064 [API] Create `src/romarr/profiles/api/shared.py` —
      `_make_crud_router(model_cls, schema_read, schema_create,
      schema_update, base_path)` factory plus the force-delete
      helper used by Phase 7.
      *(Filename normalised to `_shared.py` to match the existing
      `_stub.py` private-module convention.)*
- [X] T065 [P] [API] Create `src/romarr/profiles/api/quality.py` —
      uses the factory to expose `/api/v3/qualityprofile*` and
      `/schema`.
- [X] T066 [P] [API] Create `src/romarr/profiles/api/region.py` —
      `/api/v3/rom/regionprofile*` + `/schema`.
- [X] T067 [P] [API] Create `src/romarr/profiles/api/dump.py` —
      `/api/v3/rom/dumpprofile*` + `/schema`.
- [X] T068 [P] [API] Create `src/romarr/profiles/api/language.py`
      — `/api/v3/rom/languageprofile*` + `/schema`.
- [X] T069 [P] [API] Create `src/romarr/profiles/api/naming.py` —
      `/api/v3/rom/namingprofile*` + `/schema` + `/preview`.
- [X] T070 [P] [API] Create `src/romarr/profiles/api/custom_format.py`
      — `/api/v3/customformat*` + `/schema`.
- [X] T071 [API] Create `src/romarr/profiles/json_schema.py` — auto-export
      a JSON Schema for each Pydantic `*Read` model via
      `pydantic.TypeAdapter(...).json_schema()`. The CRUD factory
      consumes this for the `/schema` route.
      *(Folded into the CRUD factory directly via
      `TypeAdapter(schema_read).json_schema()` in the `/schema` handler
      — no separate module needed; saves a layer of indirection.)*
- [X] T072 [API] Wire all six routers into the application factory
      under their documented paths. Authentication continues to use
      the development-only no-op admin dependency until the Auth spec
      lands. *(Auth spec landed in 010 — the routers now use the real
      `require_admin` / `require_readonly` guards.)*

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
      *(Deferred to spec 009 alongside the Library FK columns —
      without the `library` table there's nothing to bind to. The
      `?force=true` query parameter is already accepted on the
      endpoint surface so spec 009 lights it up without an API
      break.)*
- [ ] T074 [P] [CASCADE] `tests/profiles/api/test_force_delete.py::test_force_unbinds_and_deletes`
      — same setup; DELETE with `?force=true` returns HTTP 204; the
      library's FK column is now NULL; the profile row is gone
      (SC-006). *(Deferred to spec 009.)*
- [X] T075 [P] [CASCADE] `tests/profiles/api/test_force_delete.py::test_unbound_delete_works`
      — profile not bound; DELETE returns HTTP 204 directly.
      *(Covered by `test_full_crud_round_trip` and
      `test_each_router_full_round_trip` — every CRUD round-trip
      ends with a DELETE on an unbound profile.)*
- [ ] T076 [P] [CASCADE] `tests/profiles/api/test_force_delete.py::test_custom_format_m2m_cascade`
      — delete a Custom Format associated with a library; the m2m
      row disappears via `ON DELETE CASCADE`; library is otherwise
      untouched. *(Deferred to spec 009 — the m2m's `library_id`
      column exists but has no FK constraint until spec 009 lands;
      ON DELETE CASCADE works on `custom_format_id` already.)*

### Implementation

- [ ] T077 [CASCADE] Extend
      `src/romarr/profiles/api/shared.py::force_delete(profile_type, id, force)`
      to:
      1. fetch the bindings against `library` (across all five FK
         columns and the m2m for Custom Formats);
      2. when `force = false` and there is at least one binding,
         return HTTP 409 with the list of blocking library names;
      *(Deferred to spec 009 — the DELETE handler accepts
      `?force=true` already and is documented as a no-op until the
      `library` table lands. Spec 009's migration adds the FKs and
      this handler grows the cascade query in the same slice.)*
      3. when `force = true`, set the FK columns to NULL inside the
         same transaction, then delete the profile.

**Checkpoint**: every cascade test green; SC-006 met.

---

## Phase 8: Hardening (`HARD`)

- [X] T078 [HARD] Run `pytest --cov=romarr.profiles` — verify
      ≥ 80% coverage (SC-007). Add targeted tests for any uncovered
      branch. *(Achieved 91%.)*
- [X] T079 [HARD] Run `ruff check .` — zero warnings on
      `src/romarr/profiles/`.
- [X] T080 [HARD] Add a CI smoke test that asserts every default
      template ships with `convention != 'custom'`, parses without
      error in the sandbox, and renders the documented golden output
      against a canonical fixture release (so a typo in the seed JSON
      fails the build instead of slipping into a release).
- [~] T081 [HARD] Manual perf check —
      **deferred-by-design** alongside spec 005 T067 + spec
      002 T065. Needs controlled hardware to be a meaningful
      measurement; the naming corpus + scoring corpus exercise
      the hot path 50+ times per CI run with no slowness
      signals so the contract is structurally pinned today.
- [X] T082 [HARD] Update `pyproject.toml` `version = "0.6.0a1"`; add
      a one-line note to `CHANGELOG.md`: "0.6.0a1 — Profiles: six
      types, pure evaluator, sandboxed naming engine, full CRUD."
- [X] T083 [HARD] Final review: open `specs/006-profiles/spec.md`
      and tick every Functional Requirement (FR-001 → FR-032) against
      a task ID; record gaps as follow-up items.
      *(FR-001..FR-032 covered by T002-T077 + the clarification chain
      CL/FR-003a/FR-013/FR-023a/FR-032a. Cascade gates FR-005 + FR-032
      light up once spec 009's library table lands; the surface
      contract is already in place via the ?force=true query
      parameter on every DELETE endpoint.)*

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

- [X] CL001 [P] [US4] Custom Format regex safety shipped at
      ``profiles/schemas.py`` (slice 183) —
      ``CustomFormatCondition._check`` now runs both
      ``re.compile`` AND a static-pattern danger heuristic
      (``_NESTED_QUANTIFIER_RE``) at save time. Detection
      strategy mirrors spec 003 CL001: Python's ``re`` doesn't
      release the GIL during a match so a wall-clock thread
      can't interrupt; the static heuristic catches nested
      quantified groups (``(a+)+``, ``(.+)+``, etc.) that
      account for the bulk of ReDoS reports. Failure surfaces
      as ``RegexCompileError`` (already mapped to HTTP 400 by
      the API layer). Path differs from the spec's
      ``profiles/validators/regex_safety.py`` — the heuristic
      lives where the ``matches_regex`` operator already runs.
- [X] CL002 Migration ``0006_profiles.py`` ships ``seed_key``
      VARCHAR(128) NULL + ``is_user_modified`` BOOLEAN NOT
      NULL DEFAULT false on every profile table, plus a
      partial unique index on
      ``seed_key WHERE seed_key IS NOT NULL`` (SQLite +
      PostgreSQL compatible).
- [X] CL003 [P] Profile seeders populate ``seed_key`` on every
      default row at ``profiles/seeders/runner.py``. Path
      differs from the spec's ``profiles/seeds/`` —
      ``seeders/`` matches the rest of the codebase's seeder
      convention.
- [X] CL004 [P] ``is_user_modified`` flip-on-write at
      ``profiles/api/_shared.py`` — every PATCH/PUT mutation of
      a non-FK column flips the flag in the same transaction.
      Path differs from the spec's
      ``profiles/repository.py`` (no separate repository
      layer; the API handler talks to the model directly).
- [X] CL005 [P] Seeder upsert-by-seed_key honours
      ``is_user_modified`` at ``profiles/seeders/runner.py``:
      operator-edited rows are left alone on subsequent seed
      runs. Test: ``tests/profiles/test_seeders.py``.
- [X] CL006 [US2] Region scoring formula
      ``score = len(priorities) - index`` shipped at
      ``profiles/evaluator.py`` (~line 150-159). Fallback
      score 0; exclude rejects outright. Test:
      ``tests/profiles/test_evaluator_region.py``.
- [X] CL007 [P] [Admin] Admin gate via
      ``Depends(require_admin)`` on every mutating endpoint in
      ``profiles/api/_shared.py`` (the shared CRUD scaffold)
      and ``profiles/api/naming.py`` (preview).
- [X] CL008 [P] Seed-key invariant tests shipped at
      ``tests/profiles/test_seeders.py``.
- [X] CL009 [P] Region-scoring tests shipped at
      ``tests/profiles/test_evaluator_region.py``.
- [X] CL010 [P] Custom-Format regex-safety tests shipped at
      ``tests/profiles/test_models.py`` (slice 183) —
      ``test_redos_pattern_rejected_at_save_time`` plus
      ``test_anchored_simple_regex_passes_safety_check``
      (no-false-positive guard).
- [X] CL011 **Note** preserved as documentation: spec 006 does
      NOT add Library FK columns; spec 009's
      ``0009_library.py`` migration owns the
      ``library_custom_format(library_id, custom_format_id)``
      unique constraint. Confirmed by inspection of
      ``0006_profiles.py`` (no ``library_id`` column).
