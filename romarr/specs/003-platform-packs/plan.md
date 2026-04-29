# Implementation Plan: Platform Packs

**Branch**: `003-platform-packs` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification at `specs/003-platform-packs/spec.md`
**Depends on**: `001-foundation` — `Platform`, `PlatformFormat`, `PlatformNamingToken`,
`platform_pack`, and the `pack_source` / `pack_version` columns on those tables

## Summary

The Platform Pack subsystem turns Romarr's platform catalog into a
data product. A **Platform Pack** is a YAML document validated against
a JSON Schema and ingested transactionally; the same primitive ships
the built-in catalog (auto-applied on first boot) and ingests
community-authored packs uploaded via the API. A **user-override**
flag (`pack_source = 'user'`) on platform rows protects local
customizations from pack updates.

Three behaviours are constitutional (Article X):

1. **Data, not code** — adding a console must not require a database
   migration. Schema-level extensibility lives in the existing JSON
   columns and reference tables; nothing in this feature widens the
   schema for "Atari Lynx support".
2. **Idempotency** — re-applying an unchanged pack must be a no-op.
3. **User wins** — locally-overridden platforms must survive any
   future pack apply.

Technical approach: PyYAML for parsing, `jsonschema` for validation,
SQLAlchemy 2.0 async for the transactional ingest, FastAPI for the
HTTP surface (stubs wired through; full schemas in the API spec).
Two new tables are added: `parsing_strategies` and
`platform_pack_application_log`. The `platform_pack` table from
foundation gains a `contents_hash` column if it isn't already there
(it is — defined in foundation `data-model.md`); a small Alembic
migration covers any deltas plus the two new tables.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: SQLAlchemy 2.0 (async), Pydantic v2,
Alembic, PyYAML, jsonschema (Draft 2020-12), FastAPI (router stubs),
python-multipart (file uploads), structlog
**Storage**: SQLite default / PostgreSQL 15+ optional. Built-in pack
read from disk on startup at
`/opt/romarr/builtin-packs/builtin-<version>.yaml` (path overridable
via `ROMARR_BUILTIN_PACK_PATH`).
**Testing**: pytest, pytest-asyncio, pytest-cov, hypothesis (cycle
detection property tests), TestClient (FastAPI), respx is **not**
needed here (no outbound HTTP).
**Target Platform**: Linux server in the Romarr Docker image.
**Project Type**: Backend Python module added under
`src/romarr/platform_packs/`.
**Performance Goals**:
- Built-in pack of approximately 20 platforms applied in < 5 s on
  fresh SQLite (SC-001).
- A 100-platform pack ingested in < 5 s (SC-005).
- Validate-only endpoint produces a diff of a 100-platform pack in
  < 1 s.
**Constraints**:
- Transactional ingest: any failure rolls back the whole pack
  (FR-007).
- Full idempotency on (`pack_version`, `contents_hash`) pair (FR-009).
- User-wins rule on `pack_source = 'user'` (FR-012, SC-003).
- No deletion of platforms (FR-015).
**Scale/Scope**:
- Tens of platforms per pack typical; up to a few hundred plausible
  for a community super-pack.
- Tens of pack-application audit rows per year per instance.
- Number of packs persisted is unbounded but small (one per version
  ever applied).

## Constitution Check

*Gate: must pass before Phase 0 research and again after Phase 1 design.*

| Article | Gate | Status |
|---------|------|--------|
| III — Technology Stack (Locked) | SQLAlchemy 2.0 async, Pydantic v2, Alembic, FastAPI; no new HTTP client (no outbound traffic). | ✅ Conformant. |
| X — Platform Extensibility (Data, Not Code) | Platforms are data; YAML pack format generic and self-contained; no schema migration required to add a platform; built-in pack auto-applied on first boot; user-override never broken. | ✅ Conformant — encoded in FR-001 through FR-022 and SC-003. |
| XII — Library Discipline | Idempotent ingestion (FR-009); transactional (FR-007); no destructive auto-actions on user-overridden rows. | ✅ Conformant. |
| XVI — Quality Gates | ≥ 80% coverage on `platform_packs/`; zero ruff warnings. | ✅ Conformant — encoded in SC-007 and Hardening phase of `tasks.md`. |
| XVII — Idempotency & Safety | Pack uploads are POST + multipart; the **upload** endpoint is not idempotent at the HTTP level but is idempotent in effect when the pack is unchanged (FR-009); re-apply endpoint is explicit, not automatic. | ✅ Conformant — explicit operator action; failed runs roll back. |

**Result**: GREEN. No constitutional violations; **Complexity
Tracking** stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/003-platform-packs/
├── plan.md              # this file
├── spec.md              # user-value specification
├── data-model.md        # 2 new tables + JSON Schema for the YAML pack
├── tasks.md             # 8-phase task list
└── checklists/
    └── requirements.md  # spec-quality checklist
```

### Source Code (additions to the existing repo)

```text
src/romarr/
├── platform_packs/                       # NEW — top-level module
│   ├── __init__.py                       # public re-exports: ingest_pack, validate_pack, apply_builtin
│   ├── schema.py                         # the JSON Schema (Draft 2020-12) used by validators
│   ├── yaml_loader.py                    # PyYAML safe_load + canonicalization for SHA-256 hashing
│   ├── validator.py                      # YAML → schema check + cross-ref checks (cycles, dups, dangling)
│   ├── ingestor.py                       # transactional pipeline (Phase B of FR-011/12/13)
│   ├── builtin.py                        # path resolution, first-boot auto-apply
│   ├── override.py                       # mark/release user override
│   ├── diff.py                           # validate-only diff producer
│   ├── audit.py                          # platform_pack_application_log helpers
│   ├── models.py                         # ParsingStrategy + PlatformPackApplicationLog SQLAlchemy 2.0 models
│   ├── schemas.py                        # Pydantic v2 *Read/*Create/*Update for the new entities + UploadResult, ValidateResult
│   └── api/                              # FastAPI router stubs
│       ├── __init__.py
│       ├── packs.py                      # /api/v3/rom/platform-pack* endpoints
│       └── platforms.py                  # /api/v3/rom/platform/{id}/override + /formats endpoints
├── domain/
│   └── models/
│       └── platform.py                   # MODIFIED: ensure pack_source/pack_version present (foundation already covers this)
├── db/
│   └── alembic/
│       └── versions/
│           └── 0003_platform_packs.py    # NEW migration: 2 new tables + any delta
└── builtin_packs/                        # NEW: shipped within the wheel/image
    └── builtin-2026.04.001.yaml          # the seeded ~20 platforms

tests/
├── platform_packs/
│   ├── conftest.py                       # async session, FastAPI TestClient with stubbed auth
│   ├── test_yaml_loader.py
│   ├── test_validator_schema.py          # ≥20 broken-pack fixtures (SC-004)
│   ├── test_validator_cross_refs.py      # cycle + dangling detection
│   ├── test_ingestor_transactional.py    # injected failure → full rollback (SC-006)
│   ├── test_ingestor_idempotency.py      # re-apply same pack = no writes (SC-002)
│   ├── test_ingestor_per_platform_rules.py # FR-011/12/13 by case
│   ├── test_override.py
│   ├── test_diff.py
│   ├── test_audit.py
│   ├── test_builtin_first_boot.py        # SC-001
│   ├── test_migration_0003.py
│   └── api/
│       ├── test_pack_endpoints.py
│       ├── test_override_endpoints.py
│       └── test_format_endpoints.py
└── fixtures/
    ├── packs/
    │   ├── valid/
    │   │   ├── minimal.yaml              # 1 platform, 1 format
    │   │   ├── two_platforms.yaml
    │   │   └── full.yaml                 # 5 platforms, 3 strategies, naming tokens
    │   ├── invalid_yaml/
    │   │   ├── truncated.yaml
    │   │   └── tab_indented.yaml
    │   ├── invalid_schema/
    │   │   ├── missing_pack_version.yaml
    │   │   ├── unknown_format_type.yaml
    │   │   ├── extra_top_level_key.yaml
    │   │   ├── duplicate_slug.yaml
    │   │   ├── duplicate_extension.yaml
    │   │   ├── ... (≥20 broken-pack files total)
    │   │   └── schema_version_too_high.yaml
    │   └── invalid_refs/
    │       ├── dangling_parent.yaml
    │       ├── parent_cycle_a_b.yaml
    │       └── parent_cycle_a_b_c.yaml
    └── builtin/
        └── test_builtin_minimal.yaml      # smaller stand-in used for first-boot tests
```

**Structure Decision**: keep the platform-packs module **separate**
from `domain/`. The two new tables (`parsing_strategies`,
`platform_pack_application_log`) belong logically with platform-pack
operations, not with the canonical domain. This isolation makes it
easier to swap pack-source backends later (e.g., a Git-pulling pack
source in v1+).

The validator is a **pure function**: it takes parsed YAML + the
current set of platform slugs and returns either an
`IngestPlan` (insertable rows + diff) or a structured `ValidationError`.
The ingestor consumes the `IngestPlan` and writes inside a single
SQLAlchemy `begin()` block.

## Phase 0 — Research

Three small open items resolved before code; results captured in a
short `specs/003-platform-packs/research.md` if confirmation is
needed at code time.

1. **YAML canonicalization for hashing** — re-emit the parsed YAML as
   sorted-keys JSON via `json.dumps(..., sort_keys=True,
   separators=(",", ":"))` then SHA-256 the bytes. This is stable
   across whitespace / comment edits in the source YAML, which is
   the property `contents_hash` needs (FR-009).
2. **JSON Schema draft** — Draft 2020-12 (matches the FastAPI default
   for OpenAPI 3.1 in the constitution). The `jsonschema` library
   supports it.
3. **Built-in pack packaging** — the YAML lives at
   `src/romarr/builtin_packs/builtin-<version>.yaml` inside the
   wheel; `importlib.resources` resolves the file at runtime; the
   Docker image places the same file at
   `/opt/romarr/builtin-packs/builtin-<version>.yaml` for operator
   inspection. Both paths are checked in order; the env var
   `ROMARR_BUILTIN_PACK_PATH` overrides both.

No further research items.

## Phase 1 — Design Outputs

- `data-model.md` — the JSON Schema (Draft 2020-12) for the YAML
  pack format as a code block; DDL for the two new tables; notes on
  the existing foundation columns (`pack_source`, `pack_version`).
- No `contracts/` — endpoint stubs only; full payload schemas land
  in the API spec.
- No `quickstart.md` — operator quickstart belongs to API + UI specs.
  A REPL one-liner for `apply_builtin_pack(session)` shows up in the
  wrap-up phase of `tasks.md`.

### Re-check: Constitution after design

Same table as above; nothing in the design pulls a constraint.
**Result**: GREEN.

## Complexity Tracking

> *Empty.* No constitutional violations. No deviations to justify.

## Clarification Deltas (Session 2026-04-29)

The 5 clarifications recorded in `spec.md` add the following architectural
constraints to this plan:

- **Adversarial-input regex validation** (FR-005a) — every pack-defined
  `platform_naming_token.pattern` AND every `parsing_strategies` regex
  template MUST compile AND pass an adversarial-time-bound check at
  validation: run against a 256-byte adversarial test input on a worker
  thread bounded by 50 ms wall-clock. Exceedance → HTTP 400 with the
  offending JSON path.
- **Hardened YAML loading** (FR-001a/b/c) — `yaml.SafeLoader` mandatory;
  1 MiB request body cap (HTTP 413); 200-platform-per-pack cap (HTTP
  400). All non-configurable.
- **`pack_version`-order downgrade rejection** (FR-013a) — reject with
  HTTP 409 when an incoming pack's `pack_version` is older than what's
  recorded for any of its slugs (`pack_source != 'user'`). Comparison is
  lexical (matches the `YYYY.MM.NNN` date order).
- **Admin-only mutating endpoints** (FR-026a) — pack upload / re-apply /
  validate / override / format-CRUD all require the `admin` role from
  spec 010. Reads accessible to any authenticated user.
- **`parsing_strategies` table ownership** (FR-014a) — owned by spec
  003. Migration `0003_platform_packs.py` creates the table and the
  `parsing_strategies` references in the platform-pack schema. Spec 001's
  "nine tables" wording is unchanged.

### Migration delta

`0003_platform_packs.py` creates:
- `parsing_strategies (id PK TEXT, name, pattern, apply_to_platforms JSON, created_at, updated_at)`
- The platform-pack `application_log`, `platform_pack`, etc. tables already
  in scope.
