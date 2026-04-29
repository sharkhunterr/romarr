# Feature Specification: Indexers (Prowlarr-First)

**Feature Branch**: `004-indexers` (branch creation skipped: git repo lives in parent dir)
**Created**: 2026-04-29
**Status**: Draft
**Depends on**:
- `001-foundation` — uses the identification cascade (filename parsing, hash typing) as the fallback when extended Torznab attributes are absent.
- `003-platform-packs` — consumes per-platform Newznab category IDs from the platform-pack data.
- `002-metadata-aggregation` — re-uses the encryption helper for indexer API keys and Prowlarr API keys at rest.
**Input**: User description: "Build the indexer integration layer. Romarr is Prowlarr-first: it does not implement indexer-specific protocols, only Newznab/Torznab. Three responsibilities: a generic Newznab/Torznab client, Prowlarr application registration endpoints, and opportunistic parsing of Romarr-specific extended Torznab attributes."

## Clarifications

### Session 2026-04-29

- Q: What's the per-call HTTP timeout against an indexer, and is it configurable? → A: 30 s default, configurable per indexer via a `timeout_seconds` column with a permitted range of 5 to 120 s. Timeouts MUST trip the per-indexer circuit breaker the same way other failures do
- Q: When a search runs across N enabled indexers, are calls serial or concurrent? → A: Concurrent fan-out via `asyncio.gather(return_exceptions=True)`; per-indexer failures are isolated and recorded as health issues; total search latency ≈ slowest-healthy indexer rather than sum-of-all
- Q: What credential authenticates `POST /api/v3/applications` (Prowlarr registering itself)? → A: The operator's admin API key (or admin session). Prowlarr is configured by the operator pasting Romarr's URL + admin API key into Prowlarr's "Apps" panel; Prowlarr posts the registration with that key, receives an app token in the response, and uses the app token (not the admin key) for every subsequent call
- Q: How does an operator rotate an Application's app token if it leaks? → A: Delete + re-register. There is no dedicated rotate endpoint at MVP. The operator deletes the Application row (admin-only `DELETE /api/v3/applications/{id}`) and re-adds Romarr in Prowlarr's Apps panel; this matches Sonarr / Radarr behaviour and avoids the dual-valid-token state machine
- Q: What's the per-search result-count cap, and is it configurable? → A: Per-indexer cap, default 100, configurable up to 500 via a `result_limit` column. The client MUST pass `limit=…` to the indexer when the indexer's caps advertise pagination support; otherwise truncate after parsing. Caps protect memory and downstream decision-engine workload

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Configure a Newznab indexer manually and search (Priority: P1)

A Romarr operator who is **not** running Prowlarr wants to add a single
Newznab-compatible indexer with URL + API key, run a connectivity
test, save it, and then issue a keyword search across that indexer
that returns parsed results.

**Why this priority**: Without manual indexer config, Romarr cannot
search at all. This is the headline path of the feature.

**Independent Test**: Configure one Newznab indexer with valid
credentials and a category list; trigger a connectivity test; verify
it succeeds; then issue a search; verify the response is a list of
parsed result records carrying release name, indexer reference,
size, and (where the indexer provides them) seeders, peers, and
infohash.

**Acceptance Scenarios**:

1. **Given** a reachable Newznab indexer, **When** the operator
   submits its URL + API key + categories via the configuration
   endpoint with `test=true`, **Then** the system performs a
   capabilities check + a minimal sample search, and the indexer is
   persisted only if both succeed.
2. **Given** a saved indexer with `enable_interactive_search = true`,
   **When** the operator issues a keyword search, **Then** the
   system returns a deduplicated list of parsed results with at
   minimum a release name, indexer reference, and size.
3. **Given** a Newznab indexer reachable but with an invalid API
   key, **When** the operator submits the configuration with
   `test=true`, **Then** the system rejects the save with a clear
   "authentication failed" message and persists nothing.

---

### User Story 2 — Prowlarr registers Romarr as a downstream application (Priority: P1)

A Romarr operator runs Prowlarr. They open Prowlarr's "Apps" panel
and add Romarr as a downstream application. Prowlarr authenticates
itself, receives a callback token, and immediately pushes its
configured indexers into Romarr.

**Why this priority**: Prowlarr-first is the project's stated indexer
strategy (Constitution Article VII). Without this path, Romarr would
re-litigate per-indexer integration — exactly what the constitution
forbids.

**Independent Test**: Send a Prowlarr-style registration POST to
`/api/v3/applications` with the documented payload; verify the
response carries an app token; have the test client immediately POST
two indexers to `/api/v3/indexer` with `source = 'prowlarr'`; verify
both indexers materialize.

**Acceptance Scenarios**:

1. **Given** Prowlarr's URL + API key, **When** Prowlarr POSTs to
   `/api/v3/applications`, **Then** the system stores an Application
   row, generates a 32-byte cryptographically-random app token,
   stores its hash (never the plaintext after the response), and
   returns the plaintext token exactly once in the response body.
2. **Given** a registered Application, **When** Prowlarr POSTs an
   indexer to `/api/v3/indexer` carrying its `prowlarr_app_id`,
   **Then** the indexer materializes with `source = 'prowlarr'` and
   `prowlarr_app_id` set; the same fields cannot be edited via the
   normal indexer-PUT endpoint by a non-Prowlarr caller.
3. **Given** an indexer registered by Prowlarr, **When** the
   operator deletes it via Romarr's API, **Then** Romarr deletes the
   row and notifies the registered Prowlarr instance via its API so
   the change is reflected in Prowlarr (best-effort; failure logs
   but does not block the local delete).

---

### User Story 3 — Extended Torznab attributes are consumed opportunistically (Priority: P1)

A Grabarr-compatible indexer emits extended Torznab attributes
(`region`, `languages`, `revision`, `dump_tags`, `hash_sha1`,
`hash_crc32`, `naming_convention`, `dat_source`) on its search
results. Romarr **uses** these attributes when present and **falls
back to filename parsing** when they are absent. Both the standard
`torznab:` namespace and the `grabarr:` namespace are accepted.

**Why this priority**: Constitution Article VII requires Romarr to
consume the extended attributes when emitted but never depend on
them. This is the bridge that makes Grabarr's investment in cleaner
metadata pay off without breaking compatibility with vanilla
indexers.

**Independent Test**: Feed the parser two synthetic Torznab feeds —
one with the extended attributes (tested under both `torznab:attr`
and `grabarr:`-prefixed forms), one without — and verify both
produce a parsed result with the same canonical shape, with the
attributed feed carrying populated `region/languages/revision/
hash_sha1/...` fields and the bare feed carrying the equivalents
derived from filename parsing.

**Acceptance Scenarios**:

1. **Given** a Torznab response containing `<torznab:attr name="region" value="USA"/>`,
   **When** the client parses it, **Then** the resulting record
   carries `region = "US"` (after the standard ISO-3166 alpha-2
   normalisation from the foundation identification layer).
2. **Given** a response containing `<grabarr:region value="EUR"/>`
   in the `grabarr:` namespace, **When** the client parses it,
   **Then** the record carries `region = "EU"` (same normalisation).
3. **Given** a response with no extended attributes, **When** the
   client parses a release name like `Sonic the Hedgehog (USA) (Rev A).md`,
   **Then** the record's region/revision/etc. are filled in by the
   foundation filename parsers and the source is recorded as
   `filename` rather than `torznab`.

---

### User Story 4 — A flaky indexer must not poison the system (Priority: P2)

One configured indexer starts returning timeouts and 500s. Romarr's
per-indexer circuit breaker opens after 5 failures within 60 s,
short-circuits subsequent calls without a network round-trip, and
re-tests in half-open state after a cooldown.

**Why this priority**: External degradation is routine; the
operator's other indexers must continue serving.

**Independent Test**: Stub one indexer's HTTP layer to fail
deterministically; trigger 6 sequential calls; verify the 6th call
short-circuits without an outbound request; advance time 60 s past
the last failure; trigger one more call and verify a single trial
request goes out; on success the breaker re-closes.

**Acceptance Scenarios**:

1. **Given** an indexer returning failures on every call, **When**
   the breaker has logged 5 failures within a 60 s window, **Then**
   the 6th call raises a `CircuitOpenError` without a network
   request and other indexers remain unaffected.
2. **Given** the breaker is open and the cooldown elapses, **When**
   the next call is made, **Then** the breaker enters half-open,
   allows exactly one trial call, and re-closes on success or
   re-opens on failure.

---

### User Story 5 — Per-indexer rate limiting prevents bans (Priority: P2)

A configured indexer has a `rate_limit_seconds = 5`. The operator
issues two searches in rapid succession against that indexer; the
second call is delayed automatically so the indexer never receives
two requests within 5 seconds.

**Why this priority**: Free-tier indexers ban accounts that exceed
their rate limits. Rate limiting protects the operator from a
self-inflicted ban without the operator having to remember it.

**Independent Test**: Configure an indexer with `rate_limit_seconds = 5`;
issue two consecutive client calls back-to-back inside the test;
record their dispatch timestamps; verify the gap between them is
at least 5 s.

**Acceptance Scenarios**:

1. **Given** `rate_limit_seconds = 5`, **When** two calls are issued
   100 ms apart, **Then** the second call's outbound HTTP request
   does not fire until at least 5 s after the first one's outbound
   timestamp.
2. **Given** the rate limit is `0`, **When** calls are issued
   back-to-back, **Then** no delay is inserted.

---

### User Story 6 — Indexer returns malformed XML (Priority: P3)

A registered indexer starts returning truncated or syntactically
broken XML. Romarr does not crash; it logs a structured error,
marks that indexer as unhealthy, surfaces the issue in the health
endpoint, and lets searches against other indexers continue.

**Why this priority**: Real-world indexers misbehave in the field.
Robustness here is what separates a production-grade *arr from a
toy.

**Independent Test**: Stub one indexer to return malformed XML;
trigger a search across two indexers (one healthy, one stubbed);
verify the healthy indexer's results come back intact, the stubbed
indexer's row in `/api/v3/health` reports a structured error, and
no exception escapes to the caller.

**Acceptance Scenarios**:

1. **Given** an indexer returning malformed XML, **When** a search
   is issued, **Then** the call returns no results from that
   indexer, an entry appears in `/api/v3/health` with a structured
   `category = 'indexer'` error referencing the indexer id, and
   sibling indexers' results come back unaffected.
2. **Given** the same indexer recovers (returns valid XML on a
   subsequent call), **When** the next search runs, **Then** the
   health entry clears and results come through.

---

### User Story 7 — Category overlap is deduplicated (Priority: P3)

A search returns the same release once under category 1060
(Console-Other) and once under category 7010 (Misc). Romarr
collapses these to a single record (deduped by GUID) and lets the
downstream decision engine score it once.

**Why this priority**: Without dedup, a release appearing in two
categories would be presented twice to the operator and could
artificially out-score competitors in the decision engine.

**Independent Test**: Stub an indexer's response to include the
same release record (identical GUID + URL) twice under different
categories; verify the parsed result list contains exactly one
entry.

**Acceptance Scenarios**:

1. **Given** a Torznab response with two `<item>` entries sharing
   the same `<guid>`, **When** parsed, **Then** the result list
   contains a single record (the duplicate is dropped, with a
   structured info log).

---

### Edge Cases

- Indexer's `t=caps` returns valid XML but with no `<searching>`
  block → indexer is saved but `enable_automatic_search` and
  `enable_interactive_search` MUST default to `false`; the operator
  is prompted to enable them manually.
- Indexer returns an unrecognised `format_type`-style XML element →
  ignored; parsing continues.
- Prowlarr posts an indexer whose `url` is not reachable from
  Romarr → indexer is **persisted** anyway (per Prowlarr's expected
  behaviour) but health check immediately marks it unhealthy.
- Two distinct Prowlarr instances both register against Romarr →
  supported; each `Application` row carries its own app token; both
  can push indexers without conflict.
- An app token is leaked → operator deletes the Application row;
  the token's hash disappears; subsequent calls bearing that token
  are rejected.
- A search returns a `nzb:` URL where Romarr expects a torrent →
  the result still parses; the protocol field is recorded so the
  downstream search-engine spec can route it to the right download
  client.
- An extended Torznab attribute carries an unknown value (e.g.,
  `region = "ZZ"`) → a structured warning is logged; the unknown
  value is dropped; the field falls back to filename parsing for
  that release.
- Same `(implementation, url)` indexer is registered twice (once
  by Prowlarr, once manually) → second registration is rejected
  with HTTP 409.
- A circuit-breaker open for indexer A does not affect indexer B
  even when A and B point to the same upstream service.
- Rate-limit clock skew (system clock jumps) → the rate limiter
  uses a monotonic clock; clock jumps do not collapse the window.

## Requirements *(mandatory)*

### Functional Requirements

**Newznab/Torznab client**

- **FR-001**: The system MUST expose a generic Newznab/Torznab HTTP
  client capable of calling `t=caps`, `t=search`, and `t=tvsearch`
  (the latter is unused for ROMs but kept for future-compat;
  exposed as a no-op for now).
- **FR-002**: The client MUST parse Torznab XML responses including
  the standard fields (`title`, `guid`, `link`, `pubDate`,
  `enclosure`, `description`, `category`, `size`, `seeders`,
  `peers`, `files`, `infoHash`, `magnetUrl`).
- **FR-003**: The client MUST parse Romarr-relevant extended
  Torznab attributes: `region`, `languages`, `revision`,
  `dump_tags`, `hash_sha1`, `hash_crc32`, `naming_convention`,
  `dat_source`. Both the standard `torznab:` namespace and the
  `grabarr:` namespace MUST be accepted.
- **FR-004**: When an extended attribute is absent, the client
  MUST fall back to the foundation filename parsers; the resulting
  record MUST record the source of each field
  (`torznab` / `grabarr` / `filename`) for traceability.
- **FR-005**: The client MUST normalise region and language values
  to ISO-3166-1 alpha-2 / ISO-639-1 using the same translation
  table used by the foundation filename parsers.

**Connectivity testing**

- **FR-006**: The system MUST provide a connectivity test that
  performs `t=caps`. If caps include a `<search>` block, the test
  MUST also perform a minimal search (`t=search&q=test&cat=1000`)
  to verify search works.
- **FR-007**: An indexer MUST NOT be persisted from a `test=true`
  configuration request unless connectivity passes.

**Per-indexer rate limit**

- **FR-008**: The system MUST enforce a per-indexer rate limit
  configured by `rate_limit_seconds` (default 5). Requests issued
  faster than that interval MUST be delayed before the outbound
  HTTP call fires.
- **FR-009**: The rate limiter MUST use a monotonic clock so
  system-clock jumps do not collapse the window.

**Per-indexer request timeout**

- **FR-009a**: Every outbound HTTP call to an indexer
  (`t=caps` / `t=search` / `t=rss`) MUST be bounded by a
  per-indexer `timeout_seconds` value (default 30 s,
  permitted range 5 to 120 s). The timeout is wall-clock and
  applies to the full read-to-end of body. Exceeding the timeout
  MUST raise a structured error, MUST count as a failure for
  circuit-breaker purposes (FR-010), and MUST NOT propagate as
  an uncaught exception to sibling indexers.

**Per-indexer circuit breaker**

- **FR-010**: The system MUST guard each indexer with a circuit
  breaker. Five failures within a 60-second window MUST open the
  circuit.
- **FR-011**: A breaker that has been open for 60 seconds without
  new failures MUST enter half-open and allow exactly one trial
  call. A successful trial closes the breaker; a failure re-opens
  it.

**Bidirectional Prowlarr sync**

- **FR-012**: The system MUST expose `/api/v3/applications`
  endpoints that Prowlarr expects: GET / POST / DELETE.
- **FR-013**: On registration (`POST /api/v3/applications`) the
  system MUST generate a cryptographically-random 32-byte app
  token, return its plaintext exactly once in the response body,
  and persist only its hash.
- **FR-013a**: `POST /api/v3/applications` MUST require the
  caller to authenticate as the operator's admin role (admin
  session cookie OR admin API key). Successful registration
  returns the app token in the response body; from that moment
  on, the registered Prowlarr instance MUST authenticate every
  subsequent call (e.g., `POST /api/v3/indexer` with
  `source = 'prowlarr'`, the deletion callback in FR-016) using
  the app token alone — the admin credential is not retained on
  the Prowlarr side. `GET /api/v3/applications` MUST be
  admin-only; `DELETE /api/v3/applications/{id}` MUST be
  admin-only and revokes the app token's hash so further calls
  bearing it are rejected with HTTP 401.
- **FR-014**: The system MUST expose
  `GET /api/v3/indexer/schema`, `GET /api/v3/indexer`,
  `POST /api/v3/indexer`, `PUT /api/v3/indexer/{id}`,
  `DELETE /api/v3/indexer/{id}` consistent with Prowlarr's expected
  contract.
- **FR-015**: Indexers pushed by Prowlarr MUST be marked
  `source = 'prowlarr'` and reference their parent Application via
  `prowlarr_app_id`. Prowlarr-pushed indexers MUST NOT be editable
  through manual paths.
- **FR-016**: When a Prowlarr-managed indexer is deleted in
  Romarr, the system MUST attempt a best-effort callback to
  Prowlarr to reflect the change; failure MUST log a warning but
  MUST NOT block the local delete.

**Direct (non-Prowlarr) configuration**

- **FR-017**: The system MUST accept a manually-configured
  Newznab/Torznab indexer (URL + API key + categories + tags).
  These MUST be marked `source = 'manual'`.
- **FR-018**: A manual configuration request MUST run
  connectivity testing before persistence (FR-006).

**RSS sync orchestration**

- **FR-019**: The system MUST expose `IndexerRssSync` with
  `sync_all_enabled_indexers()` and `sync_indexer(indexer_id)`.
  The class MUST return parsed results without making any
  decision; scheduling and dispatch belong to a future spec.
- **FR-019a**: When a single search invocation targets N enabled
  indexers, the system MUST fan calls out concurrently via
  `asyncio.gather(..., return_exceptions=True)` (or equivalent).
  A failure on one indexer (timeout, circuit-open, malformed XML,
  authentication error) MUST NOT cancel sibling indexer calls;
  the failure MUST be captured, logged, surfaced as an
  `IndexerHealthIssue` (FR-024), and the merged result list MUST
  be the union of every successful response. Total search
  wall-clock latency MUST be approximately
  max(per-indexer latency) rather than sum-of-all.

**Category mapping consumption**

- **FR-020**: The system MUST read the optional
  `newznab_category_ids` JSON column on the platform table (added
  by the platform-pack pipeline) and use it to suggest categories
  on indexer configuration UIs and to filter searches by platform.

**Persistence & encryption**

- **FR-021**: The system MUST persist indexers and applications
  in two new tables (`indexer`, `application`) per
  `data-model.md`.
- **FR-022**: All API keys (indexer `api_key`, application
  `prowlarr_api_key`) MUST be encrypted at rest using the same
  Fernet helper introduced in the metadata feature
  (`ROMARR_AUTH_SECRET_KEY`-derived key).
- **FR-023**: App tokens (Application `app_token`) MUST be stored
  as a salted hash; the plaintext is returned only once at
  registration.

**Health & observability**

- **FR-024**: A failing indexer (malformed XML, sustained errors,
  open breaker) MUST surface in the future `/api/v3/health`
  endpoint via a structured `IndexerHealthIssue` record. This
  feature ships the issue producer; the consumer endpoint is
  formalised in the Notifications/Health spec.
- **FR-025**: The system MUST log every outbound indexer call at
  `INFO` level with the indexer id, the operation
  (`caps`/`search`/`rss`), the outcome, and the elapsed time, so
  operators can tail logs to diagnose problems.

**Result deduplication**

- **FR-026**: When a single search returns multiple records with
  the same `guid` (e.g., the indexer indexes the same release
  under two categories), the parser MUST collapse them to a single
  record, recording the union of categories.
- **FR-026a**: Each indexer MUST carry a `result_limit` column
  (default 100, permitted range 1 to 500) that bounds the number
  of `<item>` records the parser will surface for a single
  search invocation. When the indexer's `t=caps` response
  advertises pagination support, the client MUST pass the
  configured limit as the `limit=` query parameter on the
  outbound `t=search` request so the indexer truncates server-side.
  When the indexer does not support `limit=`, the parser MUST
  truncate after parsing (post-dedup) and log an INFO-level
  notice indicating the cap was reached. The cap applies
  per-indexer-per-search; merging across indexers (FR-019a) is
  performed after each indexer has been individually capped.

### Key Entities

- **Indexer**: A Newznab/Torznab-compatible search source. Owns
  its credentials, its rate-limit policy, its enabled set of
  categories, and its source provenance (`manual` vs `prowlarr`).
- **Application**: A Prowlarr instance that has registered Romarr
  as a downstream application. Holds a callback token (hashed)
  and the credentials Romarr uses to call back into Prowlarr.
- **Search Result**: A parsed Torznab `<item>` enriched with the
  union of `torznab:` / `grabarr:` extended attributes plus a
  filename-parsed fallback shape, with provenance per field.
- **Indexer Health Issue**: A structured record produced when an
  indexer misbehaves. Surfaced to the future health endpoint.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can configure a single Newznab indexer
  end-to-end (URL + API key + categories + connectivity test) in
  under 30 seconds of operator time and immediately receive
  parsed search results.
- **SC-002**: A Prowlarr instance, posting standard payloads to
  `/api/v3/applications` and then `/api/v3/indexer`, ends up with
  its indexers materialised in Romarr in 100% of the
  Prowlarr-shape compatibility test fixtures.
- **SC-003**: Across a fixture corpus of at least 30 Torznab
  feeds (mix of vanilla, Romarr-extended, Grabarr-prefixed), the
  parser produces the documented canonical shape with correct
  field provenance in 100% of cases.
- **SC-004**: Five consecutive failures from one indexer within
  60 seconds open its circuit breaker; the sixth call returns
  immediately without an outbound HTTP request; sibling indexers
  remain unaffected (zero collateral failures across a 100-call
  fixture suite).
- **SC-005**: With `rate_limit_seconds = 5`, two back-to-back
  outbound HTTP calls to one indexer are observably spaced by at
  least 5 seconds (timing slack ≤ 200 ms over 100 trials).
- **SC-006**: An indexer returning malformed XML produces a
  structured health issue and zero application crashes across
  100 sequential calls.
- **SC-007**: Inspecting the database file with a SQLite browser
  shows zero plaintext indexer API keys and zero plaintext
  Prowlarr API keys.
- **SC-008**: A search whose Torznab response contains the same
  GUID under two categories yields exactly one parsed result in
  100% of dedup test cases.
- **SC-009**: Test coverage on the indexers module MUST be at
  least 75%.

## Assumptions

These resolve the OPEN CLARIFICATIONS supplied with the input,
applying the operator's proposals.

- **Invalid XML handling**: A failing indexer logs a structured
  error, is surfaced in `/api/v3/health` (consumer endpoint
  formalised in a later spec), and never crashes a search
  (FR-024, US6).
- **`POST /api/v3/indexer/{id}/test`**: implemented in this
  feature; runs `t=caps` plus a minimal sample search and
  returns a structured result.
- **Category overlap dedup**: dedupe by GUID within a single
  search response; let the downstream decision engine score the
  surviving record (FR-026, US7).
- **App token format**: 32 random bytes (base64-encoded), stored
  as a salted hash (FR-013, FR-023). The plaintext is returned
  only at registration time.

Other assumptions:

- Per-indexer logging stays at INFO level by default. A future
  observability spec may add OpenTelemetry tracing.
- The `/api/v3/health` endpoint is **not** delivered by this
  feature; the producer side ships here, the consumer endpoint
  is delivered alongside Notifications.
- The Newznab category IDs documented in the input are accepted
  defaults; the platform-pack `newznab_category_ids` column is
  the operator-editable source of truth.

### Out of Scope

- RSS sync **scheduling** (Tasks/Scheduler spec; this spec ships
  the synchronous `sync_all_enabled_indexers()` function it will
  call).
- The decision/search engine that turns search results into
  grab decisions (Search & Decision Engine spec).
- Per-platform → category mapping data (Platform Packs spec
  populates `newznab_category_ids` on the platform table; this
  spec only consumes it).
- Cookie-based indexers (deferred to v1+; requires session
  handling that Prowlarr already does well).
- Captcha-protected indexers (deferred indefinitely; operators
  must use Prowlarr's solver).
- The `/api/v3/health` HTTP surface (Notifications/Health spec).
- Per-user indexer credentials (Auth/Multi-user spec).
