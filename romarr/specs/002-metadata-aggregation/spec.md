# Feature Specification: Metadata Aggregation

**Feature Branch**: `002-metadata-aggregation` (branch creation skipped: git repo lives in parent dir)
**Created**: 2026-04-29
**Status**: Draft
**Depends on**: `001-foundation` — uses `Game`, `Platform`, and the `locked_fields` JSON column from the foundation domain model
**Input**: User description: "Build the metadata aggregation layer for Romarr. 9 metadata providers, an aggregator that merges them per-field with priority, a local cache with TTL, and a lock-aware merge that never destroys existing field values."

## Clarifications

### Session 2026-04-29

- Q: Who manages the IGDB Twitch OAuth bearer token's lifecycle? → A: Application-managed. The operator stores `client_id` and `client_secret` (encrypted at rest); the IGDB provider client lazily obtains a bearer via the Twitch `client_credentials` flow on first use and on a 401 mid-flight; the bearer is cached in memory only with `expires_at` and is NOT persisted
- Q: What happens to the on-disk cover file when a refresh changes the cover's content type (e.g., `123.jpg` → `123.png`)? → A: One-cover-per-Game invariant. The new bytes are written at the new extension and any sibling `data/covers/<game_id>.*` with a different extension is deleted; `Game.cover_path` is updated atomically
- Q: What's the eviction / size-bound policy for the `metadata_cache` table? → A: TTL-only eviction. The unique constraint `(provider_name, provider_game_id)` keeps cache size bounded at one row per (provider, Game); refreshes overwrite in place. No LRU and no max-size cap at MVP — premature complexity until an operator reports it
- Q: What happens when concurrent refresh-metadata calls fire on the same Game? → A: Coalesce into a single in-flight refresh per Game via a per-Game advisory lock. Concurrent callers block on the lock and, when it releases, receive the same just-computed result; provider quota is burned once
- Q: How does the aggregator throttle outbound provider request rates? → A: Per-provider token-bucket limiter with the rate exposed as a Setting on `metadata_provider_config`. Conservative defaults seeded on first run (IGDB 4 req/s, MobyGames 1 req/s, ScreenScraper 2 req/s, others 5 req/s); operators can raise or lower per provider. 429 responses still trip the circuit breaker as a safety net

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Enrich a Game from a primary provider (Priority: P1)

A Romarr operator has the foundation layer up, has just added *Sonic the
Hedgehog* on Mega Drive, and wants the system to fetch its summary, cover
art, genres, release date, developer, and publisher automatically from a
configured primary metadata provider.

**Why this priority**: This is the headline value proposition of the
metadata feature. Without enrichment, a Game record carries only the
title from filename matching.

**Independent Test**: Configure one provider with valid credentials. Add
a Game. Trigger a metadata refresh. Verify the Game now carries summary,
cover URL → local cover file, genres, release date, developer, publisher.

**Acceptance Scenarios**:

1. **Given** a primary provider is configured and reachable, **When**
   the operator adds a Game and triggers metadata refresh, **Then** the
   Game record is populated with summary, cover, genres, release date,
   developer, and publisher; cover art is stored locally; the raw
   provider response is cached.
2. **Given** the same Game and provider, **When** the operator triggers
   another refresh **before** the cache TTL expires, **Then** no new
   API call is made and the cached response is reused.
3. **Given** the cache is younger than its TTL, **When** the operator
   manually changes the priority list for a single field, **Then** the
   field is re-aggregated from cached responses without any API call.

---

### User Story 2 — Locked fields are never overwritten (Priority: P1)

A Romarr operator has manually edited the title of a Game (e.g., to use
the regional title they prefer). They mark that field as **locked**. A
later refresh must never overwrite it, even when a higher-priority
provider returns a different value.

**Why this priority**: This is the explicit "RomM issue #1770" scenario
called out in the constitution (Article IX) and in the input. Silent
overwrite of curated data is the worst class of bug for this product.

**Independent Test**: Create a Game with a manually-edited title. Add
the title to `locked_fields`. Trigger a refresh that would otherwise
overwrite it. Verify the title is unchanged.

**Acceptance Scenarios**:

1. **Given** a Game whose `locked_fields` contains `"title"`, **When**
   the operator triggers a metadata refresh, **Then** the persisted
   title is unchanged regardless of any provider's returned value.
2. **Given** the same Game, **When** the operator unlocks the field and
   triggers another refresh, **Then** the title is updated from the
   highest-priority provider that returned a non-empty value.

---

### User Story 3 — Adding a new provider is additive, not destructive (Priority: P1)

A Romarr operator already has IGDB configured. They later add
ScreenScraper as a second provider and re-run aggregation. Their
existing field values must NOT be destroyed; aggregation must merge
additively, only filling fields that were previously empty or
overriding only when the new provider has higher priority for that
field AND the field is not locked.

**Why this priority**: This is the additive-merge invariant. Without
it, the cost of trying a new provider is "lose existing curation",
which would discourage exploration.

**Independent Test**: Configure provider A; refresh; record Game state.
Add provider B with a higher priority for some fields; refresh again;
verify only the affected non-locked fields changed and nothing was
nullified.

**Acceptance Scenarios**:

1. **Given** a Game enriched by provider A only, **When** provider B is
   enabled and refresh is triggered, **Then** any field where B has
   higher priority and returns a non-empty value is updated; every
   other previously-populated field retains its value; no field is
   set to NULL.
2. **Given** a Game with `summary` populated and provider B has lower
   priority on `summary`, **When** refresh runs, **Then** the existing
   `summary` is unchanged.

---

### User Story 4 — A failing provider must not poison the pipeline (Priority: P2)

A Romarr operator has 4 providers configured. One of them starts
returning timeouts for every request. The aggregator must not block on
that provider, must open its circuit breaker after a small number of
failures, and must continue to enrich Games from the other providers.

**Why this priority**: External services degrade frequently; the
operator's experience must degrade gracefully.

**Independent Test**: Stub one provider's HTTP layer to fail
deterministically. Trigger refresh on 10 Games. Verify the 9 healthy
provider calls still succeed and the failing provider's circuit
breaker opens after the configured threshold.

**Acceptance Scenarios**:

1. **Given** a provider returning errors on every call, **When** the
   aggregator runs across many Games, **Then** after 5 failures within
   60 seconds the circuit breaker opens, subsequent calls short-circuit
   without a network round-trip, and other providers continue serving.
2. **Given** the breaker is open and the provider recovers, **When**
   the cooldown elapses, **Then** the breaker enters half-open, allows
   one trial call, and re-closes on success.

---

### User Story 5 — Provider configuration is encrypted at rest (Priority: P2)

A Romarr operator stores an IGDB Twitch OAuth secret, a ScreenScraper
password, and a MobyGames API key. These secrets must be encrypted at
rest in the database; reading the database file directly must not
expose them as plain text.

**Why this priority**: Personal-use Romarr instances are commonly
exposed via reverse proxy and database backups travel over networks.
Plain-text secrets in a backup are a credential-leak waiting to happen.

**Independent Test**: Configure a provider with a known secret; query
the underlying configuration table directly; verify the secret is not
visible as plaintext; round-trip through the configured-loader and
verify the original secret is recovered.

**Acceptance Scenarios**:

1. **Given** an operator-supplied encryption key, **When** the operator
   stores a provider's API key via the configuration endpoint,
   **Then** the value persisted in the database is ciphertext; the
   plaintext is recoverable only through the application using the key.
2. **Given** the encryption key is rotated, **When** the operator
   triggers a re-encryption, **Then** all existing secrets are
   re-encrypted with the new key and old ciphertext is unreadable.

---

### User Story 6 — Cover art is stored locally with the right format (Priority: P3)

When a Game's cover is fetched, the bytes are saved to a local
directory using the right file extension based on the response
content type (`jpg`, `png`, or `webp`).

**Why this priority**: A canonical cover path lets later UI/exporters
serve covers without re-fetching, and constitutes the "data" Romarr
owns for offline use.

**Independent Test**: Trigger refresh for a Game whose primary cover
provider returns a JPEG; verify a local file appears at the expected
path with `.jpg` extension; same for PNG (`.png`) and WebP (`.webp`).

**Acceptance Scenarios**:

1. **Given** a provider returning `Content-Type: image/jpeg`, **When**
   the cover is fetched, **Then** the file is stored as
   `data/covers/<game_id>.jpg`.
2. **Given** a provider returning `Content-Type: image/png`, **When**
   the cover is fetched, **Then** the file is stored as
   `data/covers/<game_id>.png`.
3. **Given** a previously-stored cover and a refresh that returns the
   same image bytes, **When** the cover step runs, **Then** the file
   is overwritten only if the bytes differ; otherwise the operation
   is a no-op.

---

### User Story 7 — Field priority changes are reflected without API calls (Priority: P3)

The operator decides that for `summary` they prefer MobyGames over
IGDB. They change the field-priority. The next aggregation reflects
the change without fetching any provider — it simply re-projects from
the cached responses.

**Why this priority**: Changing taste should be cheap. Re-aggregating
from cache is the lock-screen vs. wallpaper of metadata.

**Independent Test**: Aggregate a Game once (cache populated for both
providers). Change the priority. Trigger re-aggregation. Verify no API
call happened and the persisted value matches the new priority winner.

**Acceptance Scenarios**:

1. **Given** cached responses for two providers exist, **When** the
   operator updates the priority list for `summary` and re-aggregation
   runs, **Then** the persisted `summary` reflects the new winner and
   no provider receives a network request.

---

### Edge Cases

- All providers fail for a Game → the Game record stays minimal (title
  from filename match); a `needs_metadata_refresh` flag is set; next
  scheduled refresh retries.
- A provider returns a value of the wrong type (e.g., string where the
  contract says list) → the value is dropped; a structured warning is
  logged; aggregation continues.
- A cached response exists past its TTL → it is treated as expired;
  next aggregation triggers a fresh fetch.
- Two providers return the same cover URL → only one is downloaded
  (deduplicated by SHA-256 of bytes after fetch).
- Provider's platform mapping is unknown for a Romarr platform slug →
  that provider is skipped for the Game with a structured warning;
  other providers continue.
- Encryption key not set at startup but secrets exist in the database
  → application refuses to start; operator must supply the key.
- Encryption key rotation while a refresh is in flight → in-flight
  refresh continues with the old key; new operations use the new key;
  re-encryption is performed transactionally.
- The same Game has two `metadata_cache` rows for the same provider
  (corrupted state) → unique constraint prevents this; if it slipped
  through historically, only the freshest row is used.

## Requirements *(mandatory)*

### Functional Requirements

**Provider clients**

- **FR-001**: The system MUST expose a `MetadataProvider` interface
  with `name`, `requires_auth`, `configure()`, `health_check()`,
  `search_games()`, `get_game()`, `get_cover()`, and
  `get_platform_mapping()`.
- **FR-002**: Nine concrete provider clients MUST be implemented behind
  this interface: IGDB, ScreenScraper, MobyGames, LaunchBox Games DB,
  SteamGridDB, RetroAchievements, HowLongToBeat, Hasheous, PlayMatch.
- **FR-003**: Each provider MUST translate its native errors into a
  shared `ProviderError` hierarchy (`AuthError`, `RateLimitError`,
  `NotFoundError`, `TransientError`, `ProviderError`) so that the
  aggregator can react uniformly.
- **FR-004**: Each provider MUST be guarded by a per-service circuit
  breaker (5 failures within 60 s opens the circuit) and by a
  tenacity-style retry of up to 3 attempts with exponential backoff
  for transient errors.
- **FR-004a**: Each provider client MUST proactively throttle
  outbound requests via a per-provider token-bucket limiter. The
  bucket's refill rate (requests per second) and burst size MUST be
  configurable per provider on the `metadata_provider_config` row
  (`rate_limit_rps`, `rate_limit_burst`); the aggregator MUST honour
  the configured limit before issuing a request rather than relying
  on 429 responses alone. Conservative defaults MUST be seeded on
  first run: IGDB 4 req/s (burst 8), MobyGames 1 req/s (burst 2),
  ScreenScraper 2 req/s (burst 4), all others 5 req/s (burst 10).
  HTTP 429 responses MUST still count as failures for circuit-breaker
  purposes (FR-004) — the throttle is a proactive safeguard, not a
  replacement for the breaker.
- **FR-005**: SteamGridDB MUST NOT be invoked during the standard
  scan/refresh flow; it is only invoked when the operator manually
  picks a cover.
- **FR-006**: RetroAchievements MUST NOT be used as a matching source;
  it only enriches an already-matched Game with `achievements_count`.
- **FR-007**: HowLongToBeat MUST only contribute the duration field
  (`hltb_main`).
- **FR-007a**: The IGDB provider client MUST obtain its bearer token
  by performing the Twitch `client_credentials` OAuth flow against
  `https://id.twitch.tv/oauth2/token` using the operator-supplied
  `client_id` and `client_secret` (the only two values persisted —
  encrypted — for IGDB). The bearer MUST be cached **in memory only**
  with its `expires_at`. The client MUST refresh the bearer (a) lazily
  on first use after process start, (b) when an in-flight request
  returns HTTP 401, and (c) when the cached bearer is within 60
  seconds of `expires_at`. The bearer MUST NOT be persisted to the
  database, written to disk, or exposed via any API endpoint. Failure
  of the OAuth call MUST raise `ProviderError(AuthError)` for IGDB
  while leaving other providers unaffected.

**Aggregation**

- **FR-008**: Aggregation MUST be **per-field, priority-ordered**. Each
  configurable field has its own ordered list of providers.
- **FR-009**: Aggregation MUST be **additive**: re-aggregation MUST
  NEVER set a previously-populated field back to NULL because the new
  winning provider returned no value.
- **FR-010**: A field listed in the Game's `locked_fields` MUST be
  skipped during aggregation; the persisted value MUST remain
  unchanged.
- **FR-011**: Default field-priority lists MUST be seeded on first run
  matching the recommendations: `title: igdb > screenscraper > mobygames > launchbox`,
  `summary: igdb > mobygames > screenscraper`, `cover: igdb > screenscraper > steamgriddb > launchbox`,
  `genres: igdb > mobygames > launchbox`, `release_date: mobygames > igdb > screenscraper`,
  `developer: mobygames > igdb`, `publisher: mobygames > igdb`,
  `rating: igdb`, `achievements_count: retroachievements`,
  `hltb_main: howlongtobeat`.
- **FR-012**: Changing the priority list for a field MUST NOT
  invalidate the cache; aggregation MUST re-project from existing
  cached responses without any new API call.
- **FR-013**: When all providers fail to return any data for a Game,
  the system MUST set a `needs_metadata_refresh` flag on the Game so
  later refreshes can retry.
- **FR-013a**: Concurrent refresh-metadata invocations on the same
  Game MUST be coalesced into a single in-flight refresh via a
  per-Game advisory lock. The first caller acquires the lock and
  performs the refresh; concurrent callers MUST block on the lock
  and, on lock release, MUST return the same result the first
  caller computed without re-invoking any provider. The lock MUST
  release on completion (success or failure) and MUST be reclaimable
  by a watchdog if the lock holder dies (e.g., process crash); a
  reasonable lock-holder TTL is 5 minutes — well above the 30-second
  warm and 5-minute cold aggregation budgets in SC-005.

**Cache**

- **FR-014**: Each provider response MUST be persisted in a
  `metadata_cache` row keyed by `(provider_name, provider_game_id)` and
  scoped to a `game_id`.
- **FR-015**: Each cache row MUST carry a `fetched_at` and an
  `expires_at`. Cache TTL MUST be configurable per provider; default
  is 30 days.
- **FR-016**: A cache row past `expires_at` MUST be treated as expired
  and replaced on the next aggregation that needs it.
- **FR-016a**: The `metadata_cache` table MUST be eviction-bound only
  by TTL (FR-016) and by the unique constraint
  `(provider_name, provider_game_id)`. A refresh of a (provider, Game)
  pair MUST overwrite the existing row in place rather than insert a
  new row. No LRU eviction, no row-count cap, and no aggregate-size
  cap MUST be applied at MVP. The system MUST surface a health-check
  warning when the table exceeds 2 GB on disk so the operator is
  aware before it becomes a problem; this warning is informational
  and does not block aggregation.

**Cover storage**

- **FR-017**: When a cover is fetched, the bytes MUST be persisted at
  `data/covers/<game_id>.<ext>` where `<ext>` is derived from the
  response `Content-Type` (`jpg`, `png`, or `webp`).
- **FR-017a**: At most ONE cover file MUST exist per Game on disk.
  When a refresh produces a new cover whose extension differs from
  the currently-stored cover, the new file MUST be written first,
  any sibling `data/covers/<game_id>.*` whose extension differs from
  the new one MUST be deleted, and `Game.cover_path` MUST be updated
  in the same transaction. The byte-equality short-circuit in User
  Story 6 acceptance scenario 3 still applies (no rewrite when bytes
  match), but a content-type change MUST always proceed through the
  replace path even if image dimensions or visible content are
  unchanged.
- **FR-018**: Screenshots are out of scope.

**Provider configuration**

- **FR-019**: Provider credentials (API keys, OAuth secrets, passwords)
  MUST be encrypted at rest using a key derived from
  `ROMARR_AUTH_SECRET_KEY`.
- **FR-020**: A `metadata_provider_config` row MUST exist per known
  provider; the `enabled` flag MUST be respected by the aggregator.
- **FR-021**: The application MUST refuse to start if encrypted
  configuration rows exist but `ROMARR_AUTH_SECRET_KEY` is not set.

**API stubs (full implementation in API spec)**

- **FR-022**: The system MUST expose endpoint stubs at:
  `GET /api/v3/metadata/provider`,
  `POST /api/v3/metadata/provider/{name}`,
  `POST /api/v3/metadata/provider/{name}/test`,
  `GET /api/v3/metadata/field-priority`,
  `PUT /api/v3/metadata/field-priority/{field_name}`,
  `POST /api/v3/game/{id}/refresh-metadata`.
  These endpoints MUST be wired through the aggregator and provider
  registry; payload schemas and authentication wiring belong to the
  API and Auth specs.

### Key Entities

- **MetadataProvider**: An adapter to a single external metadata
  source. Owns its credentials, its rate-limit policy, and its
  per-field translation from raw provider data to Romarr's canonical
  Game shape.
- **Provider Configuration**: Persisted, encrypted credentials and
  enable/disable state for each known provider.
- **Field Priority**: An ordered list of providers per Game-field.
- **Metadata Cache Entry**: A single provider's response for a single
  Game, with a freshness window.
- **Aggregation**: The act of producing a canonical Game shape from
  the union of provider cache entries, respecting per-field priority
  and `locked_fields`.
- **Cover File**: A locally-stored cover image with extension
  determined by content type.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can configure a primary provider, add a
  Game, trigger a refresh, and observe the Game gain at least four
  populated metadata fields plus a local cover file in under 30
  seconds of operator-perceived time, on a typical home network.
- **SC-002**: Re-running aggregation on a Game whose `title` is
  locked, against any provider configuration, leaves the persisted
  `title` unchanged in 100% of test cases.
- **SC-003**: Adding a second provider to a previously-enriched Game
  and re-aggregating leaves every previously-non-empty, non-locked
  field that the new provider does not "win" untouched in 100% of
  test cases. No field is silently set to NULL.
- **SC-004**: When a single provider is unavailable, the aggregator's
  circuit breaker opens after exactly 5 failures within a 60-second
  window; further attempts to that provider return immediately
  without a network round-trip until the cooldown elapses.
- **SC-005**: A full aggregation pass over 100 Games with all caches
  warm completes in under 30 seconds; with all caches cold and four
  providers reachable, in under 5 minutes.
- **SC-006**: Inspecting the database file with a SQLite browser shows
  zero plaintext provider credentials.
- **SC-007**: For a cached, in-window response, aggregating triggers
  zero outbound HTTP calls.
- **SC-008**: Cover files end up stored under `data/covers/` with
  extensions `jpg`, `png`, or `webp` matching the originating
  response's content type in 100% of test cases.
- **SC-009**: Test coverage on the metadata module MUST be at least
  75%.

## Assumptions

These resolve the open clarifications supplied with the input,
applying the operator's proposals.

- **Provider platform IDs**: Each provider's platform identifier is
  stored on the existing `platform` table (columns `igdb_id`,
  `screenscraper_id`, `mobygames_id`, etc., already present from the
  foundation spec). The aggregator looks up each provider's own ID
  for the Game's Platform when calling `search_games` /
  `get_platform_mapping`.
- **Cache invalidation on priority change**: A field-priority change
  MUST NOT invalidate the cache. The aggregator simply re-projects
  the canonical Game shape from existing cached responses.
- **All providers fail for a Game**: The Game record stays minimal
  (title from filename match), a `needs_metadata_refresh` flag is set
  on the Game, and the next scheduled refresh retries.

Other assumptions:

- The encryption key for provider credentials is supplied via
  `ROMARR_AUTH_SECRET_KEY`; key derivation uses an industry-standard
  KDF (PBKDF2 / scrypt / Argon2 — final choice in `plan.md`).
- The 9 providers listed are exhaustive for MVP; adding a 10th is a
  later spec, not a code change here (the registry pattern accepts
  new providers without aggregator changes).
- Bulk LaunchBox XML import is interface-defined here and deferred
  to v1; only the per-Game query path is implemented.
- The HowLongToBeat provider has no official API and uses the same
  request shape as the existing community Python clients; if its
  surface changes, only that one client module is touched.

### Out of Scope

- UI for editing metadata (UI spec).
- Background metadata refresh scheduler (Tasks/Scheduler spec; this
  spec exposes the synchronous `refresh()` function it will call).
- Bulk LaunchBox XML import (interface defined; full implementation
  deferred to v1).
- Screenshots (firm-out per Constitution Article IX).
- Manual cover override via SteamGridDB UI (UI spec).
- Per-user provider credentials (Auth spec).
