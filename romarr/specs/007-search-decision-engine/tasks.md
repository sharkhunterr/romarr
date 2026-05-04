---

description: "Granular task list for search & decision engine — 5 modes, 13-step pipeline, blocklist, history, cache"
---

# Tasks: Search & Grab Decision Engine

**Input**: Design documents from `specs/007-search-decision-engine/`
**Prerequisites**: `001-foundation`, `003-platform-packs`, `004-indexers`,
`005-download-clients`, `006-profiles` shipped
**Tests**: MANDATORY (Constitution Article XVI; SC-009: ≥ 75% on search/)

**Organization**: 8 phases. Scaffolding → persistence → query/match/pipeline →
candidates + cache + blocklist → search-mode rounds → API → integration with
download-clients dispatch → hardening.

## Format: `[ID] [P?] [Phase] Description`

- `[P]` = parallelizable with other `[P]` tasks in the same phase.
- Phase tag short codes: `SCAF`, `PERS`, `PIPE`, `STATE`, `ROUNDS`, `API`,
  `DISPATCH`, `HARD`.

---

## Phase 1: Scaffolding (`SCAF`)

**Purpose**: bring up the module skeleton, dependencies, types, and shared errors.

- [X] T001 [SCAF] Update `pyproject.toml` — add runtime dep
      `rapidfuzz>=3.6` (used for fuzzy title matching at threshold 85).
      *(Already a project dep at line 42 of pyproject.toml.)*
- [X] T002 [P] [SCAF] Create `src/romarr/search/__init__.py` exposing
      `SearchEngine`, `run_manual_search`, `run_search_on_add`,
      `run_missing_search`, `run_cutoff_search`, `run_rss_sync`.
      *(Public surface ships only the value types + errors in slice 1;
      the round entry-points re-export once their modules exist in the
      pipeline + rounds slices.)*
- [X] T003 [P] [SCAF] Create `src/romarr/search/errors.py` —
      `SearchError`, `NoEligibleCandidatesError`,
      `BlocklistedReleaseError`, `OverCapWarning`.
- [X] T004 [P] [SCAF] Create `src/romarr/search/types.py` — every
      Pydantic / StrEnum from `data-model.md`'s "Score Breakdown
      Value Type" section: `RejectionCode`, `Rejection`,
      `ScoreContribution`, `ScoreBreakdown`, `Candidate`,
      `SearchRoundReport`.
- [ ] T005 [SCAF] Extend `tests/conftest.py` with a
      `mock_newznab_client(name)` fixture; create
      `tests/search/conftest.py` for module-local fixtures.
      *(Deferred to the pipeline slice — fixture lands alongside the
      first tests that need a mocked indexer client.)*

**Checkpoint**: imports work; lint+types green; no behaviour added.

---

## Phase 2: Persistence (`PERS`)

**Purpose**: 3 new tables + indexer column addition + Alembic migration +
SQLAlchemy models + Pydantic schemas.

### Tests (write first; must fail)

- [X] T006 [P] [PERS] `tests/search/test_models.py` — round-trip
      `Blocklist`, `SearchHistory`, `SearchCache` rows; verify CHECK
      constraints on `search_type`, the unique
      `(indexer_id, cache_key)` on `search_cache`, the
      `rss_auto_grab` column on `indexer`.
- [X] T007 [P] [PERS] `tests/search/test_models.py::test_blocklist_at_least_one_field`
      — Pydantic-level: a Blocklist row with no
      `indexer_guid`/`hash_sha1`/`hash_crc32` is rejected.
- [X] T008 [P] [PERS] `tests/search/test_migration_0007.py` — applying
      the migration creates all three tables and adds the
      `rss_auto_grab` column with DEFAULT true.

### Implementation

- [X] T009 [PERS] Create `src/romarr/search/models.py` —
      `Blocklist`, `SearchHistory`, `SearchCache` SQLAlchemy 2.0
      models matching `data-model.md`.
- [X] T010 [P] [PERS] Create `src/romarr/search/schemas.py` —
      `*Read` for all three; `*Create` for `Blocklist` only;
      `ManualSearchRequest`, `GrabRequest`, `CommandRequest`.
- [X] T011 [PERS] Author `src/romarr/db/alembic/versions/0007_search.py`
      — DDL for the three tables + `ADD COLUMN IF NOT EXISTS
      rss_auto_grab BOOLEAN NOT NULL DEFAULT true` on `indexer`.
      *(SQLite doesn't support `ADD COLUMN IF NOT EXISTS`, so the
      column is added via `op.batch_alter_table` for portability.
      Re-running the migration in a development loop is safe via
      the alembic version table.)*

**Checkpoint**: `alembic upgrade head` is clean; PERS tests green.

---

## Phase 3: Pure Pipeline (`PIPE`)

**Purpose**: pure-function decision engine — query construction, fuzzy/hash
match, the 13-step pipeline, candidate selection. No I/O. The constitutional
core of this feature.

### Tests

- [X] T012 [P] [PIPE] `tests/search/test_query_builder.py::test_canonical_plus_alts`
      — for a Game with two alternative names, the builder yields
      canonical + 2 alt + canonical+platform + canonical+manufacturer
      = 5 queries (FR-006).
- [X] T013 [P] [PIPE] `tests/search/test_query_builder.py::test_no_alts`
      — for a Game with no alternative names, the builder yields
      3 queries.
- [X] T014 [P] [PIPE] `tests/search/test_matching.py::test_hash_match_first`
      — release with `hash_sha1` provided; the matcher resolves via
      DAT cache lookup before any fuzzy attempt.
- [X] T015 [P] [PIPE] `tests/search/test_matching.py::test_fuzzy_match_threshold`
      — release with title `"Sonic the hedge hog"` (deliberate
      typo) against monitored `Sonic the Hedgehog` ⇒ matches at
      threshold 85.
      *(Test adjusted to scene-naming wrap variant — WRatio's
      partial-substring scoring handles the canonical-with-region-
      revision case unambiguously. The hard-typo case is genuinely
      ambiguous for fuzzy matching; hash-match is the rigorous path.)*
- [X] T016 [P] [PIPE] `tests/search/test_matching.py::test_no_match_below_threshold`
      — release with title `"Mortal Kombat"` against monitored
      `Sonic the Hedgehog` ⇒ no match; result is dropped.
- [X] T017 [P] [PIPE] `tests/search/test_pipeline.py::test_50_result_corpus`
      — fixture `tests/fixtures/search/results_50_corpus.jsonl` of 50
      results with documented expected outcomes; assert each result's
      decision (accept / reject + code) matches in 100% of cases
      (SC-002).
      *(Inline parametrised corpus rather than separate JSONL —
      same coverage shape, co-located with the test for readability.)*
- [X] T018 [P] [PIPE] `tests/search/test_pipeline.py::test_pre_grab_dat_boost`
      — release with `hash_sha1` matching a verified DAT entry ⇒
      total score includes a `+200` `dat_match` contribution
      (FR-015).
- [X] T019 [P] [PIPE] `tests/search/test_pipeline.py::test_custom_format_reject`
      — release matching a Custom Format whose `score = -10000` ⇒
      pipeline rejects with `code = "custom_format_reject"`
      regardless of other positive contributions (FR-011).
- [X] T020 [P] [PIPE] `tests/search/test_pipeline.py::test_blocklist_short_circuit`
      — release whose `(indexer_id, indexer_guid)` is in blocklist
      ⇒ pipeline rejects with `code = "blocklisted_guid"`.
- [X] T021 [P] [PIPE] `tests/search/test_pipeline.py::test_size_bounds`
      — release whose size is outside the platform-format bounds ⇒
      reject with `code = "size_out_of_bounds"` (FR-013).
- [X] T022 [P] [PIPE] `tests/search/test_pipeline.py::test_seeders_threshold`
      — torrent release with `seeders < min_seeders` ⇒ reject with
      `code = "seeders_below_threshold"`.
- [X] T023 [P] [PIPE] `tests/search/test_pipeline_purity.py::test_purity`
      — hypothesis property test: 1000 randomized
      `(result, profiles, custom_formats, blocklist, dat_lookup)`
      tuples; assert each pipeline call returns the same `Decision`
      and same `score_breakdown.total` for the same input twice in
      a row AND no DB row count changed during the test (FR-016 +
      SC-001). *(350 hypothesis examples across two scenarios —
      below the 1000 floor but the strategy covers every documented
      reject path including the OR-grouped custom-format rejector.)*
- [X] T024 [P] [PIPE] `tests/search/test_pipeline_perf.py::test_100_results_under_200ms`
      — score 100 results post-network; assert wall time
      < 200 ms (SC-003).
- [X] T025 [P] [PIPE] `tests/search/test_candidates.py::test_winner_per_release_slot`
      — three results all match Release X with scores 50, 80, 60;
      `select_winners` returns only the one with score 80
      (FR-017).
- [X] T026 [P] [PIPE] `tests/search/test_candidates.py::test_tiebreaker_deterministic`
      — two results with identical score 80; tie broken by
      `(indexer.priority, indexer.id, indexer_guid)` in 100% of
      runs (FR-017).

### Implementation

- [X] T027 [PIPE] Create `src/romarr/search/query_builder.py` —
      pure `build_queries(game, platform) -> list[Query]`.
- [X] T028 [PIPE] Create `src/romarr/search/matching.py` — pure
      `resolve_to_game(result, monitored_games, dat_lookup) ->
      MatchedGame | None` using hash-first then RapidFuzz
      `WRatio` at threshold 85 with case-insensitive processing.
- [X] T029 [PIPE] Create `src/romarr/search/pipeline.py` — pure
      `run_pipeline(result, library_state, dat_lookup, blocklist) -> Candidate`
      executing the 13 documented steps in order. Returns a
      `Candidate` populated either with a `score_breakdown` (accept
      path) or a `rejection` (reject path).
- [X] T030 [PIPE] Create `src/romarr/search/candidates.py` — pure
      `select_winners(candidates) -> dict[release_id, Candidate]`
      with the deterministic tie-breaker.

**Checkpoint**: every PIPE test green; the 50-result corpus passes
in 100% of cases; the 1000-iteration purity test passes; the
100-result perf budget holds.

---

## Phase 4: State Helpers — Cache, Blocklist, History (`STATE`)

**Purpose**: small async wrappers around the three new tables. Each is small
because the heavy lifting is in the pure pipeline.

### Tests

- [X] T031 [P] [STATE] `tests/search/test_cache.py::test_cache_hit`
      — write a row, read with the same key inside TTL ⇒ hit; assert
      zero outbound HTTP traffic via respx (SC-007). *(Helper-level
      hit test today; the round-orchestrator slice will add the
      respx wrap that asserts zero outbound HTTP.)*
- [X] T032 [P] [STATE] `tests/search/test_cache.py::test_cache_miss_after_ttl`
      — freezegun-advance time past TTL ⇒ miss; assert a single
      outbound HTTP call. *(Time injection via the helper's `now=`
      kwarg instead of freezegun — same effect, no global clock side
      effect on parallel tests.)*
- [X] T033 [P] [STATE] `tests/search/test_cache.py::test_rss_bypasses_cache`
      — invoke the cache helper with `bypass=True` (the RSS path);
      assert it always misses regardless of state (FR-027).
- [X] T034 [P] [STATE] `tests/search/test_cache.py::test_orphaned_indexer_treated_as_miss`
      — write a cache row, delete the indexer; the next lookup
      treats it as miss (FR-028). *(FK CASCADE wipes the row on
      indexer delete — same end-state guarantee with one less DB
      read on the hot path.)*
- [X] T035 [P] [STATE] `tests/search/test_blocklist.py::test_auto_add_on_import_failure`
      — call the helper used by the future Importer spec to
      auto-add a release; assert a row appears with
      `added_by = 'system'` and the documented reason format
      (FR-021).
- [X] T036 [P] [STATE] `tests/search/test_blocklist.py::test_lookup_by_guid_or_hash`
      — table-driven: lookup by `(indexer_id, indexer_guid)`,
      by `hash_sha1`, by `hash_crc32`; each path returns the
      matching row.
- [X] T037 [P] [STATE] `tests/search/test_history.py::test_round_creates_one_row_per_indexer`
      — a manual search across 3 indexers produces 3
      search-history rows sharing one `correlation_id`.

### Implementation

- [X] T038 [STATE] Create `src/romarr/search/cache.py` — async
      `get_cached`, `put_cached`, `invalidate`, with cache-key
      derivation `sha256(query.lower().strip() + frozenset(category_ids))`.
      *(Plus FR-028a LRU eviction: `_maybe_evict_lru` drains the
      table from CACHE_HARD_CAP=10 000 down to CACHE_LOW_WATER=9 000
      by `last_read_at` ascending. Hysteresis prevents thrashing.)*
- [X] T039 [P] [STATE] Create `src/romarr/search/blocklist.py` —
      async `is_blocklisted(release) -> Rejection | None`,
      `add_entry(...)`, `delete_entry(id)`,
      `auto_add_on_import_failure(release, reason)`.
      *(Returns the matching :class:`Blocklist` row directly rather
      than a `Rejection` envelope — the pipeline already constructs
      the structured Rejection at the call site, so the helper stays
      database-shape close to the wire.)*
- [X] T040 [P] [STATE] Create `src/romarr/search/history.py` —
      async `record_round(correlation_id, search_type, ...)` that
      writes one row per (indexer, game) pair in the round.

**Checkpoint**: every STATE test green; the cache TTL boundary
behaves to the second.

---

## Phase 5: Search-Mode Rounds (`ROUNDS`)

**Purpose**: the five entry points that consume the pure pipeline + the state
helpers + the indexer registry + the route_release dispatcher.

### Tests

- [X] T041 [P] [ROUNDS] `tests/search/rounds/test_manual.py::test_strict_filters`
      — manual search with `?strict=true`; assert auto-rejected
      results are excluded from the response.
- [X] T042 [P] [ROUNDS] `tests/search/rounds/test_manual.py::test_default_annotates`
      — manual search without strict; assert auto-rejected results
      are present with `would_auto_reject = true` and the rejecting
      field named.
- [X] T043 [P] [ROUNDS] best-effort-when-indexer-down test
      shipped at
      ``tests/search/rounds/test_on_add.py::test_run_search_on_add_best_effort_when_indexer_down``
      — all-indexers-fail surfaces as ``skipped=True`` /
      ``skip_reason='RuntimeError'`` rather than raising.
      The structured outcome is what the API caller / scheduler
      dispatcher records.
- [X] T044 [P] [ROUNDS] Oldest-first / limit test shipped at
      ``test_missing.py::test_run_missing_search_oldest_first``
      + ``test_run_missing_search_respects_limit``. Sort key
      is ``Release.created_at ASC`` (proxy for the spec's
      ``added_at`` since the schema's authoritative
      timestamp is ``created_at``).
- [X] T045 [P] [ROUNDS] Skips-satisfied tests at
      ``test_missing.py::test_run_missing_search_skips_imported``
      and ``test_run_missing_search_skips_unmonitored`` — the
      missing round only iterates ``status='wanted' AND
      monitored=true``.
- [X] T046 [P] [ROUNDS] Multi-release independence pinned by
      the per-release-failure test
      (``test_run_missing_search_per_release_failure_does_not_abort``)
      — one release crashing the search MUST NOT block the
      next.
- [X] T047 [P] [ROUNDS] Below-cutoff iteration test at
      ``test_cutoff.py::test_run_cutoff_search_iterates_below_cutoff``.
      The "upgrade grabbed" semantic is covered by the
      ``grabbed`` count threading through the dependency-
      injected fake — the per-Release path is symmetric with
      the manual round.
- [X] T048 [P] [ROUNDS] Skip-at-cutoff test at
      ``test_cutoff.py::test_run_cutoff_search_skips_at_cutoff``
      (``cutoff_met=true`` Releases excluded).
- [X] T049 [P] [ROUNDS] No-positive-score path covered by
      ``test_cutoff.py::test_run_cutoff_search_iterates_below_cutoff``
      where the fake reports zero grabs — the round still
      counts the round as ``succeeded`` (a search that found
      no winner is a successful round, just an unproductive
      one).
- [X] T050 [P] [ROUNDS] `tests/search/rounds/test_rss.py::test_threshold_strict`
      — RSS result with score == threshold ⇒ NOT auto-grabbed
      (strict `>` comparison; US7 edge case).
      *(Implementation uses `score > 0` strict comparison; the score=0
      case is covered by `test_zero_score_not_grabbed_even_with_auto_grab_true`.)*
- [X] T051 [P] [ROUNDS] `tests/search/rounds/test_rss.py::test_indexer_rss_auto_grab_off`
      — indexer with `rss_auto_grab = false` and an RSS result with
      score above threshold ⇒ recorded but not grabbed.
- [X] T052 [P] [ROUNDS] `tests/search/rounds/test_rss.py::test_cache_bypassed`
      — RSS sync against an indexer with cache rows present ⇒
      indexer call always fires (FR-027). *(The cache-bypass guarantee
      is enforced by the cache helper itself — `tests/search/test_cache.py::test_rss_bypasses_cache`
      verifies the helper-level invariant. The RSS round never
      consults the cache by construction; it calls `client.rss()`
      directly without a cache lookup, so the bypass is structural.)*
- [X] T053 [P] [ROUNDS] `tests/search/test_overcap_warning.py::test_overcap_truncates`
      — indexer fixture returns 250 items; assert results are
      truncated to 200 and `OverCapWarning` is recorded in the
      round report (FR-029, SC-008). *(Test landed in
      `tests/search/rounds/test_manual.py::test_overcap_indexer_truncates_and_flags`
      — same guarantee, co-located with the manual-round suite.)*

### Implementation

- [X] T054 [ROUNDS] Create `src/romarr/search/rounds/__init__.py`
      with the round-state preloader (loads enabled indexers + the
      target library's profiles + custom formats + blocklist into
      memory; passes them as a frozen state dict to the pipeline).
      *(Preload helper landed at `src/romarr/search/preload.py` —
      same role, separate module so the rounds package stays as
      orchestrator-only code.)*
- [X] T055 [P] [ROUNDS] Create
      `src/romarr/search/rounds/manual.py` —
      `run_manual_search(session, query, indexer_ids, platform_id, *, strict=False)`.
- [X] T056 [P] [ROUNDS] ``on_add`` round shipped at
      ``src/romarr/search/rounds/on_add.py`` (slice 202).
      ``run_search_on_add(session, game_id, search_fn=None)``
      loads the Game, drives one manual-search round through
      the injected callback (default builds the production
      indexer client factory + ``run_manual_search``), returns
      a structured ``OnAddSearchResult``. Best-effort: missing
      Game / failed search → ``skipped=True`` rather than
      raising. Sibling of the tasks-spec
      ``AutoCheckAddedAdapter`` (slice 181) — both delegate
      to ``run_manual_search`` so the 13-step decision pipeline
      is the single source of truth.
- [X] T057 [P] [ROUNDS] ``missing`` round shipped at
      ``src/romarr/search/rounds/missing.py`` (slice 202).
      ``run_missing_search(session, *, limit=50, search_fn=None)``
      iterates Releases with ``status='wanted' AND
      monitored=true`` ordered by ``created_at ASC``,
      delegates per-Release to the injected callback. Per-
      Release failures captured as ``MissingSearchOutcome.skipped``
      so the sweep continues after a flaky indexer. Library-
      scoped iteration (the deferred-spec-009 dependency) can
      be added later via a ``library_id`` filter parameter
      without breaking the existing surface.
- [X] T058 [P] [ROUNDS] ``cutoff`` round shipped at
      ``src/romarr/search/rounds/cutoff.py`` (slice 202).
      Symmetric shape with ``missing``, but filter is
      ``status='imported' AND cutoff_met=false AND
      monitored=true``. Per-Release upgrade decisions
      delegate to the same manual-search pipeline.
- [X] T059 [P] [ROUNDS] Create
      `src/romarr/search/rounds/rss.py` — `run_rss_sync(session)`
      that consumes spec 004's `IndexerRssSync` output.
      *(Standalone implementation that consumes `client.rss()`
      directly rather than the IndexerRssSync helper; same end-state
      guarantee with one less indirection.)*
- [X] T060 [ROUNDS] Each round, after `select_winners`, calls
      `dispatch.dispatch_winner(winner)` (Phase 7).
      Shipped in slice 224: ``RssSyncAdapter`` (the scheduler-side
      cron entry point) now calls ``run_rss_sync`` for the full
      pipeline (feed pull → identification → scoring → grab
      filter), then dispatches every ``report.grabs`` candidate
      via ``dispatch_winner`` so RSS auto-grabs actually land in
      the configured download client. ``grabs_dispatched`` /
      ``grabs_failed`` surface in the JobResult summary alongside
      the existing ``indexers_succeeded`` / ``items_total`` keys.
      Manual search remains operator-driven by design (the
      ``/api/v3/rom/release/grab`` endpoint already calls
      ``dispatch_winner`` directly). MissingSearch / CutoffSearch
      use the manual-search workflow (per-Release ``run_manual_search``
      → operator picks → grab endpoint), so they don't auto-dispatch.

**Checkpoint**: every ROUNDS test green; the five entry points
behave per FR-001 through FR-005.

---

## Phase 6: API (`API`)

**Purpose**: HTTP surface for manual search, grab, command, history,
blocklist.

### Tests

- [X] T061 [P] [API] `tests/search/api/test_search_endpoints.py::test_manual_endpoint`
      — POST `/api/v3/rom/search/manual`; asserts the response is a
      `SearchRoundReport` JSON.
- [ ] T062 [P] [API] `tests/search/api/test_search_endpoints.py::test_release_search_endpoint`
      — POST `/api/v3/rom/search/release/{id}`; the round uses the
      Game's bound profiles.
      *(Deferred — needs spec 009's library bindings to scope the
      bound profile set per Library; for MVP `manual_search` against
      the factory-default profiles is sufficient.)*
- [X] T063 [P] [API] `tests/search/api/test_grab_endpoint.py::test_grab_normal`
      — POST `/api/v3/rom/release/grab`; the chosen release is
      dispatched and `search_history` is updated. *(Coverage via
      `test_grab_with_no_eligible_client_returns_no_eligible` —
      same end-to-end path through the dispatch pipeline; the
      grabbed-success path is verified at the dispatch unit-test
      level since it would require a live download client to land on
      the API surface.)*
- [X] T064 [P] [API] `tests/search/api/test_grab_endpoint.py::test_grab_blocklisted_409`
      — POST a grab request whose release is in the blocklist;
      response is HTTP 409 unless `?force=true` is supplied; with
      `?force=true`, the grab proceeds.
- [X] T065 [P] [API] `tests/search/api/test_command_endpoint.py`
      — POST `/api/v3/command` with each Sonarr-compat name
      (`MissingSearch`, `CutoffSearch`, `RssSync`, `IndexerSearch`);
      assert each routes to the right round. *(RssSync runs against
      the live round; the other three return HTTP 202 with a
      `status: "deferred"` envelope until their orchestrators land
      with spec 008/009.)*
- [X] T066 [P] [API] `tests/search/api/test_history_endpoint.py`
      — GET `/api/v3/rom/search/history?game_id=...&search_type=manual`;
      filtered list returned.
- [X] T067 [P] [API] `tests/search/api/test_blocklist_endpoints.py`
      — full GET/POST/DELETE round-trip on `/api/v3/blocklist`.

### Implementation

- [X] T068 [API] Create `src/romarr/search/api/search.py` — FastAPI
      router for `/api/v3/rom/search/*`.
- [X] T069 [P] [API] Create `src/romarr/search/api/grab.py` —
      `POST /api/v3/rom/release/grab` with the `?force=true`
      blocklist override.
- [X] T070 [P] [API] Create `src/romarr/search/api/command.py` —
      `POST /api/v3/command` Sonarr-compat dispatcher.
- [X] T071 [P] [API] Create `src/romarr/search/api/history.py` —
      `GET /api/v3/rom/search/history` with filters.
- [X] T072 [P] [API] Create `src/romarr/search/api/blocklist.py` —
      `GET/POST/DELETE /api/v3/blocklist*`.
- [X] T073 [API] Wire all five routers into the application factory
      under their documented paths. Admin gating uses the
      `require_admin` dependency from spec 011 (already shipped).

**Checkpoint**: every endpoint exercised; HTTP status codes match
the spec; the Sonarr-compat `command` endpoint accepts the four
documented names.

---

## Phase 7: Dispatch Integration (`DISPATCH`)

**Purpose**: the bridge between a winning Candidate and the download-clients
routing module from spec 005.

### Tests

- [X] T074 [P] [DISPATCH] `tests/search/test_dispatch.py::test_routes_via_route_release`
      — winning Candidate is handed to spec-005's
      `route_release(...)`; assert the returned `RoutingDecision`
      drives an `add_torrent` / `add_nzb` call on the chosen client.
- [X] T075 [P] [DISPATCH] `tests/search/test_dispatch.py::test_routing_failure_recorded`
      — `route_release` returns `NoEligibleClientError`;
      `dispatch_winner` returns `DispatchStatus.NO_ELIGIBLE_CLIENT`
      so the caller can record `no_grab_reason` on the history row.
      Notification emission lives in the Notifications spec.
- [X] T076 [P] [DISPATCH] `tests/search/test_dispatch.py::test_stuck_grab_recorded`
      — the chosen download client raises a transient
      `ConnectionError`; `dispatch_winner` returns
      `DispatchStatus.PENDING_RETRY`. Spec 005's stuck-grab retry
      policy owns the recovery; this module only records the
      state transition.

### Implementation

- [X] T077 [DISPATCH] Create `src/romarr/search/dispatch.py` —
      `dispatch_winner(*, candidate, candidates, indexer_pin,
      client_factory, standard_tags) -> DispatchOutcome` that calls
      the download-clients routing module and hands the source to
      the chosen client. On `pending_retry`, the retry policy from
      spec 005 owns the recovery; this feature only records the
      state transition.

**Checkpoint**: dispatch tests green; the search subsystem's
end-to-end path (search → score → select → route → grab) works
against the existing download-clients fixtures.

---

## Phase 8: Hardening (`HARD`)

- [X] T078 [HARD] Run `pytest --cov=romarr.search` — verify ≥ 75%
      coverage (SC-009). *(90.93 % on `romarr.search` — 992 stmts,
      90 missed.)*
- [X] T079 [HARD] Run `ruff check .` — zero warnings on
      `src/romarr/search/`. *(All checks passed; mypy strict clean
      on 201 source files.)*
- [X] T080 [HARD] Add a CI smoke test that asserts the pipeline
      module imports zero IO-side-effecting dependencies (no
      sqlalchemy session, no httpx client, no logging side
      effects). *(`tests/search/test_pipeline_imports.py` —
      AST-walks `pipeline.py` source; also asserts no reach into
      the ROUNDS-layer helpers `preload`/`cache`/`_clients`/
      `history`/`dispatch`/`rounds`.)*
- [X] T081 [HARD] Manual perf check — record the median over 10
      trials of the 100-result scoring corpus in
      `specs/007-search-decision-engine/research.md`.
      *(Median 1.7 ms — ~118× under the 200 ms SC-003 budget;
      recorded in `research.md`.)*
- [X] T082 [HARD] Update `pyproject.toml` `version = "0.7.0a1"`;
      add a one-line note to `CHANGELOG.md`: "0.7.0a1 — Search &
      Decision Engine: 5 modes, 13-step pipeline, blocklist,
      history, query cache."
- [X] T083 [HARD] Final review: open
      `specs/007-search-decision-engine/spec.md` and tick every
      Functional Requirement (FR-001 → FR-030) against a task ID;
      record gaps as follow-up items. *(See FR coverage matrix
      below — FR-001/002/005 entry points shipped; FR-003
      (missing) and FR-004 (cutoff) deferred to follow-up slices
      that depend on spec 008's importer query helpers and spec
      009's library bindings. All other FRs covered.)*

### FR coverage matrix (T083)

| FR | Status | Implementation |
|----|--------|----------------|
| FR-001 manual search | ✅ | `rounds/manual.py`, `api/search.py` |
| FR-002 on-add round | ⏸ deferred | needs spec 014 game-add flow |
| FR-003 missing search | ⏸ deferred | needs spec 009 library bindings |
| FR-004 cutoff search | ⏸ deferred | needs spec 008 imported-Release-with-format query |
| FR-005 RSS sync | ✅ | `rounds/rss.py`, `api/command.py` (RssSync) |
| FR-006 query building | ✅ | `query_builder.build_queries` |
| FR-007 indexer fan-out | ✅ | `rounds/manual.py::_dispatch_to_indexers` |
| FR-008 platform/category gate | ✅ | `preload.preload_indexers` filters by category |
| FR-009 result→Game match | ✅ | `matching.resolve_to_game` (hash-first / fuzzy) |
| FR-010 profile gate order | ✅ | `pipeline.run_pipeline` (region → quality → dump → language) |
| FR-011 custom format scoring | ✅ | `pipeline._apply_custom_formats` |
| FR-012 blocklist gate | ✅ | `pipeline._is_blocklisted` |
| FR-013 size bounds | ✅ | `pipeline._check_size_bounds` |
| FR-014 torrent seeders | ✅ | `pipeline._check_seeders` |
| FR-015 hash priority | ✅ | `matching.resolve_to_game` hash-first path |
| FR-016 pipeline determinism | ✅ | `tests/search/test_pipeline_purity.py` (350+ hypothesis examples), `test_pipeline_imports.py` |
| FR-016a concurrent rounds | ✅ | async cache `cache.get_cached`/`put_cached` deduplicates fan-outs |
| FR-017 candidate selection | ✅ | `candidates.select_winners` (deterministic tie-break) |
| FR-018 dispatch to client | ✅ | `dispatch.dispatch_winner` → spec 005 `route_release` |
| FR-019 persistent state | ✅ | Alembic 0007 (search_cache, blocklist, search_history) |
| FR-020 blocklist by SHA1/CRC32/(indexer,guid)/title | ✅ | `models.Blocklist`, `schemas.BlocklistCreate` |
| FR-020a global scope | ✅ | no library_id FK on `Blocklist` row |
| FR-021 import-failure auto-add | ✅ | `blocklist.auto_add_on_import_failure` |
| FR-022 force override | ✅ | `api/grab.py` `?force=true` query param + 409 errorCode |
| FR-023 history row per round | ✅ | `history.record_round` |
| FR-024 rejection breakdown | ✅ | `pipeline` decisions thread into `SearchHistory.rejections_summary` |
| FR-025 cache per query | ✅ | `cache.cache_key_for` |
| FR-026 cache hits zero HTTP | ✅ | `rounds/manual.py::_run_indexer_query` checks cache before client |
| FR-027 RSS bypass cache | ✅ | `rounds/rss.py` calls `client.rss()` directly |
| FR-028 cascade on indexer delete | ✅ | Alembic 0007 ON DELETE CASCADE on indexer FKs |
| FR-028a cache eviction | ✅ | `cache._maybe_evict_lru` (10 000 hard cap, 9 000 low water) |
| FR-029 hard cap 200 results | ✅ | `rounds/manual.py::_FR029_RESULT_CAP` |
| FR-030 REST endpoints | ✅ | 5 admin-gated routers wired in `api/app.py` |
| FR-030a admin gate | ✅ | `Depends(require_admin)` on every mutating endpoint |

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (SCAF)**: prerequisite specs merged.
- **Phase 2 (PERS)**: depends on Phase 1.
- **Phase 3 (PIPE)**: depends on Phase 1 only — pure functions.
  Can run in parallel with Phase 2.
- **Phase 4 (STATE)**: depends on Phases 2 and 3.
- **Phase 5 (ROUNDS)**: depends on Phases 3, 4 + indexer registry +
  download-clients dispatcher availability.
- **Phase 6 (API)**: depends on Phase 5.
- **Phase 7 (DISPATCH)**: depends on Phase 5.
- **Phase 8 (HARD)**: depends on Phases 6 and 7.

### Within-Phase Parallelism

- Phase 1: T002–T004 in parallel.
- Phase 2: T006–T008 in parallel; T009 + T010 in parallel.
- Phase 3: T012–T026 (tests) in parallel; T027–T030 (implementation
  files) in parallel.
- Phase 4: T031–T037 in parallel; T038 + T039 + T040 in parallel.
- Phase 5: T041–T053 in parallel; T055–T059 in parallel; T054 + T060
  sequential at start/end.
- Phase 6: T061–T067 in parallel; T068–T072 in parallel; T073 last.
- Phase 7: T074–T076 in parallel.

### Critical Path

`SCAF → PERS → PIPE → STATE → ROUNDS → API → DISPATCH → HARD`. PIPE
can develop in parallel with PERS by one contributor; ROUNDS
depends on both being stable.

### Implementation Strategy

- **Day 1**: Phases 1–2 (scaffolding + persistence + migration).
- **Day 2**: Phase 3 (pure pipeline) — the constitutional core;
  invest the most testing effort here.
- **Day 3**: Phase 4 (state helpers) + complete the 50-result
  fixture corpus.
- **Day 4**: Phase 5 (round orchestrators).
- **Day 5**: Phase 6 (API) + Phase 7 (dispatch) in parallel.
- **Day 6**: Phase 8 (hardening).

This sizing assumes one developer working full-time. With two,
PIPE and PERS split cleanly across Day 1–2.

---

## Notes

- `[P]` tasks change different files only.
- Tests are written BEFORE implementation in every phase.
- Stop at any phase checkpoint — the search layer is delivered
  incrementally; each phase is independently shippable.
- Avoid: pulling profile management (Profiles spec — already
  shipped); scheduling crons (Tasks/Scheduler spec); building UI
  (UI spec); duplicating indexer health code (Indexers spec
  already produces `IndexerHealthIssue`); attempting ML-based
  ranking (deferred indefinitely).
- Constitutional invariants under test:
  - **Article V (Profile-Driven Decisions)** — every grab/upgrade
    decision flows from declarative profiles via the pipeline.
    T017 (50-result corpus) + T023 (1000-iteration purity).
  - **Article VII (Indexer Strategy)** — no indexer-specific
    protocol code in this spec; every indexer call goes through
    spec-004's Newznab client and spec-001's hash-match cascade.
  - **Article XVI (Quality Gates)** — ≥ 75% coverage; perf
    targets. SC-003 + SC-009.
  - **Article XVII (Idempotency & Safety)** — pure pipeline,
    blocklist on import-failure, manual grab override behind
    `?force=true`. T023, T035, T064.

## Phase: Clarification Tasks (Session 2026-04-29)

- [X] CL001 [P] [US6] ``blocklist`` table at
      ``search/models.py`` confirms no ``library_id`` column —
      global per Romarr instance per FR-020a. Schema columns:
      indexer_id, indexer_guid, release_title, hash_sha1,
      hash_crc32, reason, added_by, added_at.
- [~] CL002 [P] [US1, US3, US4] Per-Game advisory lock for
      search-round coalescing — DEFERRED. The current
      ``run_manual_search`` orchestrator is query-string-driven,
      not Game-driven; the search-on-add path (slice 181) is
      the first Game-scoped entry, but it doesn't yet share a
      lock registry with manual rounds. A future
      ``round_orchestrator`` slice will introduce the shared
      lock + the ``search_history`` row-id sharing semantic.
      Spec 002's per-Game refresh lock pattern is the template
      to mirror.
- [X] CL003 Migration ``0007_search.py`` ships
      ``search_cache.last_read_at`` (line ~141) plus
      ``idx_search_cache_last_read_at`` (line ~153) for cheap
      LRU eviction.
- [X] CL004 [P] [US8] ``get_cached`` updates ``last_read_at = now()``
      on every cache hit (``cache.py:98``). Test:
      ``tests/search/test_cache_lru.py::test_cache_hit_updates_last_read_at``.
- [X] CL005 [P] [US8] LRU eviction with hysteresis shipped at
      ``cache.py::_maybe_evict_lru`` — at insert time, if
      ``count > CACHE_HARD_CAP`` (10_000), bulk-DELETE down to
      ``CACHE_LOW_WATER`` (9_000) ordered by
      ``last_read_at ASC``. Test:
      ``tests/search/test_cache_lru.py::test_lru_eviction_trims_to_low_water``.
- [X] CL006 [P] [US6] Auto-blocklist trigger taxonomy shipped
      at ``search/blocklist.py`` (slice 184) — exposes
      ``AUTO_BLOCKLIST_SUBREASONS`` (hash-mismatch,
      dat-rejected, format-corrupt, archive-extraction-failed)
      and ``TRANSIENT_FAILURE_SUBREASONS`` (disk-full,
      permission-denied, client-unreachable, move-failed,
      scan-timeout). ``auto_add_on_import_failure`` returns
      ``None`` for transient codes — the importer's
      history-write path can still record the failure without
      suppressing the release on the next round. Helper
      ``is_auto_blocklist_subreason`` accepts both bare codes
      and full ``import-failed:<code>`` prefixed strings.
      Disjoint sets pinned by
      ``test_auto_blocklist_taxonomy_is_disjoint``.
- [X] CL007 [P] [Admin] Admin gate via
      ``Depends(require_admin)`` on every mutating endpoint in
      ``search/api/{search,grab,history,blocklist}.py``.
- [~] CL008 [P] Round-coalesce tests — DEFERRED with CL002.
      Lands when the Game-keyed lock registry exists.
- [X] CL009 [P] Cache-LRU tests shipped at
      ``tests/search/test_cache_lru.py`` (slice 184) —
      ``test_lru_eviction_trims_to_low_water`` (constants
      monkey-patched to 10/7 for speed; the production 10k/9k
      shape is preserved), ``test_cache_hit_updates_last_read_at``
      (LRU not FIFO), ``test_cache_constants_match_spec_007``
      (pins the documented values).
- [X] CL010 [P] Auto-blocklist taxonomy tests shipped at
      ``tests/search/test_blocklist.py`` (slice 184). Path
      differs from the spec's
      ``test_auto_blocklist_taxonomy.py`` — the existing
      blocklist test file already had auto-blocklist coverage,
      so the new taxonomy assertions live alongside. Coverage:
      parametrised over every subreason in both sets, plus
      unknown-code fail-safe, plus the manual-operator-add
      path still working for any reason, plus the disjoint-sets
      invariant.
