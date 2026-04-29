# Specification Quality Checklist: REST API & WebSocket

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

- The four OPEN CLARIFICATIONS supplied with the input (base path
  v3-only, CSRF, CORS, GZip) arrived with the operator's proposed
  answers; all four are recorded in the Assumptions section as
  decisions, so no [NEEDS CLARIFICATION] markers remain.
- This spec is **the unified HTTP surface** that wires every prior
  spec's routers. It depends on every prior feature, but introduces
  almost no new domain logic — only the cross-cutting concerns
  (middleware, pagination helper, error envelope, OpenAPI
  customisation, WebSocket bridge) and a few new bridge routers
  (`system/status`, `system/log`, `system/backup`, `wanted`,
  `queue`, `history`, `calendar`, `tag`, `command`).
- **No `data-model.md`** per the user's explicit request. Three
  small new tables (`tag`, `queue_entry`, `idempotency_cache`) are
  documented inline in `plan.md`'s "Inline Data Model Touch-ups"
  section. The migration creates them; no FK changes to existing
  tables.
- Constitutional invariants under test:
  - **Article IV (API Conventions & Compatibility Surface)** —
    Sonarr v3 conventions wherever resources overlap; ROM-specific
    endpoints under `/api/v3/rom/*`; `/signalr/messages`
    WebSocket; OpenAPI 3.1 with Swagger UI and ReDoc.
  - **Article XVII (Idempotency & Safety)** — Idempotency-Key
    cache (FR-020-021 + SC-005); CSRF on cookie POSTs
    (FR-026-028 + SC-007); rate limiting on auth (FR-022-024 +
    SC-006).
  - **Article XVI (Quality Gates)** — ≥ 80% coverage (SC-008);
    OpenAPI 3.1 spec validates (SC-002); 90+ documented routes
    each with happy + error tests (SC-009).
  - **Article III (Locked Stack)** — FastAPI + slowapi +
    fastapi-csrf-protect + Pydantic v2; no new HTTP client.
- The Sonarr-shape compatibility test (SC-001) replays a captured
  Notifiarr probe payload against the running app and asserts the
  response's key set is a superset of Sonarr's expected shape.
  This locks the constitutional Article IV surface against
  regressions.
- The WebSocket bridge consumes the same in-process pub/sub channel
  spec 011 introduced. The 12+ documented `messageType` events are
  produced by specs 008 / 009 / 011 / 012; this feature only
  forwards them. Consumer responsibility ends at the WebSocket
  client (the UI in spec 014).
- Cross-cutting concerns live in this feature ONLY — per-spec
  routers MUST NOT re-implement pagination, error formatting,
  rate limiting, or idempotency caching. The hardening phase's
  static checks enforce this.
