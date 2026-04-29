# Implementation Plan: Indexers (Prowlarr-First)

**Branch**: `004-indexers` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification at `specs/004-indexers/spec.md`
**Depends on**:
- `001-foundation` — filename parser dispatcher, region/language code translation, ISO normalisation, identification value types.
- `002-metadata-aggregation` — encryption helper (`metadata.encryption.encrypt/decrypt`) reused for indexer API keys.
- `003-platform-packs` — `platform.newznab_category_ids` JSON column populated by the pack pipeline.

## Summary

The indexer subsystem ships three things on top of the existing
foundation + platform-packs infrastructure:

1. **A generic Newznab/Torznab HTTP client** that calls `t=caps`,
   `t=search`, and parses XML responses into a canonical
   `SearchResult` Pydantic model. Standard fields plus
   Romarr-relevant extended attributes (region/languages/revision/
   dump_tags/hash_sha1/hash_crc32/naming_convention/dat_source) are
   parsed under both `torznab:` and `grabarr:` namespaces, with
   per-field provenance. When extended attributes are absent, the
   client delegates to the foundation filename parser dispatcher.
2. **Prowlarr application registration & sync surface** at
   `/api/v3/applications` and `/api/v3/indexer*` matching the
   contract Prowlarr expects from a downstream *arr. App tokens are
   32 random bytes returned exactly once and stored salted-hashed.
3. **Per-indexer rate limiting and circuit breaking** that protect
   operators from self-inflicted bans and that isolate failing
   indexers without affecting healthy ones. The circuit breaker
   reuses the implementation introduced in foundation
   (`identification/hashmatch/circuit_breaker.py`); rate limiting
   is new, monotonic-clock-based, per indexer.

The indexer module **does not** own any decision logic — that
lives in the future Search & Decision Engine spec. It also does
not schedule RSS — the Tasks/Scheduler spec consumes
`IndexerRssSync.sync_all_enabled_indexers()` on a cron.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: SQLAlchemy 2.0 (async), Pydantic v2,
Alembic, httpx (async), tenacity, lxml (XML parsing — same
dependency already pulled in by the foundation DAT parser),
structlog. **No new HTTP client library.**
**Storage**: SQLite default / PostgreSQL 15+ optional. Two new
tables: `indexer`, `application`. One new column on `platform`:
`newznab_category_ids` JSON (added by Platform Packs spec; this
spec only reads it).
**Testing**: pytest, pytest-asyncio, pytest-cov, respx (mocks of
indexer HTTP), hypothesis (parser property tests on the dedup
invariant), freezegun (rate-limit time travel), TestClient (FastAPI
endpoints). At least 30 Torznab response fixtures of varying shape.
**Target Platform**: Linux server in the Romarr Docker image.
**Project Type**: Backend Python module added under
`src/romarr/indexers/`.
**Performance Goals**:
- Connectivity test (caps + minimal search) returns in < 5 s p95
  against a healthy indexer.
- Search across 5 indexers in parallel returns in < 8 s p95
  (constitution Article XVI; consumed by future Search spec).
- Parsing a 200-result Torznab response in < 200 ms.
**Constraints**:
- No indexer-specific protocol code (Constitution Article VII).
- Per-indexer rate limiting on a monotonic clock (FR-009).
- Circuit breaker per indexer; isolation invariant (FR-010, FR-011).
- All API keys encrypted at rest (FR-022) — re-uses the metadata
  layer's encryption helper.
- App tokens stored as salted hashes (FR-023).
**Scale/Scope**:
- Tens of indexers per instance typical; a power-user might run
  20+.
- Search responses up to a few hundred items per query; thousands
  in pathological cases.
- One Application row per Prowlarr instance; usually one, sometimes
  two.

## Constitution Check

*Gate: must pass before Phase 0 research and again after Phase 1 design.*

| Article | Gate | Status |
|---------|------|--------|
| III — Technology Stack (Locked) | httpx async, lxml, SQLAlchemy async; no `requests`/`urllib3`; no new HTTP library. | ✅ Conformant. |
| VII — Indexer Strategy (Prowlarr-first) | Romarr does NOT implement indexer-specific protocols. Newznab/Torznab only. Romarr can register as a Prowlarr application. Extended Torznab attributes consumed when present, never required. | ✅ Conformant — encoded in FR-001 to FR-016. |
| XVI — Quality Gates | ≥ 75% coverage on `indexers/`; performance targets above; zero ruff warnings. | ✅ Conformant — encoded in SC-009 and Hardening phase. |
| XVII — Idempotency & Safety | Manual indexer creation is `POST /api/v3/indexer` — accepts an optional `Idempotency-Key` header (FR per Constitution Article XVII). Test connectivity does not write state on failure. App tokens leak-resistant (hashed at rest). | ✅ Conformant. |

**Result**: GREEN. No constitutional violations; **Complexity
Tracking** stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/004-indexers/
├── plan.md              # this file
├── spec.md              # user-value specification
├── data-model.md        # 2 new tables + provenance types + Newznab category notes
├── tasks.md             # 10-phase task list
└── checklists/
    └── requirements.md  # spec-quality checklist
```

### Source Code (additions to the existing repo)

```text
src/romarr/
├── indexers/                            # NEW — top-level module
│   ├── __init__.py                       # public re-exports: NewznabClient, IndexerRegistry, IndexerRssSync
│   ├── types.py                          # SearchResult, ParsedTorznabAttr, IndexerCapabilities, RssResult, FieldProvenance
│   ├── errors.py                         # IndexerError, IndexerAuthError, IndexerProtocolError, CircuitOpenError, RateLimitDelayed
│   ├── rate_limiter.py                   # monotonic-clock per-indexer async rate limiter
│   ├── client.py                         # NewznabClient: caps + search + RSS, wraps rate_limiter + circuit_breaker
│   ├── parser/                           # XML → SearchResult
│   │   ├── __init__.py
│   │   ├── caps.py                       # parse t=caps response
│   │   ├── search.py                     # parse t=search response (rss item) — also used for RSS
│   │   ├── extended_attrs.py             # torznab:attr + grabarr:* extraction with provenance tracking
│   │   └── dedup.py                      # collapse same-GUID items, union categories
│   ├── connectivity.py                   # test_connectivity(): caps + minimal search
│   ├── registry.py                       # async load_enabled_indexers(session), list/get/save/delete
│   ├── prowlarr.py                       # callback helpers: notify Prowlarr on local indexer changes
│   ├── rss.py                            # IndexerRssSync (the orchestration class)
│   ├── health.py                         # IndexerHealthIssue producer
│   ├── tokens.py                         # 32-byte token gen + salted hash + verify
│   ├── models.py                         # Indexer + Application SQLAlchemy 2.0 models
│   ├── schemas.py                        # Pydantic *Read/*Create/*Update for Indexer + Application + nested SearchResult
│   └── api/                              # FastAPI routers — wired stubs
│       ├── __init__.py
│       ├── applications.py               # /api/v3/applications*
│       ├── indexers.py                   # /api/v3/indexer*
│       └── tests.py                      # POST /api/v3/indexer/{id}/test
└── db/
    └── alembic/
        └── versions/
            └── 0004_indexers.py          # NEW migration: 2 new tables

tests/
├── indexers/
│   ├── conftest.py
│   ├── test_rate_limiter.py
│   ├── test_circuit_breaker_reuse.py     # confirm we reuse the foundation's breaker, not a new one
│   ├── test_tokens.py
│   ├── test_models.py
│   ├── test_migration_0004.py
│   ├── parser/
│   │   ├── test_caps.py
│   │   ├── test_search.py
│   │   ├── test_extended_attrs.py        # both torznab:attr and grabarr:* — ≥30 fixtures
│   │   └── test_dedup.py
│   ├── test_client_caps.py
│   ├── test_client_search.py
│   ├── test_client_failure_modes.py      # malformed XML, 5xx, timeouts
│   ├── test_connectivity.py
│   ├── test_registry.py
│   ├── test_prowlarr_callbacks.py
│   ├── test_rss.py
│   └── api/
│       ├── test_applications_endpoints.py
│       ├── test_indexer_crud_endpoints.py
│       ├── test_indexer_test_endpoint.py
│       └── test_indexer_schema_endpoint.py
└── fixtures/
    ├── torznab_caps/
    │   ├── valid_full.xml
    │   ├── valid_minimal.xml
    │   ├── no_search_block.xml
    │   ├── malformed_truncated.xml
    │   └── ... (≥10 caps fixtures)
    └── torznab_search/
        ├── vanilla_no_extended.xml
        ├── extended_torznab_namespace.xml
        ├── extended_grabarr_namespace.xml
        ├── duplicate_guid_two_categories.xml
        ├── unknown_extended_value.xml
        └── ... (≥30 search fixtures)
```

**Structure Decision**: keep the parser as a **separate package**
under `indexers/parser/` so XML parsing is isolated from HTTP and
testable in pure-Python without httpx. The dedup invariant is a
pure function. The client wires together rate-limit → breaker →
HTTP → parser; failures bubble out as typed exceptions consumed by
`registry.py` and `health.py`.

The circuit breaker is **imported** from
`romarr.identification.hashmatch.circuit_breaker` — Constitution
Article III forbids a second breaker library. The rate limiter is
new because the foundation didn't need it; it lives at
`indexers/rate_limiter.py`.

## Phase 0 — Research

Three small research items resolved before code; results in
`research.md` if confirmation is needed at code time.

1. **lxml namespaces with mixed prefixes** — Torznab's
   `<torznab:attr>` and Grabarr's `<grabarr:attr>` (when emitted)
   are siblings inside an `<item>`. lxml's `nsmap`-aware iteration
   over `item.findall('.//{*}attr')` matches both; we extract the
   namespace URI to record provenance.
2. **Token format** — 32 random bytes via `secrets.token_bytes(32)`,
   exposed as URL-safe base64 (`secrets.token_urlsafe(32)` returns
   ~43 chars). Stored as `bcrypt(plaintext + per-row salt)` —
   bcrypt is already pulled in by FastAPI-Users (introduced in the
   Auth spec); this spec adds the dependency proactively because
   we need it before Auth lands.
3. **Prowlarr's exact contract** — Prowlarr's `Add Application`
   flow POSTs `{name, syncLevel, prowlarrUrl, baseUrl, apiKey,
   ...}` to `/api/v3/applications`. The exact JSON shape is
   captured as a fixture under
   `tests/fixtures/prowlarr_payloads/` so the test suite mirrors
   real-world payloads. We do NOT reverse-engineer beyond the
   fixtures we capture; if Prowlarr changes its shape, that's a
   compatibility update task, not a new spec.

No further research items.

## Phase 1 — Design Outputs

- `data-model.md` — DDL for `indexer` and `application` tables,
  notes on the existing `platform.newznab_category_ids` column,
  category-mapping reference table, provenance types.
- No `contracts/` — endpoint stubs only; full payload schemas in
  the API spec.
- No `quickstart.md` — operator quickstart belongs to the API
  spec; a REPL one-liner for `NewznabClient.search(...)` shows up
  in the wrap-up phase of `tasks.md`.

### Re-check: Constitution after design

Same table as above; nothing changed in design that pulls a
constraint.

**Result**: GREEN.

## Complexity Tracking

> *Empty.* No constitutional violations. No deviations to justify.

## Clarification Deltas (Session 2026-04-29)

The 5 clarifications recorded in `spec.md` add the following architectural
constraints to this plan:

- **Per-indexer outbound timeout** (FR-009a) — new `indexer.timeout_seconds`
  column (default 30, range 5-120). Every `t=caps`/`t=search`/`t=rss`
  call is wall-clock-bounded by it. Timeouts trip the per-indexer
  circuit breaker.
- **Concurrent search fan-out** (FR-019a) — when targeting N indexers,
  use `asyncio.gather(..., return_exceptions=True)`. Per-indexer failures
  are isolated, surfaced as `IndexerHealthIssue`, and never cancel
  siblings. Total wall-clock latency ≈ slowest healthy indexer.
- **`POST /api/v3/applications` admin gate** (FR-013a) — the operator's
  admin role authenticates registration; the app token returned authenticates
  every Prowlarr-side call thereafter. Delete revokes the token's hash.
- **No app-token rotate endpoint** — operators rotate by delete +
  re-register (Clarifications). FR-013a's enumerated endpoints are the
  full set; no `PATCH /rotate` ships.
- **Per-indexer result limit** (FR-026a) — new `indexer.result_limit`
  column (default 100, range 1-500). When the indexer's caps advertise
  pagination support, the client passes `limit=…` to the indexer;
  otherwise the parser truncates after dedup with an INFO log.

### Migration delta

`0004_indexers.py` adds two columns to `indexer`:
- `timeout_seconds INTEGER NOT NULL DEFAULT 30`
- `result_limit INTEGER NOT NULL DEFAULT 100`
