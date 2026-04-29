---

description: "Granular task list for metadata aggregation — 9 providers + aggregator + integration"
---

# Tasks: Metadata Aggregation

**Input**: Design documents from `specs/002-metadata-aggregation/`
**Prerequisites**: `001-foundation` shipped (Game, Platform, locked_fields)
**Tests**: MANDATORY (Constitution Article XVI; SC-009: ≥75% coverage on metadata/)

**Organization**: 15 phases. The user explicitly asked for one phase per provider client
(9 phases) plus an aggregator phase plus an integration phase; scaffolding, persistence,
provider framework, and hardening sit around them.

## Format: `[ID] [P?] [Phase] Description`

- `[P]` = parallelizable with other `[P]` tasks in the same phase.
- Phase tag short codes: `SCAF`, `PERS`, `FRAME`, `IGDB`, `SS`, `MG`, `LB`, `SGDB`,
  `RA`, `HLTB`, `HASH`, `PM`, `AGG`, `INT`, `HARD`.

---

## Phase 1: Scaffolding (`SCAF`)

**Purpose**: extend the project with the metadata-layer skeleton, dependencies, and
test harness — no provider logic yet.

- [ ] T001 [SCAF] Update `pyproject.toml` — add runtime deps (`cryptography`,
      `Pillow`, `python-multipart`) and dev deps (`respx` already present from
      foundation). Note: `cryptography` and `python-multipart` already shipped via
      auth/foundation; `Pillow` deferred until the cover-validation slice
      actually needs it.
- [X] T002 [P] [SCAF] Create `src/romarr/metadata/__init__.py` exposing
      `refresh_game_metadata`, `Aggregator`, and the provider registry.
- [X] T003 [P] [SCAF] Create `src/romarr/metadata/errors.py` — `ProviderError`,
      `AuthError`, `RateLimitError`, `NotFoundError`, `TransientError`.
- [X] T004 [P] [SCAF] Create `src/romarr/metadata/types.py` — `ProviderField`
      `StrEnum`, `GameSearchResult`, `GameMetadata`, `AggregationResult` Pydantic
      models from `data-model.md`.
- [X] T005 [P] [SCAF] Extend `src/romarr/config/settings.py` with `auth_secret_key:
      SecretStr | None` and `cover_storage_path: Path = Path("data/covers")`. Settings
      MUST refuse to load when the metadata layer is enabled and `auth_secret_key`
      is None and the database has at least one encrypted config row (FR-021).
      (auth_secret_key + data_dir already present from spec 010 work; encryption
      helper raises EncryptionKeyMissingError on use when key is empty.)
- [X] T006 [SCAF] Extend `tests/conftest.py` with a `respx_mock` fixture and a
      `fake_secret_key` fixture; create `tests/metadata/conftest.py` for module-
      local fixtures. (metadata_env fixture isolates per-test secret key + data dir.)

**Checkpoint**: imports work, lint+types green; no behaviour added yet.

---

## Phase 2: Persistence (`PERS`)

**Purpose**: 3 new tables, the `game.needs_metadata_refresh` column, and the
encryption helper.

### Tests (write first; must fail)

- [X] T007 [P] [PERS] `tests/metadata/test_encryption.py` — round-trip a JSON
      payload through `encrypt()`/`decrypt()`; assert ciphertext is **not**
      JSON-parseable; assert decrypt with a wrong key raises
      `cryptography.fernet.InvalidToken`.
- [X] T008 [P] [PERS] `tests/metadata/test_cache.py::test_ttl_boundary` — write a
      cache row with `expires_at = now + 1s`, advance `freezegun` past it, assert
      the cache lookup treats the row as expired.
- [X] T009 [P] [PERS] `tests/metadata/test_cache.py::test_unique_provider_game` —
      attempting to insert a second `(provider_name, provider_game_id)` pair for
      the same game raises an `IntegrityError`.
- [X] T010 [P] [PERS] `tests/metadata/test_field_priority.py::test_unique_rank_per_field`
      — two providers cannot share `priority_order` within a field.
- [X] T011 [P] [PERS] `tests/metadata/test_migration_0002.py` — applying
      `0002_metadata_layer.py` against a fresh DB produces 9 seeded provider
      rows, the documented field-priority seed (count-check), and the new
      `game.needs_metadata_refresh` column.

### Implementation

- [X] T012 [PERS] Create `src/romarr/metadata/encryption.py` — scrypt KDF +
      Fernet wrapper; module-level `encrypt(data: bytes) -> bytes`,
      `decrypt(ciphertext: bytes) -> bytes`; raises a clear error when the key
      is unset.
- [X] T013 [P] [PERS] Create `src/romarr/metadata/models.py` (or add to
      `src/romarr/domain/models/metadata.py`) — `MetadataProviderConfig`,
      `MetadataCache`, `FieldPriority` SQLAlchemy 2.0 models matching
      `data-model.md`.
- [ ] T014 [P] [PERS] Create `src/romarr/metadata/schemas.py` — three Pydantic
      schemas per entity (`*Read/*Create/*Update`). (Deferred to API stub
      slice — schemas are only consumed by the FastAPI routers.)
- [X] T015 [PERS] Extend `src/romarr/domain/models/game.py` with
      `needs_metadata_refresh: Mapped[bool]` (default false). (Already shipped
      as part of foundation 0001 baseline — every metadata-target column was
      pre-provisioned to keep the layer purely additive.)
- [X] T016 [PERS] Author `src/romarr/db/alembic/versions/0002_metadata_layer.py`
      — add column, create the 3 tables, insert the 9 provider config rows and
      the field-priority seed verbatim from `data-model.md`. Idempotent.
- [X] T017 [PERS] Create `src/romarr/metadata/cache.py` — async helpers
      `get_cached(session, provider, game_id) -> MetadataCache | None`,
      `put_cached(session, provider, game_id, provider_game_id, data, ttl)`,
      `invalidate_cached(session, provider, game_id)`.
- [X] T018 [PERS] Create `src/romarr/metadata/covers.py` —
      `derive_extension(content_type) -> Literal['jpg','png','webp']`,
      `cover_path(game_id, ext) -> Path`,
      `write_cover(game_id, content_type, data) -> Path` (content-aware overwrite
      via SHA-256 comparison).

**Checkpoint**: `alembic upgrade head` produces a clean DB; all `tests/metadata/`
PERS tests pass.

---

## Phase 3: Provider Framework (`FRAME`)

**Purpose**: shared ABC + retry/circuit-breaker harness reused by every provider.

### Tests

- [X] T019 [P] [FRAME] `tests/metadata/test_registry.py` — registry returns
      enabled providers in `priority_global` order; disabled providers are
      filtered out; an unknown provider name returns `None` without raising.
- [X] T020 [P] [FRAME] `tests/metadata/test_provider_base.py` — concrete subclass
      that implements only `name` and stubs the methods round-trips through the
      registry. (Covers retry policy: AuthError / NotFoundError NOT retried;
      TransientError / RateLimitError retried per tenacity policy.)

### Implementation

- [X] T021 [FRAME] Create `src/romarr/metadata/providers/__init__.py` —
      registry of known providers (mapping `name → class`).
- [X] T022 [FRAME] Create `src/romarr/metadata/providers/base.py` —
      `MetadataProvider` ABC with all 6 methods from spec.md FR-001; a
      `with_retry_and_breaker` decorator using `tenacity` (3 attempts,
      exponential backoff with jitter) wrapped by the existing
      `identification/hashmatch/circuit_breaker` (Constitution Article III: no
      duplicated breaker library). Token-bucket throttle (FR-004a) lives on
      the base class so every provider gets the proactive limiter for free.
- [X] T023 [FRAME] Create `src/romarr/metadata/registry.py` — async
      `load_enabled_providers(session) -> list[MetadataProvider]` that:
      reads `metadata_provider_config`, decrypts each `config_encrypted`, hands
      it to the matching class's `configure()`, and returns instantiated
      objects in `priority_global` order.

**Checkpoint**: registry tests green; can instantiate any one provider class
purely from a test fixture.

---

## Phase 4: Provider — IGDB (`IGDB`)

- [ ] T024 [IGDB] `tests/metadata/providers/test_igdb.py::test_oauth_flow` —
      respx-mocked Twitch OAuth `client_credentials` grant; assert the access
      token is cached in-memory; assert a 401 triggers a single re-auth and
      retry.
- [ ] T025 [IGDB] `tests/metadata/providers/test_igdb.py::test_search_and_get`
      — respx-mocked `/games` and `/covers`; assert the returned
      `GameMetadata` populates the documented fields.
- [ ] T026 [IGDB] `tests/metadata/providers/test_igdb.py::test_platform_mapping`
      — assert `get_platform_mapping("megadrive")` → IGDB platform id 29 (the
      established IGDB id for Mega Drive); the mapping is read from the
      `platform.igdb_id` column populated by foundation.
- [ ] T027 [IGDB] Create `src/romarr/metadata/providers/igdb.py` — Twitch
      OAuth client-credentials grant, in-memory token cache, query language
      bodies (`fields *; search "..."; where platforms = (29);`), cover URL
      derivation, returns `GameMetadata` populating
      `title/summary/genres/release_date/developer/publisher/rating/themes/franchises/age_rating/cover`.

**Checkpoint**: IGDB tests green; module passes ruff + (optional) mypy.

---

## Phase 5: Provider — ScreenScraper (`SS`)

- [ ] T028 [SS] `tests/metadata/providers/test_screenscraper.py::test_xml_parse`
      — fixture `tests/fixtures/providers/screenscraper_game_response.xml` gets
      parsed into `GameMetadata`.
- [ ] T029 [SS] `tests/metadata/providers/test_screenscraper.py::test_user_password_auth`
      — credentials end up as URL parameters; assert no plaintext password in
      logs.
- [ ] T030 [SS] Create `src/romarr/metadata/providers/screenscraper.py` —
      ssapiV2 endpoint, XML → JSON normalization at the boundary, populates
      `title/summary/cover/genres/release_date/players_min/players_max`.

---

## Phase 6: Provider — MobyGames (`MG`)

- [ ] T031 [MG] `tests/metadata/providers/test_mobygames.py::test_api_key_in_header`
      — assert key sent as `?api_key=...` query param (per docs); 403 maps to
      `AuthError`.
- [ ] T032 [MG] `tests/metadata/providers/test_mobygames.py::test_search_and_get`
      — respx-mocked `/games`; populates
      `title/summary/genres/release_date/developer/publisher/age_rating`.
- [ ] T033 [MG] Create `src/romarr/metadata/providers/mobygames.py`.

---

## Phase 7: Provider — LaunchBox (`LB`)

- [ ] T034 [LB] `tests/metadata/providers/test_launchbox.py::test_per_game_query`
      — query the local LaunchBox cache by Game title; populate from a
      fixture XML row.
- [ ] T035 [LB] `tests/metadata/providers/test_launchbox.py::test_bulk_import_stub`
      — calling `LaunchBoxBulkImporter.run()` raises `NotImplementedError`
      with the documented "deferred to v1" message; the interface is otherwise
      callable.
- [ ] T036 [LB] Create `src/romarr/metadata/providers/launchbox.py` — implements
      the per-Game query path against a small SQLite-backed cache, plus the
      `LaunchBoxBulkImporter` stub.

---

## Phase 8: Provider — SteamGridDB (`SGDB`)

- [ ] T037 [SGDB] `tests/metadata/providers/test_steamgriddb.py::test_cover_only`
      — assert `search_games()` raises `NotImplementedError` (covers-only
      provider); `get_cover()` returns bytes for a known SteamGridDB id.
- [ ] T038 [SGDB] `tests/metadata/providers/test_steamgriddb.py::test_excluded_from_scan_flow`
      — instantiate the registry and assert SteamGridDB is **excluded** from
      `load_enabled_providers(scan=True)` even when enabled (FR-005).
- [ ] T039 [SGDB] Create `src/romarr/metadata/providers/steamgriddb.py` — only
      `get_cover()` is real; all other methods raise `NotImplementedError`.

---

## Phase 9: Provider — RetroAchievements (`RA`)

- [ ] T040 [RA] `tests/metadata/providers/test_retroachievements.py::test_achievements_only`
      — populates only `achievements_count`; never contributes to other fields
      (FR-006).
- [ ] T041 [RA] Create `src/romarr/metadata/providers/retroachievements.py`.

---

## Phase 10: Provider — HowLongToBeat (`HLTB`)

- [ ] T042 [HLTB] `tests/metadata/providers/test_howlongtobeat.py::test_durations_only`
      — populates only `hltb_main` (FR-007).
- [ ] T043 [HLTB] Create `src/romarr/metadata/providers/howlongtobeat.py`
      — request body shape mirrors community Python clients; respx fixture
      drives the test.

---

## Phase 11: Provider — Hasheous (`HASH`)

- [ ] T044 [HASH] `tests/metadata/providers/test_hasheous.py::test_reuses_identification_client`
      — assert the metadata Hasheous adapter holds a reference to the
      foundation's `identification/hashmatch/hasheous.py` client and does not
      open its own httpx connection pool.
- [ ] T045 [HASH] Create `src/romarr/metadata/providers/hasheous.py` — thin
      adapter implementing `MetadataProvider` over the existing identification
      Hasheous client; metadata fields come from the IGDB-equivalent payload
      Hasheous proxies.

---

## Phase 12: Provider — PlayMatch (`PM`)

- [ ] T046 [PM] `tests/metadata/providers/test_playmatch.py` — same shape as
      Hasheous; reuses the identification PlayMatch client.
- [ ] T047 [PM] Create `src/romarr/metadata/providers/playmatch.py`.

---

## Phase 13: Aggregator (`AGG`)

**Purpose**: the pure-function lock-aware additive merger. The product's most
constitutional invariant.

### Tests (the heart of the spec)

- [X] T048 [AGG] `tests/metadata/test_aggregator.py::test_locked_field_blocks_overwrite`
      — Game has `locked_fields = {"title"}`; provider returns a different
      title; aggregation never updates the title (US2, SC-002).
- [X] T049 [AGG] `tests/metadata/test_aggregator.py::test_additive_merge_keeps_existing_when_no_provider_contributes`
      — Game has `summary = "X"` from provider A; provider B is added but
      contributes nothing for `summary`; aggregation MUST NOT set `summary` to
      NULL (US3, SC-003).
- [X] T050 [AGG] `tests/metadata/test_aggregator.py::test_higher_priority_provider_wins`
      — provider B has higher priority for `summary`; B contributes a value;
      aggregation persists B's value, not A's.
- [X] T051 [AGG] `tests/metadata/test_aggregator.py::test_priority_change_picks_new_winner_from_same_cache`
      — caches populated for two providers; flip priority order; re-aggregate;
      assert pure-function recompute (no respx assertion until refresh.py
      lands in INT slice; FR-012, US7, SC-007).
- [X] T052 [AGG] `tests/metadata/test_aggregator.py::test_property_additive_merge`
      — hypothesis-generated input states; the post-aggregation
      previously-non-empty, non-locked fields are a superset of the
      pre-aggregation set (the additive-merge invariant; FR-009).
- [X] T053 [AGG] `tests/metadata/test_aggregator.py::test_all_providers_empty_sets_refresh_flag`
      — every cached entry is empty; aggregation sets
      `needs_metadata_refresh = true` (FR-013, US-edge).

### Implementation

- [X] T054 [AGG] Create `src/romarr/metadata/aggregator.py` — pure
      `aggregate(game_id, locked_fields, cached, field_priority) -> AggregationResult`.
      For each `ProviderField`: walk the field-priority list, pick the first
      provider whose cached entry has a non-empty value, skip locked fields.
      Returns `AggregationResult` with `skipped_locked` and the
      `needs_metadata_refresh` flag. Also accepts an optional ``existing``
      mapping so the FR-009 additive-invariant carries pre-existing
      non-locked values forward when no provider contributes.
- [ ] T055 [AGG] Create `src/romarr/metadata/refresh.py` — async
      `refresh_game_metadata(session, game_id, *, force=False) -> AggregationResult`
      orchestrating: load locked fields + game; for each enabled provider,
      look up cache; if missing or expired or `force=True`, call provider's
      `search_games + get_game + get_cover`; persist cache row; finally call
      pure `aggregate(...)`; persist non-locked changes onto the Game; persist
      cover bytes via `covers.write_cover`.

**Checkpoint**: aggregator tests green including the property-based
additive-merge invariant; refresh function ties it together.

---

## Phase 14: Integration & API Stubs (`INT`)

**Purpose**: wire the metadata layer to the FastAPI app and expose the six
endpoint stubs.

- [ ] T056 [P] [INT] `tests/metadata/api/test_provider_endpoints.py` — TestClient
      hits each of `GET/POST/test` on `/api/v3/metadata/provider`; encrypted
      `config` round-trips via the configure endpoint.
- [ ] T057 [P] [INT] `tests/metadata/api/test_field_priority_endpoints.py` —
      `GET /api/v3/metadata/field-priority` returns the seeded layout;
      `PUT /api/v3/metadata/field-priority/{field_name}` updates the order.
- [ ] T058 [P] [INT] `tests/metadata/api/test_refresh_endpoint.py` —
      `POST /api/v3/game/{id}/refresh-metadata` triggers `refresh.py` and
      returns the resulting `AggregationResult` JSON.
- [ ] T059 [INT] Create `src/romarr/metadata/api/providers.py` — FastAPI
      router stubs for the 3 provider endpoints.
- [ ] T060 [INT] Create `src/romarr/metadata/api/field_priority.py` — FastAPI
      router for the 2 field-priority endpoints.
- [ ] T061 [INT] Create `src/romarr/metadata/api/refresh.py` — FastAPI router
      for the refresh endpoint.
- [ ] T062 [INT] Wire the three routers into the application factory under
      `/api/v3/metadata/*` and `/api/v3/game/{id}/refresh-metadata`. NOTE:
      **authentication wiring is deferred to the Auth spec**; this feature
      uses a development-only no-op dependency that always returns an
      `is_admin=True` user.

**Checkpoint**: each endpoint returns a sensible response from a test client
against an in-memory DB.

---

## Phase 15: Hardening & Wrap-up (`HARD`)

- [ ] T063 [HARD] Run `pytest --cov=romarr.metadata` — verify coverage on
      `metadata/` ≥ 75% (SC-009). Add targeted tests for any uncovered
      branch.
- [ ] T064 [HARD] Run `ruff check .` — zero warnings on
      `src/romarr/metadata/`.
- [ ] T065 [HARD] Add manual perf check: enable IGDB + ScreenScraper +
      MobyGames + LaunchBox against a recorded VCR cassette of 100 Games;
      record cold-time and warm-time in `specs/002-metadata-aggregation/research.md`
      against SC-005.
- [ ] T066 [HARD] Add an integration smoke test that boots a minimal
      FastAPI app, encrypts a provider config, restarts the test fixture,
      decrypts it, and confirms it round-trips (SC-006).
- [ ] T067 [HARD] Add a CLI sub-command stub `romarr metadata reencrypt` —
      argparse interface only; raises `NotImplementedError("rotation
      implemented in 0.2")` until the Auth spec lands. Documented in the
      module's README.
- [ ] T068 [HARD] Update `pyproject.toml` `version = "0.2.0a1"`; add a
      one-line note to `CHANGELOG.md`: "0.2.0a1 — Metadata aggregation:
      9 providers, lock-aware aggregator, encrypted config."
- [ ] T069 [HARD] Final review: open `specs/002-metadata-aggregation/spec.md`
      and tick every Functional Requirement (FR-001 → FR-022) against a
      task ID; record any gaps.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (SCAF)**: foundation must be merged.
- **Phase 2 (PERS)**: depends on Phase 1.
- **Phase 3 (FRAME)**: depends on Phase 2 (registry needs the config table).
- **Phases 4–12 (one per provider)**: depend on Phase 3. Within the
  9 provider phases there are no inter-dependencies — they can be developed
  in parallel by 9 contributors. Each provider phase ships its own httpx
  client, normalizer, and tests.
- **Phase 13 (AGG)**: depends on Phase 3 (types) — does NOT depend on the
  provider phases (the aggregator is pure and tests use mocks). The
  refresh-orchestration sub-step within Phase 13 (T055) does depend on at
  least one provider being available.
- **Phase 14 (INT)**: depends on Phase 13.
- **Phase 15 (HARD)**: depends on Phase 14.

### Within-Phase Parallelism

- Phase 1: T002–T005 in parallel.
- Phase 2: T007–T011 (tests) in parallel; T013–T014 (models + schemas) in
  parallel.
- Phase 3: T019, T020 in parallel.
- Phases 4–12: every provider's tests can be written in parallel; the
  implementation files are also independent (one file per provider).
- Phase 13: aggregator tests T048–T053 are independent file-level tests.
- Phase 14: T056–T058 in parallel; routers T059–T061 in parallel; only
  the wiring step T062 is sequential.

### Critical Path

`SCAF → PERS → FRAME → AGG (test side) → INT → HARD`. The 9 provider
phases run in parallel with the aggregator and integration work as soon
as `FRAME` lands. A single contributor can sequence them in priority
order: IGDB → ScreenScraper → MobyGames → Hasheous → PlayMatch →
LaunchBox → RetroAchievements → HowLongToBeat → SteamGridDB.

### Implementation Strategy

- **Day 1**: Phase 1 (scaffolding) + Phase 2 (persistence) — encrypted
  storage and migrations are the highest risk; lock them down early.
- **Day 2**: Phase 3 (framework) + start IGDB.
- **Day 3**: Finish IGDB; start Phase 13 (aggregator pure tests in parallel
  with whichever provider you're on).
- **Day 4–6**: ScreenScraper, MobyGames, Hasheous, PlayMatch (the providers
  that contribute the most useful fields).
- **Day 7**: LaunchBox, RetroAchievements, HowLongToBeat, SteamGridDB.
- **Day 8**: Phase 14 (integration & API stubs).
- **Day 9**: Phase 15 (hardening).

This sizing assumes one developer working full-time. With multiple
contributors, the 9 provider phases are the obvious parallelization
front.

---

## Notes

- `[P]` tasks change different files only.
- Tests are written BEFORE implementation in every phase.
- Stop at any phase checkpoint — the metadata layer is delivered
  incrementally; each phase is independently shippable.
- Avoid: pulling auth wiring (Auth spec); implementing background
  scheduling (Tasks spec); building a UI (UI spec); implementing the
  LaunchBox bulk XML import (deferred to v1); implementing screenshots
  (firm-out per Constitution Article IX); duplicating circuit-breaker
  code from `identification/hashmatch/`.

## Phase: Clarification Tasks (Session 2026-04-29)

- [ ] CL001 [P] [US1] Implement IGDB OAuth bearer manager in `src/romarr/metadata/providers/igdb_oauth.py` — `client_credentials` flow against `https://id.twitch.tv/oauth2/token`; in-memory cache only with `expires_at`; refresh on first use, on 401 mid-flight, and within 60 s of expiry; never persisted (FR-007a)
- [ ] CL002 [P] [US1] Update IGDB provider client in `src/romarr/metadata/providers/igdb.py` to consume the bearer manager; handle `ProviderError(AuthError)` on Twitch OAuth failure
- [ ] CL003 [US6] Implement one-cover-per-Game replace logic in `src/romarr/metadata/cover_storage.py` — write new file at new extension, delete sibling `data/covers/<game_id>.*` with different extension, update `Game.cover_path` atomically (FR-017a)
- [ ] CL004 Migration `0002_metadata.py` adds two columns: `metadata_provider_config.rate_limit_rps INTEGER NOT NULL DEFAULT 5` and `metadata_provider_config.rate_limit_burst INTEGER NOT NULL DEFAULT 10`
- [ ] CL005 Update `metadata_provider_config` seeder in `src/romarr/metadata/seeds/provider_seeds.py` with provider-specific rate limit defaults (igdb 4/8, mobygames 1/2, screenscraper 2/4, others 5/10)
- [ ] CL006 [P] [US4] Implement per-provider token-bucket limiter in `src/romarr/metadata/rate_limiter.py` reading `rate_limit_rps` / `rate_limit_burst` from each provider's config row (FR-004a)
- [ ] CL007 [P] [US1] Add per-Game advisory lock around `MetadataAggregator.refresh_game(...)` in `src/romarr/metadata/aggregator.py` — coalesce concurrent refreshes; lock-holder TTL 5 minutes; second caller receives the first caller's result without re-querying providers (FR-013a)
- [ ] CL008 [P] Implement `metadata_cache` size-warning health-check producer in `src/romarr/metadata/health.py` — emit `OnHealthIssue` when table > 2 GB on disk (FR-016a)
- [ ] CL009 [P] Add tests in `tests/metadata/test_oauth_lifecycle.py` covering bearer expiry, 401 retry, and the never-persisted invariant
- [ ] CL010 [P] Add tests in `tests/metadata/test_refresh_coalesce.py` covering concurrent refresh on the same Game returning the same result
