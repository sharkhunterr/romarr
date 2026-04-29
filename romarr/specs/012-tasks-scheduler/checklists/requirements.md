# Specification Quality Checklist: Tasks & Scheduler

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

- The four OPEN CLARIFICATIONS supplied with the input (shutdown
  grace, auto-pause on critical health, misfire grace, RSS
  rate-limit handling) arrived with the operator's proposed
  answers; all four are recorded in the Assumptions section as
  decisions, so no [NEEDS CLARIFICATION] markers remain.
- This spec is **the orchestrator** for every prior spec. It does
  not introduce new domain logic; it fires the runners that earlier
  specs already exposed (`run_missing_search`, `HealthEngine.refresh()`,
  `IndexerRssSync.sync_all_enabled_indexers()`, `scan_full`, etc.)
  on documented cadences.
- Three new runners ship with this feature:
  - `BackupRunner` — DB + config TAR.gz at the configured backup_path.
  - `RefreshAllMetadataRunner` — paginated bulk variant of spec 002's
    per-Game refresh.
  - `DatUpdateRunner` — downloads fresh DATs from configured sources
    and feeds them to spec 001's `DatManager.ingest`.
- Constitutional invariants under test:
  - **Article I (Single-instance)** — APScheduler runs in the FastAPI
    loop; no Celery, no separate worker, no Redis broker. Multi-
    instance deployments are explicitly unsupported.
  - **Article XVII (Idempotency & Safety)** — concurrency cap
    (FR-012, SC-003); misfire grace (FR-007, SC-004); auto-pause on
    critical health (FR-018, SC-005); graceful shutdown (FR-020-021,
    SC-006); idempotent seeder (FR-008).
  - **Article XVI (Quality Gates)** — ≥ 75% coverage on `tasks/`
    (SC-010); < 1% idle CPU (SC-009); throttled WS progress (FR-023,
    SC-008).
  - **Article III (Locked Stack)** — APScheduler is the documented
    Scheduler; no other scheduling library is added.
- The WebSocket producer ships in this feature (`WebSocketBroadcaster`);
  the consumer side (the `/signalr/messages` handler that clients
  connect to) lives in spec 014 (REST API & WebSocket). The contract
  between them is the in-process pub/sub channel shipped by spec 011.
- The Sonarr-compat command endpoint (FR-016) ships at least
  8 names: `MissingSearch`, `CutoffSearch`, `RssSync`, `RefreshGame`,
  `RescanLibrary`, `DownloadDats`, `IndexerSearch`, `Backup`.
  Operators familiar with Sonarr will find their muscle memory works.
- API endpoint stubs are intentional: full payload schemas come from
  the auto-generated OpenAPI in spec 014.
