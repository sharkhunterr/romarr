# Implementation Plan: Search & Grab Decision Engine

**Branch**: `007-search-decision-engine` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification at `specs/007-search-decision-engine/spec.md`
**Depends on**: `001-foundation`, `003-platform-packs`, `004-indexers`, `005-download-clients`, `006-profiles`

## Summary

The search subsystem is the orchestrator that turns "wanted Games"
into "grabbed Releases." It exposes five entry points (one per
search mode), runs every result through a 13-step decision
pipeline composed of pure functions, picks the highest-scored
candidate per Release slot, and dispatches the chosen result via
the download-clients routing module.

Three deliverables on top of the prerequisite specs:

1. **A pure-function decision pipeline** that consumes the
   `ProfileEvaluator`, `compute_custom_format_score`, the
   blocklist, and the foundation's hash-match cascade. Pure means
   deterministic — same inputs ⇒ same outputs — and the per-round
   in-memory state is preloaded once so the pipeline performs no
   per-result database round-trips.
2. **Five search-mode orchestrators**: `run_manual_search`,
   `run_search_on_add`, `run_missing_search`, `run_cutoff_search`,
   `run_rss_sync`. Each is a small async function that fans out
   across enabled indexers, drives the pipeline, persists the
   resulting search-history rows, and dispatches the winners.
3. **A query-result cache** scoped to non-RSS modes, keyed on
   `(indexer_id, query, frozenset(category_ids))` with a per-
   indexer TTL (default 60 minutes).

This feature ships **functions, not crons**. The Tasks/Scheduler
spec wires `run_missing_search()` to a cron; this spec just
exposes the function.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: SQLAlchemy 2.0 (async), Pydantic v2,
Alembic, `rapidfuzz>=3.6` (fuzzy title matching at threshold 85),
structlog. **No new HTTP client.** httpx + the already-shipped
`NewznabClient` carry the network side.
**Storage**: SQLite default / PostgreSQL 15+ optional. Three new
tables: `blocklist`, `search_history`, `search_cache`. One column
addition: `indexer.rss_auto_grab BOOLEAN NOT NULL DEFAULT true`
(introduced by this feature's migration).
**Testing**: pytest, pytest-asyncio, pytest-cov, hypothesis (purity
property tests on the pipeline), respx (indexer mocks via the
existing `NewznabClient`), freezegun (cache-TTL tests),
TestClient (FastAPI endpoints). Fixture corpora ≥ 50 results for
the scoring/rejection coverage.
**Target Platform**: Linux server in the Romarr Docker image.
**Project Type**: Backend Python module added under
`src/romarr/search/`.
**Performance Goals**:
- Scoring 100 indexer results post-network in < 200 ms (SC-003).
- Manual search across 5 indexers in < 8 s p95 (constitutional
  budget from Article XVI; consumed here).
- Cache lookup at < 5 ms p95 (one indexed read).
- A scheduled missing-search batch of 50 Games dispatching to 5
  indexers fits in a 30-second window (network bound).
**Constraints**:
- Pipeline pure (FR-016) — no per-result DB round-trips.
- Result hard cap 200 per indexer per query (FR-029).
- Cache always missed by RSS sync (FR-027).
- Round-robin distribution across indexers (FR-007).
**Scale/Scope**:
- Wanted catalog: tens of thousands of Releases worst case.
- Results per round: hundreds typical, capped at 200/indexer/query.
- Search-history rows: a few per Game per day; the table grows
  linearly and gets a periodic prune from the Tasks spec.
- Cache rows: bounded by `(indexer_count) × (queries_in_window)`;
  a few thousand at most.

## Constitution Check

*Gate: must pass before Phase 0 research and again after Phase 1 design.*

| Article | Gate | Status |
|---------|------|--------|
| III — Technology Stack (Locked) | SQLAlchemy 2.0 async, Pydantic v2, Alembic, httpx via existing client, RapidFuzz (well-maintained Python library, allowed under Article VIII's "well-maintained Python library" allowance for non-protocol code). | ✅ Conformant. |
| V — Profile-Driven Decisions | Every grab/upgrade/import decision flows from the existing profile system; this spec composes them, never duplicates them. | ✅ Conformant — encoded in FR-009 to FR-016. |
| VII — Indexer Strategy (Prowlarr-first) | Romarr does not implement indexer-specific protocols here; every search call goes through the existing Newznab/Torznab client and the foundation hash-match cascade. | ✅ Conformant. |
| XVI — Quality Gates | ≥ 75% coverage on `search/`; perf targets above; zero ruff warnings. | ✅ Conformant — encoded in SC-009 + Hardening phase. |
| XVII — Idempotency & Safety | Pure pipeline (FR-016); blocklist auto-protects against re-grabbing known-bad releases; manual grab endpoint requires `?force=true` to bypass blocklist; cache deletion of orphaned rows is idempotent. | ✅ Conformant — encoded in FR-016, FR-020 to FR-022. |

**Result**: GREEN. No constitutional violations; **Complexity
Tracking** stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/007-search-decision-engine/
├── plan.md              # this file
├── spec.md              # user-value specification
├── data-model.md        # 3 new tables + indexer column + score-breakdown types
├── tasks.md             # 8-phase task list
└── checklists/
    └── requirements.md  # spec-quality checklist
```

### Source Code (additions to the existing repo)

```text
src/romarr/
├── search/                              # NEW — top-level module
│   ├── __init__.py                       # public re-exports: SearchEngine, run_*; the 5 search-mode entry points
│   ├── types.py                          # Candidate, ScoreBreakdown, Rejection, SearchRoundReport
│   ├── errors.py                         # SearchError, NoEligibleCandidatesError, BlocklistedReleaseError, OverCapWarning
│   ├── query_builder.py                  # PURE: build_queries(game, platform) -> list[Query]
│   ├── matching.py                       # PURE: hash-match-then-fuzzy resolve_to_game(result, monitored_games) -> Game | None
│   ├── pipeline.py                       # PURE: run_pipeline(result, profiles, custom_formats, blocklist, dat_lookup) -> Decision
│   ├── candidates.py                     # PURE: select_winners(candidates) -> dict[release_id, Candidate]
│   ├── cache.py                          # async SearchCache helpers (get/put/invalidate)
│   ├── blocklist.py                      # async blocklist helpers
│   ├── history.py                        # async search-history helpers
│   ├── rounds/
│   │   ├── __init__.py
│   │   ├── manual.py                     # run_manual_search(query, indexer_ids, platform_id, strict)
│   │   ├── on_add.py                     # run_search_on_add(game) — best-effort
│   │   ├── missing.py                    # run_missing_search(limit=50)
│   │   ├── cutoff.py                     # run_cutoff_search(limit=50)
│   │   └── rss.py                        # run_rss_sync()
│   ├── dispatch.py                       # hand the winning Candidate to spec-005's route_release(...)
│   ├── models.py                         # Blocklist + SearchHistory + SearchCache SQLAlchemy 2.0 models
│   ├── schemas.py                        # Pydantic schemas (read/create/update + RoundReport)
│   └── api/                              # FastAPI router stubs
│       ├── __init__.py
│       ├── search.py                     # /api/v3/rom/search/*
│       ├── grab.py                       # /api/v3/rom/release/grab
│       ├── command.py                    # /api/v3/command (Sonarr compat)
│       ├── history.py                    # /api/v3/rom/search/history
│       └── blocklist.py                  # /api/v3/blocklist*
└── db/
    └── alembic/
        └── versions/
            └── 0007_search.py             # NEW migration: 3 tables + the indexer.rss_auto_grab column

tests/
├── search/
│   ├── conftest.py                       # respx fixtures, sample profile / library fixtures, mock NewznabClient
│   ├── test_models.py
│   ├── test_migration_0007.py
│   ├── test_query_builder.py             # canonical + alt-names + platform-name + manufacturer (FR-006)
│   ├── test_matching.py                  # hash-then-fuzzy with RapidFuzz threshold 85 (FR-009)
│   ├── test_pipeline.py                  # 50-result fixture corpus (SC-002)
│   ├── test_pipeline_purity.py           # hypothesis: 1k randomized inputs (FR-016 + SC-001)
│   ├── test_pipeline_perf.py             # 100-result corpus < 200 ms (SC-003)
│   ├── test_candidates.py                # tie-breaking determinism (FR-017)
│   ├── test_cache.py                     # TTL boundaries, RSS bypass (SC-007)
│   ├── test_blocklist.py                 # auto-add on import-fail; CRUD (FR-021)
│   ├── test_history.py                   # row shape per round
│   ├── rounds/
│   │   ├── test_manual.py                # strict=true filters; default annotates would_auto_reject
│   │   ├── test_on_add.py                # best-effort + indexer-down handling
│   │   ├── test_missing.py               # limit=50 oldest-first (SC-004)
│   │   ├── test_cutoff.py                # below-cutoff trigger (SC-005)
│   │   └── test_rss.py                   # threshold > 0 + indexer rss_auto_grab=false
│   ├── test_overcap_warning.py           # 200-result hard cap (SC-008, FR-029)
│   └── api/
│       ├── test_search_endpoints.py
│       ├── test_grab_endpoint.py         # ?force=true override
│       ├── test_command_endpoint.py      # Sonarr-compat names
│       ├── test_history_endpoint.py
│       └── test_blocklist_endpoints.py
└── fixtures/
    ├── search/
    │   ├── results_50_corpus.jsonl       # 50 mixed indexer results with expected outcomes
    │   ├── overcap_indexer_response.xml  # 250-item Torznab response
    │   └── grab_payloads/                # Sonarr-compat command payloads
```

**Structure Decision**: keep the **pipeline pure** in
`pipeline.py` and the **round orchestrators** in `rounds/*.py`. The
orchestrators are async (they read from indexers, the cache, and
the database); the pipeline they call is sync and pure. This split
makes the constitutional purity gate (FR-016) trivially testable
and lets the round orchestrators be small enough to skim
end-to-end.

The candidates selector (`candidates.py`) is also pure: it consumes
a list of pipeline outcomes and emits the per-Release-slot winners
with deterministic tie-breaking.

The cache (`cache.py`) is intentionally on its own module — its
TTL/freezegun tests are independent of indexer mocks.

## Phase 0 — Research

Three small research items resolved before code; results captured
in `research.md` if confirmation is needed at code time.

1. **RapidFuzz threshold and locale** — `rapidfuzz.fuzz.WRatio` at
   threshold 85 is the documented default in the *arr ecosystem.
   Operators may override later via config; for MVP we hardcode
   85 and rely on the fuzzy matcher's case-insensitive,
   accent-folding behaviour by passing the `processor` argument set
   to `lambda s: s.lower()`.
2. **Cache key shape** — `(indexer_id, query.lower().strip(),
   frozenset(category_ids))`. We hash this tuple to a 32-character
   hex digest stored as the lookup column to keep the index small.
3. **Pure-pipeline preload pattern** — at the top of every search
   round, the orchestrator preloads: enabled profiles for the
   target Library, enabled custom formats, the blocklist, the
   monitored Game catalogue (slim shape: id, platform_id, slug,
   sort_title, alt_names). The pipeline then takes those as
   arguments and never re-reads the DB. This is the same pattern
   the Profiles spec uses for its evaluator.

No further research items.

## Phase 1 — Design Outputs

- `data-model.md` — DDL for `blocklist`, `search_history`,
  `search_cache`; the column addition on `indexer`; the
  `Candidate` / `ScoreBreakdown` / `Rejection` value types.
- No `contracts/` — endpoint stubs only; full payload schemas live
  in the API spec.
- No `quickstart.md` — a REPL one-liner showing
  `await SearchEngine.run_manual_search(...)` lives in the wrap-up
  phase of `tasks.md`.

### Re-check: Constitution after design

Same table as above; nothing in the design pulls a constraint.
**Result**: GREEN.

## Complexity Tracking

> *Empty.* No constitutional violations. No deviations to justify.

## Clarification Deltas (Session 2026-04-29)

The 5 clarifications recorded in `spec.md` add the following architectural
constraints to this plan:

- **Global blocklist scope** (FR-020a) — `blocklist` rows have NO
  `library_id` column. A `(indexer_id, indexer_guid)` or hash entry
  excludes the release from search rounds across every library.
  `?force=true` on manual grab is the per-call escape hatch.
- **Per-Game search-round coalesce lock** (FR-016a) — concurrent search
  rounds against the same Game share a single in-flight round via a
  per-Game in-process advisory lock. Watchdog TTL: 5 minutes. Second
  caller blocks and receives the same `search_history` row id.
  Mirrors spec 002's metadata refresh-coalesce.
- **`search_cache` 10k-row LRU cap** (FR-028a) — schema gains
  `search_cache.last_read_at`. Cache hits update it. INSERT past 10,000
  rows triggers a single bulk DELETE down to 9,000 (LRU with hysteresis).
- **Auto-blocklist content-correctness only** (FR-021 rewritten) —
  the importer (spec 008) is the producer of failure subreasons. Only
  `hash-mismatch`, `dat-rejected`, `format-corrupt`,
  `archive-extraction-failed` cause an auto-blocklist entry. Transient/
  operational subreasons (`disk-full`, `permission-denied`,
  `client-unreachable`, `move-failed`, `scan-timeout`) record in
  `search_history` but do NOT call the helper.
- **Admin-only mutations** (FR-030a) — POST `/search/manual`,
  POST `/search/release/{id}`, POST `/release/grab`, POST `/command`,
  POST `/blocklist`, DELETE `/blocklist/{id}` all require admin role.
  Reads (`GET /search/history`, `GET /blocklist`) accessible to any
  authenticated user.

### Migration delta

`0007_search.py` adds to `search_cache`:
- `last_read_at TIMESTAMP NOT NULL DEFAULT (current_timestamp)`
- Index on `last_read_at` for the LRU eviction query.

`blocklist` schema is unchanged (no `library_id` column needed).
