# Feature Specification: Search & Grab Decision Engine

**Feature Branch**: `007-search-decision-engine` (branch creation skipped: git repo lives in parent dir)
**Created**: 2026-04-29
**Status**: Draft
**Depends on**:
- `001-foundation` — identification cascade, `ParsedFilename`, region/language ISO normalisation, DAT lookup helpers.
- `004-indexers` — `NewznabClient`, indexer registry, extended Torznab attribute parsing, RSS-sync helper, `SearchResult` types.
- `005-download-clients` — `route_release(...)` to dispatch the chosen result to the right client.
- `006-profiles` — `ProfileEvaluator`, `compute_custom_format_score(...)`, the bound profile shapes on `Library`.
- `003-platform-packs` — `platform.newznab_category_ids` consumed for category filtering.
**Input**: User description: "Build the search engine and grab decision engine. Five search modes (manual, search-on-add, scheduled missing, scheduled cutoff, RSS sync) adapted for the ROM domain where missing-search dominates. A 13-step decision pipeline. Blocklist, search history, indexer-query caching, deterministic score-based candidate selection."

## Clarifications

### Session 2026-04-29

- Q: Is the blocklist scoped globally or per-library? → A: Global per Romarr instance. A `(indexer_id, indexer_guid)` or hash entry blocks the release across every library. Reason: the blocklist captures a property of the release (broken file / hash-mismatch) that doesn't change per library; per-library scopes would let the same bad file loop into different libraries. The `?force=true` query parameter on manual grab is the legitimate per-call escape hatch
- Q: When two search rounds target the same Game concurrently, what does the second caller observe? → A: Coalesce. The second caller waits on the per-Game advisory lock and, when the lock releases, returns the first round's result without re-querying indexers. Same pattern as spec 002's metadata refresh-coalesce. The second round MUST NOT re-fan-out indexer calls; it MUST receive the same `search_history` row reference
- Q: What's the eviction / size-bound policy for `search_cache`? → A: TTL-only eviction PLUS a hard 10,000-row cap with LRU eviction by `last_read_at` once the cap is reached. Unlike `metadata_cache` (whose unique key bounds size), `search_cache` keys include the unbounded `query` string, so a row-count cap is necessary to protect disk
- Q: Which import-failure subreasons trigger an auto-blocklist entry, and which are skipped? → A: Auto-blocklist ONLY on content-correctness failures of the file itself — `hash-mismatch`, `dat-rejected`, `format-corrupt`, `archive-extraction-failed`. Transient / operational subreasons — `disk-full`, `permission-denied`, `client-unreachable`, `move-failed`, `scan-timeout` — record the failure in `search_history` but MUST NOT add to the blocklist; the importer's own retry logic handles those
- Q: What role is required to invoke the search / grab / blocklist / command endpoints? → A: Admin-only on all mutating endpoints (`POST /search/manual`, `POST /search/release/{id}`, `POST /release/grab`, `POST /command`, `POST /blocklist`, `DELETE /blocklist/{id}`). Reads (`GET /search/history`, `GET /blocklist`) accessible to any authenticated user. Same pattern as specs 003 / 004 / 005 / 006

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Manual interactive search returns ranked results (Priority: P1)

A Romarr operator types a title (e.g. *Sonic the Hedgehog*) into a
search box; Romarr queries every enabled indexer in parallel,
parses each result, computes a score against the chosen library's
profiles plus its custom formats, and returns a ranked list. The
operator picks one and clicks "Grab".

**Why this priority**: Manual search is the operator's main day-1
tool. It is also the simplest end-to-end test of the entire
search-decision pipeline.

**Independent Test**: Configure three mock indexers with canned
Torznab responses; configure a library with default profiles; issue
a manual search; verify the response is a ranked list with the
documented score breakdown per result and that no grab was
dispatched.

**Acceptance Scenarios**:

1. **Given** three configured indexers and a query string, **When**
   the operator submits the manual search, **Then** the response
   is a list of parsed results, each annotated with a structured
   score breakdown (region score, language score, custom format
   contributions, DAT-match boost), sorted by total score
   descending.
2. **Given** the same search, **When** the operator hits the grab
   endpoint with a chosen result's reference, **Then** the result
   is handed to the routing module of the download-clients spec
   and a row appears in the search history with
   `grabbed_release_id` populated.
3. **Given** the operator passes `?strict=true` to the manual
   search, **When** the response returns, **Then** every result
   that would be auto-rejected by the profiles is filtered out;
   when omitted, the response includes them but each is marked
   `would_auto_reject = true` with the rejecting field named.

---

### User Story 2 — A new Game triggers Search on Add (Priority: P1)

The operator adds a new Game (POST /api/v3/game). The Game is
`monitored = true`. Without any further action, Romarr fires an
automatic search and either grabs a high-scoring release or records
a "no grab" entry in the search history.

**Why this priority**: This is what makes the *arr workflow feel
automatic. Without it, every new Game requires an explicit search
step.

**Independent Test**: POST a new Game with `monitored = true`;
inject canned indexer responses; verify a search history row
appears with `search_type = 'auto_added'` and either a successful
grab or a recorded `no_grab_reason`.

**Acceptance Scenarios**:

1. **Given** a new Game with `monitored = true`, **When** the Game
   is created, **Then** the API layer fires a best-effort search
   and the API response is unaffected by the search outcome
   (success or failure).
2. **Given** the search yields a release with score > 0, **When**
   the search round completes, **Then** the release is grabbed
   automatically.
3. **Given** the search fails (every indexer is down), **When**
   the search round completes, **Then** the Game is still created,
   a `search_history` row records the failure with
   `no_grab_reason = 'all_indexers_failed'`, and the Game is
   queued for the scheduled missing search.

---

### User Story 3 — Decision engine rejects releases that violate profiles (Priority: P1)

The library is bound to a Region profile that excludes Korea, a
Dump profile that does not allow hacks, and a Quality profile that
does not allow `.zip`. A search returns a Korean release, a hack
release, and a `.zip` file; all three are rejected with the
correct structured reason.

**Why this priority**: The constitutional invariant
(Article V — Profile-Driven Decisions) lives or dies on the
correctness of these filters.

**Independent Test**: Inject three offending releases; run the
decision pipeline; verify each yields a `Decision = REJECT` plus
the documented reason code.

**Acceptance Scenarios**:

1. **Given** a release whose parsed region intersects
   `exclude_regions`, **When** the pipeline evaluates it, **Then**
   it is rejected with `code = "region_excluded"`.
2. **Given** a release whose `dump_status = 'hack'` against a
   profile with `allow_hacks = false`, **When** the pipeline runs,
   **Then** it is rejected with `code = "dump_status_disallowed"`.
3. **Given** a release whose extension is not in
   `allowed_formats`, **When** the pipeline runs, **Then** it is
   rejected with `code = "format_not_allowed"`.
4. **Given** the same release evaluated twice, **When** the
   pipeline runs back-to-back, **Then** both runs return identical
   decisions and identical scores (purity invariant).

---

### User Story 4 — Scheduled missing search dominates the workflow (Priority: P2)

The operator's library has 200 monitored Games, of which 80 are
`status = 'wanted'` (no Imported Release yet). The scheduled
missing search runs, batches up to 50 of them per run, queries
indexers, and grabs the highest-scoring result for each.

**Why this priority**: For ROMs, "new" releases are rare; the
recurring re-search is what catches releases that quietly become
available later. This is the dominant search mode in the *arr
ecosystem adapted to the retro domain.

**Independent Test**: Seed 80 wanted Games; invoke
`run_missing_search()` directly with a max-games-per-run of 50;
verify exactly 50 Games are searched, the chosen 50 are processed
oldest-first by `added_at`, and the remaining 30 are deferred to
the next run.

**Acceptance Scenarios**:

1. **Given** N wanted Games and a max of 50 per run, **When** the
   missing search runs, **Then** exactly `min(N, 50)` Games are
   processed and the candidates are picked oldest-first.
2. **Given** a Game whose Releases all match the cutoff, **When**
   the missing search evaluates the Game, **Then** the Game is
   skipped (it is not "wanted" anymore).
3. **Given** a Game with multiple wanted Releases (USA + EUR + JPN
   all wanted), **When** the missing search runs, **Then** each
   Release is searched independently and a release matches a
   target Release X when its parsed regions intersect X.

---

### User Story 5 — Cutoff search upgrades existing Releases (Priority: P2)

The operator has imported `Sonic the Hedgehog (USA).md` (raw
format) but the Quality profile's cutoff is `chd`. The scheduled
cutoff search re-queries indexers; if a `.chd` release is
available with a positive score, Romarr grabs it as an upgrade.

**Why this priority**: Cutoff search is the upgrade lifecycle.
Without it, operators must re-search manually every time they
change a profile.

**Independent Test**: Import a release whose format equals the
quality profile's `allowed_formats[0]` but not its
`upgrade_until_format`; inject a higher-format release into the
indexer mock; run the cutoff search; verify the upgrade is grabbed
and the search history records `search_type = 'cutoff_scheduled'`.

**Acceptance Scenarios**:

1. **Given** a Release whose imported format is below cutoff,
   **When** the cutoff search finds a release at or above cutoff,
   **Then** the upgrade is grabbed.
2. **Given** a Release whose imported format equals cutoff,
   **When** the cutoff search runs, **Then** the Release is
   skipped (no upgrade attempted).
3. **Given** a Release whose imported format is below cutoff but
   the only available upstream releases score <= 0, **When** the
   cutoff search runs, **Then** the Release is left unchanged and
   a search history row records `no_grab_reason`.

---

### User Story 6 — Blocklist prevents grabbing known-bad releases (Priority: P2)

A previous import failed because the file's hash did not match the
DAT entry. Romarr automatically added that release to the
blocklist. Any future search returning that same release (matched
by indexer GUID or by hash) skips it with a structured reason.

**Why this priority**: Without a blocklist, the same broken
release can be re-grabbed in a loop on every scheduled search.

**Independent Test**: Add a release to the blocklist by hash;
inject a search response containing that release; verify it is
filtered out and the search history shows `results_count - 1`
candidates after blocklist application.

**Acceptance Scenarios**:

1. **Given** an entry in `blocklist` matching a release's
   `(indexer_id, indexer_guid)`, **When** the pipeline runs,
   **Then** the release is rejected with
   `code = "blocklisted_guid"`.
2. **Given** an entry matching a release's `hash_sha1` or
   `hash_crc32`, **When** the pipeline runs, **Then** the release
   is rejected with `code = "blocklisted_hash"`.
3. **Given** the operator manually POSTs a blocklist entry,
   **When** they re-run a search, **Then** the matching release is
   excluded.
4. **Given** the import pipeline fails for a release with a
   structured reason (e.g., `hash-mismatch`), **When** the failure
   is reported, **Then** the release is auto-added to the
   blocklist with `reason = "import-failed: <subreason>"` and
   `added_by = 'system'`.

---

### User Story 7 — RSS sync auto-grabs above threshold (Priority: P3)

Romarr periodically pulls each indexer's RSS feed. For each result
that matches a wanted Game/Release, the pipeline computes a score;
if the score exceeds the library's RSS auto-grab threshold, the
release is grabbed automatically.

**Why this priority**: RSS catches the rare "new" releases without
operator interaction; less critical for ROMs than for movies/TV
but still expected in the *arr ecosystem.

**Independent Test**: Stub one indexer's RSS feed to include a
matching release with a known score; run `run_rss_sync()`; verify
the release is grabbed and the search history records
`search_type = 'rss'`.

**Acceptance Scenarios**:

1. **Given** an RSS result whose score exceeds the configured
   threshold (default 0), **When** RSS sync runs, **Then** the
   release is grabbed automatically.
2. **Given** an RSS result whose score is at or below the
   threshold, **When** RSS sync runs, **Then** the release is
   recorded in the search history but not grabbed.
3. **Given** an indexer with `rss_auto_grab = false`, **When** RSS
   sync runs, **Then** results from that indexer are recorded but
   never auto-grabbed regardless of score.

---

### User Story 8 — Cache cuts redundant indexer calls (Priority: P3)

The operator runs the same search twice within an hour. The second
call reads from the cache and never hits the indexer.

**Why this priority**: Indexer rate limits are a real constraint;
caching protects the operator from hitting them and reduces
network-dependent latency.

**Independent Test**: Trigger a manual search; record indexer call
count; trigger the same search again; assert the indexer call
count is unchanged. Advance time past TTL; trigger a third time;
assert the count incremented.

**Acceptance Scenarios**:

1. **Given** a manual search query and a cache TTL of 60 minutes
   (default), **When** the same query is issued twice within 60
   minutes, **Then** the second call returns a cached response
   with zero outbound HTTP traffic.
2. **Given** the cache entry has expired, **When** the same query
   runs, **Then** a fresh indexer call is made and the cache row
   is replaced.
3. **Given** an RSS sync run, **When** the result list is parsed,
   **Then** caching is **skipped** — RSS always reads fresh feeds.

---

### Edge Cases

- A search returns more than the configured per-indexer hard limit
  (default 200) → the response is truncated and a structured warning
  is logged; the operator is prompted to refine via the UI hint
  field.
- A query yields zero results from every indexer → the search
  history records the empty round with
  `no_grab_reason = 'no_results'`; the operator's auto-add path is
  unaffected.
- Two indexers return the same release (same GUID) for the same
  query → dedup happens at the indexer-parser level (already in
  spec 004); the score is computed against the single dedup'd
  record.
- A release matches multiple wanted Releases of the same Game
  (e.g., a multi-region release matches both USA and EUR slots) →
  the release is scored separately per Release slot; whichever
  slot has the higher score wins; the other slot is **not** also
  grabbed (a single release fills only one slot).
- An RSS result whose score is exactly the threshold (default 0) →
  treated as "do not auto-grab"; threshold comparison is strictly
  `> threshold`.
- A manual grab call references a release whose
  `(indexer_id, indexer_guid)` is in the blocklist → grab is
  rejected with HTTP 409 unless `?force=true` is supplied.
- The score breakdown ranges contradict (e.g., custom format yields
  +200 but DAT-match boost adds another +200 to push above the
  rejection threshold while another custom format yields -10000) →
  the `<= -10000` rejection rule wins; even one outright-reject
  custom format causes the entire candidate to be discarded.
- The chosen download client is unreachable at grab time → the
  routing module of spec 005 returns its `stuck` retry state;
  `search_history` records the grab as `pending_retry`.
- The cache row's stored response references an indexer that has
  since been deleted → the cache hit is dropped and the search
  proceeds as a miss.

## Requirements *(mandatory)*

### Functional Requirements

**Search modes**

- **FR-001**: The system MUST expose a manual interactive search
  function that fans out across all enabled indexers in parallel,
  applies the decision pipeline, and returns a ranked list of
  candidates. By default it shows every result (with auto-reject
  flags); a `strict` flag filters out the auto-rejected ones.
- **FR-002**: When a Game with `monitored = true` is created, the
  system MUST fire a best-effort automatic search; failure MUST NOT
  fail the Game creation API call.
- **FR-003**: The system MUST expose `run_missing_search(limit)`
  which iterates monitored Games whose Releases are
  `status = 'wanted'`, oldest-first by `added_at`, batched to at
  most `limit` Games per call (default 50). Scheduling is owned by
  a later spec.
- **FR-004**: The system MUST expose `run_cutoff_search(limit)`
  which iterates Releases whose imported format is below the
  Library's quality-profile cutoff. Scheduling is owned by a later
  spec.
- **FR-005**: The system MUST expose `run_rss_sync()` which iterates
  all enabled indexers, parses their RSS feeds (no caching),
  evaluates each item against the wanted catalog, and auto-grabs
  releases whose score exceeds the library's RSS threshold. RSS
  scheduling is owned by a later spec.

**Query construction**

- **FR-006**: For a target Game, the system MUST build a list of
  candidate queries: canonical title, alternative names from
  metadata (when present), title-with-platform-name,
  title-with-manufacturer.
- **FR-007**: The system MUST round-robin candidate queries across
  enabled indexers so no single indexer receives a disproportionate
  share of traffic.
- **FR-008**: The system MUST filter searches by the platform's
  Newznab category IDs from `platform.newznab_category_ids`. When
  the primary category yields zero results, the system MUST retry
  with documented fallback categories (1060 Other Console, 7010
  Misc).

**Decision pipeline (per indexer result)**

- **FR-009**: The pipeline MUST resolve each result to a Game via:
  (a) hash-match against DAT/Hasheous/PlayMatch when a hash is
  provided; (b) RapidFuzz title fuzzy match (threshold 85) against
  monitored Games on the inferred platform. No match ⇒ skip.
- **FR-010**: The pipeline MUST apply, in order, the Region,
  Language, Dump, and Quality profile filters; any rejection
  short-circuits remaining steps.
- **FR-011**: The pipeline MUST compute the Custom Format score by
  summing every matching format's contribution; a score
  contribution of `≤ -10000` from any single format MUST cause
  outright rejection.
- **FR-012**: The pipeline MUST consult the blocklist by
  `(indexer_id, indexer_guid)`, by `hash_sha1`, and by `hash_crc32`;
  any match rejects the result.
- **FR-013**: The pipeline MUST enforce per-platform-format size
  bounds when present (`min_size_bytes`/`max_size_bytes` on the
  matching `platform_format` row).
- **FR-014**: For torrent results, the pipeline MUST reject any
  result where `seeders < indexer.min_seeders`.
- **FR-015**: When a hash is provided in extended Torznab attrs,
  the pipeline MUST query the foundation's hash-match cascade
  (DAT cache, Hasheous, PlayMatch) and apply a `+200` boost when
  the result is `verified`.
- **FR-016**: The pipeline MUST be **deterministic**: identical
  inputs ⇒ identical decisions and identical scores; no I/O beyond
  reads of state already loaded into memory.
- **FR-016a**: Concurrent search rounds against the same Game
  MUST be coalesced via a per-Game in-process advisory lock. The
  first caller acquires the lock and runs the round; subsequent
  callers MUST block on the lock and, upon release, MUST receive
  the first round's result reference (the same `search_history`
  row id) without issuing any additional indexer call or starting
  a new round. The lock MUST release on completion (success or
  failure) and MUST be reclaimable by a watchdog if the lock
  holder dies. The lock-holder TTL is 5 minutes — well above the
  expected per-round wall-clock budget. This mirrors spec 002's
  metadata refresh-coalesce pattern.

**Candidate selection**

- **FR-017**: For each (target Game, target Release-slot), the
  pipeline MUST keep only the highest-scored surviving candidate;
  ties are broken deterministically by `(indexer.priority,
  indexer.id, indexer_guid)`.
- **FR-018**: The system MUST hand the chosen candidate to the
  download-clients routing module (spec 005). Routing failures
  surface as `pending_retry` in the search history (spec 005's
  stuck-grab retry policy applies).

**Persistence**

- **FR-019**: The system MUST persist `blocklist`, `search_history`,
  and `search_cache` per the data-model section. Cascade-on-delete
  rules MUST match the documented FK behaviour (Release / Game
  delete cascades clean up the search-history references but
  preserve the search-history row itself).

**Blocklist**

- **FR-020**: The blocklist MUST support entries by
  `(indexer_id, indexer_guid)` and by hash. Either match excludes
  a candidate.
- **FR-020a**: Blocklist scope is **global per Romarr instance**.
  An entry — whether matched on `(indexer_id, indexer_guid)`, on
  `hash_sha1`, or on `hash_crc32` — MUST exclude the candidate
  release from search rounds and auto-grab decisions across every
  library on the instance, regardless of which library originally
  triggered the entry. The blocklist row schema MUST NOT carry a
  `library_id` column at MVP. Per-call overrides remain available
  via `POST /api/v3/rom/release/grab?force=true` (FR-022 / Edge
  Cases). A future per-library blocklist scope may be introduced
  as a v1+ extension; until then the global scope is authoritative.
- **FR-021**: A failed import MUST auto-add the offending release
  to the blocklist with a structured `reason` (e.g.,
  `import-failed:hash-mismatch`) **only when** the importer's
  reported subreason indicates a permanent content-correctness
  failure of the file itself. The permitted auto-blocklist
  subreasons are: `hash-mismatch`, `dat-rejected`,
  `format-corrupt`, `archive-extraction-failed`. Transient or
  operational subreasons (e.g., `disk-full`, `permission-denied`,
  `client-unreachable`, `move-failed`, `scan-timeout`) MUST be
  recorded in `search_history` but MUST NOT cause an
  auto-blocklist entry to be created. The importer spec (008) is
  responsible for emitting subreasons in this taxonomy; this spec
  consumes them. Operators retain the ability to manually add a
  blocklist entry via the CRUD endpoints (FR-022) for any release
  regardless of subreason.
- **FR-022**: The system MUST expose CRUD endpoints for blocklist
  management.

**Search history**

- **FR-023**: Every search round MUST produce a search-history row
  with `search_type`, `query`, `indexer_id`, `game_id`,
  `results_count`, `grabbed_release_id` (nullable),
  `no_grab_reason` (nullable), `started_at`, `finished_at`,
  `duration_ms`.
- **FR-024**: Failed pipeline rejections MUST be aggregated into a
  structured `no_grab_reason`; the search-history row MUST capture
  the dominant rejection reason.

**Caching**

- **FR-025**: Non-RSS searches MUST cache results per
  `(indexer_id, query, category_ids_set)` for a TTL configurable
  per indexer (default 60 minutes).
- **FR-026**: Cache hits MUST issue zero outbound HTTP calls.
- **FR-027**: RSS sync MUST NOT consult the cache; it always reads
  fresh.
- **FR-028**: When a referenced indexer is deleted, the system
  MUST treat its cache rows as miss (and prune them on the next
  scheduled cleanup, owned by a later spec).
- **FR-028a**: The `search_cache` table MUST be bounded by both
  TTL (FR-025) and a row-count cap of 10,000 entries. The schema
  MUST carry a `last_read_at` column updated on every cache hit
  (read); when an INSERT would push the table past 10,000 rows
  the system MUST evict the oldest `last_read_at` rows down to
  9,000 in the same transaction (LRU eviction with hysteresis).
  The eviction MUST be a single bulk DELETE; row-by-row eviction
  is forbidden for performance. This protects disk in the
  pathological case of an automation issuing many unique queries.

**Limits**

- **FR-029**: Per-indexer per-query results MUST be hard-capped at
  200; over-cap responses MUST be truncated with a structured
  warning that surfaces to the operator (UI hint field).

**API**

- **FR-030**: The system MUST expose:
  - `POST /api/v3/rom/search/manual` (body: `{query,
    indexer_ids[], platform_id}`, query param `?strict=`).
  - `POST /api/v3/rom/search/release/{id}` (search a specific
    Release using its bound profiles).
  - `POST /api/v3/rom/release/grab` (body:
    `{indexer_id, indexer_guid, download_url}`; query param
    `?force=` to override blocklist).
  - `POST /api/v3/command` (Sonarr-compat command endpoint
    accepting `MissingSearch`, `CutoffSearch`, `RssSync`,
    `IndexerSearch`).
  - `GET /api/v3/rom/search/history` (filter by date / search_type
    / indexer / game).
  - `GET/POST/DELETE /api/v3/blocklist`.
- **FR-030a**: All mutating endpoints in FR-030
  (`POST /api/v3/rom/search/manual`,
  `POST /api/v3/rom/search/release/{id}`,
  `POST /api/v3/rom/release/grab`, `POST /api/v3/command`,
  `POST /api/v3/blocklist`, `DELETE /api/v3/blocklist/{id}`)
  MUST require the caller to hold the `admin` role provided by
  the Auth spec. Read endpoints (`GET /api/v3/rom/search/history`,
  `GET /api/v3/blocklist`, `GET /api/v3/blocklist/{id}`) MUST be
  accessible to any authenticated user. Unauthenticated requests
  MUST be rejected with HTTP 401; authenticated non-admin
  requests on a mutating endpoint MUST be rejected with HTTP 403.
  This matches the pattern used by specs 003 / 004 / 005 / 006.

### Key Entities

- **Search Round**: A single invocation of a search-mode entry
  point; produces one or more search-history rows.
- **Candidate**: A parsed `SearchResult` enriched with score
  breakdown plus the matched Game/Release slot.
- **Score Breakdown**: a structured per-result score document
  showing the contribution of each profile and each custom format,
  used by the UI and by tests.
- **Blocklist Entry**: a record that suppresses a release by GUID
  or by hash with a structured reason.
- **Search History Entry**: an immutable audit row of one search
  round.
- **Search Cache Entry**: a (indexer, query, categories) → results
  row with a TTL used by non-RSS search modes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A manual search across 3 mock indexers returns a
  ranked list whose order is byte-for-byte identical across two
  consecutive runs in 100% of test fixtures (determinism).
- **SC-002**: Across a 50-result fixture corpus, every documented
  rejection case (region excluded, language missing,
  dump-status disallowed, format disallowed, blocklist hit,
  custom-format ≤ -10000) yields the documented structured reason
  in 100% of cases.
- **SC-003**: Scoring 100 indexer results (post-network) completes
  in under 200 ms.
- **SC-004**: A scheduled missing search with 80 wanted Games and
  a `limit = 50` processes exactly 50 Games oldest-first; the
  remaining 30 are processed on the next run.
- **SC-005**: A cutoff search picks an upgrade only when the
  available release's score is strictly positive AND its quality
  profile state is at least the cutoff in 100% of test cases.
- **SC-006**: A blocklisted release (by GUID or by hash) is
  filtered in 100% of search rounds; the manual grab endpoint
  rejects a blocklisted release with HTTP 409 unless
  `?force=true` is supplied.
- **SC-007**: For a query whose result is in cache and within TTL,
  the system makes zero outbound HTTP calls; for an expired entry,
  exactly one outbound call per affected indexer.
- **SC-008**: Hard-capping at 200 results per indexer triggers the
  structured warning in 100% of over-cap test cases.
- **SC-009**: Test coverage on the search module MUST be at least
  75%.

## Assumptions

These resolve the OPEN CLARIFICATIONS supplied with the input,
applying the operator's proposals.

- **Manual search default**: shows every result; each is annotated
  with `would_auto_reject` and the rejecting field name. The
  `?strict=true` query param removes auto-rejected results
  upstream.
- **RSS auto-grab**: enabled by default with a per-library threshold
  (default 0). Strict comparison `score > threshold` triggers a
  grab. Each indexer carries a `rss_auto_grab` flag (added on the
  indexer table by this feature's migration) defaulting to `true`;
  setting it false keeps RSS results in the history but never
  auto-grabs them.
- **Multi-Release wanted**: each wanted Release is searched
  independently; a release matches a target Release X when their
  parsed regions intersect. Each release fills at most one Release
  slot per round.
- **Result hard cap**: 200 per indexer per query; overflow truncated
  with a structured warning (FR-029).

Other assumptions:

- The 13-step pipeline runs in-process and is pure aside from the
  cache read it performs at step 0 and the blocklist-and-cache
  reads at steps 8 and 12. All in-memory; no per-result database
  round-trips beyond preloaded state.
- `RapidFuzz` is the chosen fuzzy-match library; threshold 85 is
  the documented default. Operators may override the threshold via
  config in a later spec.
- The grab-out path uses spec-005's `route_release(...)` and
  inherits its routing semantics (indexer-pinned override,
  source-type matching, priority-based fallback, no-eligible-
  client error).
- Concurrent search rounds against the same Game are serialised at
  the application level; only one round per Game runs at a time
  (a small in-process advisory lock; the cron in the Tasks spec
  staggers cohorts).

### Out of Scope

- Profile management (Profiles spec — already shipped).
- Background scheduling (Tasks/Scheduler spec — consumes this
  spec's `run_*` entry points).
- UI for search results (UI spec).
- Indexer health monitoring (Indexers spec already produces
  `IndexerHealthIssue`; this spec does not duplicate it).
- ML-based ranking — deferred indefinitely; rule-based scoring is
  sufficient for ROMs.
- Per-result deduplication across indexers (already done by the
  parser in spec 004).
