# Specification Quality Checklist: Import Pipeline

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

- The five OPEN CLARIFICATIONS supplied with the input (grace period,
  cross-fs detection, webhook auth, unmonitored-Game DAT match, multi-disc
  cue+bin hash target) arrived with the operator's proposed answers; all
  five are recorded in the Assumptions section as decisions, so no
  [NEEDS CLARIFICATION] markers remain.
- This spec depends on four prerequisite specs:
  `001-foundation` (Hasher, identification cascade, hash-match cascade,
  unidentified_dump table),
  `005-download-clients` (DownloadClient ABC, list_managed_downloads,
  tag operations, lifecycle policy field),
  `006-profiles` (ProfileEvaluator, NamingTemplateEngine),
  `007-search-decision-engine` (blocklist auto-add helper, RapidFuzz).
  Each dependency is explicit at the top of `spec.md` and at the start of
  `plan.md`.
- **Forward dependency** — this spec references `library.path`,
  `library.lifecycle_policy`, `library.keep_dump_history`,
  `library.preserve_archive` from the future `010-library` spec. The
  data-model and migration are designed to tolerate either ordering, but
  the **roadmap order has these specs the wrong way round** — Library
  (010) really should be specified before Import (008) is implemented.
  This is flagged in `plan.md` "Forward Dependency" section so the
  implementer sees it immediately.
- Constitutional invariants under test:
  - **Article XII (Library Discipline)** — hardlinks default (FR-024 +
    SC-003); imports idempotent (FR-025 + FR-033 + SC-002 + SC-007); no
    auto-deletion without explicit lifecycle (FR-029 + edge cases).
  - **Article XVII (Idempotency & Safety)** — re-import no-op,
    concurrent imports coalesce, webhook auth constant-time, hash
    mismatch never auto-rejects.
  - **Article V (Profile-Driven Decisions)** — the profile gate uses
    spec 006's evaluator with no business-logic duplication.
  - **Article XVI (Quality Gates)** — ≥ 75% coverage (SC-010); perf
    budgets met.
- The auto-blocklist on import failure (FR-035, US6) is the bridge back
  to the search engine — without it, broken releases get re-grabbed in a
  loop. The handshake with spec 007 is captured by FR-035 + the test in
  Phase 15 (T083).
- The 13-step pipeline is documented as a numbered list in spec.md and
  re-stated as the 13 implementation phases (`WATCH`, `EXTRACT`, `HASH`,
  `DATMATCH`, `IDENTIFY`, `GAMEMATCH`, `MULTIDISC`, `PROFILEGATE`,
  `RENDER`, `MOVE`, `DBUPDATE`, `LIFECYCLE`, `NOTIFY`) in tasks.md, plus
  `SCAF` and `HARD` bookends — exactly the "one phase per pipeline step
  from 1-13" the user asked for.
- The atomic mover (Phase 11) gets four dedicated test files
  (hardlink, cross-fs, idempotency, fault-injection) because it is the
  riskiest module — bugs there corrupt user collections. Constitutional
  Article XII gates ride on its correctness.
