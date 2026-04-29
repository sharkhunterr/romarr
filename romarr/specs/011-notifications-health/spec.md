# Feature Specification: Notifications & Health

**Feature Branch**: `011-notifications-health` (branch creation skipped: git repo lives in parent dir)
**Created**: 2026-04-29
**Status**: Draft
**Depends on**:
- `001-foundation` — `Game`, `Release`, `Dump`, `Platform` value shapes
  consumed by event payloads.
- `002-metadata-aggregation` — Fernet encryption helper re-used to encrypt
  `apprise_url` at rest.
- `004-indexers` — `IndexerHealthIssue` producer surfaces here through the
  health-check engine; the Indexers spec already wired the production side.
- `005-download-clients` — connection-test helpers consumed by health checks.
- `006-profiles` — sandboxed Jinja2 engine reused for message templates.
- `008-import-pipeline` — emits `OnImport`/`OnUpgrade`/`OnFail` events into
  the in-process channel that this feature consumes.
- `009-library-exporters` — emits library-related health events
  (path heartbeat, disk space) into the same channel.
- `010-auth-multiuser` — admin-only refresh endpoint; `OnHealthIssue`
  history attribution via the user-id FK.
**Input**: User description: "Build the notifications layer using Apprise as the unified backend, plus Sonarr/Radarr-compatible webhooks for ecosystem tooling. Seven event types with Jinja2 templates. Health check engine with debounced OnHealthIssue emission and a /api/v3/health endpoint for dashboards."

## Clarifications

### Session 2026-04-29

- Q: Is `GET /api/v3/health` fully public, or does it tier the response by auth? → A: Tiered. Public callers (no auth) receive the top-level `{status: "ok" | "warning" | "error"}` and HTTP 200 only — sufficient for Uptime-Kuma probes. Authenticated callers (any role) receive the full per-component breakdown with messages. Component messages can leak topology (third-party services, credential states) and MUST NOT reach unauthenticated callers
- Q: How does the `OnHealthIssue` debounce survive a process restart so a failing-then-restarting Romarr doesn't re-spam the operator? → A: Persist the last-emitted state per component on the `health_check` table (extend existing FR-018 schema with a `last_emitted_state` column). On every cycle (including the first post-restart cycle), the engine compares the new check result to the persisted last-emitted state, not to in-memory state. Transitions are computed against the persisted value; same-state means no emission. Restarts are invisible to subscribers
- Q: How is the Sonarr v3 webhook shape mapped onto Romarr's Game/Release domain? → A: Sonarr v3 envelope with a documented semantic remap: `series ↔ Game` (`series.title = game.title`, `series.tvdbId = game.igdb_id`, `series.path = library.path`), `episodes[0] ↔ Release` (`title`, `seasonNumber = 0`, `episodeNumber = release.id`), `release.quality.quality.name = release.format`, `release.indexer = indexer.name`. The full field-by-field cross-walk lives in `/api/v3/notification/webhook-payloads.md`. Schema validators on the consumer side pass; downstream tools (Notifiarr, Homepage) treat the keys as opaque structural contracts
- Q: What auth gates the notification endpoints? → A: Admin-only on all mutating endpoints (POST / PUT / DELETE) AND on the test endpoint (`POST /notification/{id}/test` triggers outbound HTTP to the configured URL — admin gate, same SSRF-rationale as spec 005's connectivity test). Reads (`GET /notification`, `GET /notification/{id}`, `GET /notification/schema`) accessible to any authenticated user. `/api/v3/health` is tiered per Q1; `POST /api/v3/health/refresh` is admin-only per existing FR-023
- Q: Should Romarr load Apprise custom plugins from `data/apprise-plugins/`? → A: NO at MVP — built-ins only. Custom plugin loading is gated behind an explicit env flag `ROMARR_APPRISE_ALLOW_CUSTOM_PLUGINS` (default `false`); flipping it on is the operator's explicit acknowledgement that the directory is a code-execution surface. Apprise's 80+ built-in providers cover every realistic MVP target

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Operator gets a Discord ping on every import (Priority: P1)

A Romarr operator wants their Discord channel to ding every time
a Romarr import succeeds. They configure a notification with a
Discord webhook URL (Apprise format `discord://...`),
`on_import = true`, and an empty tag filter. Imports trigger a
formatted message in Discord within seconds.

**Why this priority**: This is the headline notification path. If
this doesn't work, the entire feature is moot.

**Independent Test**: Configure one notification with a
respx-mocked Discord webhook; trigger a synthetic OnImport event;
assert the mock received a POST with the rendered message body.

**Acceptance Scenarios**:

1. **Given** a notification with `on_import = true` and a Discord
   Apprise URL, **When** the import pipeline emits an `OnImport`
   event, **Then** the configured channel receives the rendered
   default template within 5 seconds and the notification's
   `last_status` records success.
2. **Given** a notification with `on_import = false`, **When** the
   same event fires, **Then** the channel is NOT pinged and no row
   in `last_status` updates for that notification.
3. **Given** the Apprise URL is malformed at create time, **When**
   the operator POSTs the configuration, **Then** the response is
   HTTP 400 with the error message Apprise itself returned (no
   custom validation on top of Apprise's own).

---

### User Story 2 — Notifiarr consumes Sonarr-format webhooks (Priority: P1)

A Romarr operator runs Notifiarr (or Tautulli-style integrations,
or Homepage dashboard). They add a "Webhook" notification target
pointing at Notifiarr's Romarr-app endpoint. Romarr POSTs a
Sonarr-format JSON payload on every grab/import/upgrade — Notifiarr
sees Romarr as a Sonarr-compatible *arr.

**Why this priority**: This is the constitutional bridge to the
*arr ecosystem (Article XIV — webhook payloads must match
Sonarr/Radarr formats). Without this, the integration story
collapses.

**Independent Test**: Configure a Webhook notification target
pointing at a respx-mocked URL; emit OnGrab + OnImport synthetic
events; assert the captured POST bodies validate against the
documented Sonarr v3 fixtures.

**Acceptance Scenarios**:

1. **Given** a Webhook notification with `on_grab = true,
   on_import = true`, **When** an `OnGrab` event fires, **Then**
   the configured URL receives a POST with `eventType = "Grab"`
   and the documented JSON shape (game / release / indexer /
   downloadClient / downloadId).
2. **Given** the same setup, **When** an `OnImport` event fires
   for an upgrade, **Then** the captured POST has
   `eventType = "Download"` and `isUpgrade = true`.
3. **Given** the Notifiarr endpoint is temporarily unreachable
   (5xx errors), **When** the webhook fires, **Then** the system
   retries 3 times with exponential backoff (1 s → 5 s → 30 s);
   final failure records `last_status = "failed"` and
   `last_error` carries the structured reason.

---

### User Story 3 — Operator validates the Apprise URL with one click (Priority: P1)

The operator just configured a new ntfy notification. Before
relying on it, they hit the "Test" button; Romarr emits a
synthetic `OnImport` event with placeholder data; the operator
sees the test message arrive (or sees a structured error if it
didn't).

**Why this priority**: Validating notifications post-deployment
is painful (you have to wait for a real event). The test button
is the operator's confidence gate.

**Independent Test**: Configure a notification with a respx-mocked
ntfy URL; POST `/api/v3/notification/{id}/test`; assert the mock
received the synthetic message body and the API response carries
`success = true, message = "Test notification sent successfully"`.

**Acceptance Scenarios**:

1. **Given** a configured notification, **When** the operator POSTs
   `/api/v3/notification/{id}/test`, **Then** a synthetic
   `OnImport` event with placeholder values (Test Game, Test
   Release) is fired through the same dispatcher that real events
   use; the response carries success or a structured error.
2. **Given** the Apprise URL points to an unreachable endpoint,
   **When** the test runs, **Then** the response is HTTP 200 with
   `success = false` and the underlying network error is reported
   structured (no stack trace in production).

---

### User Story 4 — Health endpoint feeds the dashboard and Uptime-Kuma (Priority: P2)

The operator's Homepage dashboard polls Romarr's
`GET /api/v3/health` every 60 seconds; Uptime-Kuma probes the same
endpoint for HTTP 200 + `status = "ok"`. The endpoint summarises
the per-component health state (indexers, download clients, DAT
freshness, disk space, DB, metadata providers, library paths) for
external monitoring.

**Why this priority**: The dashboard integration is one of the
core *arr ecosystem features; without it, Romarr feels disconnected
from the homelab observability stack.

**Independent Test**: Inject one failing indexer + one healthy
indexer + a low-disk-space library + an old DAT (40 days);
GET `/api/v3/health`; assert the response groups results per
component category, the overall status is `warning` (because the
worst severity is `warning`), and the failing components carry
their structured messages.

**Acceptance Scenarios**:

1. **Given** all components healthy, **When** the operator queries
   `GET /api/v3/health`, **Then** the response returns HTTP 200
   with `status = "ok"` and a per-category summary.
2. **Given** at least one component is `warning` and none are
   `error`, **When** queried, **Then** the overall status is
   `warning` and HTTP 200.
3. **Given** at least one component is `error`, **When** queried,
   **Then** the overall status is `error` and HTTP 200 — the
   endpoint never returns 5xx for component issues; only a true
   internal error returns 503.
4. **Given** a request to `POST /api/v3/health/refresh` from an
   admin-authenticated client, **When** received, **Then** all
   health checks rerun synchronously and the latest snapshot is
   returned. Non-admin callers get HTTP 403.

---

### User Story 5 — Debounced OnHealthIssue avoids notification spam (Priority: P2)

An indexer goes down at 14:00 and stays down for 90 minutes.
Romarr runs health checks every 10 minutes (per the future Tasks
spec). Without debouncing, the operator would receive 9 identical
"indexer down" notifications. With debouncing, they get **one** at
14:00 (the ok→warning/error transition) and **one** at 15:30 (the
recovery transition). No spam in between.

**Why this priority**: Notification fatigue erodes trust. Debouncing
is what makes the system useful long-term.

**Independent Test**: Force a check to fail; run the health-check
loop 10 times in a row; assert exactly **one** `OnHealthIssue`
event was emitted; restore the underlying component; run one more
cycle; assert **one** recovery event emitted.

**Acceptance Scenarios**:

1. **Given** a component fails check N+1 after passing check N,
   **When** the engine processes the new result, **Then** it
   transitions ok → warning/error AND emits exactly one
   `OnHealthIssue` event.
2. **Given** the same component continues to fail across N more
   cycles with the same severity, **When** each subsequent cycle
   runs, **Then** no new event is emitted (the row's
   `last_seen_at` updates but state is unchanged).
3. **Given** a component recovers (warning/error → ok) on cycle
   M, **When** the cycle runs, **Then** the engine emits exactly
   one recovery `OnHealthIssue` event with `state = "recovered"`.
4. **Given** a component escalates warning → error, **When** the
   engine processes the new result, **Then** it emits exactly one
   `OnHealthIssue` event because the state changed; downgrades
   error → warning behave symmetrically.

---

### User Story 6 — Tag filter scopes notifications per channel (Priority: P2)

The operator runs two notifications: "Discord — Family" listens
on imports tagged `family-friendly`, and "Discord — Power" listens
on imports tagged `mature`. An import for a tagged Game routes
exclusively to the matching channel.

**Why this priority**: Without tag filtering, a single Discord
channel would receive every event; the operator would have to
manage filtering downstream. This is the simplest scoping
mechanism.

**Independent Test**: Configure two notifications with
disjoint tag filters; emit two `OnImport` events for Games
carrying matching tags; assert each notification only received
its scoped event.

**Acceptance Scenarios**:

1. **Given** a notification with `tags = ["family-friendly"]`,
   **When** an `OnImport` for a Game tagged `["family-friendly",
   "platformer"]` fires, **Then** the notification fires (the
   intersection is non-empty).
2. **Given** the same notification, **When** an `OnImport` for an
   untagged Game fires, **Then** the notification does NOT fire.
3. **Given** a notification with `tags = []` (empty), **When**
   any `OnImport` fires, **Then** the notification fires for
   every Game (empty filter = match all).

---

### User Story 7 — Per-event template overrides (Priority: P3)

The operator wants to use Markdown formatting in their Discord
notifications instead of the default plain-text template. They
override `on_import_format` for their Discord notification with
their own Jinja2 template; future imports use the new format
while all other notifications keep the defaults.

**Why this priority**: Useful but not blocking — defaults work
out of the box.

**Independent Test**: Configure a notification with a custom
`on_import_format`; trigger a synthetic OnImport; assert the
captured Apprise message body matches the custom template
output, not the default.

**Acceptance Scenarios**:

1. **Given** a notification with `on_import_format = '**{{
   game.title }}** imported on **{{ platform.name }}**'`,
   **When** an `OnImport` fires for *Sonic* on Mega Drive,
   **Then** the rendered body is exactly
   `**Sonic the Hedgehog** imported on **Mega Drive**`.
2. **Given** the same notification, **When** the operator's
   template references an unknown variable, **Then** the save
   request is rejected at validation time (HTTP 400) with the
   structured `template_unknown_token` error from spec 006's
   sandbox engine.
3. **Given** a notification with NO `on_import_format` override,
   **When** the same event fires, **Then** the rendered body is
   the documented default template's output.

---

### User Story 8 — Upgrade events fire both OnImport and OnUpgrade (Priority: P3)

A release replaces an existing Dump (per the import pipeline's
keep_dump_history logic). Romarr fires both `OnImport` and
`OnUpgrade` so notifications subscribed to either receive the
event.

**Why this priority**: Useful for operators who want a single
"new file" feed (subscribe to OnImport) versus a separate
"upgrade" feed (subscribe to OnUpgrade only).

**Independent Test**: Trigger an import that replaces an existing
Dump; configure two notifications: one with `on_import = true,
on_upgrade = false` and one with `on_import = false, on_upgrade
= true`; assert both fire exactly once.

**Acceptance Scenarios**:

1. **Given** an import replaces an existing Dump, **When** the
   pipeline emits both events, **Then** notifications subscribed
   to either flag receive the appropriate event with the
   appropriate template; the same notification subscribed to
   both flags receives **both** events (and thus two messages).

---

### Edge Cases

- An Apprise URL becomes invalid post-creation (e.g., the Discord
  webhook is rotated server-side) → the next emission fails;
  `last_status = "failed"` records the error; the operator gets
  no further messages until they fix the URL. There is no health
  alert on a failing Apprise URL — the operator's responsibility
  to monitor `last_status`.
- A template renders to an empty string → Apprise rejects the
  message; the failure is logged with reason
  `empty_message_after_render`.
- An emoji-heavy default template lands on a destination that
  rejects emoji (e.g., a strict SMS gateway via Apprise) →
  Apprise's own behaviour applies; Romarr does not strip emoji.
- A notification with all event flags `false` is created → rejected
  at validation as `no_event_subscribed`.
- The webhook target's URL contains a credential leak risk
  (e.g., `?token=...` query param) → Romarr stores it as part of
  the Apprise URL (encrypted) but does NOT expose it in any GET
  response; the API redacts the path's query.
- A health check times out (e.g., an unresponsive indexer's caps
  endpoint) → the check is recorded with status `error` and
  message `timeout`; the next cycle re-runs.
- DAT freshness check finds no DATs at all → the check returns
  `warning` with message `no_dats_ingested`; this is the
  pre-first-DAT-fetch state and is expected.
- The operator deletes a notification that has events in flight
  → the in-flight event is delivered or fails gracefully; no
  cascade impact.
- Ten thousand `OnImport` events fire in the same minute (e.g.,
  bulk manual import) → the dispatcher consumes them serially
  per notification (Apprise is not async-safe across the same
  endpoint); no event is lost; back-pressure is bounded by an
  in-process queue with a 10 000 event ceiling. Beyond that, new
  events are dropped with a structured warning rather than
  exploding memory.
- Two notifications subscribe to the same event with two custom
  templates → each renders independently; no shared state.
- A health refresh is requested during an in-flight scheduled
  cycle → the manual refresh waits for the scheduled cycle to
  finish, then returns the latest snapshot (no concurrent runs).

## Requirements *(mandatory)*

### Functional Requirements

**Apprise integration**

- **FR-001**: All outbound notifications MUST go through Apprise
  (Constitution Article XIV). No ad-hoc per-service integrations
  are permitted in this feature.
- **FR-001a**: Apprise MUST be initialised at process start with
  custom-plugin loading **disabled** by default. Apprise's
  built-in providers (Discord, Slack, Telegram, Matrix, ntfy,
  Gotify, Pushover, email/SMTP, generic webhook, plus the rest
  of Apprise's 80+ shipped providers) MUST be available; loading
  arbitrary Python files from `data/apprise-plugins/` MUST be
  refused unless the operator explicitly sets
  `ROMARR_APPRISE_ALLOW_CUSTOM_PLUGINS = true`. When the flag is
  off (default), the directory is not consulted; when on, Apprise's
  default plugin-loader behaviour applies. The flag's existence
  is documented in the README/quickstart with a clear warning that
  enabling it makes the directory a code-execution surface.
- **FR-002**: The system MUST persist notification configurations
  in a `notification` table per `data-model.md`. Each row carries
  one Apprise URL, per-event flags, an optional tag filter, and
  optional per-event Jinja2 template overrides.
- **FR-003**: The Apprise URL MUST be encrypted at rest using
  the existing Fernet helper from spec 002.
- **FR-004**: A configuration whose Apprise URL is rejected by
  `Apprise.add(...)` MUST cause the create/update endpoint to
  return HTTP 400 with the underlying Apprise error message; no
  additional URL validation is performed.

**Webhook target (Sonarr/Radarr-compat)**

- **FR-005**: In addition to Apprise URLs, the system MUST
  support a "Webhook" target that POSTs Sonarr v3-format JSON to
  a configured URL. The Webhook target is configured as an
  Apprise URL with the `json://` or `jsons://` scheme — Apprise
  handles the transport, this feature shapes the body.
- **FR-006**: Webhook payloads MUST match Sonarr v3 JSON for the
  documented event types (`Grab`, `Download` for imports, etc.).
  Body schemas are documented at
  `/api/v3/notification/webhook-payloads.md`.
- **FR-006a**: The Sonarr v3 envelope's TV-domain keys MUST be
  populated from Romarr's Game/Release domain via the following
  canonical semantic remap (full field list in
  `/api/v3/notification/webhook-payloads.md`):
  - `series.title` ← `game.title`
  - `series.tvdbId` ← `game.igdb_id` (NULL → 0 fallback)
  - `series.tvMazeId`, `series.imdbId` ← 0 / null
  - `series.path` ← `library.path`
  - `episodes[]` is always exactly one element representing the
    `Release`: `episodes[0].title = release.name`,
    `episodes[0].seasonNumber = 0`,
    `episodes[0].episodeNumber = release.id`
  - `release.quality.quality.name` ← `release.format`
  - `release.indexer` ← `indexer.name`
  - `release.releaseGroup` ← parsed-filename release group
    (when present; empty string otherwise)
  - `downloadId` ← download client's info-hash / nzo_id
  Empty fields MUST be emitted as `0` for numeric Sonarr keys
  and `""` for string keys (never omitted) so consumer schema
  validators always pass. The mapping MUST be documented as the
  canonical contract; consumers (Notifiarr, Homepage, Tautulli)
  treat the keys as opaque envelopes, not as TV-specific.
- **FR-007**: A Webhook target MUST retry on HTTP 5xx and on
  connection errors with exponential backoff: 1 s → 5 s → 30 s
  (3 attempts total). After the third failure the notification's
  `last_status = "failed"` and `last_error` records the
  structured reason.

**Events**

- **FR-008**: The system MUST emit seven event types onto an
  in-process pub/sub channel: `OnGrab`, `OnImport`, `OnUpgrade`,
  `OnFail`, `OnHealthIssue`, `OnDatUpdate`, `OnGameAdded`.
- **FR-009**: An import that replaces a previous Dump MUST emit
  BOTH `OnImport` and `OnUpgrade` (FR per spec 008).
- **FR-010**: Each event payload MUST be a Pydantic model whose
  fields match the documented templates' variable list.

**Templates**

- **FR-011**: The system MUST ship default Jinja2 templates for
  the seven event types as documented; operators MAY override
  any template per notification.
- **FR-012**: Template rendering MUST use the sandboxed engine
  from spec 006 (Article XI compliance — same sandbox primitives,
  same allow-list of filters, no escape paths).
- **FR-013**: A custom template that references an unknown
  variable or function MUST be rejected at save time with a
  structured error pointing to the offending location.

**Tag filtering**

- **FR-014**: A notification with a non-empty `tags` array MUST
  fire only for events whose Game carries at least one matching
  tag (intersection logic).
- **FR-015**: A notification with an empty `tags` array MUST
  fire for every event of its subscribed types (no filter).

**Test endpoint**

- **FR-016**: `POST /api/v3/notification/{id}/test` MUST emit
  a synthetic `OnImport` event with placeholder data through the
  exact same dispatcher that real events use; the response
  carries `success: bool, error_message: str | None`.

**Health checks**

- **FR-017**: The system MUST run a health check engine that
  produces structured results per component category: indexers,
  download clients, DAT freshness, disk space, DB connection,
  metadata providers, library path availability.
- **FR-018**: Health results MUST be stored in a `health_check`
  table with `(component, status, message, last_checked_at,
  first_seen_at, last_seen_at, last_emitted_state)`. Only the
  **current** state is persisted; historical trending is out of
  scope. The `last_emitted_state` column records the most
  recent state for which an `OnHealthIssue` event was successfully
  enqueued (initial value: NULL until the first cycle runs).
- **FR-019**: DAT freshness check MUST emit `warning` for a DAT
  older than 30 days, `error` for one older than 90 days.
- **FR-020**: Disk space check MUST emit `warning` when free
  space is between `min_disk_free_gb` and 1.5× that threshold,
  `error` below `min_disk_free_gb`.

**OnHealthIssue debouncing**

- **FR-021**: An `OnHealthIssue` event MUST be emitted ONLY on
  state transitions: `ok → warning`, `ok → error`,
  `warning → error`, `error → warning`,
  `warning → ok` (recovery), `error → ok` (recovery).
  Repeated failures of the same severity MUST NOT re-emit.
- **FR-021a**: The transition comparison MUST be made against the
  **persisted** `last_emitted_state` column on `health_check`
  (FR-018), NOT against in-memory state. Every successful
  emission MUST update `last_emitted_state` in the same
  transaction so the new value is durable. After a process
  restart, the first cycle MUST consult `last_emitted_state` —
  if it equals the new check's status, no emission fires
  (suppresses post-restart spam); if it differs, the standard
  transition emission rule applies. The first-ever cycle on a
  fresh database (`last_emitted_state IS NULL`) emits ONLY when
  the new status is non-ok; the initial `ok` state does not
  emit.
- **FR-022**: Recovery events MUST carry `state = "recovered"`
  in the payload so notification templates can render
  `"<component> is back to healthy"` shapes.

**API**

- **FR-023**: The system MUST expose:
  - `GET    /api/v3/notification` (list)
  - `GET    /api/v3/notification/{id}` (detail; Apprise URL
    redacted)
  - `POST   /api/v3/notification` (create)
  - `PUT    /api/v3/notification/{id}` (update)
  - `DELETE /api/v3/notification/{id}` (revoke)
  - `POST   /api/v3/notification/{id}/test` (synthetic event)
  - `GET    /api/v3/notification/schema` (lists implementations:
    `apprise`, `webhook`)
  - `GET    /api/v3/health` (current snapshot)
  - `POST   /api/v3/health/refresh` (admin only)
- **FR-024**: `GET /api/v3/notification/{id}` MUST redact the
  full `apprise_url` value, returning only a fingerprint or the
  scheme prefix (e.g., `discord://...`); the full plaintext URL
  is never returned post-creation.
- **FR-024b**: All mutating notification endpoints
  (`POST /api/v3/notification`, `PUT /api/v3/notification/{id}`,
  `DELETE /api/v3/notification/{id}`,
  `POST /api/v3/notification/{id}/test`) MUST require the caller
  to hold the `admin` role provided by the Auth spec. The test
  endpoint is admin-gated because it fires outbound HTTP to the
  configured Apprise URL — same SSRF-rationale as spec 005's
  connectivity-test endpoint. Read endpoints
  (`GET /api/v3/notification`, `GET /api/v3/notification/{id}`,
  `GET /api/v3/notification/schema`) MUST be accessible to any
  authenticated user. The Apprise URL is redacted in
  `GET /api/v3/notification/{id}` per FR-024 regardless of
  caller role. Same pattern as specs 003 / 004 / 005 / 006 /
  007 / 008 / 009.

- **FR-024a**: `GET /api/v3/health` MUST tier its response by
  authentication state. Unauthenticated callers MUST receive
  ONLY the top-level `{status: "ok" | "warning" | "error"}`
  field and HTTP 200 — no per-component breakdown, no per-check
  messages, no last-checked timestamps. Authenticated callers
  (any role; `read` scope on API keys is sufficient) MUST
  receive the full snapshot including the per-category groupings
  and structured messages defined in User Story 4. The endpoint
  MUST NOT return HTTP 5xx for component issues regardless of
  caller — only a true internal failure (e.g., database
  unreachable) returns 503. This protects against topology and
  credential-state disclosure to unauthenticated scanners while
  preserving Uptime-Kuma probe simplicity.

**Back-pressure & resilience**

- **FR-025**: Event delivery MUST be non-blocking on the emitting
  side: the import pipeline / scanner / scheduler call into the
  pub/sub channel and continue without awaiting Apprise's HTTP
  call.
- **FR-026**: An in-process queue MUST bound the in-flight event
  count to 10 000; on overflow, oldest pending events are dropped
  with a structured warning recorded in the dispatcher's logs.
- **FR-027**: The dispatcher MUST process events serially per
  notification (one at a time per `notification.id`) to avoid
  thundering Apprise endpoints. Different notifications can be
  processed in parallel.

### Key Entities

- **Notification**: A configured subscription to a subset of
  events with one Apprise URL, optional tag filter, optional
  per-event template overrides, and audit metadata
  (`last_used_at`, `last_status`, `last_error`).
- **Event**: An in-memory Pydantic payload emitted by upstream
  modules onto the pub/sub channel. Seven event types are
  documented (`OnGrab`, `OnImport`, `OnUpgrade`, `OnFail`,
  `OnHealthIssue`, `OnDatUpdate`, `OnGameAdded`).
- **Health Check Result**: A `(component, status, message)` triple
  persisted in `health_check` representing the **current** state
  of a single component.
- **Health Snapshot**: The grouped output of `/api/v3/health`,
  collapsed by category, with an overall status (`ok` /
  `warning` / `error`) for dashboards.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A configured Discord notification subscribed to
  `OnImport` receives the rendered default template within 5
  seconds of an import in 100% of test cases (excluding network
  delays beyond Apprise's own retry).
- **SC-002**: A Webhook target receiving 5xx errors retries
  exactly 3 times with the documented backoff
  (1 s → 5 s → 30 s); after the third failure
  `last_status = "failed"` in 100% of test cases.
- **SC-003**: A Sonarr v3-format webhook payload validates
  against the documented Sonarr fixtures byte-for-byte (modulo
  ordering of optional fields) in 100% of test cases.
- **SC-004**: A failing health check produces exactly **one**
  `OnHealthIssue` event on the first failure and **one** recovery
  event on first recovery; persistent failure across 10
  cycles produces zero additional events (SC-005 invariant).
- **SC-005**: `GET /api/v3/health` returns within 200 ms p95 from
  cached state; with `?refresh=true` (or via the explicit
  `POST /api/v3/health/refresh`), it runs all checks
  synchronously and returns within 5 seconds p95.
- **SC-006**: Inspecting the database file shows zero plaintext
  Apprise URLs; the API's `GET /notification/{id}` returns only
  the redacted form.
- **SC-007**: A custom template referencing an unknown variable
  is rejected at save time with a structured error in 100% of
  injected-bad-template fixtures (≥ 10 cases).
- **SC-008**: With 10 000 events queued in a single minute (bulk
  manual import simulation), the dispatcher consumes them
  serially per notification, and overflow beyond 10 000 produces
  the documented structured warning rather than crashing the
  process.
- **SC-009**: Test coverage on the notifications module MUST be
  at least 75%.

## Assumptions

These resolve the OPEN CLARIFICATIONS supplied with the input,
applying the operator's proposals.

- **Health check trending**: only the current state is persisted
  in `health_check`. Historical trending (line charts of uptime
  per component) is deferred to v1+; operators who want trending
  scrape `GET /api/v3/health` from Uptime-Kuma.
- **Severity in OnHealthIssue templates**: yes. The template
  receives `severity` (`warning`/`error`/`recovered`) plus a
  default emoji prefix (`⚠️` for warning, `🚨` for error,
  `✅` for recovery). Templates may render their own.
- **Custom Apprise plugins**: disabled by default at MVP
  (FR-001a). The 80+ built-in Apprise providers cover every
  documented operator need. Loading arbitrary `.py` files from
  `data/apprise-plugins/` requires the operator to set
  `ROMARR_APPRISE_ALLOW_CUSTOM_PLUGINS = true` — an explicit
  acknowledgement that the directory becomes a code-execution
  surface for anyone with write access to it.
- **Webhook retry policy**: 3 attempts with exponential backoff
  (1 s, 5 s, 30 s); after the third failure mark
  `last_status = "failed"` and store the last error in
  `last_error`. No further retries until the operator manually
  re-triggers via the Test button.

Other assumptions:

- The seven event types are the MVP set; adding an 8th is a code
  change in the import pipeline / scanner plus a column addition
  on `notification`. Routine.
- Tag filtering uses the existing `tag` system (a separate spec
  introduces the `tag` table; this feature only reads it).
  Operators with no tags configured see "match all" semantics
  via the empty-array path.
- `OnHealthIssue` events flow through the same dispatcher as
  every other event; subscribers can opt in via
  `on_health_issue = true`. There is no separate health
  notification channel.
- The `/api/v3/health` endpoint is **tiered by auth** (FR-024a):
  unauthenticated callers receive only the top-level `status`
  field plus HTTP 200, sufficient for Uptime-Kuma probes;
  authenticated callers (any role — `read` scope or session)
  receive the full per-component breakdown including status
  messages. The minimal public surface keeps probes simple while
  preventing topology disclosure to unauthenticated scanners.

### Out of Scope

- UI for notification config (UI spec).
- Custom rule engine for event filtering (e.g., "only notify on
  imports of Games rated > 8") — deferred to v1+.
- Notification batching / digests (deferred to v1+).
- Push notifications via Web Push to PWA (UI spec, separate
  flow).
- SMTP server integration beyond what Apprise provides.
- Per-channel throttling (Apprise handles per-service rate
  limits).
- Health check **history** for trending (deferred to v1+).
