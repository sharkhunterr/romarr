# Specification Quality Checklist: Library Management & Exporters

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-04-29
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- The four OPEN CLARIFICATIONS supplied with the input (path
  unavailability detection, ES-DE media subfolder, library deletion
  with `keep_dump_history`, multi-library + same Game) arrived with
  the operator's proposed answers; all four are recorded in the
  Assumptions section as decisions, so no [NEEDS CLARIFICATION]
  markers remain.
- This spec **closes the forward dependency** that spec 008 (Import
  Pipeline) flagged. The migration `0009_libraries.py` finalises the
  FK on `unidentified_dump.library_id` if spec 008 already ran, or
  ships it directly if 009 runs first. Either order works.
- This spec also adds `Release.library_id` (NULLable FK) so spec 008's
  importer can record which library a Release belongs to.
- Constitutional invariants under test:
  - **Article XII (Library Discipline)** — hardlinks default for
    media mirror (FR-018); deletion never cascades to files (FR-026 +
    SC-006); idempotent re-scan via `(path, size, mtime)` (FR-010);
    orphan detection via path-disappeared (FR-011).
  - **Article V (Profile-Driven Decisions)** — multi-library routing
    is determined entirely by per-library profile bindings (FR-006);
    no hardcoded heuristics.
  - **Article XVI (Quality Gates)** — ≥ 75% coverage on `libraries/`
    (SC-010); 10 000-file scan < 5 min (SC-003).
  - **Article XVII (Idempotency & Safety)** — gamelist.xml emission
    atomic (FR-017); library deletion blocked by HTTP 409 with
    `?force=true` override that **never** deletes files (FR-026 +
    FR-027); heartbeat debounced over a 5-minute window (FR-029).
- The four exporters (RomM, ES-DE, Pegasus, LaunchBox) all extend a
  common `ExporterBase` ABC; this is the same pattern spec 005 used
  for download clients and spec 002 used for metadata providers.
- Cover-asset materialisation under
  `<library_path>/<platform_slug>/media/covers/` is hardlink-first
  (Article XII) with `EXDEV` fallback to `shutil.copy2`, mirroring
  the import-pipeline mover's pattern.
- API endpoint stubs are intentional: full payload schemas come from
  the auto-generated OpenAPI; authentication wiring lands in the Auth
  spec.
