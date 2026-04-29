# Specification Quality Checklist: Authentication & Multi-User

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

- The four OPEN CLARIFICATIONS supplied with the input (API key
  default lifetime, setup token regeneration, trusted-proxy header
  list, session storage backend) arrived with the operator's proposed
  answers; all four are recorded in the Assumptions section as
  decisions, so no [NEEDS CLARIFICATION] markers remain.
- This spec **replaces every prior spec's "development-only no-op
  admin dependency"**. Task T072 + T087 explicitly sweep the codebase
  to verify no `dev_only_admin` import remains. After this spec lands,
  every protected endpoint runs through the real auth chain.
- This spec **converts every `*_by` text column** in earlier specs
  (`import_history.imported_by`, `platform_pack.applied_by`,
  `blocklist.added_by`) to FK references to `user.id`, with a sentinel
  `system` user (`id=1`) preserving the existing `'system'` strings as
  audit-row attribution. The migration uses Alembic's
  `batch_alter_table` for SQLite parity with PostgreSQL.
- Constitutional invariants under test:
  - **Article XVII (Idempotency & Safety)** — setup token one-shot
    (FR-019–FR-021 + SC-002); API key revocation immediate (FR-007 +
    SC-005); 401 responses don't leak method (FR-023 + SC-008);
    password + API key + OIDC client secret encrypted at rest
    (FR-004, FR-006, FR-025 + SC-009).
  - **Article III (Locked Stack)** — FastAPI-Users + Authlib +
    bcrypt + BLAKE2b + Redis are well-maintained Python libraries;
    no custom auth crypto ships.
  - **Article XVI (Quality Gates)** — ≥ 75% coverage (SC-010);
    perf budgets met.
- The chained authentication dependency (FR-022) runs cheap checks
  first (API key BLAKE2b is O(1)) and the most expensive last
  (bcrypt password verification at cost 12). Short-circuiting ensures
  a successful early method skips the rest.
- Sessions use a server-side store (Redis preferred, DB fallback).
  This is operator-friendly: revoking a session is one DELETE, no JWT
  blacklist gymnastics needed.
- The setup token is **single-shot and non-regeneratable** by an
  existing admin; the lone-admin password-recovery path is
  documented as manual DB intervention in MVP.
- The auth chain's order — API key → cookie → JWT → trusted proxy —
  is fixed and tested (T065, T066). Reverse-proxy header support is
  off by default (`ROMARR_TRUST_PROXY_AUTH = false`) so a default
  Romarr deployment is not header-spoofable.
