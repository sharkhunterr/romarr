# Feature Specification: REST API & WebSocket

**Feature Branch**: `013-rest-api-websocket` (branch creation skipped: git repo lives in parent dir)
**Created**: 2026-04-29
**Status**: Draft
**Depends on**: every prior spec — this is the unified HTTP surface that
exposes every spec's functions as REST endpoints under `/api/v3/*` plus
the SignalR-compat WebSocket at `/signalr/messages`.
**Input**: User description: "Build the complete REST API surface, modeled on Sonarr v3 / Radarr v3 conventions wherever resources overlap so existing tooling (Notifiarr, Recyclarr, Janitorr, Homepage, Homarr, Organizr) works transparently. Plus a SignalR-compat WebSocket, OpenAPI 3.1, uniform pagination, idempotency keys, rate limiting."

## Clarifications

### Session 2026-04-29

- Q: How is `Idempotency-Key` body equality determined on replay? → A: Hash of the canonicalised JSON body using RFC 8785 (JSON Canonicalization Scheme — keys sorted alphabetically, no insignificant whitespace, normalized number representation). The hash is stored on the `idempotency_cache` row; the replay's body hash is compared. Multipart and binary bodies (rare on Romarr) fall back to byte-comparison
- Q: Does the `/signalr/messages` WebSocket implement the actual SignalR protocol or "SignalR-shaped" plain JSON-over-WebSocket? → A: Plain JSON-over-WebSocket with SignalR-shaped message envelopes (`{messageType: string, body: object}`); the constitutional "SignalR-compat" mandate refers to the path and the `messageType` event taxonomy, not the SignalR wire protocol (negotiate / hub-methods / binary mode are NOT implemented). Server-side ping every 30 s; clients ping back. Framing documented at `/api/v3/notification/webhook-payloads.md` alongside webhook payloads
- Q: Should `GET /api/v3/system/status` tier its response by auth like `/api/v3/health`? → A: Yes — same pattern as spec 011 FR-024a. Public callers receive `{version, isProduction}` only (sufficient for Sonarr-shape probe-recognition); authenticated callers (any role) receive the full field set (`urlBase`, `osName`, `runtimeVersion`, `appData`, `startTime`, `instanceName`). Minimises topology disclosure to unauthenticated scanners while preserving the *arr peer-recognition contract
- Q: Sonarr v3 vs v4 field set on `system/status`? → A: Emit the UNION. v3-era tools (Notifiarr, Recyclarr, Homepage as originally written) consume v3 keys; v4-era tools consume v4 additions (`databaseType`, `databaseVersion`, `migrationVersion`, `runtimeName`). JSON consumers tolerate unknown keys, so the union strictly broadens compat without breaking either era
- Q: What's the scope and entity-type model for tags? → A: Polymorphic. A global `tag` table (id, name unique, color hex, label) plus a `tag_assignment` association table `(tag_id, entity_type ENUM, entity_id)` where `entity_type ∈ {'game', 'indexer', 'notification', 'release'}`. Same tag (e.g., `family-friendly`) can be applied across multiple entity types without duplicating definitions; rename / recolor / merge work centrally

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Notifiarr discovers Romarr as a Sonarr-shaped *arr (Priority: P1)

A Romarr operator runs Notifiarr. Notifiarr probes
`GET /api/v3/system/status` with the operator's API key in
`X-Api-Key`. The response shape — version, instanceName,
authentication, urlBase, etc. — matches Sonarr's well-known JSON
structure closely enough that Notifiarr recognises Romarr as an
*arr peer and starts pulling history without further config.

**Why this priority**: Constitutional Article IV mandates this
compatibility surface. Without it, the entire ecosystem-tooling
story collapses.

**Independent Test**: With a valid API key, hit
`GET /api/v3/system/status`; assert the response carries the
documented Sonarr-shaped fields and content-types. Run a
fixture-based "Sonarr probe" against the response.

**Acceptance Scenarios**:

1. **Given** a valid API key, **When** the operator hits
   `GET /api/v3/system/status` with `X-Api-Key`, **Then** the
   response is HTTP 200 with the Sonarr-compatible JSON shape and
   content-type `application/json`.
2. **Given** the same call with `?apikey=` query param instead of
   the header, **When** the request runs, **Then** authentication
   succeeds equivalently (FR-022 from the auth spec).
3. **Given** an unauthenticated call to the same endpoint,
   **When** the request runs, **Then** the response is HTTP 200
   anyway — `/api/v3/system/status` is one of the four
   intentionally public endpoints (per the input).

---

### User Story 2 — Operator drives Romarr through a clean OpenAPI surface (Priority: P1)

A Romarr operator opens `/api/v3/docs` (Swagger UI) in the
browser. They see every documented endpoint grouped by resource
tag, each with a summary, a request schema, and a list of
documented response codes. They invoke
`POST /api/v3/game` with an example payload right from the UI;
the request authenticates via cookie session, the response
materialises the new Game.

**Why this priority**: This is how new operators learn Romarr.
A broken or undocumented OpenAPI is a hostile-to-onboarding
choice.

**Independent Test**: GET `/api/v3/openapi.json`; pipe it through
an OpenAPI 3.1 validator; assert zero validation errors. Open
`/api/v3/docs` and `/api/v3/redoc` in TestClient; assert HTTP
200 with the documented HTML shells.

**Acceptance Scenarios**:

1. **Given** the running application, **When** the operator GETs
   `/api/v3/openapi.json`, **Then** the response validates against
   the OpenAPI 3.1 schema with zero errors.
2. **Given** the same spec, **When** an external Sonarr-aware
   client parses it, **Then** every endpoint carries a unique
   `operationId`, a tag, a summary, and at minimum responses for
   200, 401, 403, 404, 422.
3. **Given** the example payloads on `POST /api/v3/game`,
   `POST /api/v3/rom/release/grab`, `POST /api/v3/command`, and
   `POST /api/v3/rom/platform-pack/upload`, **When** an operator
   inspects them in `/api/v3/docs`, **Then** they see realistic,
   documented examples (not Pydantic auto-generated boilerplate).

---

### User Story 3 — Pagination is consistent across every list endpoint (Priority: P1)

The operator's UI paginates the Library page (Games), the
Activity page (Queue + History), and the Settings → Indexers page.
Each list endpoint accepts `?page=`, `?pageSize=`, `?sortKey=`,
`?sortDirection=` with the same semantics. The response envelope
is the same shape everywhere (`page`, `pageSize`, `sortKey`,
`sortDirection`, `totalRecords`, `records`).

**Why this priority**: A frontend cannot ship if every list
endpoint disagrees on pagination semantics. Sonarr's contract
is the operator's expectation.

**Independent Test**: Across at least 5 list endpoints (Games,
Releases, History, Indexers, Notifications), invoke each with
the same `?page=2&pageSize=10&sortKey=id&sortDirection=desc`
query; assert each response has the canonical envelope and the
right slice.

**Acceptance Scenarios**:

1. **Given** any list endpoint, **When** invoked without
   pagination parameters, **Then** defaults apply
   (`page=1, pageSize=50, sortKey` per the resource's documented
   default, `sortDirection=asc`).
2. **Given** any list endpoint, **When** invoked with
   `?pageSize=2000`, **Then** the response caps `pageSize` at
   1000 and includes the right slice (FR-009).
3. **Given** any list endpoint, **When** invoked with
   `?sortKey=NotARealField`, **Then** the response is HTTP 400
   with the documented error format.

---

### User Story 4 — WebSocket pushes live updates to the UI (Priority: P2)

The operator opens the Activity page. The page upgrades to a
WebSocket connection at `/signalr/messages`. As scheduled jobs
fire, the WebSocket pushes `taskStarted`, `taskProgress`, and
`taskFinished` events; as downloads progress, it pushes
`queueUpdated`. The page renders progress bars, toasts, and
queue updates in real time without polling.

**Why this priority**: Polling for state changes wastes
bandwidth and feels laggy. WebSocket is the constitutional way
(Article IV — "WebSocket compatibility at /signalr/messages").

**Independent Test**: Connect a WebSocket client to
`/signalr/messages` with a valid API key in the query string;
trigger a job (e.g., `MissingSearch`); assert the client
received at minimum a `taskStarted` and `taskFinished` event in
order, with the documented JSON shape.

**Acceptance Scenarios**:

1. **Given** a connected WebSocket client, **When** a job runs,
   **Then** the client receives `taskStarted` → optional
   `taskProgress`* → `taskFinished` events with the documented
   `messageType` field.
2. **Given** an unauthenticated WebSocket connection attempt,
   **When** the upgrade is requested, **Then** the server
   refuses with HTTP 401 before completing the upgrade.
3. **Given** a queue change (download progress), **When** the
   change is detected, **Then** the WebSocket emits a
   `queueUpdated` event carrying the affected `queueId` and
   `state`.
4. **Given** a client that disconnects, **When** events are
   emitted, **Then** they are NOT replayed on reconnection;
   clients fill gaps via REST polling (lossy WS contract).

---

### User Story 5 — Idempotency-Key replay returns the cached response (Priority: P2)

The operator's automation script POSTs `/api/v3/rom/release/grab`
with `Idempotency-Key: abc123`. The network connection drops
mid-response. The script retries with the same body and the same
Idempotency-Key. The second call returns the same response body
and HTTP status as the first — the grab is not duplicated.

**Why this priority**: Without idempotency keys, network
failures produce duplicate grabs, duplicate game-creates, and
duplicate notifications. Critical for any automation use case.

**Independent Test**: POST a `grab` with an Idempotency-Key;
capture the response. Replay the same POST with the same key;
assert the response body and status code match byte-for-byte;
assert no second `Release.status` transition or download-client
add was issued.

**Acceptance Scenarios**:

1. **Given** a POST with an `Idempotency-Key` header, **When**
   the same key is replayed within 24 hours, **Then** the
   response carries the cached status and body; no side effects
   re-fire.
2. **Given** the same key with a **different** request body,
   **When** the replay runs, **Then** the response is HTTP 422
   with reason `idempotency_key_body_mismatch`.
3. **Given** an `Idempotency-Key` older than 24 hours, **When**
   reused, **Then** it is treated as a fresh request (the cache
   row is purged on access).

---

### User Story 6 — Rate limit blocks brute-force on auth (Priority: P2)

An attacker scripts a credential-stuffing attack against
`POST /api/v3/auth/login`. After 5 attempts in 60 seconds from
the same IP, the rate limiter starts returning HTTP 429 for that
IP. Legitimate operators on different IPs are unaffected.

**Why this priority**: Without rate limiting on auth, password
brute-force is trivial. Constitutional safety requirement.

**Independent Test**: POST 6 logins in 60 s from the same IP;
assert the 6th returns HTTP 429 with the documented
`Retry-After` header. POST from a different IP; assert HTTP 401
(not 429).

**Acceptance Scenarios**:

1. **Given** 5 prior calls in the last 60 s from one IP,
   **When** the 6th `POST /api/v3/auth/login` arrives, **Then**
   the response is HTTP 429 with `Retry-After` populated.
2. **Given** a request bearing an API key on a normal endpoint,
   **When** the per-key rate limiter is consulted, **Then** the
   100 req/min default applies; a different key has its own
   bucket.
3. **Given** the rate limit is enforced via in-memory state and
   Redis is configured, **When** the enforcer runs, **Then**
   counters live in Redis (so multiple Romarr instances —
   though Article I says we don't ship them — would share
   state).

---

### User Story 7 — CSRF protection on cookie POSTs (Priority: P3)

A malicious site embeds a hidden form that POSTs to Romarr.
With the operator logged in (cookie session present), the form
is submitted via the user's browser. CSRF protection rejects
the request with HTTP 403 because the double-submit cookie
token does not match. The same operator's automation script,
authenticating via API key, bypasses CSRF entirely.

**Why this priority**: Cookie-session POSTs without CSRF are a
classic attack surface. API-key POSTs are immune (CSRF is a
cookie-only attack class).

**Independent Test**: POST a state-mutating endpoint with a
session cookie but **no** CSRF token; assert HTTP 403. POST the
same endpoint with API key only; assert HTTP 200/201/204 normally.

**Acceptance Scenarios**:

1. **Given** an authenticated cookie session, **When** the
   operator POSTs without the matching CSRF token, **Then** the
   response is HTTP 403 reason `csrf_token_missing` or
   `csrf_token_mismatch`.
2. **Given** an API-key authenticated request, **When** the
   request POSTs to a state-mutating endpoint, **Then** CSRF is
   skipped — the request is honoured.
3. **Given** GET / HEAD / OPTIONS requests, **When** they
   arrive (including with cookie auth), **Then** CSRF is skipped
   (read methods are not state-mutating).

---

### User Story 8 — Sonarr-compat command bus drives orchestration (Priority: P3)

A Romarr operator's deployment script wants to trigger a manual
backup before deploying a config change. It POSTs
`{"name": "Backup"}` to `/api/v3/command`. Romarr maps the
command to the scheduler's `Backup` job, returns a Sonarr-shaped
`{"id": 42, "name": "Backup", "status": "queued"}`. The script
polls `/api/v3/command/42` until `status = "completed"`.

**Why this priority**: This is the constitutional Sonarr-compat
orchestration surface (Article IV). Useful but not blocking
day-1.

**Independent Test**: POST `/api/v3/command` with
`{"name": "Backup"}`; assert HTTP 201 with a Sonarr-shaped
command id; GET `/api/v3/command/{id}`; assert the polling
shape matches Sonarr's command-status JSON.

**Acceptance Scenarios**:

1. **Given** a known command name (e.g., `MissingSearch`,
   `Backup`, `RefreshGame`), **When** the operator POSTs to
   `/api/v3/command`, **Then** the response is HTTP 201 with the
   Sonarr-shaped command JSON; the id maps 1:1 to the underlying
   `job_run_id`.
2. **Given** a known name with kwargs (e.g.,
   `{"name": "RefreshGame", "gameId": 42}`), **When** the
   command runs, **Then** the runner receives the documented
   `kwargs` and refreshes only that game.
3. **Given** an unknown command name, **When** POSTed, **Then**
   the response is HTTP 400 with reason `unknown_command`.

---

### Edge Cases

- A Sonarr-style consumer expects an undocumented field (e.g.,
  Sonarr-only `applicationUrl`) → we ship it on `system/status`
  for compatibility even though it is not strictly necessary;
  the field is documented as "Sonarr-compat shim".
- An operator hits the 1 000-pageSize cap and asks for more →
  documented behaviour is to use multiple pages; the response's
  `totalRecords` field tells them how many pages exist.
- A request times out after 30 seconds → the gateway returns
  HTTP 504; the underlying job (if any) continues and its
  outcome is observable via the WebSocket / `/api/v3/system/tasks`.
- An operator has both a session cookie AND an `X-Api-Key`
  header in the same request → API key wins (per the auth chain
  order from spec 010); CSRF check is skipped because API key
  bypass applies.
- An OpenAPI tag is missing or duplicated → fail at app-startup
  with a clear error rather than silently shipping a confusing
  doc.
- The WebSocket ping/pong fails → the server tears down the
  connection and removes the subscriber; the client reconnects
  and re-subscribes via REST polling for catch-up.
- A `DELETE /api/v3/blocklist/all` call is invoked → operation
  is admin-only AND requires an `Idempotency-Key` (so a network
  retry does not double-purge); replay returns the same
  cached "deleted N rows" response.
- A response body exceeds 10 MB → GZip compression kicks in
  (default for ≥ 1 KB responses); content-encoding is `gzip`.
- `GET /api/v3/health` is hit very frequently by Uptime-Kuma →
  the rate limiter exempts it from per-IP limits (it's
  intentionally public for monitoring).
- `Idempotency-Key` is reused across two **different** POST
  endpoints (e.g., one to `/api/v3/game`, one to `/api/v3/rom/release/grab`)
  → the cache is keyed by `(endpoint, key)`, so the second call
  is a cache miss and processed normally.
- A multipart upload (e.g., platform-pack YAML) exceeds 10 MB
  → the upload is rejected with HTTP 413 reason
  `payload_too_large`.

## Requirements *(mandatory)*

### Functional Requirements

**Routing & coverage**

- **FR-001**: The system MUST expose every endpoint documented
  in the input under `/api/v3/*` (Sonarr-compat surface) or
  `/api/v3/rom/*` (ROM-specific surface). At minimum: System,
  Health, Backup, Log, Game, Release, Wanted, Queue, History,
  Calendar, six profile types, Custom Format, Indexer,
  Application, DownloadClient, Notification, Tag, Platform,
  PlatformPack, DAT, Library, Metadata, Search, Blocklist,
  Tasks, Auth, User, Command — totalling **at least 90
  documented routes**.
- **FR-002**: ROM-specific endpoints MUST live under
  `/api/v3/rom/*` to keep the Sonarr-compat surface clean
  (Article IV).
- **FR-003**: The Sonarr-compat command endpoint
  `POST /api/v3/command` MUST accept at least the documented
  names: `ApplicationUpdate`, `RefreshGame`, `RescanLibrary`,
  `DownloadDats`, `IndexerSearch`, `MissingSearch`,
  `CutoffSearch`, `RssSync`, `Backup`, `RefreshMetadata`,
  `ExporterRun`.

**Authentication & authorisation**

- **FR-004**: Every endpoint MUST be protected by the auth chain
  from spec 010 EXCEPT the documented public set:
  `GET /api/v3/system/status`, `GET /api/v3/openapi.json`,
  `GET /api/v3/docs`, `GET /api/v3/redoc`,
  `POST /api/v3/auth/login`, `POST /api/v3/auth/oidc/start`,
  `GET /auth/oidc/callback`, `POST /api/v3/auth/setup`,
  `GET /api/v3/health` (per spec 011's documented
  unauthenticated-with-redaction policy).
- **FR-005**: Each endpoint MUST declare its required role
  (`admin` / `user` / `readonly`) via the `require_role`
  dependency from spec 010.

**Pagination, filtering, sorting**

- **FR-006**: All list endpoints MUST accept `?page` (default 1,
  1-indexed), `?pageSize` (default 50, max 1 000), `?sortKey`
  (resource-specific default), `?sortDirection` (`asc`/`desc`,
  default `asc`).
- **FR-007**: All list endpoints MUST return the canonical
  envelope `{page, pageSize, sortKey, sortDirection,
  totalRecords, records}` for Sonarr compatibility.
- **FR-008**: An invalid `sortKey` for a resource MUST yield
  HTTP 400 with the documented error format.
- **FR-009**: A `pageSize > 1000` MUST be capped at 1 000;
  the response carries the documented `pageSize=1000` value.

**Error format**

- **FR-010**: Every error response MUST carry the canonical
  envelope `{errorMessage, details?, errorCode?}` (per the
  input). HTTP status codes per the documented mapping (400 /
  401 / 403 / 404 / 409 / 422 / 500).

**OpenAPI**

- **FR-011**: The system MUST serve `/api/v3/openapi.json`
  conformant to the OpenAPI 3.1 schema (validator pass).
- **FR-012**: The system MUST serve Swagger UI at
  `/api/v3/docs` and ReDoc at `/api/v3/redoc` for the same spec.
- **FR-013**: Every endpoint MUST have a unique `operationId`,
  a resource tag (e.g., `Game`, `Release`, `Profile`, `Indexer`),
  a summary, and at minimum responses for 200, 401, 403, 404,
  422.
- **FR-014**: Documented examples MUST exist on at least these
  endpoints: `POST /api/v3/game`,
  `POST /api/v3/rom/release/grab`, `POST /api/v3/command`,
  `POST /api/v3/rom/platform-pack/upload`.
- **FR-015**: Security schemes MUST be documented in the spec:
  API key via `X-Api-Key` header, API key via `apikey` query
  param, cookie session. Per spec 010 FR-022 (clarified), no
  generic `Authorization: Bearer JWT` scheme is exposed at MVP.

**WebSocket**

- **FR-016**: The system MUST expose a WebSocket endpoint at
  `/signalr/messages`. The "SignalR-compat" naming refers to
  the path and the `messageType` event taxonomy (Constitution
  Article IV), NOT to the SignalR wire protocol. The framing
  MUST be plain JSON-over-WebSocket with one message per frame
  whose envelope is `{messageType: string, body: object}`. The
  SignalR-specific negotiate handshake, hub-method invocation
  pattern, and binary-protocol mode MUST NOT be implemented at
  MVP. The server MUST send a JSON ping `{messageType: "ping"}`
  every 30 seconds; clients MUST respond with
  `{messageType: "pong"}` within 10 seconds or the connection
  is torn down (Edge Case). The framing contract MUST be
  documented at `/api/v3/notification/webhook-payloads.md`
  alongside the webhook payload schemas.
- **FR-017**: The WebSocket MUST emit at minimum the documented
  message types: `queueUpdated`, `gameUpdated`, `gameAdded`,
  `gameDeleted`, `releaseGrabbed`, `releaseImported`,
  `releaseFailed`, `taskStarted`, `taskProgress`,
  `taskFinished`, `healthChanged`, `systemMessage`.
- **FR-018**: WebSocket auth MUST honour the same chain as
  REST: cookie session, API key in query string `?apikey=`, or
  `Authorization` header on the upgrade request.
- **FR-019**: WebSocket events are **lossy** — disconnected
  clients do NOT receive missed events on reconnection; clients
  catch up via REST polling.

**Idempotency-Key**

- **FR-020**: POST endpoints MUST honour an optional
  `Idempotency-Key` header. The server stores
  `(endpoint, key) → (status, body)` for 24 hours; replays
  return the cached response.
- **FR-021**: A replay with a body different from the original
  MUST return HTTP 422 reason
  `idempotency_key_body_mismatch`. Body equality MUST be
  determined by hashing the **canonicalised JSON** of the
  body per RFC 8785 (JCS — JSON Canonicalization Scheme: keys
  sorted alphabetically, no insignificant whitespace,
  normalized number representation). The
  `idempotency_cache.request_body_hash` column stores the
  canonical hash; the replay's body is canonicalised the same
  way and the hashes are compared in constant time. Multipart
  and binary request bodies (rare on Romarr's API surface)
  fall back to plain SHA-256 byte-equality on the raw bytes.

**Rate limiting**

- **FR-022**: `POST /api/v3/auth/login`, `POST /api/v3/auth/setup`,
  and `GET /auth/oidc/callback` MUST rate-limit at **10 requests
  / minute / source IP** per spec 010 FR-010a (clarified).
  Above the threshold, the endpoint MUST return HTTP 429 with
  `Retry-After` set and MUST NOT perform the bcrypt comparison
  (so failed attempts cannot oracle the hash work).
- **FR-023**: `GET /api/v3/health` MUST be exempt from the
  per-IP rate limit defined in FR-022 / FR-024 to support
  high-frequency Uptime-Kuma probes (per spec 011's documented
  monitoring contract). The endpoint's response is already
  tiered by auth (spec 011 FR-024a) so unauthenticated probes
  receive only the minimal `{status}` shape; abuse beyond the
  rate-limit window cannot disclose component details.
- **FR-024**: All other authenticated endpoints MUST rate-limit
  at 100 requests / minute / API key (configurable). Cookie-
  session and JWT requests share the same per-API-key bucket
  (mapped via the user id).
- **FR-025**: Rate limiter state MUST live in Redis when
  configured; in-memory fallback otherwise.

**CSRF**

- **FR-026**: State-mutating endpoints (POST / PUT / PATCH /
  DELETE) MUST enforce CSRF when the request authenticates via
  cookie session. Double-submit cookie pattern.
- **FR-027**: API-key authenticated requests MUST bypass CSRF.
- **FR-028**: Read methods (GET / HEAD / OPTIONS) MUST bypass
  CSRF.

**Compression & CORS**

- **FR-029**: Responses ≥ 1 KB MUST be GZip-compressed by default.
- **FR-030**: CORS MUST be configurable via
  `ROMARR_CORS_ALLOWED_ORIGINS`; default empty (same-origin only).

**Sonarr compatibility**

- **FR-031**: `GET /api/v3/system/status` MUST return a
  Sonarr-shaped JSON body. The response is **tiered by
  authentication state** (mirroring spec 011 FR-024a):
  - **Public callers** (no auth) MUST receive only
    `{version, isProduction}`. This is the minimum
    Sonarr-aware tools (Notifiarr probe, Recyclarr, Homepage)
    need to recognise Romarr as an *arr peer.
  - **Authenticated callers** (any role; `read` scope on API
    keys is sufficient) MUST receive the full Sonarr-shaped
    body including `version`, `instanceName`, `urlBase`,
    `osName`, `runtimeVersion`, `appData` (sanitized),
    `startTime`, `isProduction`.
  A Sonarr-aware client probing the public surface MUST
  recognise Romarr as an *arr peer in 100% of
  compatibility-test cases (the `version` string carries the
  recognition signal). Tooling that needs the full set
  authenticates with an API key.

### Key Entities

- **HTTP Endpoint**: One of approximately 90+ documented routes
  exposed under `/api/v3/*`. Owns its required role, its
  request schema, its response shape, and its OpenAPI metadata.
- **Pagination Envelope**: The canonical
  `{page, pageSize, sortKey, sortDirection, totalRecords,
  records}` shape used by every list response.
- **Error Envelope**: The canonical
  `{errorMessage, details?, errorCode?}` shape used by every
  non-2xx response.
- **Idempotency Cache Entry**: A `(endpoint, key) → (status,
  body)` row with a 24-hour TTL, persisted in Redis (preferred)
  or a small DB table.
- **WebSocket Subscription**: A connected client's session,
  authenticated and subscribed to the firehose of `messageType`
  events. Lossy on disconnect.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A Sonarr-aware client (Notifiarr, Recyclarr-style
  probe) recognises Romarr as an *arr peer when probing
  `GET /api/v3/system/status` in 100% of fixture-based
  compatibility tests.
- **SC-002**: `GET /api/v3/openapi.json` validates against the
  OpenAPI 3.1 schema with zero errors.
- **SC-003**: At least 5 distinct list endpoints (Game, Release,
  History, Indexer, Notification) accept the documented
  pagination parameters and return the canonical envelope in
  100% of test cases.
- **SC-004**: A WebSocket client connected to
  `/signalr/messages` receives at minimum
  `taskStarted` + `taskFinished` events for every job run AND a
  `queueUpdated` event for every queue state change in 100% of
  test cases.
- **SC-005**: A POST replay with the same `Idempotency-Key`
  within 24 hours returns the cached response (status + body)
  byte-for-byte in 100% of test cases.
- **SC-006**: A 6th login attempt within 60 s from the same IP
  returns HTTP 429 with `Retry-After` populated in 100% of
  test cases.
- **SC-007**: A cookie-session POST without a matching CSRF
  token returns HTTP 403 in 100% of test cases; an API-key POST
  to the same endpoint succeeds.
- **SC-008**: Test coverage on the `api/` module MUST be at
  least 80%.
- **SC-009**: Across the documented 90+ routes, every endpoint
  has at least one integration test exercising its happy path
  + at least one error path.

## Assumptions

These resolve the OPEN CLARIFICATIONS supplied with the input,
applying the operator's proposals.

- **Base path**: only `/api/v3/*`. No `/api/` alias for Sonarr
  v2 consumers; the README documents the upgrade path for
  v2-only tooling (rare in 2026).
- **CSRF**: enabled for cookie-session POSTs via the
  double-submit cookie pattern. API-key requests bypass.
- **CORS**: configurable via
  `ROMARR_CORS_ALLOWED_ORIGINS`; default empty (same-origin
  only). Operators reverse-proxying through a different domain
  set the env var explicitly.
- **GZip**: enabled by default for responses ≥ 1 KB.

Other assumptions:

- The route count "90+" is a floor, not a ceiling. The actual
  surface is the union of every prior spec's documented
  endpoints plus the new ones introduced here (`system/status`,
  `system/log`, `tag`, `queue`, `history`, `calendar`,
  `command` aliases, `webhook-payloads.md` static doc).
- A small number of routes need backing tables that earlier
  specs did NOT create:
  - **`tag`** (id, name UNIQUE, color hex, label, created_at,
    updated_at) plus a polymorphic association table
    **`tag_assignment`** (tag_id FK, entity_type ENUM, entity_id,
    UNIQUE on `(tag_id, entity_type, entity_id)`). The
    `entity_type` enum at MVP is exactly
    `{'game', 'indexer', 'notification', 'release'}`. The same
    `tag` row can be applied across multiple entity types
    without duplicating its name/color/label; rename or recolor
    propagates centrally. Cascade rule: deleting a `tag` row
    cascades the matching `tag_assignment` rows; deleting an
    entity (Game / Indexer / etc.) cascades its assignments via
    a per-entity-type cleanup hook (no ORM-level FK to the
    polymorphic `entity_id` is possible).
  - **`queue_entry`** (id, release_id FK, download_client_id FK,
    download_client_native_id, state enum, progress, size_bytes,
    eta_seconds, last_updated_at, error_msg, attempt_count,
    last_attempt_at). Used by spec 005's stuck-grab retry,
    spec 008's import pipeline, and the queue endpoints here.
  - **`idempotency_cache`** (key, endpoint, request_body_hash,
    response_status, response_body, created_at, expires_at).
    Optional — Redis is the preferred backend; this table is
    the fallback.
  These three tables are introduced inline by this feature's
  migration. The user explicitly noted "no new data-model.md
  needed" because these are minor schema deltas — the plan
  documents them inline.
- Sonarr-shape compatibility for `system/status` emits the
  **union** of Sonarr v3 and v4 fields so tools written against
  either era see what they expect. The authenticated-tier
  response (FR-031) MUST include the v3 keys
  (`version`, `instanceName`, `urlBase`, `osName`,
  `runtimeVersion`, `appData`, `startTime`, `isProduction`)
  PLUS the v4 additions (`databaseType` — `"sqlite"` or
  `"postgres"`; `databaseVersion`; `migrationVersion` — Alembic's
  current head revision; `runtimeName` — `"Python"`). Two
  fixtures live under `tests/fixtures/api/`:
  `sonarr_v3_status_fixture.json` and
  `sonarr_v4_status_fixture.json`; the conformance test asserts
  the response's key set is a superset of both.

### Out of Scope

- GraphQL (firm out).
- gRPC (firm out).
- Streaming responses for very large list endpoints (deferred
  to v1+).
- Webhook signing for outbound events (deferred to v1+).
- Bulk operations beyond the basic batch endpoints already
  listed (deferred to v1+).
- Per-resource fine-grained permissions (Auth spec — current
  RBAC is the three-tier admin/user/readonly model).
- Sonarr v2 endpoint aliases under `/api/` (firm out).
