# Implementation Plan: Profiles

**Branch**: `006-profiles` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification at `specs/006-profiles/spec.md`
**Depends on**: `001-foundation` (Game, Release, Dump, Platform, DumpStatus, NamingConvention, ParsedFilename)

## Summary

The profile subsystem turns Romarr's grab/upgrade/import decisions
into a data product. Six profile types (`Quality`, `Region`,
`Dump`, `Language`, `Naming`, `CustomFormat`) plus a many-to-many
`library_custom_format` association deliver:

1. **Persisted, editable, seed-on-boot defaults** for every type.
2. **A pure-function evaluator** consumed by the future search,
   importer, and grab specs. Pure means deterministic, no I/O, no
   logging side effects beyond a structured return value — so
   testing covers every rule with millisecond-level iterations.
3. **A sandboxed Jinja-style naming template engine** that knows
   exactly which tokens and which functions exist; everything else
   raises a sandbox-violation error at save or render time.
4. **Full CRUD APIs** with schema-discovery endpoints (UI form
   generation), plus a naming-template preview endpoint for the
   profile editor.
5. **Library-binding protection**: deleting a profile bound to a
   library returns HTTP 409 unless `?force=true` is supplied.

This feature **does not** itself dispatch grabs or move files —
that's the search engine and the importer respectively. It ships
the building blocks they consume.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: SQLAlchemy 2.0 (async), Pydantic v2,
Alembic, Jinja2 (used in **sandboxed** mode via
`jinja2.sandbox.ImmutableSandboxedEnvironment`), structlog. **No
new HTTP client; this feature has no outbound traffic.**
**Storage**: SQLite default / PostgreSQL 15+ optional. Six new
tables plus one m2m. The `library` table is owned by a later spec
and is not introduced here; this migration creates only the FK
columns the library spec will reference, gated by an `IF NOT
EXISTS` check (in case both specs land in any order).
**Testing**: pytest, pytest-asyncio, pytest-cov, hypothesis (purity
property tests for evaluators), TestClient (FastAPI endpoints),
golden-fixture corpus per convention (≥ 10 per of no-intro,
redump, tosec, es-de, romm = 50+ filename rendering tests; 50+
release-scoring fixtures).
**Target Platform**: Linux server in the Romarr Docker image.
**Project Type**: Backend Python module added under
`src/romarr/profiles/`.
**Performance Goals**:
- Each evaluator function returns in < 1 ms on a typical input.
- Full evaluation of one release through all 5 evaluators returns
  in < 5 ms.
- Naming template render returns in < 1 ms per release.
- 50-release Custom Format scoring corpus runs in < 50 ms.
**Constraints**:
- All evaluators MUST be **pure** (FR-007). No DB; no logging that
  has side effects beyond returning a reason field; no time, no
  random.
- The naming template engine MUST be sandboxed (FR-024, FR-025);
  arbitrary Jinja constructs are forbidden.
- Defaults seeded idempotently — running the seeder on a populated
  DB MUST NOT touch user-edited rows (FR-003).
**Scale/Scope**:
- Profiles per type: typically a handful per operator; tens at
  most.
- Custom Formats per library: typically 5-15 attached.
- Naming template renders: roughly one per imported file —
  hundreds-of-thousands lifetime, so the < 1 ms-per-render budget
  matters.

## Constitution Check

*Gate: must pass before Phase 0 research and again after Phase 1 design.*

| Article | Gate | Status |
|---------|------|--------|
| III — Technology Stack (Locked) | SQLAlchemy 2.0 async, Pydantic v2, Alembic, Jinja2 sandbox; no new tech. | ✅ Conformant. |
| V — Profile-Driven Decisions | Six profile types, declarative, no hardcoded business logic; profile changes never trigger destructive auto-actions. | ✅ Conformant — encoded in FR-001 to FR-027. |
| XI — Naming Discipline | Naming conventions are first-class objects; six supported conventions (No-Intro / Redump / TOSEC / GoodTools-via-foundation / ES-DE / RomM / custom) plus a sandboxed Jinja template engine; golden tests per convention. | ✅ Conformant — encoded in FR-024 to FR-028 + the SC-004 acceptance bar. |
| XVI — Quality Gates | ≥ 80% coverage on `profiles/`; performance targets above; zero ruff warnings. | ✅ Conformant — encoded in SC-007 + Hardening phase. |
| XVII — Idempotency & Safety | Profile evaluator is pure (idempotent by construction); seed-on-boot is idempotent; profile deletion is protected by HTTP 409 + explicit force flag. | ✅ Conformant — encoded in FR-003, FR-007, FR-032. |

**Result**: GREEN. No constitutional violations; **Complexity Tracking** stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/006-profiles/
├── plan.md              # this file
├── spec.md              # user-value specification
├── data-model.md        # 6 new tables + library_custom_format m2m + library FK additions
├── tasks.md             # 8-phase task list
└── checklists/
    └── requirements.md  # spec-quality checklist
```

### Source Code (additions to the existing repo)

```text
src/romarr/
├── profiles/                            # NEW — top-level module
│   ├── __init__.py                       # public re-exports: ProfileEvaluator, NamingTemplateEngine, seed_defaults
│   ├── types.py                          # Decision enum, RegionScore, EvaluationReason, NamingTokens namespace classes
│   ├── errors.py                         # ProfileError, TemplateSyntaxError, TemplateUnknownTokenError, SandboxViolationError, RegexCompileError, ProfileInUseError
│   ├── evaluator.py                      # PURE static functions (FR-006)
│   ├── scoring.py                        # PURE compute_custom_format_score + condition operator dispatch
│   ├── naming/
│   │   ├── __init__.py
│   │   ├── engine.py                     # sandboxed Jinja env, render(profile, game, release, dump) -> str
│   │   ├── tokens.py                     # whitelist of allowed tokens + their accessor functions
│   │   ├── filters.py                    # only the four allowed filter functions: lower, upper, replace, truncate
│   │   └── postprocess.py                # collapse spaces / drop empty bracketed groups / replace illegal chars
│   ├── seeders/
│   │   ├── __init__.py
│   │   ├── runner.py                     # idempotent seeder (FR-003); skips user-edited rows by checking updated_at vs created_at
│   │   ├── quality.json                  # 3 default Quality profiles
│   │   ├── region.json                   # 3 default Region profiles
│   │   ├── dump.json                     # 3 default Dump profiles
│   │   ├── language.json                 # 3 default Language profiles
│   │   ├── naming.json                   # 3 default Naming profiles + the 5 default templates
│   │   ├── custom_formats.json           # 11 default Custom Formats
│   │   └── scene_groups.json             # config-file-shippable list of scene groups for release_group extraction
│   ├── models.py                         # SQLAlchemy 2.0 models for the 6 profile types + the m2m
│   ├── schemas.py                        # Pydantic *Read/*Create/*Update + nested EvaluationResult, NamingPreviewRequest/Response
│   ├── json_schema.py                    # JSON Schema export for /schema endpoints (auto-generated from Pydantic)
│   └── api/                              # FastAPI router stubs
│       ├── __init__.py
│       ├── quality.py                    # /api/v3/qualityprofile*
│       ├── region.py                     # /api/v3/rom/regionprofile*
│       ├── dump.py                       # /api/v3/rom/dumpprofile*
│       ├── language.py                   # /api/v3/rom/languageprofile*
│       ├── naming.py                     # /api/v3/rom/namingprofile* + preview
│       ├── custom_format.py              # /api/v3/customformat*
│       └── shared.py                     # _make_crud_router() factory + force-delete helper
└── db/
    └── alembic/
        └── versions/
            └── 0006_profiles.py          # NEW migration: 6 tables + m2m + the 5 library FK columns (idempotent)

tests/
├── profiles/
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_migration_0006.py
│   ├── test_seeders.py                   # idempotency + user-edit preservation (FR-003)
│   ├── test_evaluator_quality.py
│   ├── test_evaluator_region.py
│   ├── test_evaluator_dump.py
│   ├── test_evaluator_language.py
│   ├── test_evaluator_purity.py          # hypothesis property test (SC-002)
│   ├── test_scoring.py                   # 50-release fixture corpus (SC-003)
│   ├── naming/
│   │   ├── test_engine_sandbox.py        # ≥ 10 sandbox-escape attempts (SC-005)
│   │   ├── test_engine_filters.py        # only the 4 filters work
│   │   ├── test_postprocess.py           # space collapse / empty group removal / illegal chars
│   │   ├── test_no_intro_corpus.py       # ≥ 10 fixtures (SC-004)
│   │   ├── test_redump_corpus.py         # ≥ 10 fixtures
│   │   ├── test_tosec_corpus.py          # ≥ 10 fixtures
│   │   ├── test_esde_corpus.py           # ≥ 10 fixtures
│   │   └── test_romm_corpus.py           # ≥ 10 fixtures
│   └── api/
│       ├── test_quality_endpoints.py
│       ├── test_region_endpoints.py
│       ├── test_dump_endpoints.py
│       ├── test_language_endpoints.py
│       ├── test_naming_endpoints.py
│       ├── test_custom_format_endpoints.py
│       ├── test_schema_endpoints.py
│       ├── test_naming_preview.py
│       └── test_force_delete.py          # SC-006
└── fixtures/
    ├── profiles/
    │   ├── parsed_releases_corpus.json   # 50 ParsedFilename samples for the scoring corpus
    │   ├── naming/
    │   │   ├── nointro/                  # ≥ 10 (input ParsedFilename + expected rendered string) golden pairs
    │   │   ├── redump/
    │   │   ├── tosec/
    │   │   ├── esde/
    │   │   └── romm/
    │   └── bad_templates/                # ≥ 10 templates that must be rejected at save
    │       ├── unknown_token.j2
    │       ├── syntax_error.j2
    │       ├── sandbox_escape_class.j2
    │       ├── sandbox_escape_globals.j2
    │       ├── disallowed_filter.j2
    │       └── ...
    └── library_binding/                  # synthetic library rows for the force-delete test (no library spec yet)
```

**Structure Decision**: keep the profiles module **fully isolated**
from the future search engine and importer. The evaluator and the
naming engine are pure functions; the search engine and the
importer will import them as a library. This keeps both consumer
specs trivial to test by mocking nothing.

The seeders are **JSON files** loaded at startup, not Python
constants, so a future "reset to defaults" operation re-reads them
and so the JSON itself can be diffed across releases.

The naming engine uses Jinja2's `ImmutableSandboxedEnvironment`,
restricts globals to the documented token namespaces, and overrides
`call_binop` / `call_unop` / `call` to whitelist the four allowed
filters.

## Phase 0 — Research

Three small research items resolved before code; results captured
in `research.md` if confirmation is needed at code time.

1. **Jinja2 sandbox configuration** — use
   `jinja2.sandbox.ImmutableSandboxedEnvironment` with
   `autoescape=False` (these are filenames, not HTML) and an
   empty default `globals` dict. Tokens are passed as a context
   dict whose top-level keys are namespace objects (`Game`,
   `Release`, `Dump`, `Platform`) — Pydantic models with
   `model_config = ConfigDict(frozen=True)` so the engine cannot
   mutate them. Override `is_safe_attribute` to allow attribute
   access only on the documented token names. Filters: register
   only `lower`, `upper`, `replace`, `truncate` and clear the
   default filter set.
2. **Idempotent seeders that respect operator edits** — every
   default-seeded row carries an `updated_at` and a
   `created_at`. The seeder uses a sentinel marker (e.g. an
   `is_factory_default = true` boolean column on each profile
   table) to know which rows the seeder owns. When `created_at !=
   updated_at`, the operator has edited the row and the seeder
   skips it.
3. **JSON Schema export from Pydantic** — `pydantic.TypeAdapter(...)
   .json_schema()` is sufficient for FR-030. The output is
   served verbatim at `/schema` endpoints; no extra tooling
   needed.

No further research items.

## Phase 1 — Design Outputs

- `data-model.md` — DDL for the six profile tables, the
  `library_custom_format` m2m, and the five FK columns added to
  the future library table. Default-seed JSON shapes documented
  alongside.
- No `contracts/` — endpoint stubs only; full payload schemas
  follow the auto-generated JSON Schema returned by `/schema`.
- No `quickstart.md` — operator quickstart belongs to API + UI
  specs. A REPL one-liner showing
  `ProfileEvaluator.evaluate_quality(profile, parsed, dump)` lives
  in the wrap-up phase of `tasks.md`.

### Re-check: Constitution after design

Same table as above; nothing in the design pulls a constraint.
**Result**: GREEN.

## Complexity Tracking

> *Empty.* No constitutional violations. No deviations to justify.

## Clarification Deltas (Session 2026-04-29)

The 5 clarifications recorded in `spec.md` add the following architectural
constraints to this plan:

- **Custom-Format regex adversarial-input test** (FR-023a) — every
  `matches_regex` pattern compiles AND runs against a 256-byte
  adversarial test input on a worker thread bounded by 50 ms at save
  time. Exceedance → HTTP 400 with the offending condition's index.
  Mirrors spec 003 FR-005a so the evaluator hot-path can rely on
  vetted patterns without per-match runtime timeouts.
- **Library FK ownership moves to spec 009** (FR-004 rewritten + FR-005
  amended) — this spec creates the six profile tables and the
  `library_custom_format` m2m WITHOUT the `library_id` FK. Spec 009's
  migration adds the five Library → Profile FKs (with
  `ON DELETE SET NULL`) AND the `library_id` FK on the m2m AND the
  unique constraint `(library_id, custom_format_id)`. Forward-reference
  pattern matches spec 005's handling of `indexer.download_client_id`.
- **Safe re-seed via `seed_key` + `is_user_modified`** (FR-003a) —
  every profile table (six core + `custom_format`) gains two columns:
  `seed_key VARCHAR NULL UNIQUE-when-not-null` and
  `is_user_modified BOOLEAN NOT NULL DEFAULT false`. The seeder upserts
  by `seed_key` only when `is_user_modified = false`. UPDATE through
  any API endpoint flips the flag in the same transaction.
- **Region scoring formula** (FR-013/FR-015 rewritten) — explicit
  `score = len(priorities) − index` (0-based). Fallback releases (when
  enabled) score 0. Excluded regions are rejected outright. Integer
  values sum cleanly with Custom Format scores in the search engine.
- **Admin-only mutations + preview** (FR-032a) — POST/PUT/DELETE on
  every profile type, `custom_format`, and the naming-preview endpoint
  require admin role. Reads + `/schema` accessible to any authenticated
  user.

### Migration delta

`0006_profiles.py` adds to **every** profile table (`quality_profile`,
`region_profile`, `dump_profile`, `language_profile`, `naming_profile`,
`custom_format`):
- `seed_key VARCHAR NULL`
- `is_user_modified BOOLEAN NOT NULL DEFAULT false`
- Unique partial index on `seed_key WHERE seed_key IS NOT NULL`

Library FK columns are NOT added by this migration; they ship in
`0009_library.py`.
