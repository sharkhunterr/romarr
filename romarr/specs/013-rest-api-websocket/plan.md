# Implementation Plan: REST API & WebSocket

**Branch**: `013-rest-api-websocket` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification at `specs/013-rest-api-websocket/spec.md`
**Depends on**: every prior spec — this is the unified HTTP surface.

## Summary

The REST API & WebSocket subsystem stitches every prior spec's
routers into a single FastAPI application with the cross-cutting
concerns each module shouldn't repeat:

1. **The application factory** (`create_app()`) that wires all
   routers, middleware (GZip, CORS, CSRF, error normaliser, rate
   limiter, idempotency cache), startup/shutdown lifespan handlers
   (scheduler, watcher, heartbeat, health engine), and the
   OpenAPI / Swagger / ReDoc endpoints.
2. **A small set of new routers** that weren't owned by any prior
   spec: `system/status`, `system/log`, `system/backup`,
   `wanted/missing`, `wanted/cutoff`, `queue`, `history`,
   `calendar`, `tag`, `command`. These bridge the cross-cutting
   read paths.
3. **The SignalR-compat WebSocket consumer** at
   `/signalr/messages` that forwards events from the in-process
   pub/sub channel (populated by specs 008, 009, 011, 012) to
   subscribed clients with the documented `messageType`.
4. **Cross-cutting concerns** delivered as middleware: pagination
   (helper, not middleware), uniform error format, GZip, CORS,
   CSRF, rate limiting (slowapi-style), Idempotency-Key cache.

This feature ships **routers and middleware**, not new domain
logic. The data-model deltas are minor — three small tables
(`tag`, `queue_entry`, `idempotency_cache`) are introduced inline
in the migration; the user explicitly noted no separate
`data-model.md` is needed.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: FastAPI (the application — already a
constitutional dep), `slowapi>=0.1.9` (rate limiting; well-
maintained Python lib), `fastapi-csrf-protect>=0.3` (CSRF
double-submit cookie), `openapi-spec-validator>=0.7` (test-only,
to validate the generated OpenAPI 3.1), structlog. **No new HTTP
client.** The existing `httpx` is used for outbound webhooks via
spec 011.
**Storage**: SQLite default / PostgreSQL 15+ optional. **Three
small new tables** introduced by this feature's migration:
`tag`, `queue_entry`, `idempotency_cache`. No new domain
entities.
**Testing**: pytest, pytest-asyncio, pytest-cov, FastAPI
TestClient (REST), `httpx-ws` or `websockets` library for WS
client tests, freezegun (TTL boundaries), respx (Notifiarr-shape
verification), `openapi-spec-validator` (SC-002).
**Target Platform**: Linux server in the Romarr Docker image.
**Project Type**: Backend Python module added under
`src/romarr/api/`. Plus a new tiny `system/` module for the
status / log / backup endpoints that don't belong to any prior
spec.
**Performance Goals**:
- `GET /api/v3/system/status` p95 < 50 ms (plain DB read).
- Paginated list endpoints p95 < 200 ms (Constitution Article XVI).
- WebSocket message latency from emit to client receive p95 < 100 ms.
- OpenAPI generation cached on first request; subsequent reads
  served from memory.
**Constraints**:
- Sonarr v3 / Radarr v3 conventions wherever resources overlap
  (Constitution Article IV).
- ROM-specific endpoints under `/api/v3/rom/*` (Article IV).
- Auth chain delegated entirely to spec 010 — no per-spec auth
  duplication.
- Idempotency keys, rate limiting, CSRF, GZip, CORS are
  cross-cutting and live ONLY in this feature's middleware.
- WebSocket auth uses the SAME chain as REST (FR-018).
**Scale/Scope**:
- Approximately 90+ documented routes.
- 12+ documented WebSocket message types.
- Idempotency cache: a few hundred to a few thousand active
  entries (24 h TTL). Redis preferred, DB fallback.
- WebSocket subscribers: 1-10 typical (one browser tab per
  operator + maybe a Homepage dashboard).

## Constitution Check

*Gate: must pass before Phase 0 research and again after Phase 1 design.*

| Article | Gate | Status |
|---------|------|--------|
| III — Technology Stack (Locked) | FastAPI + Pydantic v2 + Alembic + slowapi + fastapi-csrf-protect; no new HTTP client. | ✅ Conformant. |
| IV — API Conventions & Compatibility Surface | `/api/v3/*` for Sonarr-compat resources; `/api/v3/rom/*` for ROM-specific; `/signalr/messages` WebSocket; OpenAPI 3.1 with Swagger + ReDoc. | ✅ Conformant — encoded in FR-001 to FR-018. |
| XVI — Quality Gates | ≥ 80% coverage on `api/` (SC-008); perf budgets above; zero ruff warnings; OpenAPI spec validates. | ✅ Conformant. |
| XVII — Idempotency & Safety | Idempotency-Key cache (FR-020-021); CSRF on cookie POSTs (FR-026); rate limiting on auth (FR-022); body-mismatch detection (FR-021). | ✅ Conformant. |

**Result**: GREEN. No constitutional violations; **Complexity
Tracking** stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/013-rest-api-websocket/
├── plan.md              # this file
├── spec.md              # user-value specification
├── tasks.md             # 11-phase task list
└── checklists/
    └── requirements.md  # spec-quality checklist
```

(No `data-model.md` per the user's explicit request — minor schema
deltas live in the migration's docstring and in the "Inline Data
Model Touch-ups" section below.)

### Source Code (additions to the existing repo)

```text
src/romarr/
├── api/                                 # NEW — top-level module
│   ├── __init__.py                       # public re-exports: create_app, APP_FACTORY
│   ├── factory.py                        # FastAPI application factory + lifespan startup/shutdown wiring
│   ├── middleware/
│   │   ├── __init__.py
│   │   ├── error_format.py               # canonical {errorMessage, details, errorCode} envelope
│   │   ├── gzip.py                       # configurable threshold (default 1 KB)
│   │   ├── cors.py                       # ROMARR_CORS_ALLOWED_ORIGINS-driven config
│   │   ├── csrf.py                       # double-submit cookie; bypass on API-key auth
│   │   ├── rate_limit.py                 # slowapi-based; Redis preferred, in-memory fallback
│   │   └── idempotency.py                # Idempotency-Key cache (Redis preferred, DB fallback)
│   ├── pagination.py                     # paginate(query, params) -> envelope helper
│   ├── envelopes.py                      # Pydantic models for {records[], totalRecords, ...} and the error envelope
│   ├── openapi.py                        # OpenAPI customizer: tags, examples, security schemes
│   ├── ws/
│   │   ├── __init__.py
│   │   ├── handler.py                    # WebSocket endpoint at /signalr/messages
│   │   ├── auth.py                       # auth-on-upgrade (cookie / apikey query / bearer)
│   │   ├── subscriptions.py              # in-memory subscriber registry
│   │   ├── messages.py                   # SignalR-compat JSON shape; messageType registry
│   │   └── bridge.py                     # consume the in-process pub/sub channel from spec 011 and forward
│   ├── routers/                          # the new bridge routers
│   │   ├── __init__.py
│   │   ├── status.py                     # GET /api/v3/system/status (Sonarr-shape)
│   │   ├── log.py                        # GET /api/v3/system/log + log/file*
│   │   ├── backup.py                     # GET/POST /api/v3/system/backup
│   │   ├── wanted.py                     # GET /api/v3/wanted/missing|cutoff + bulk search triggers
│   │   ├── queue.py                      # GET/DELETE /api/v3/queue + retry
│   │   ├── history.py                    # GET /api/v3/history + history/since
│   │   ├── calendar.py                   # GET /api/v3/calendar (MVP: empty schema-valid response)
│   │   ├── tag.py                        # GET/POST/PUT/DELETE /api/v3/tag*
│   │   └── command.py                    # POST/GET /api/v3/command (Sonarr-compat alias)
│   └── models.py                         # Tag, QueueEntry, IdempotencyCache SQLAlchemy 2.0 models
└── db/
    └── alembic/
        └── versions/
            └── 0013_rest_api.py          # NEW migration: tag + queue_entry + idempotency_cache (3 small tables)

tests/
├── api/
│   ├── conftest.py                       # TestClient app factory, WS test client, mocked OpenAPI validator
│   ├── test_factory.py                   # create_app() wires all routers; lifespan handlers run
│   ├── test_models.py                    # round-trip the 3 small new models
│   ├── test_migration_0013.py
│   ├── middleware/
│   │   ├── test_error_format.py          # FR-010 envelope across 6 status codes
│   │   ├── test_gzip.py                  # FR-029 threshold
│   │   ├── test_cors.py                  # FR-030 default vs configured
│   │   ├── test_csrf.py                  # cookie POST blocked, API-key bypass (US7, SC-007)
│   │   ├── test_rate_limit.py            # 5/min auth login (SC-006), 100/min API key
│   │   └── test_idempotency.py           # 24h TTL, body-mismatch (US5, SC-005)
│   ├── test_pagination.py                # 5 list endpoints with the canonical envelope (SC-003)
│   ├── test_openapi_valid.py             # SC-002: OpenAPI 3.1 validator passes
│   ├── test_openapi_examples.py          # FR-014: examples present on the documented endpoints
│   ├── test_sonarr_status_compat.py      # SC-001: Sonarr-shape probe match
│   ├── ws/
│   │   ├── test_auth.py                  # cookie / apikey / bearer; FR-018
│   │   ├── test_messages.py              # 12+ messageType events
│   │   ├── test_lossy.py                 # disconnected client gets no replay
│   │   └── test_bridge.py                # in-process channel events forward to subscribers
│   ├── routers/
│   │   ├── test_status.py
│   │   ├── test_log.py
│   │   ├── test_backup.py
│   │   ├── test_wanted.py
│   │   ├── test_queue.py
│   │   ├── test_history.py
│   │   ├── test_calendar.py
│   │   ├── test_tag.py
│   │   └── test_command.py
│   └── test_endpoint_coverage.py         # SC-009: every documented route has ≥ 1 happy + ≥ 1 error test
└── fixtures/
    ├── api/
    │   ├── sonarr_status_fixture.json    # captured from real Sonarr v4
    │   ├── notifiarr_probe_payload.json
    │   └── openapi_3_1_validator/        # the JSON Schema for OpenAPI 3.1
```

**Structure Decision**: keep all cross-cutting concerns
(middleware, pagination helper, error envelope) **here** and never
in per-spec router modules. Each prior spec's router (under
`src/romarr/<spec>/api/`) imports the helpers from
`romarr.api.envelopes` / `romarr.api.pagination`; nothing in those
routers re-implements pagination or error formatting.

The WebSocket bridge (`api/ws/bridge.py`) is the only place that
**consumes** the in-process pub/sub channel that specs 008 / 009 /
011 / 012 populate. It forwards each event to the registered
WebSocket subscribers with the documented JSON shape.

The three new SQLAlchemy models live under `src/romarr/api/models.py`
since they are entirely API-layer concerns (Tag is a UI/API
concept; QueueEntry is a transient view of download-client state;
IdempotencyCache is an HTTP-layer optimisation).

## Phase 0 — Research

Three small research items resolved before code; results captured
in `research.md` if confirmation is needed at code time.

1. **OpenAPI 3.1 customisation in FastAPI** — FastAPI emits 3.0 by
   default but supports 3.1 via `app.openapi_version = "3.1.0"`
   plus a custom `openapi.py` module that post-processes the dict
   to add tags, examples, and security schemes. We override
   `app.openapi` to call our customiser once and cache the result.
2. **SignalR compat shape** — Sonarr's "SignalR" implementation
   actually sends plain JSON messages over a WebSocket; we
   replicate the shape (`{messageType: "<type>", data: {...}}`)
   without bringing in a SignalR protocol library. Captured
   fixtures from a real Sonarr instance live under
   `tests/fixtures/api/sonarr_ws_messages.jsonl`.
3. **CSRF double-submit cookie via fastapi-csrf-protect** — the
   library issues a `csrf_token` cookie on first GET; cookie-
   authenticated POSTs must echo the token in
   `X-CSRF-Token` header. The middleware bypasses CSRF when the
   request's resolved `AuthMethod` (from spec 010) is
   `API_KEY`, `JWT`, or `PROXY`.

No further research items.

## Inline Data Model Touch-ups

Per the user's explicit request, **no separate `data-model.md`**.
The three new tables are documented here:

### `tag`

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | PK |
| `name` | TEXT | UNIQUE NOT NULL |
| `color` | TEXT | nullable; hex color (`#RRGGBB`) |
| `created_at` | TIMESTAMP | NOT NULL DEFAULT CURRENT_TIMESTAMP |
| `updated_at` | TIMESTAMP | NOT NULL DEFAULT CURRENT_TIMESTAMP |

Indexes: UNIQUE on `name`. Used by Game tags, Notification
filters, Indexer tags. The `tags JSON` array on existing tables
stores tag *names*, not ids — this is a deliberate denormalisation
for portability (renaming a tag rewrites the JSON across affected
rows in a single transaction).

### `queue_entry`

| Column | Type | Constraints |
|---|---|---|
| `id` | INTEGER | PK |
| `release_id` | INTEGER | nullable; FK → `release.id` ON DELETE CASCADE |
| `download_client_id` | INTEGER | NOT NULL; FK → `download_client.id` ON DELETE CASCADE |
| `download_client_native_id` | TEXT | NOT NULL; the qBit info-hash / SAB nzo_id |
| `state` | TEXT | NOT NULL CHECK in (`queued`, `downloading`, `paused`, `stuck`, `pending_retry`, `completed`, `failed`) |
| `progress` | NUMERIC(5,2) | NOT NULL DEFAULT 0 |
| `size_bytes` | BIGINT | nullable |
| `eta_seconds` | INTEGER | nullable |
| `attempt_count` | INTEGER | NOT NULL DEFAULT 0 |
| `last_attempt_at` | TIMESTAMP | nullable |
| `error_msg` | TEXT | nullable |
| `last_updated_at` | TIMESTAMP | NOT NULL DEFAULT CURRENT_TIMESTAMP |
| `created_at` | TIMESTAMP | NOT NULL DEFAULT CURRENT_TIMESTAMP |

Indexes: `(download_client_id, download_client_native_id)` UNIQUE
(prevents duplicate rows for the same in-flight download); non-
unique on `state` for "show me stuck downloads"; non-unique on
`last_updated_at DESC`. Used by spec 005's stuck-grab retry, by
spec 008's import pipeline, and by the `/api/v3/queue` endpoints
here.

### `idempotency_cache`

| Column | Type | Constraints |
|---|---|---|
| `endpoint` | TEXT | composite PK part 1 |
| `key` | TEXT | composite PK part 2 |
| `request_body_hash` | TEXT | NOT NULL; SHA-256 of the request body |
| `response_status` | INTEGER | NOT NULL |
| `response_body` | BLOB | NOT NULL |
| `response_content_type` | TEXT | NOT NULL DEFAULT `'application/json'` |
| `created_at` | TIMESTAMP | NOT NULL DEFAULT CURRENT_TIMESTAMP |
| `expires_at` | TIMESTAMP | NOT NULL; `created_at + 24 h` |

Indexes: composite PK on `(endpoint, key)`; non-unique on
`expires_at` for cleanup. Redis is the preferred backend; this
table is the fallback. A 24 h TTL is the documented expiry
(FR-020).

The migration `0013_rest_api.py` creates these three tables and
nothing else — no FK changes to existing tables.

## Phase 1 — Design Outputs

- **No `data-model.md`** — schema deltas inline above (per user
  request).
- **No `contracts/`** — every endpoint's payload schema comes from
  the auto-generated OpenAPI spec; the captured Sonarr fixture
  documents the conformance contract for `system/status`.
- **No `quickstart.md`** — the README's "API Quickstart" section
  ships with this feature.

### Re-check: Constitution after design

Same table as above; nothing in the design pulls a constraint.
**Result**: GREEN.

## Complexity Tracking

> *Empty.* No constitutional violations. No deviations to justify.

## Clarification Deltas (Session 2026-04-29)

The 5 clarifications recorded in `spec.md` (plus 2 housekeeping
consistency edits with spec 010) add the following architectural
constraints to this plan:

- **JCS-canonical body hash for `Idempotency-Key`** (FR-021 amended) —
  body equality on replay is determined by hashing the canonicalised
  JSON per RFC 8785 (keys sorted, no insignificant whitespace, normalised
  numbers). The `idempotency_cache.request_body_hash` column stores this
  hash. Multipart and binary bodies fall back to plain SHA-256 of the
  raw bytes.
- **Plain JSON-over-WebSocket envelope** (FR-016 amended) — the
  `/signalr/messages` endpoint is NOT actual SignalR. Each frame carries
  one JSON object `{messageType: string, body: object}`. Server pings
  `{messageType: "ping"}` every 30 s; clients respond
  `{messageType: "pong"}` within 10 s or the connection is torn down.
  Contract documented at `/api/v3/notification/webhook-payloads.md`.
- **Tiered `system/status` response** (FR-031 amended) — public callers
  receive `{version, isProduction}` ONLY (sufficient for the Sonarr-shape
  probe-recognition signal). Authenticated callers (any role) receive the
  full Sonarr-shaped body. Mirrors the spec 011 FR-024a tiering pattern.
- **Sonarr v3+v4 union for `system/status`** (Assumption rewritten) —
  the authenticated-tier response emits the union of v3 and v4 keys
  (`databaseType`, `databaseVersion`, `migrationVersion`, `runtimeName`
  added). Two fixtures live under `tests/fixtures/api/`; conformance
  test asserts the response is a superset of both.
- **Polymorphic `tag` table** (Assumption rewritten) — global `tag`
  table (id, name UNIQUE, color hex, label, timestamps) plus
  `tag_assignment(tag_id FK, entity_type ENUM, entity_id, UNIQUE on the
  three-tuple)`. Enum at MVP:
  `{'game', 'indexer', 'notification', 'release'}`. Same tag spans
  multiple entity types. Tag-row delete cascades the assignments;
  entity delete cascades via per-entity-type cleanup hook.

### Housekeeping deltas (cross-spec consistency)

- FR-015 (security schemes) — bearer JWT removed; only API key + cookie
  session are advertised (per spec 010's clarified FR-022).
- FR-022 (rate limit) — bumped to **10 req/min/source-IP** to align
  with spec 010 FR-010a; covers `/auth/login`, `/auth/setup`, and
  `/auth/oidc/callback`.
- FR-023 — repurposed to document the `/api/v3/health` rate-limit
  exemption for Uptime-Kuma (formerly the redundant 1/min setup limit).

### Migration delta

`0013_api.py` creates:
- `tag (id PK, name VARCHAR UNIQUE, color VARCHAR, label VARCHAR, created_at, updated_at)`
- `tag_assignment (tag_id FK, entity_type ENUM, entity_id INT, UNIQUE(tag_id, entity_type, entity_id))`
- `queue_entry` per the existing inline plan
- `idempotency_cache (key, endpoint, request_body_hash VARCHAR, response_status INT, response_body BLOB, created_at, expires_at)`

The `request_body_hash` column is the JCS-canonical SHA-256 hash; the
schema does not store the raw body.
