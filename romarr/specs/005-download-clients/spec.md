# Feature Specification: Download Clients

**Feature Branch**: `005-download-clients` (branch creation skipped: git repo lives in parent dir)
**Created**: 2026-04-29
**Status**: Draft
**Depends on**:
- `001-foundation` — Library model carries the lifecycle policy field that consumes the
  routing decisions made here.
- `002-metadata-aggregation` — re-uses the encryption helper for client passwords
  and API keys at rest.
- `004-indexers` — `indexer.download_client_id` column already exists; this spec
  finally backfills the FK to the new `download_client` table.
**Input**: User description: "Build the download client integration layer. MVP supports qBittorrent + SABnzbd via official/well-maintained Python libraries; no custom protocol implementations. A common DownloadClient ABC, auto-managed categories/tags, source-type routing, encrypted credentials at rest, and a stuck-grab retry policy."

## Clarifications

### Session 2026-04-29

- Q: What happens when `add_torrent` is called for an info-hash already present in qBittorrent? → A: Idempotent success. Detect the existing torrent, return its info-hash as `client_id`, and additively merge the `romarr` and `romarr-{platform_slug}` tags onto the existing torrent without removing any pre-existing user tags or changing the existing category
- Q: When a release exposes both a magnet URL and a `.torrent` URL, which form does Romarr send to qBit? → A: Prefer `.torrent` URL > raw `.torrent` bytes > magnet URL. The `.torrent` form contains the full piece map and tracker list immediately, sparing qBit a DHT metadata round-trip, and is required by most private trackers
- Q: What's the minimum supported qBittorrent API version? → A: API version 2.8.3 (qBittorrent 4.4.0+, March 2022). Older versions lack the tag and category APIs Romarr depends on. Older qBit instances fail the connectivity test with a structured `VersionError("upgrade qBittorrent to 4.4.0 or newer")`
- Q: Should download clients carry a per-client circuit breaker in addition to the stuck-grab retry policy? → A: Yes — same pattern as spec 004 indexers and spec 002 providers (5 failures within 60 s opens; auto half-open after 60 s). The stuck-grab retry policy (FR-021/022) is preserved and complementary: stuck retries respect the breaker (when open they bump `last_attempt_at` without an outbound call). Auth errors and 5xx responses count as failures
- Q: What role is required to invoke the `/api/v3/downloadclient/*` endpoints? → A: Admin-only on all mutating endpoints (POST / PUT / DELETE) AND on the connectivity-test endpoint (which would otherwise be an SSRF surface). Reads (GET) accessible to any authenticated user. Same pattern as spec 003 / 004

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Configure qBittorrent and grab a torrent (Priority: P1)

A Romarr operator who already has qBittorrent running locally
configures it via the API. The connection test passes, the `romarr`
category is auto-created on the qBit side, and Romarr can hand a
torrent (URL, magnet, or `.torrent` bytes) to qBit with the right
category and tags.

**Why this priority**: Without a working torrent client, Romarr
cannot fulfil grabs from torrent indexers. This is the headline path
for most operators.

**Independent Test**: Configure a qBittorrent client with valid
credentials; trigger a connection test; verify the test reports
success and reports that the `romarr` category was created (or
already existed); then call `add_torrent` with a sample magnet,
category `romarr`, and tags `[romarr, romarr-megadrive]`; verify
the torrent appears in qBit's `torrents_info` list with the
expected category, tags, and save path.

**Acceptance Scenarios**:

1. **Given** a reachable qBittorrent instance, **When** the operator
   POSTs the configuration with `test=true`, **Then** the system
   authenticates, ensures the `romarr` category exists (creating it
   if missing), and persists the client only on success.
2. **Given** a saved qBittorrent client, **When** Romarr calls
   `add_torrent` with a magnet URL, category `romarr`, and tags
   `[romarr, romarr-megadrive]`, **Then** the torrent is added with
   exactly those tags and category, and `add_torrent` returns the
   client-side identifier (info-hash).
3. **Given** a torrent previously added by Romarr, **When** the
   client is later queried via `get_status(client_id)`, **Then** the
   response includes `state`, `progress`, `eta`, `seeders`, `peers`,
   and `download_rate` in the canonical `DownloadStatus` shape.

---

### User Story 2 — Configure SABnzbd and grab an NZB (Priority: P1)

A Romarr operator configures a SABnzbd instance via API. The
connection test passes (or warns the operator that the `romarr`
category needs to be created manually inside SAB), and Romarr can
hand an `.nzb` to SAB with category `romarr`.

**Why this priority**: Usenet is the second pillar of acquisition;
without it, Romarr is torrent-only.

**Independent Test**: Configure a SABnzbd client with a valid API
key; trigger a connection test; verify it reports success and either
confirms the `romarr` category exists or warns the operator to
create it manually (SAB does not expose a category-creation API);
call `add_nzb` with a sample NZB URL; verify SAB's queue lists the
job under category `romarr`.

**Acceptance Scenarios**:

1. **Given** a reachable SABnzbd instance, **When** the operator
   submits its URL + API key with `test=true`, **Then** the system
   authenticates and either confirms the `romarr` category is
   present or returns a structured `CategoryWarning` instructing
   the operator to create it manually.
2. **Given** a saved SABnzbd client, **When** Romarr calls
   `add_nzb` with an NZB URL and category `romarr`, **Then** the
   NZB is queued with that category and `add_nzb` returns the SAB
   `nzo_id`.
3. **Given** an NZB previously added, **When** Romarr calls
   `get_status(client_id)`, **Then** the canonical `DownloadStatus`
   is returned (Usenet-relevant fields populated; seeders/peers
   are NULL).

---

### User Story 3 — Romarr routes torrents and NZBs to the right client (Priority: P1)

The operator has both qBittorrent and SABnzbd configured. Romarr
decides to grab a release; it picks the right client based on the
release's source type (torrent vs. NZB) and the indexer's optional
`download_client_id` override.

**Why this priority**: Wrong-client routing wastes grabs and breaks
the import pipeline. Routing must be deterministic and explicit.

**Independent Test**: Configure two clients (one qBit torrent-only,
one SAB usenet-only); attempt to grab a magnet URL → assert qBit
receives it; attempt to grab an NZB URL → assert SAB receives it;
configure a torrent indexer with `download_client_id` pointing to a
specific qBit instance and assert that one wins.

**Acceptance Scenarios**:

1. **Given** the release source is a magnet URL or `.torrent`,
   **When** routing runs, **Then** the highest-priority enabled
   torrent client wins.
2. **Given** the release source is an `.nzb`, **When** routing
   runs, **Then** the highest-priority enabled Usenet client wins.
3. **Given** the originating indexer has `download_client_id`
   set, **When** routing runs, **Then** that client wins regardless
   of priority — provided it is enabled and capable of the source
   type. If the indexer-pinned client cannot handle the source type
   (e.g., torrent-only client for an NZB), routing falls back to
   priority-based selection AND records the mismatch as a
   structured warning.
4. **Given** no eligible client exists for a source type, **When**
   routing runs, **Then** the grab is rejected with a clear error
   message and a `Notification` event is emitted (consumer in the
   Notifications spec).

---

### User Story 4 — Connection test catches misconfiguration (Priority: P2)

The operator submits a misconfigured client (wrong host, wrong
password, missing category). The connection test produces a
specific, actionable error rather than a generic failure.

**Why this priority**: Misconfiguration is the most common support
issue in *arr land; clear errors save the operator hours.

**Independent Test**: Run the test against an unreachable host →
assert `ConnectionError`; against a reachable host with wrong
credentials → assert `AuthError`; against a SAB instance with no
`romarr` category → assert success-with-warning, not failure.

**Acceptance Scenarios**:

1. **Given** an unreachable host, **When** the test runs, **Then**
   it returns `ConnectionError` with a host/port detail; the client
   is NOT persisted.
2. **Given** a reachable host with wrong username/password, **When**
   the test runs, **Then** it returns `AuthError` with a clear
   message; the client is NOT persisted.
3. **Given** a SABnzbd reachable instance with no `romarr`
   category configured, **When** the test runs, **Then** it returns
   a successful `ConnectivityTestResult` with a non-blocking
   `CategoryWarning("missing 'romarr' category — please create it
   in SABnzbd Settings → Categories")`.
4. **Given** a qBittorrent instance with no `romarr` category,
   **When** the test runs, **Then** the system creates the category
   automatically (qBit supports the API for it) and reports success
   with no warning.

---

### User Story 5 — Multiple instances of the same client type (Priority: P2)

The operator runs two qBittorrent instances: one local for fast
links, one on a remote seedbox for unattended seeding. Both can be
configured concurrently; routing distinguishes them by priority and
indexer overrides.

**Why this priority**: This is a normal *arr deployment pattern.
Without multi-instance support, operators have to choose one or
hack their way around the limit.

**Independent Test**: Configure two qBittorrent clients with
different `(host, port)` pairs; assert both persist; assert routing
respects their priority field; assert grabs that target indexer A
(pinned to client 1) go to client 1 even when client 2 has higher
priority.

**Acceptance Scenarios**:

1. **Given** two qBittorrent clients are configured, **When** a
   torrent grab is dispatched, **Then** the higher-priority enabled
   client receives it.
2. **Given** the indexer for that grab has `download_client_id`
   pinned to the lower-priority client, **When** the grab is
   dispatched, **Then** the pinned client wins.

---

### User Story 6 — Auto-managed categories and tags (Priority: P3)

When Romarr first connects to a qBittorrent instance, it ensures
the `romarr` category exists and applies the standard tags
(`romarr`, `romarr-{platform-slug}`) on every grab. SABnzbd
similarly receives every grab under the `romarr` category. After
Romarr has imported a download (handled in the Importer spec),
qBittorrent grabs receive an additional `romarr-imported` tag.

**Why this priority**: Tagging conventions are what let downstream
tooling (Janitorr, Recyclarr-style cleanup, manual triage) recognise
Romarr-managed downloads.

**Independent Test**: Connect to a fresh qBit; assert the `romarr`
category appears; add a torrent; assert tags `romarr` and
`romarr-megadrive` are applied; simulate a post-import call to
`set_tags` adding `romarr-imported`; assert the tag is present.

**Acceptance Scenarios**:

1. **Given** a fresh qBittorrent connection, **When** the system
   tests connectivity, **Then** the `romarr` category is created if
   missing.
2. **Given** an `add_torrent` call, **When** it runs, **Then** tags
   `romarr` and `romarr-{platform-slug}` are applied to the torrent.
3. **Given** the Importer (later spec) signals an import is done,
   **When** the helper applies the imported-tag, **Then** the
   torrent now also carries `romarr-imported`.

---

### User Story 7 — Unreachable client at grab time retries gracefully (Priority: P3)

Romarr decides to grab a release but the configured download
client is temporarily unreachable. Rather than failing immediately,
the grab is queued in a "stuck" state, retried every 5 minutes,
and only marked as failed (with a notification) after one hour of
sustained unreachability.

**Why this priority**: Transient outages happen (seedbox restarts,
home network blips). Failing fast loses grabs the operator has to
re-issue manually.

**Independent Test**: Inject a transient `ConnectionError` for the
client; trigger a grab; verify the queue carries the grab with
`state = 'stuck'`; advance time by 5 minutes and re-trigger
processing → verify a retry happened; advance time past 1 hour →
verify the grab is marked `failed` with a structured reason.

**Acceptance Scenarios**:

1. **Given** a configured client is unreachable, **When** Romarr
   tries to grab, **Then** the grab is recorded with
   `state = 'stuck'` and a `last_attempt_at` timestamp.
2. **Given** the client recovers within 1 hour, **When** the
   periodic retry fires (every 5 minutes by default), **Then** the
   grab succeeds and the queue transitions to `state = 'downloading'`.
3. **Given** the client remains unreachable for 1 hour, **When**
   the retry fires past the threshold, **Then** the grab is marked
   `failed` and a `Notification` event is emitted.

---

### Edge Cases

- Operator submits a client with `enable_for_torrents = false`
  AND `enable_for_usenet = false` → rejected at validation as
  "client must support at least one source type".
- Operator submits a SAB client with username/password fields
  populated → rejected at validation as "SABnzbd uses API key only".
- Operator submits a qBit client with no username/password →
  rejected at validation (qBit requires basic credentials).
- Same `(type, host, port)` registered twice → HTTP 409.
- A qBittorrent instance running on `https://` with a self-signed
  cert and `ssl_cert_validation = 'enabled'` → connection fails
  with a clear "TLS verification failed" message; operator can
  switch to `'disabled-for-local'` for RFC1918 ranges only.
- The remote qBit's API version is older than the minimum we
  support → connection test fails with a structured "client
  too old, please upgrade qBittorrent" message.
- The download client and Romarr run in different containers
  with different filesystem views (path mapping problem) →
  documented as a known v1 follow-up; no automatic remapping in
  MVP.
- A torrent download finishes while the client is paused
  globally → `get_status` correctly reports `state = 'paused'`,
  not `'completed'`; the importer's polling logic uses the
  protocol-specific status mapping.
- Two grabs land on the same torrent (same info-hash) inside a
  short window → qBit deduplicates; Romarr accepts the existing
  client_id rather than creating a second download.
- Operator deletes a download client while grabs are in flight
  → in-flight grabs reference the client by id; grabs become
  "stuck" until the operator re-points the indexer or deletes
  the queue entry.

## Requirements *(mandatory)*

### Functional Requirements

**Provider abstraction**

- **FR-001**: The system MUST expose a `DownloadClient` abstract
  base class with the documented async method set: `configure`,
  `test_connection`, `add_torrent`, `add_nzb`, `get_status`,
  `list_managed_downloads`, `remove`, `pause`, `resume`,
  `set_category`, `get_completed_files`.
- **FR-002**: The base class MUST expose `name`, `type`,
  `supports_torrents`, `supports_usenet` as class-level metadata
  used by routing and by the schema-discovery endpoint.
- **FR-003**: `TorrentSource` MUST be a discriminated union of
  URL, magnet link, and raw `.torrent` bytes. `NzbSource` MUST be
  a discriminated union of URL and raw `.nzb` bytes.
- **FR-003a**: When a release carries multiple acquisition forms
  (e.g., both a `.torrent` URL and a magnet URL on the same
  Torznab item), the routing layer MUST select forms in the
  preference order **`.torrent` URL > raw `.torrent` bytes >
  magnet URL** before invoking `add_torrent`. Magnet URLs MUST
  only be used when no torrent-file form is available. The same
  preference applies symmetrically to NZB sources: **`.nzb` URL >
  raw `.nzb` bytes**. The selected form MUST be recorded on the
  resulting grab event so the operator can see why a particular
  payload was used.

**MVP implementations**

- **FR-004**: The system MUST ship a qBittorrent implementation
  using the `qbittorrent-api` Python library (>= 2024.x), wrapping
  authentication, torrent add/remove/pause/resume, status, file
  listing, category creation, and tag application.
- **FR-004a**: When `add_torrent` is invoked with a magnet URL,
  `.torrent` URL, or raw `.torrent` bytes whose info-hash is
  already present in the target qBittorrent instance (regardless
  of whether the existing torrent was added by Romarr, by another
  *arr, or manually), the implementation MUST treat the call as
  an idempotent success. It MUST: (a) return the existing
  torrent's info-hash as `client_id`; (b) additively apply the
  `romarr` and `romarr-{platform_slug}` tags onto the existing
  torrent (the qBittorrent API supports `add tags` without
  disturbing existing tags); (c) leave the existing category
  untouched (do NOT overwrite a user's existing category — only
  set the `romarr` category if no category was previously set).
  No new download is created and no data is re-downloaded. The
  same idempotent-success contract applies to `add_nzb` against
  SABnzbd when the queue already contains an entry whose source
  URL matches.
- **FR-005**: The system MUST ship a SABnzbd implementation using
  direct httpx calls against the SAB API: `mode=addurl`,
  `mode=queue`, `mode=history`, `mode=delete`. SAB authentication
  is the API key only.
- **FR-005a**: The qBittorrent connectivity test MUST query the
  remote API version (`GET /api/v2/app/webapiVersion`) and
  reject the configuration with a structured `VersionError` when
  the remote version is below **2.8.3** (which corresponds to
  qBittorrent application version 4.4.0, released March 2022).
  The error message MUST instruct the operator to upgrade to
  qBittorrent 4.4.0 or newer. SABnzbd has no equivalent
  minimum-version requirement; its API has been stable across
  the supported releases.

**Future-proofing for v1 implementations**

- **FR-006**: Stub implementations for Transmission, Deluge, and
  NZBGet MUST exist behind the same ABC; their methods MUST raise
  `NotImplementedError` with a clear "deferred to v1" message and
  the schema-discovery endpoint MUST report them as
  `available = false`.
- **FR-007**: rTorrent is **not** stubbed in this feature; it is
  v2+ work.

**Connection test**

- **FR-008**: A connectivity test on a candidate client MUST: (a)
  authenticate; (b) confirm or create the `romarr` category for
  qBittorrent; (c) for SABnzbd, confirm the `romarr` category
  exists and emit a non-blocking `CategoryWarning` if it does not;
  (d) return a structured result with the client's version string,
  any warnings, and a clear error otherwise.
- **FR-009**: A client MUST NOT be persisted from a `test=true`
  configuration request unless connectivity passes (warnings are
  acceptable; outright errors are not).

**Auto-managed categories & tags**

- **FR-010**: Romarr MUST add the `romarr` category to qBittorrent
  on first successful connectivity test (qBit exposes a
  category-creation API).
- **FR-011**: SABnzbd does NOT expose a category-creation API; the
  test result MUST surface a `CategoryWarning` instead, instructing
  the operator to create the category manually.
- **FR-012**: Every torrent added MUST carry the tag `romarr` and
  the tag `romarr-{platform_slug}` (using the foundation's platform
  slug).
- **FR-013**: After a successful import (signal arrives from the
  Importer spec), the system MUST add the tag `romarr-imported` to
  the torrent on qBittorrent. SAB does not expose a tag concept;
  the import status is tracked in Romarr's own DB instead.

**Routing**

- **FR-014**: When a release has an originating indexer with
  `download_client_id` set, routing MUST select that client,
  provided it is enabled AND supports the source type. If both
  conditions are met, the override wins regardless of priority.
- **FR-015**: When the indexer override is unset or unsuitable,
  routing MUST select the highest-priority enabled client that
  supports the source type. The source type is derived from the
  release: magnet/`.torrent` ⇒ torrent-only; `.nzb` ⇒ Usenet-only.
- **FR-016**: When no eligible client is found, the grab MUST be
  rejected with a clear, structured error and a `Notification`
  event emitted. No silent failure.

**Persistence and encryption**

- **FR-017**: The system MUST persist clients in a new
  `download_client` table per `data-model.md`.
- **FR-018**: The Alembic migration MUST also add the previously
  deferred FK from `indexer.download_client_id` →
  `download_client.id` ON DELETE SET NULL.
- **FR-019**: Client passwords and API keys MUST be encrypted at
  rest using the same Fernet helper introduced in the metadata
  feature (`ROMARR_AUTH_SECRET_KEY`-derived).

**TLS handling**

- **FR-020**: Each client MUST carry a `ssl_cert_validation`
  field with three values: `enabled` (default), `disabled`,
  `disabled-for-local`. `disabled-for-local` MUST disable
  validation only for RFC 1918 / RFC 4193 / loopback addresses.

**Stuck-grab retry policy**

- **FR-021**: When `add_torrent` or `add_nzb` fails because the
  client is unreachable (`ConnectionError`/`TimeoutError`), the
  grab MUST be parked in a `stuck` state in the future queue
  table (introduced by the API spec) with a `last_attempt_at`
  timestamp and an `attempt_count` counter.
- **FR-022**: A retry policy MUST re-attempt stuck grabs every 5
  minutes. After 1 hour of sustained unreachability, the grab MUST
  be marked `failed` and a `Notification` event emitted.

**Per-client circuit breaker**

- **FR-022a**: Each download client MUST be guarded by a per-client
  circuit breaker mirroring the pattern used by spec 004 (indexers)
  and spec 002 (metadata providers): five failures within a 60 s
  window MUST open the breaker; while open, all outbound calls
  MUST short-circuit without a network round-trip; after 60 s
  without further failures the breaker MUST enter half-open and
  allow exactly one trial call (success closes; failure re-opens).
  The breaker MUST count both transient errors
  (`ConnectionError` / `TimeoutError` / 5xx) and persistent errors
  (`AuthError` / `VersionError`) as failures. The stuck-grab retry
  policy (FR-021 / FR-022) MUST respect the breaker: when the
  breaker is open, a stuck-retry tick MUST bump `last_attempt_at`
  and `attempt_count` without issuing an outbound call. The breaker
  is per-client and MUST NOT propagate failures to siblings even
  when two clients point at the same upstream service.

**Validation**

- **FR-023**: A client configuration MUST satisfy the rule
  `enable_for_torrents OR enable_for_usenet`; configurations that
  enable neither MUST be rejected at validation.
- **FR-024**: A SABnzbd configuration MUST NOT carry username or
  password (SAB uses API key only). A qBittorrent configuration
  MUST carry username AND password.
- **FR-025**: `(type, host, port)` MUST be unique per database;
  duplicates MUST be rejected with HTTP 409.

**API endpoints (full schemas in API spec)**

- **FR-026**: The system MUST expose endpoint stubs at:
  - `GET /api/v3/downloadclient`
  - `GET /api/v3/downloadclient/{id}`
  - `POST /api/v3/downloadclient`
  - `PUT /api/v3/downloadclient/{id}`
  - `DELETE /api/v3/downloadclient/{id}`
  - `POST /api/v3/downloadclient/{id}/test`
  - `GET /api/v3/downloadclient/schema` (lists implementations and
    their config fields)
- **FR-026a**: Mutating endpoints (`POST` / `PUT` / `DELETE` on
  `/api/v3/downloadclient` and the connectivity-test endpoint
  `POST /api/v3/downloadclient/{id}/test`) MUST require the
  caller to hold the `admin` role provided by the Auth spec. The
  connectivity-test endpoint is admin-gated because issuing an
  outbound HTTP request to an operator-supplied URL is an SSRF
  surface that MUST NOT be open to a non-admin user. Read
  endpoints (`GET /api/v3/downloadclient`,
  `GET /api/v3/downloadclient/{id}`,
  `GET /api/v3/downloadclient/schema`) MUST be accessible to any
  authenticated user. Encrypted credentials MUST NEVER appear in
  read-endpoint responses, regardless of caller role.

### Key Entities

- **Download Client**: A configured connection to a qBittorrent,
  SABnzbd, or future Transmission/Deluge/NZBGet instance. Owns
  its credentials (encrypted), its enable flags per source type,
  its priority, its TLS handling.
- **Torrent / NZB Source**: A discriminated union representing
  the various payload shapes a release can take.
- **Download Status**: A canonical, client-agnostic snapshot of a
  download (state, progress, ETA, seeders/peers, rates).
- **Connectivity Test Result**: A structured outcome of a test
  including success/failure, version info, and any non-blocking
  warnings (e.g., `CategoryWarning`).
- **Routing Decision**: The (deterministic) result of choosing a
  client for a given release, recording the indexer override
  status and the priority comparison.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can configure a qBittorrent client
  end-to-end (URL + credentials + connectivity test that
  auto-creates the `romarr` category) in under 30 seconds.
- **SC-002**: An operator can configure a SABnzbd client
  end-to-end (URL + API key + connectivity test) in under 30
  seconds; a missing `romarr` category is surfaced as a
  non-blocking warning, not a failure.
- **SC-003**: With one torrent client and one Usenet client
  configured, routing picks the right one in 100% of cases across
  a fixture corpus of at least 30 mixed releases (torrents,
  magnets, NZBs).
- **SC-004**: Indexer-pinned `download_client_id` overrides win
  over priority-based routing in 100% of test cases.
- **SC-005**: When no eligible client exists for a source type,
  the grab is rejected with a structured error and a notification
  event in 100% of test cases.
- **SC-006**: The connectivity test produces a distinct, typed
  error (`ConnectionError`, `AuthError`, `CategoryWarning`,
  `VersionError`, `TLSError`) for each documented misconfiguration
  scenario across the test corpus.
- **SC-007**: With a transient client outage injected, a grab is
  parked as `stuck`, retried at the configured 5-minute cadence,
  and either recovered or marked `failed` after the 1-hour
  threshold in 100% of test cases.
- **SC-008**: Inspecting the database file shows zero plaintext
  download-client passwords and zero plaintext API keys.
- **SC-009**: Test coverage on the downloaders module MUST be at
  least 75%.

## Assumptions

These resolve the OPEN CLARIFICATIONS supplied with the input,
applying the operator's proposals.

- **Path mapping**: Remote path mapping between Romarr and a
  download client running on a different host is **deferred to
  v1**. The MVP documentation instructs operators to mount the
  same paths on both sides.
- **TLS validation**: Per-client `ssl_cert_validation` setting
  with three values (`enabled` / `disabled` /
  `disabled-for-local`); default is `enabled`. The
  `disabled-for-local` mode disables only for RFC 1918 / RFC 4193
  / loopback addresses.
- **Unreachable client retry policy**: Stuck grabs retry every
  5 minutes; after 1 hour they are marked failed and notify
  (FR-021, FR-022).
- **Watch-folder support**: NOT supported. Romarr always uses the
  client's API. Watch dirs cause race conditions and silent data
  loss.

Other assumptions:

- The `romarr` category name is fixed at MVP. Renaming the
  Romarr-managed category is a v1+ feature that requires
  coordinated migration across all download clients.
- Per-grab tags are limited to `romarr`, `romarr-{platform_slug}`,
  and `romarr-imported` for MVP. Custom-tag templating is a UI
  spec follow-up.
- The future queue/history table that the stuck-grab retry policy
  writes to is owned by the API spec; this feature defines the
  retry contract and its state transitions.
- Multi-tenant deployments (per-user download clients) are out of
  scope; the Auth spec may revisit this.

### Out of Scope

- Lifecycle execution (the Importer spec performs the
  `hardlink` / `move` / `copy` step after download completes).
- Multi-instance management UI (UI spec).
- Transmission, Deluge, NZBGet *implementations* (designed for
  via the ABC and stubbed; deferred to v1).
- rTorrent (deferred to v2+).
- Per-torrent ratio/seed-time enforcement beyond what the client
  itself supports.
- Bandwidth scheduling — operators use the client's own
  scheduler.
- Remote path mappings (deferred to v1; documented workaround).
- Watch-folder ingestion (firm-out — race conditions).
