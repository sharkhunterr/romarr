# Implementation Plan: Notifications & Health

**Branch**: `011-notifications-health` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification at `specs/011-notifications-health/spec.md`
**Depends on**: `001-foundation`, `002-metadata-aggregation`, `004-indexers`,
`005-download-clients`, `006-profiles`, `008-import-pipeline`,
`009-library-exporters`, `010-auth-multiuser`.

## Summary

The Notifications & Health subsystem is the closing piece of Romarr's
operational story. It does three things on top of the existing
upstream specs:

1. **A notification engine** that consumes events from the in-process
   pub/sub channel (already populated by specs 008 and 009) and
   delivers them via Apprise (Constitution Article XIV) or a
   Sonarr-format Webhook target. Per-event Jinja2 templates ride on
   spec 006's sandbox.
2. **A health-check engine** that probes every operational component
   (indexers, download clients, DAT freshness, disk space, DB,
   metadata providers, library paths) and emits debounced
   `OnHealthIssue` events on state transitions only.
3. **The `/api/v3/health` endpoint** that summarises the current
   snapshot for external monitors (Uptime-Kuma, Homepage dashboard,
   any HTTP probe).

This feature ships **functions, not crons**. The Tasks/Scheduler
spec wires the periodic health-check loop and the dispatcher
back-pressure handler.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: `apprise>=1.8` (single dependency — Article
XIV), SQLAlchemy 2.0 (async), Pydantic v2, Alembic, lxml/jinja2
(re-used from spec 006), httpx (for the Webhook target's POST), structlog.
**No new HTTP client.**
**Storage**: SQLite default / PostgreSQL 15+ optional. Two new tables
(`notification`, `health_check`); no column additions on existing
tables.
**Testing**: pytest, pytest-asyncio, pytest-cov, respx (mocks for
Discord / ntfy / Notifiarr URLs), freezegun (debounce timing,
backoff windows), TestClient (FastAPI), captured Sonarr fixtures
for the Webhook payload conformance gate.
**Target Platform**: Linux server in the Romarr Docker image.
**Project Type**: Backend Python module added under
`src/romarr/notifications/`.
**Performance Goals**:
- Per-event delivery latency < 5 s p95 from emit to Apprise
  POST (excluding the destination's own latency).
- `GET /api/v3/health` from cache < 200 ms p95.
- `POST /api/v3/health/refresh` synchronous run < 5 s p95.
- Dispatcher throughput: 100 events/second sustained per
  configured notification.
**Constraints**:
- All notifications go through Apprise (Article XIV; FR-001).
- Webhook payloads must match Sonarr v3 format (Article XIV;
  FR-006).
- Health checks emit ONLY on state transitions (FR-021).
- Apprise URL encrypted at rest (FR-003).
- `/api/v3/health` is unauthenticated by design for Uptime-Kuma
  (assumption documented).
**Scale/Scope**:
- Notifications per instance: typically 1-5 (Discord + ntfy +
  Notifiarr); up to ~50 plausible.
- Events per day: tens to hundreds for a power user.
- Health check components: indexers + download clients +
  libraries + DAT + DB + metadata providers — typically
  10-50 components total.

## Constitution Check

*Gate: must pass before Phase 0 research and again after Phase 1 design.*

| Article | Gate | Status |
|---------|------|--------|
| III — Technology Stack (Locked) | Apprise as the single notification backend; no `requests`/`urllib3`. | ✅ Conformant. |
| XIV — Notifications | All outbound notifications go through Apprise; ad-hoc per-channel integrations are forbidden; webhook payloads match Sonarr/Radarr formats so Notifiarr consumes Romarr events transparently. The 7 documented event types match the constitutional list. | ✅ Conformant — encoded in FR-001, FR-005, FR-006, FR-008. |
| XVI — Quality Gates | ≥ 75% coverage on `notifications/`; perf budgets above; zero ruff warnings. | ✅ Conformant — encoded in SC-009 + Hardening phase. |
| XVII — Idempotency & Safety | Debounced health emissions (FR-021); idempotent test endpoint; encrypted Apprise URLs; webhook retries bounded. | ✅ Conformant. |

**Result**: GREEN. No constitutional violations; **Complexity
Tracking** stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/011-notifications-health/
├── plan.md              # this file
├── spec.md              # user-value specification
├── data-model.md        # notification + health_check tables + value types
├── tasks.md             # 10-phase task list
└── checklists/
    └── requirements.md  # spec-quality checklist
```

### Source Code (additions to the existing repo)

```text
src/romarr/
├── notifications/                       # NEW — top-level module
│   ├── __init__.py                       # public re-exports: NotificationEngine, HealthEngine, dispatch_event
│   ├── types.py                          # EventType, EventPayload, HealthStatus, HealthSnapshot, ComponentCategory
│   ├── errors.py                         # NotificationError, AppriseInvalidUrl, TemplateError, WebhookRetryExhausted, HealthCheckTimeout
│   ├── channel.py                        # async in-process pub/sub channel + 10k-event back-pressure
│   ├── apprise_wrapper.py                # thin Apprise wrapper with URL validation + decrypt-at-call
│   ├── webhook.py                        # Sonarr-format webhook target with retry policy
│   ├── templates/
│   │   ├── __init__.py
│   │   ├── defaults.py                   # the 7 default Jinja2 strings
│   │   ├── renderer.py                   # composes spec 006's NamingTemplateEngine sandbox; renders per-event templates
│   │   └── payload_builders.py           # builds Apprise payload + Sonarr-format webhook payload from EventPayload
│   ├── dispatcher.py                     # async dispatcher: dequeue → for each enabled notification → match flag+tags → render → deliver
│   ├── health/
│   │   ├── __init__.py
│   │   ├── engine.py                     # health-check engine; runs all checks; produces snapshot
│   │   ├── checks/
│   │   │   ├── __init__.py
│   │   │   ├── indexer.py                # caps reachable + valid XML
│   │   │   ├── download_client.py        # connection test
│   │   │   ├── dat_freshness.py          # 30/90-day thresholds
│   │   │   ├── disk_space.py             # min_disk_free_gb + 1.5x warning
│   │   │   ├── db.py                     # round-trip query under 1 s
│   │   │   ├── metadata_provider.py      # each provider's health_check()
│   │   │   └── library_path.py           # stat() within 5 s
│   │   └── debouncer.py                  # PURE: state-transition detection
│   ├── models.py                         # Notification + HealthCheck SQLAlchemy 2.0 models
│   ├── schemas.py                        # Pydantic *Read/*Create/*Update + TestNotificationResponse, HealthSnapshotResponse
│   └── api/                              # FastAPI router stubs
│       ├── __init__.py
│       ├── notifications.py              # /api/v3/notification* + /test
│       ├── health.py                     # /api/v3/health + /health/refresh
│       └── webhook_payloads_md.py        # static doc generator for /api/v3/notification/webhook-payloads.md
└── db/
    └── alembic/
        └── versions/
            └── 0011_notifications.py     # NEW migration

tests/
├── notifications/
│   ├── conftest.py                       # respx fixtures, sample notifications, fake event channel
│   ├── test_models.py
│   ├── test_migration_0011.py
│   ├── test_channel.py                   # back-pressure (SC-008), serial-per-notification dispatch
│   ├── test_apprise_wrapper.py           # ≥ 5 services mocked: Discord, Telegram, ntfy, Slack, Gotify
│   ├── test_webhook_retry.py             # 1/5/30 backoff (SC-002)
│   ├── test_webhook_sonarr_compat.py     # byte-for-byte vs. captured Sonarr fixtures (SC-003)
│   ├── templates/
│   │   ├── test_defaults.py              # all 7 default templates render correctly
│   │   ├── test_renderer.py              # uses spec 006's sandbox
│   │   ├── test_unknown_variable.py      # ≥ 10 bad templates rejected at save (SC-007)
│   │   └── test_payload_builders.py      # Apprise vs Sonarr-webhook shapes
│   ├── test_dispatcher.py                # tag filtering, event-flag filtering
│   ├── test_test_endpoint.py             # synthetic OnImport flows through real dispatcher
│   ├── health/
│   │   ├── test_engine.py                # all check categories run
│   │   ├── checks/
│   │   │   ├── test_indexer.py
│   │   │   ├── test_download_client.py
│   │   │   ├── test_dat_freshness.py     # 30 / 90 day boundaries
│   │   │   ├── test_disk_space.py        # warning vs error threshold
│   │   │   ├── test_db.py
│   │   │   ├── test_metadata_provider.py
│   │   │   └── test_library_path.py
│   │   ├── test_debouncer.py             # state-transition logic (SC-004)
│   │   └── test_snapshot.py              # GET /api/v3/health response shape
│   └── api/
│       ├── test_notification_endpoints.py
│       ├── test_test_endpoint.py
│       ├── test_health_endpoint.py
│       ├── test_health_refresh_admin_only.py
│       └── test_webhook_payloads_doc.py  # static doc renders the documented schemas
└── fixtures/
    ├── notifications/
    │   ├── apprise_responses/             # canned responses from Discord, ntfy, etc.
    │   ├── sonarr_webhook_fixtures/       # captured from a real Sonarr instance
    │   │   ├── grab_payload.json
    │   │   ├── download_payload.json
    │   │   ├── upgrade_payload.json
    │   │   └── health_payload.json
    │   ├── bad_templates/                 # ≥ 10 deliberately broken templates
    │   └── health_check_corpus.jsonl
```

**Structure Decision**: keep the **debouncer** as a pure function in
`health/debouncer.py` so its state-transition logic can be tested
without I/O. The dispatcher and the health engine are async; the
template renderer and the payload builders are pure (consume an
`EventPayload`, return a string or a dict). The 7 default templates
live as Python strings under `templates/defaults.py` so they are
diffable in PRs and shipped without filesystem dependency.

The Webhook target is **not** a separate Apprise plugin; it's a
small async function in `webhook.py` that the dispatcher invokes
when the notification's `apprise_url` matches the `webhook://` or
`webhook+sonarr://` scheme. Apprise still owns transport for every
non-webhook URL.

The `/api/v3/health` endpoint is intentionally **unauthenticated**
for Uptime-Kuma compatibility (see assumption in `spec.md`); to
keep that safe we redact internal error messages in unauthenticated
responses (the full structured details are admin-only via a
header-based check).

## Phase 0 — Research

Three small research items resolved before code; results captured
in `research.md` if confirmation is needed at code time.

1. **Apprise async-safety** — Apprise's `notify()` is sync. We
   wrap it in `asyncio.to_thread` per call. Apprise itself
   handles per-service rate limits internally; we don't add our
   own throttling on top.
2. **Sonarr v3 fixture provenance** — captured from a real Sonarr
   v4 installation's `OnDownload` and `OnGrab` webhook hooks (Sonarr
   v3 API is preserved in v4). Fixtures committed under
   `tests/fixtures/notifications/sonarr_webhook_fixtures/`. The
   conformance test asserts byte-for-byte match modulo the order of
   optional fields.
3. **Debouncer state model** — store `(component, status)` pairs;
   on each cycle compare the new status to the persisted one;
   transition emits exactly one event; same-status updates only
   the `last_seen_at` timestamp. Pure function fed by the
   `health_check` table.

No further research items.

## Phase 1 — Design Outputs

- `data-model.md` — DDL for `notification`, `health_check`; the
  value types `EventType`, `EventPayload`, `HealthStatus`,
  `HealthSnapshot`.
- No `contracts/` — full payload schemas come from the documented
  Sonarr fixtures; the static `webhook-payloads.md` doc is shipped
  by the API spec.
- No `quickstart.md` — operator quickstart is the README's
  "Notifications" section; this spec ships the API.

### Re-check: Constitution after design

Same table as above; nothing in the design pulls a constraint.
**Result**: GREEN.

## Complexity Tracking

> *Empty.* No constitutional violations. No deviations to justify.

## Clarification Deltas (Session 2026-04-29)

The 5 clarifications recorded in `spec.md` add the following architectural
constraints to this plan:

- **Tiered `/api/v3/health` response** (FR-024a) — public callers
  (no auth) receive ONLY `{status: "ok" | "warning" | "error"}` plus
  HTTP 200. Authenticated callers (any role; `read` scope sufficient)
  receive the full per-component breakdown with messages. Component
  messages CAN leak topology and MUST be auth-gated. Internal failure
  is the only path to HTTP 503.
- **Persistent debounce state across restarts** (FR-018 amended +
  FR-021a) — `health_check.last_emitted_state` column. Every cycle —
  including the first post-restart cycle — compares the new check
  result to this persisted value, NOT to in-memory state. Successful
  emissions update the column in the same transaction. Restarts are
  invisible to subscribers; no spam.
- **Sonarr v3 envelope semantic remap** (FR-006a) — the webhook target
  emits Sonarr-shaped JSON with documented mapping:
  `series.title ← game.title`, `series.tvdbId ← game.igdb_id`
  (NULL→0), `series.path ← library.path`; `episodes[]` always one
  element representing the Release; `release.quality.quality.name ←
  release.format`; `release.indexer ← indexer.name`; `release.releaseGroup`
  ← parsed-filename group (or empty). Empty fields emit as `0` for
  numeric keys / `""` for string keys (never omitted). Full cross-walk
  documented at `/api/v3/notification/webhook-payloads.md`.
- **Admin-only mutations + test endpoint** (FR-024b) — POST/PUT/
  DELETE on notifications AND `POST /notification/{id}/test` require
  admin (the test endpoint fires outbound HTTP — same SSRF rationale
  as spec 005's `/test`). Reads accessible to any authenticated user.
- **Apprise custom plugins disabled by default** (FR-001a) — Apprise
  initialised at process start with custom-plugin loading OFF. The
  built-in 80+ providers cover MVP. Loading from
  `data/apprise-plugins/` requires
  `ROMARR_APPRISE_ALLOW_CUSTOM_PLUGINS = true`. README documents the
  flag with a clear "code execution surface" warning.

### Migration delta

`0011_notifications.py` adds to `health_check`:
- `last_emitted_state VARCHAR NULL` (NULL = never emitted; otherwise
  one of `'ok' | 'warning' | 'error'`)

The Apprise initialisation flag is config-only, not a schema change.
