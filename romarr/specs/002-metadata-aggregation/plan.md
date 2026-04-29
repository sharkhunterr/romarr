# Implementation Plan: Metadata Aggregation

**Branch**: `002-metadata-aggregation` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification at `specs/002-metadata-aggregation/spec.md`
**Depends on**: `001-foundation` (Game, Platform, locked_fields, Alembic baseline)

## Summary

Romarr's metadata aggregation layer delivers three tightly-coupled
subsystems on top of the foundation domain model:

1. **Provider clients** (9 of them: IGDB, ScreenScraper, MobyGames,
   LaunchBox, SteamGridDB, RetroAchievements, HowLongToBeat, Hasheous,
   PlayMatch) sharing a common `MetadataProvider` ABC, each guarded by
   tenacity retries and a per-service circuit breaker.
2. **Persistence** for three new tables (`metadata_cache`,
   `metadata_provider_config`, `field_priority`) plus a thin column
   addition (`needs_metadata_refresh`) on the existing `game` table. A
   small encryption helper protects provider credentials at rest using
   a key derived from `ROMARR_AUTH_SECRET_KEY`.
3. **Aggregator** — a pure-function merger that turns the union of
   cached provider responses into a canonical Game shape, respecting
   per-field priority lists and `locked_fields`. It is **lock-aware**
   and **additive** by construction; the RomM #1770 bug pattern is
   forbidden by the merge function's invariants.

Technical approach: every provider client is async `httpx`; tenacity
guards transient errors; a shared circuit-breaker module (already
introduced in foundation for hash-match cascade) is reused here; the
aggregator is pure Python with no I/O so it can be exhaustively tested
without network. Cover bytes are persisted under `data/covers/` with
the extension chosen from the response Content-Type.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: SQLAlchemy 2.0 (async), Pydantic v2, Alembic,
httpx (async), tenacity, structlog, cryptography (Fernet for symmetric
encryption with a key derived via scrypt KDF), Pillow (cover validation
only — no resizing in MVP), python-multipart for the upload endpoint
stub
**Storage**: SQLite default / PostgreSQL 15+ optional (same SQLAlchemy
models). Cover bytes on the local filesystem under `data/covers/`.
**Testing**: pytest, pytest-asyncio, pytest-cov, respx (httpx mocks for
all 9 providers), freezegun (TTL boundaries), hypothesis (aggregator
property tests on the additive-merge invariant).
**Target Platform**: Linux server, single multi-arch Docker image.
This feature ships as a Python package importable standalone.
**Project Type**: Backend Python module added under `src/romarr/metadata/`.
**Performance Goals**:
- Cold aggregation of 100 Games across 4 enabled providers: < 5 min
  (SC-005).
- Warm aggregation of 100 Games (all caches in-window): < 30 s.
- Cache-only re-aggregation after a priority change: zero outbound
  HTTP (FR-012, SC-007).
**Constraints**:
- Lock-aware merge: previously-populated, non-locked fields must
  never be set to NULL by aggregation (FR-009).
- Encryption at rest for provider credentials (FR-019, FR-021).
- Per-provider circuit breaker reused from `identification/hashmatch/`
  (Constitution Article III: no new circuit-breaker library).
- All providers go through `httpx` async (Constitution Article III:
  no `requests`/`urllib3` direct).
**Scale/Scope**:
- ≤ 9 providers (extensibility hook present, but adding a 10th is a
  separate spec).
- One `metadata_cache` row per (provider, game) pair; expected size
  is ≤ 9 × tens-of-thousands of Games = a few hundred thousand rows
  worst case for a power user.
- Cover storage ≈ a few MB per Game; acceptable on local disk.

## Constitution Check

*Gate: must pass before Phase 0 research and again after Phase 1 design.*

| Article | Gate | Status |
|---------|------|--------|
| III — Technology Stack (Locked) | httpx async, SQLAlchemy 2.0 async, Pydantic v2, Alembic; no `requests`/`urllib3`. | ✅ Conformant. |
| IX — Metadata Aggregation | 9 named providers; per-field priority-ordered; re-matching MUST NOT destroy existing field values; lockable fields skipped; covers stored locally; screenshots out of scope; cache TTL configurable per provider, default 30 days. | ✅ Conformant — encoded in FR-002, FR-008, FR-009, FR-010, FR-011, FR-014, FR-015, FR-017, FR-018. |
| XVI — Quality Gates | ≥ 75% coverage on `metadata/`; zero ruff warnings; mypy strict on `domain/` and `identification/` (this layer is not in the strict set, but should be added later). | ✅ Conformant — encoded in SC-009 and Hardening phase. |
| XVII — Idempotency & Safety | No automatic destructive actions on locked fields; cover overwrite is content-aware; re-ingesting the same response produces no churn. | ✅ Conformant — FR-009, FR-010, edge cases in spec.md. |

**Result**: GREEN. No constitutional violations; **Complexity Tracking** below stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/002-metadata-aggregation/
├── plan.md              # this file
├── spec.md              # user-value specification
├── data-model.md        # 3 new tables + game column addition
├── tasks.md             # 15-phase task list (one phase per provider)
└── checklists/
    └── requirements.md  # spec-quality checklist
```

### Source Code (additions to the existing repo)

```text
src/romarr/
├── metadata/                          # NEW — top-level metadata module
│   ├── __init__.py                    # public re-exports: registry, aggregator, refresh function
│   ├── types.py                       # GameSearchResult, GameMetadata, ProviderField, ProviderCapabilities
│   ├── errors.py                      # ProviderError hierarchy
│   ├── encryption.py                  # ROMARR_AUTH_SECRET_KEY-derived Fernet helper
│   ├── covers.py                      # cover storage helper (path resolution + content-type → extension)
│   ├── registry.py                    # known providers registry; loads from metadata_provider_config
│   ├── cache.py                       # CRUD over metadata_cache + TTL helpers
│   ├── aggregator.py                  # lock-aware, additive, per-field priority merger (PURE)
│   ├── refresh.py                     # synchronous orchestration: search → fetch → cache → aggregate → persist
│   ├── api/                           # FastAPI routers — STUBS only; full impl in API spec
│   │   ├── __init__.py
│   │   ├── providers.py               # GET/POST /api/v3/metadata/provider*
│   │   ├── field_priority.py          # GET/PUT /api/v3/metadata/field-priority*
│   │   └── refresh.py                 # POST /api/v3/game/{id}/refresh-metadata
│   └── providers/
│       ├── __init__.py                # ABC + helpers
│       ├── base.py                    # MetadataProvider ABC, ProviderField enum
│       ├── igdb.py
│       ├── screenscraper.py
│       ├── mobygames.py
│       ├── launchbox.py               # bulk-XML stub + per-Game query path
│       ├── steamgriddb.py             # cover-only, never invoked in scan flow
│       ├── retroachievements.py       # achievements_count only
│       ├── howlongtobeat.py           # hltb_main only
│       ├── hasheous.py                # reuses identification/hashmatch/hasheous client
│       └── playmatch.py               # reuses identification/hashmatch/playmatch client
├── domain/
│   └── models/
│       └── game.py                    # MODIFIED: add `needs_metadata_refresh` boolean column
└── db/
    └── alembic/
        └── versions/
            └── 0002_metadata_layer.py # NEW migration: 3 tables + game column

tests/
├── metadata/
│   ├── conftest.py                    # respx fixtures, fake encryption key
│   ├── test_encryption.py
│   ├── test_covers.py
│   ├── test_cache.py
│   ├── test_aggregator.py             # the lock-aware additive-merge invariants (hypothesis)
│   ├── test_refresh.py
│   ├── test_registry.py
│   └── providers/
│       ├── test_igdb.py               # respx-mocked OAuth + /games + /covers
│       ├── test_screenscraper.py
│       ├── test_mobygames.py
│       ├── test_launchbox.py
│       ├── test_steamgriddb.py
│       ├── test_retroachievements.py
│       ├── test_howlongtobeat.py
│       ├── test_hasheous.py
│       └── test_playmatch.py
└── fixtures/
    ├── covers/
    │   ├── sample.jpg
    │   ├── sample.png
    │   └── sample.webp
    └── providers/
        ├── igdb_game_response.json
        ├── screenscraper_game_response.xml
        ├── mobygames_game_response.json
        ├── launchbox_metadata_partial.xml
        ├── steamgriddb_game_response.json
        ├── retroachievements_game_response.json
        ├── howlongtobeat_game_response.json
        ├── hasheous_lookup_response.json
        └── playmatch_lookup_response.json

data/                                  # gitignored
└── covers/                            # populated at runtime
```

**Structure Decision**: keep providers under
`src/romarr/metadata/providers/`, **not** alongside identification's
hash-match clients. The hash-match cascade in identification/ already
ships Hasheous and PlayMatch clients for hash lookup; in metadata/ we
**reuse** those httpx client objects but build new adapter classes that
implement the `MetadataProvider` ABC. This preserves the constitutional
identification cascade ordering and avoids duplicating HTTP code.

The aggregator is a **pure function**. It takes a `dict[provider_name, GameMetadata]`
plus the field-priority table and the Game's `locked_fields`, and
returns a `dict[field_name, value]` to be merged onto the Game. Pure-
function testing yields fast, deterministic property-based tests for
the additive-merge and lock-aware invariants — the two constitutional
invariants of this feature.

## Phase 0 — Research

Three open technical questions resolved before implementation; results
go into `specs/002-metadata-aggregation/research.md` if confirmation is
needed at code time.

1. **Encryption primitive**: use `cryptography.fernet.Fernet` (AES-128
   CBC + HMAC) with a key derived from `ROMARR_AUTH_SECRET_KEY` via
   `scrypt` (`n=2**14, r=8, p=1`, salt = a constant per-installation
   value seeded into a `metadata_provider_config_meta` table on first
   run). Rotation = decrypt-with-old → re-encrypt-with-new in a single
   transaction.
2. **IGDB OAuth flow**: Twitch's OAuth client-credentials grant. Token
   lifetime ≈ 60 days; we cache the token in-memory and refresh on
   401. We do NOT store the access token at rest — only the Client ID
   + Client Secret are persisted (encrypted).
3. **LaunchBox bulk XML**: skip in MVP. The bulk archive is
   ≈ 200 MB and the per-Game query path is enough for the constitutional
   acceptance bar. Define the import interface (`LaunchBoxBulkImporter`)
   so the v1 spec can drop in the implementation.

No further research items; everything else is locked by the
constitution or is direct provider-API plumbing.

## Phase 1 — Design Outputs

- `data-model.md` — full DDL for the 3 new tables, the
  `game.needs_metadata_refresh` column, indexes, encryption-at-rest
  notes, default field-priority seed.
- No `contracts/` directory — the API endpoints are stubs that wrap
  pure functions in the metadata module. Their full request/response
  schemas live in the API spec.
- No `quickstart.md` — operator-facing quickstart belongs to API + UI
  specs. A REPL one-liner shows up in the wrap-up phase of `tasks.md`.

### Re-check: Constitution after design

Same table as above; nothing changed in design that pulls a constraint.
**Result**: GREEN.

## Complexity Tracking

> *Empty.* No constitutional violations. No deviations to justify.

## Clarification Deltas (Session 2026-04-29)

The 5 clarifications recorded in `spec.md` add the following architectural
constraints to this plan:

- **IGDB OAuth token lifecycle** (FR-007a) — application-managed,
  in-memory only. The IGDB client lazily fetches a bearer via the Twitch
  `client_credentials` flow against
  `https://id.twitch.tv/oauth2/token`. Refresh on first use, on 401 mid
  flight, and when within 60 s of `expires_at`. Bearer MUST NOT be
  persisted to DB or disk. Persisted IGDB credentials remain just
  `client_id` + `client_secret` (encrypted).
- **Cover content-type change replaces atomically** (FR-017a) —
  one-cover-per-Game invariant. New file is written first; any sibling
  `data/covers/<game_id>.*` with a different extension is deleted;
  `Game.cover_path` is updated in the same transaction. The byte-equality
  short-circuit still applies for unchanged content type.
- **`metadata_cache` size bound** (FR-016a) — TTL-only eviction. Unique
  constraint `(provider_name, provider_game_id)` keeps size bounded at
  one row per (provider, Game). No LRU. A health-check warning fires when
  the table exceeds 2 GB on disk; informational only.
- **Per-Game refresh-coalesce lock** (FR-013a) — concurrent
  `refresh-metadata` calls on the same Game share a single in-flight
  refresh via a per-Game advisory lock. Lock-holder TTL: 5 minutes.
  Second caller blocks on the lock and receives the first caller's
  result without re-invoking providers.
- **Per-provider token-bucket rate limiter** (FR-004a) — the aggregator
  proactively throttles outbound requests via a token bucket per provider.
  New columns on `metadata_provider_config`: `rate_limit_rps`,
  `rate_limit_burst`. Defaults seeded on first run: IGDB 4 rps / burst 8;
  MobyGames 1 / 2; ScreenScraper 2 / 4; others 5 / 10. HTTP 429 still
  trips the existing circuit breaker.

### Migration delta

Append two columns to `metadata_provider_config`:
`rate_limit_rps INTEGER NOT NULL DEFAULT 5`,
`rate_limit_burst INTEGER NOT NULL DEFAULT 10`.
Seeder MUST set provider-specific defaults via the seed_key path. See
`data-model.md` updates.
