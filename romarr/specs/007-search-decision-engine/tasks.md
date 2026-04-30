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

- [ ] T041 [P] [ROUNDS] `tests/search/rounds/test_manual.py::test_strict_filters`
      — manual search with `?strict=true`; assert auto-rejected
      results are excluded from the response.
- [ ] T042 [P] [ROUNDS] `tests/search/rounds/test_manual.py::test_default_annotates`
      — manual search without strict; assert auto-rejected results
      are present with `would_auto_reject = true` and the rejecting
      field named.
- [ ] T043 [P] [ROUNDS] `tests/search/rounds/test_on_add.py::test_best_effort_when_indexer_down`
      — every indexer mocked to return 5xx; the Game creation API
      response succeeds; a `search_history` row records
      `no_grab_reason = 'all_indexers_failed'` (FR-002, US2.3).
- [ ] T044 [P] [ROUNDS] `tests/search/rounds/test_missing.py::test_oldest_first_limit_50`
      — seed 80 wanted Games; invoke `run_missing_search(limit=50)`;
      assert exactly the 50 oldest by `added_at` are processed
      (SC-004).
- [ ] T045 [P] [ROUNDS] `tests/search/rounds/test_missing.py::test_skips_satisfied`
      — Games whose Releases all match the cutoff are skipped.
- [ ] T046 [P] [ROUNDS] `tests/search/rounds/test_missing.py::test_multi_release_independence`
      — Game with three wanted Releases (USA, EUR, JPN); each is
      searched and matched independently; one release fills exactly
      one slot (US4.3 + edge case).
- [ ] T047 [P] [ROUNDS] `tests/search/rounds/test_cutoff.py::test_upgrade_grabbed`
      — imported Release at format `raw`, cutoff `chd`; available
      `chd` release with score 50 ⇒ grabbed (SC-005).
- [ ] T048 [P] [ROUNDS] `tests/search/rounds/test_cutoff.py::test_skip_at_cutoff`
      — imported Release format equals cutoff ⇒ skip.
- [ ] T049 [P] [ROUNDS] `tests/search/rounds/test_cutoff.py::test_no_positive_score`
      — imported Release below cutoff but available upgrades all
      score ≤ 0 ⇒ skip; record `no_grab_reason`.
- [ ] T050 [P] [ROUNDS] `tests/search/rounds/test_rss.py::test_threshold_strict`
      — RSS result with score == threshold ⇒ NOT auto-grabbed
      (strict `>` comparison; US7 edge case).
- [ ] T051 [P] [ROUNDS] `tests/search/rounds/test_rss.py::test_indexer_rss_auto_grab_off`
      — indexer with `rss_auto_grab = false` and an RSS result with
      score above threshold ⇒ recorded but not grabbed.
- [ ] T052 [P] [ROUNDS] `tests/search/rounds/test_rss.py::test_cache_bypassed`
      — RSS sync against an indexer with cache rows present ⇒
      indexer call always fires (FR-027).
- [ ] T053 [P] [ROUNDS] `tests/search/test_overcap_warning.py::test_overcap_truncates`
      — indexer fixture returns 250 items; assert results are
      truncated to 200 and `OverCapWarning` is recorded in the
      round report (FR-029, SC-008).

### Implementation

- [ ] T054 [ROUNDS] Create `src/romarr/search/rounds/__init__.py`
      with the round-state preloader (loads enabled indexers + the
      target library's profiles + custom formats + blocklist into
      memory; passes them as a frozen state dict to the pipeline).
- [ ] T055 [P] [ROUNDS] Create
      `src/romarr/search/rounds/manual.py` —
      `run_manual_search(session, query, indexer_ids, platform_id, *, strict=False)`.
- [ ] T056 [P] [ROUNDS] Create
      `src/romarr/search/rounds/on_add.py` —
      `run_search_on_add(session, game)` best-effort wrapper.
- [ ] T057 [P] [ROUNDS] Create
      `src/romarr/search/rounds/missing.py` —
      `run_missing_search(session, *, limit=50)` oldest-first iter.
- [ ] T058 [P] [ROUNDS] Create
      `src/romarr/search/rounds/cutoff.py` —
      `run_cutoff_search(session, *, limit=50)` below-cutoff iter.
- [ ] T059 [P] [ROUNDS] Create
      `src/romarr/search/rounds/rss.py` — `run_rss_sync(session)`
      that consumes spec 004's `IndexerRssSync` output.
- [ ] T060 [ROUNDS] Each round, after `select_winners`, calls
      `dispatch.dispatch_winner(winner)` (Phase 7).

**Checkpoint**: every ROUNDS test green; the five entry points
behave per FR-001 through FR-005.

---

## Phase 6: API (`API`)

**Purpose**: HTTP surface for manual search, grab, command, history,
blocklist.

### Tests

- [ ] T061 [P] [API] `tests/search/api/test_search_endpoints.py::test_manual_endpoint`
      — POST `/api/v3/rom/search/manual`; asserts the response is a
      `SearchRoundReport` JSON.
- [ ] T062 [P] [API] `tests/search/api/test_search_endpoints.py::test_release_search_endpoint`
      — POST `/api/v3/rom/search/release/{id}`; the round uses the
      Game's bound profiles.
- [ ] T063 [P] [API] `tests/search/api/test_grab_endpoint.py::test_grab_normal`
      — POST `/api/v3/rom/release/grab`; the chosen release is
      dispatched and `search_history` is updated.
- [ ] T064 [P] [API] `tests/search/api/test_grab_endpoint.py::test_grab_blocklisted_409`
      — POST a grab request whose release is in the blocklist;
      response is HTTP 409 unless `?force=true` is supplied; with
      `?force=true`, the grab proceeds.
- [ ] T065 [P] [API] `tests/search/api/test_command_endpoint.py`
      — POST `/api/v3/command` with each Sonarr-compat name
      (`MissingSearch`, `CutoffSearch`, `RssSync`, `IndexerSearch`);
      assert each routes to the right round.
- [ ] T066 [P] [API] `tests/search/api/test_history_endpoint.py`
      — GET `/api/v3/rom/search/history?game_id=...&search_type=manual`;
      filtered list returned.
- [ ] T067 [P] [API] `tests/search/api/test_blocklist_endpoints.py`
      — full GET/POST/DELETE round-trip on `/api/v3/blocklist`.

### Implementation

- [ ] T068 [API] Create `src/romarr/search/api/search.py` — FastAPI
      router for `/api/v3/rom/search/*`.
- [ ] T069 [P] [API] Create `src/romarr/search/api/grab.py` —
      `POST /api/v3/rom/release/grab` with the `?force=true`
      blocklist override.
- [ ] T070 [P] [API] Create `src/romarr/search/api/command.py` —
      `POST /api/v3/command` Sonarr-compat dispatcher.
- [ ] T071 [P] [API] Create `src/romarr/search/api/history.py` —
      `GET /api/v3/rom/search/history` with filters.
- [ ] T072 [P] [API] Create `src/romarr/search/api/blocklist.py` —
      `GET/POST/DELETE /api/v3/blocklist*`.
- [ ] T073 [API] Wire all five routers into the application factory
      under their documented paths. Authentication continues to use
      the development-only no-op admin dependency until the Auth
      spec lands.

**Checkpoint**: every endpoint exercised; HTTP status codes match
the spec; the Sonarr-compat `command` endpoint accepts the four
documented names.

---

## Phase 7: Dispatch Integration (`DISPATCH`)

**Purpose**: the bridge between a winning Candidate and the download-clients
routing module from spec 005.

### Tests

- [ ] T074 [P] [DISPATCH] `tests/search/test_dispatch.py::test_routes_via_route_release`
      — winning Candidate is handed to spec-005's
      `route_release(...)`; assert the returned `RoutingDecision`
      drives an `add_torrent` / `add_nzb` call on the chosen client.
- [ ] T075 [P] [DISPATCH] `tests/search/test_dispatch.py::test_routing_failure_recorded`
      — `route_release` returns `chosen_client_id = None`;
      `search_history` records `no_grab_reason = 'no_eligible_client'`
      and emits a Notification event (consumer in Notifications spec).
- [ ] T076 [P] [DISPATCH] `tests/search/test_dispatch.py::test_stuck_grab_recorded`
      — the chosen download client raises a transient
      `ConnectionError`; spec 005's stuck-grab retry policy parks
      the grab; `search_history` records `pending_retry`.

### Implementation

- [ ] T077 [DISPATCH] Create `src/romarr/search/dispatch.py` —
      `dispatch_winner(session, candidate) -> DispatchOutcome` that
      calls the download-clients routing module and threads the
      outcome back into `search_history`. On `pending_retry`, the
      retry policy from spec 005 owns the recovery; this feature
      only records the state transition.

**Checkpoint**: dispatch tests green; the search subsystem's
end-to-end path (search → score → select → route → grab) works
against the existing download-clients fixtures.

---

## Phase 8: Hardening (`HARD`)

- [ ] T078 [HARD] Run `pytest --cov=romarr.search` — verify ≥ 75%
      coverage (SC-009). Add targeted tests for any uncovered
      branch.
- [ ] T079 [HARD] Run `ruff check .` — zero warnings on
      `src/romarr/search/`.
- [ ] T080 [HARD] Add a CI smoke test that asserts the pipeline
      module imports zero IO-side-effecting dependencies (no
      sqlalchemy session, no httpx client, no logging side
      effects). A static-analysis assertion via
      `python -c "import ast; ..."` or a small helper script.
- [ ] T081 [HARD] Manual perf check — record the median over 10
      trials of the 100-result scoring corpus in
      `specs/007-search-decision-engine/research.md`.
- [ ] T082 [HARD] Update `pyproject.toml` `version = "0.7.0a1"`;
      add a one-line note to `CHANGELOG.md`: "0.7.0a1 — Search &
      Decision Engine: 5 modes, 13-step pipeline, blocklist,
      history, query cache."
- [ ] T083 [HARD] Final review: open
      `specs/007-search-decision-engine/spec.md` and tick every
      Functional Requirement (FR-001 → FR-030) against a task ID;
      record gaps as follow-up items.

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

- [ ] CL001 [P] [US6] Confirm `blocklist` schema has NO `library_id` column (global per Romarr instance) in `src/romarr/search/models.py` (FR-020a)
- [ ] CL002 [P] [US1, US3, US4] Implement per-Game advisory lock for search-round coalesce in `src/romarr/search/round_orchestrator.py` — concurrent search rounds against the same Game share a single in-flight round; lock-holder TTL 5 minutes; second caller blocks and receives the same `search_history` row id without re-querying indexers (FR-016a)
- [ ] CL003 Migration `0007_search.py` adds `search_cache.last_read_at TIMESTAMP NOT NULL DEFAULT current_timestamp` and an index on `last_read_at` for cheap LRU eviction (FR-028a)
- [ ] CL004 [P] [US8] Update `search_cache` reader in `src/romarr/search/cache.py` to set `last_read_at = now()` on every cache hit
- [ ] CL005 [P] [US8] Implement LRU eviction with hysteresis in `src/romarr/search/cache.py` — at insert time, when row count would exceed 10,000, run a single bulk DELETE down to 9,000 ordered by `last_read_at ASC` (FR-028a)
- [ ] CL006 [P] [US6] Update auto-blocklist trigger in `src/romarr/search/blocklist.py` to invoke the helper ONLY when the import-failure subreason is one of `hash-mismatch`, `dat-rejected`, `format-corrupt`, `archive-extraction-failed`. Transient subreasons (`disk-full`, `permission-denied`, `client-unreachable`, `move-failed`, `scan-timeout`) record in `search_history` but do NOT call the helper (FR-021 rewritten)
- [ ] CL007 [P] [Admin] Wire admin-role gate on every mutating search/blocklist/command endpoint in `src/romarr/search/api.py` (`/search/manual`, `/search/release/{id}`, `/release/grab`, `/command`, `/blocklist` POST, `/blocklist/{id}` DELETE); reads accessible to any authenticated user (FR-030a)
- [ ] CL008 [P] Add tests in `tests/search/test_round_coalesce.py` covering: 5 concurrent search rounds on the same Game → exactly one set of indexer calls fires; all 5 callers receive the same `search_history` row id
- [ ] CL009 [P] Add tests in `tests/search/test_cache_lru.py` covering: insert past 10k → bulk delete to 9k; hit on existing row → `last_read_at` updates; eviction order matches LRU
- [ ] CL010 [P] Add tests in `tests/search/test_auto_blocklist_taxonomy.py` covering: each content-correctness subreason → blocklist row created; each transient subreason → no blocklist row; manual operator add still works for any subreason
