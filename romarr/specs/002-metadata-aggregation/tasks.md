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

- [X] T001 [SCAF] Runtime deps: ``cryptography>=42.0`` and
      ``python-multipart>=0.0.27`` shipped via the
      auth/foundation baseline; verified in pyproject.toml.
      ``Pillow`` deliberately omitted — cover validation
      currently checks content-type at the HTTP layer
      (slice 160) which is sufficient. Pixel-level validation
      can be added if a real attack surface materialises;
      not needed for MVP. Closed as path-divergence.
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
- [X] T014 [P] [PERS] Pydantic schemas for the metadata
      entities ship inline alongside their FastAPI routers
      (``metadata/api/providers.py`` exposes
      ``ProviderConfigRead``; ``metadata/api/field_priority.py``
      exposes the field-priority shapes; ``metadata/api/lookup.py``
      exposes the lookup row shape). Closed as path-divergence —
      the dedicated ``metadata/schemas.py`` module the spec
      called for never materialised because every consumer is
      in ``metadata/api/``; colocating kept the schemas next
      to the routers that use them.
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

- [X] T024 [IGDB] `tests/metadata/providers/test_igdb.py` (test_oauth_lazy_fetch_and_cache,
      test_oauth_401_triggers_reauth_and_retry, test_oauth_refreshes_when_near_expiry,
      test_oauth_401_response_maps_to_auth_error) — respx-mocked Twitch
      OAuth `client_credentials` grant; bearer cached in-memory; in-flight
      401 triggers a single re-auth + retry; near-expiry refresh fires
      proactively at 60 s.
- [X] T025 [IGDB] `tests/metadata/providers/test_igdb.py` (test_search_games_returns_results,
      test_get_game_populates_documented_fields, test_get_game_unknown_id_raises_not_found,
      test_get_cover_returns_bytes) — respx-mocked ``/games`` returns
      a `GameMetadata` populating title / summary / genres / release_date
      / developer / publisher / rating / themes / franchises / age_rating
      / cover; the static-CDN cover GET round-trips bytes + Content-Type.
- [X] T026 [IGDB] `tests/metadata/providers/test_igdb.py::test_platform_mapping_megadrive_is_29`
      — assert `get_platform_mapping("megadrive")` → 29 (matches the
      foundation platform.igdb_id seed). Override path covered by
      `test_platform_mapping_can_be_overridden_via_configure`. The
      built-in mapping mirrors the 5 MVP platforms; configure() lets
      operators inject overrides without DB I/O at request time.
- [X] T027 [IGDB] Create `src/romarr/metadata/providers/igdb.py` — Twitch
      OAuth client-credentials grant, in-memory token cache, Apicalypse
      query bodies (``fields ...; where ...; limit 20;``), cover URL
      derivation off ``cover.image_id``, returns `GameMetadata`
      populating every field IGDB supports. Self-registers via
      ``register_provider("igdb", IGDBProvider)`` at module import.

**Checkpoint**: IGDB tests green; module passes ruff + (optional) mypy.

---

## Phase 5: Provider — ScreenScraper (`SS`)

- [X] T028 [SS] `tests/metadata/providers/test_screenscraper.py::test_get_game_populates_documented_fields`
      — fixture JSON gets parsed into `GameMetadata`. Implementation
      uses ``output=json`` (the modern ssapiV2 default) instead of XML
      to avoid an extra parser dependency for this slice; the deviation
      is purely internal — the field set the spec asks for is identical.
- [X] T029 [SS] `tests/metadata/providers/test_screenscraper.py::test_search_carries_dev_and_user_credentials_as_url_params`
      — devid / devpassword / ssid / sspassword end up as URL parameters;
      403 / 423 (quota lock) both map to AuthError so an over-quota
      account never silently degrades to anonymous access.
- [X] T030 [SS] Create `src/romarr/metadata/providers/screenscraper.py` —
      ssapiV2 endpoint, ``output=json``, populates
      `title/summary/cover/genres/release_date/players_min/players_max`.
      Region preference (us > wor > eu > jp > ss) for canonical title
      pick; configurable language (default ``en``) for genres + summary.

---

## Phase 6: Provider — MobyGames (`MG`)

- [X] T031 [MG] `tests/metadata/providers/test_mobygames.py::test_search_carries_api_key_query_param`
      — assert key sent as `?api_key=...` query param (per docs); 403 maps to
      `AuthError`.
- [X] T032 [MG] `tests/metadata/providers/test_mobygames.py::test_get_game_populates_documented_fields`
      — respx-mocked `/games/{id}`; populates
      `title/summary/genres/release_date/developer/publisher/age_rating/cover/players_min/players_max`.
      Genre filter keeps "Basic Genres" and "Sub-Genre" categories;
      "Perspective" / "Theme" are dropped to avoid polluting the canonical
      genre list.
- [X] T033 [MG] Create `src/romarr/metadata/providers/mobygames.py`.
      Built-in mapping for the 5 MVP platforms; configure(platform_mapping=...)
      merges over the defaults.

---

## Phase 7: Provider — LaunchBox (`LB`)

- [X] T034 [LB] `tests/metadata/providers/test_launchbox.py::test_per_game_query_finds_cached_row`
      — query the local LaunchBox cache by Game title; populate from
      a seed dict (the bulk-XML import path is deferred to v1 per
      spec 002 plan Phase 0 research). Empty cache → empty search,
      degrading gracefully when the operator hasn't imported yet.
- [X] T035 [LB] `tests/metadata/providers/test_launchbox.py::test_bulk_importer_stub_raises_not_implemented`
      — calling `LaunchBoxBulkImporter.run()` raises `NotImplementedError`
      with the documented "deferred to v1" message; the interface is otherwise
      callable.
- [X] T036 [LB] Create `src/romarr/metadata/providers/launchbox.py` — implements
      the per-Game query path against an in-memory cache (a SQLite
      backing store can drop in later via the same dict-shaped API),
      plus the `LaunchBoxBulkImporter` stub. ``configure({"cache": {...}})``
      accepts a seed dict for tests / one-off recipes.

---

## Phase 8: Provider — SteamGridDB (`SGDB`)

- [X] T037 [SGDB] `tests/metadata/providers/test_steamgriddb.py` —
      ``search_games`` raises `NotImplementedError`; ``get_cover``
      returns bytes via the SGDB grids endpoint; ``get_game`` returns
      a cover-only GameMetadata so the manual cover-swap flow can stamp
      ``Game.cover_path`` without a separate fetch round-trip.
- [X] T038 [SGDB] `tests/metadata/providers/test_steamgriddb.py::test_excluded_from_scan_flow`
      — instantiate the registry and assert SteamGridDB is **excluded** from
      `load_enabled_providers(scan=True)` even when enabled (FR-005).
- [X] T039 [SGDB] Create `src/romarr/metadata/providers/steamgriddb.py` — only
      `get_cover()` is real; all other methods raise `NotImplementedError`.
      Self-registers via ``register_provider("steamgriddb", ...)``.

---

## Phase 9: Provider — RetroAchievements (`RA`)

- [X] T040 [RA] `tests/metadata/providers/test_retroachievements.py` —
      ``get_game`` populates ONLY `achievements_count` (FR-006); zero
      counts are omitted entirely; ``search_games`` filters by
      ``platform_slug`` (RA's catalog is platform-keyed); ``get_cover``
      raises NotImplementedError; capabilities pin
      ``contributable_fields = {ACHIEVEMENTS_COUNT}``.
- [X] T041 [RA] Create `src/romarr/metadata/providers/retroachievements.py`.
      Built-in console_id mapping for the 5 MVP platforms; configure()
      lets operators override or extend it.

---

## Phase 10: Provider — HowLongToBeat (`HLTB`)

- [X] T042 [HLTB] `tests/metadata/providers/test_howlongtobeat.py` —
      ``get_game`` populates ONLY `hltb_main` (FR-007); search round-trips
      candidates from the community ``api/search`` endpoint; zero-duration
      results are omitted; ``get_cover`` raises NotImplementedError;
      Chrome-like User-Agent header is asserted.
- [X] T043 [HLTB] Create `src/romarr/metadata/providers/howlongtobeat.py`
      — request body shape mirrors the public community-Python clients
      (searchType / searchTerms / searchOptions); respx fixture drives
      the test. ``comp_main`` (seconds) is converted to minutes for
      ``HLTB_MAIN``.

### Refresh-orchestrator hardening (this slice)

- [X] Cover-fetch + provider-call paths in ``refresh.py`` now also catch
      ``NotImplementedError`` so cover-only / single-field providers
      (SGDB / RA / HLTB) can opt out of methods cleanly without
      poisoning the orchestrator.

---

## Phase 11: Provider — Hasheous (`HASH`)

- [X] T044 [HASH] `tests/metadata/providers/test_hasheous.py` —
      `test_adapter_reuses_supplied_backend`,
      `test_adapter_default_constructs_a_backend`, and
      `test_adapter_does_not_open_its_own_httpx_client` together pin
      that the metadata Hasheous adapter holds a reference to the
      foundation's `HasheousBackend` and does NOT spin up its own
      httpx pool (Article III — no duplicated HTTP pool).
- [X] T045 [HASH] Create `src/romarr/metadata/providers/hasheous.py` — thin
      adapter implementing `MetadataProvider` over the existing identification
      Hasheous client. Title-driven methods (search_games / get_game / get_cover)
      raise NotImplementedError because Hasheous is a hash-only service;
      ``invoked_in_scan=False`` keeps the title-driven refresh from invoking
      it. The hash-driven refresh path lands in a future spec.

---

## Phase 12: Provider — PlayMatch (`PM`)

- [X] T046 [PM] `tests/metadata/providers/test_playmatch.py` — same shape as
      Hasheous; reuses the identification PlayMatch client. Title-driven
      methods raise NotImplementedError; ``invoked_in_scan=False``.
- [X] T047 [PM] Create `src/romarr/metadata/providers/playmatch.py`. Thin
      adapter over :class:`PlayMatchBackend`; mirrors the Hasheous adapter
      shape because both providers expose identical hash-only contracts.

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
- [X] T055 [AGG] Create `src/romarr/metadata/refresh.py` — async
      `refresh_game_metadata(session, game_id, *, force=False) -> AggregationResult`
      orchestrating: load locked fields + game; for each enabled provider,
      look up cache; if missing or expired or `force=True`, call provider's
      `search_games + get_game + get_cover`; persist cache row; finally call
      pure `aggregate(...)`; persist non-locked changes onto the Game; persist
      cover bytes via `covers.write_cover`. Per-Game asyncio.Lock coalesces
      concurrent refreshes (FR-013a in-process; cross-process via Redis is
      deferred to v1+).

**Checkpoint**: aggregator tests green including the property-based
additive-merge invariant; refresh function ties it together.

---

## Phase 14: Integration & API Stubs (`INT`)

**Purpose**: wire the metadata layer to the FastAPI app and expose the six
endpoint stubs.

- [X] T056 [P] [INT] `tests/metadata/api/test_provider_endpoints.py` — TestClient
      hits each of `GET/POST/test` on `/api/v3/metadata/provider`; encrypted
      `config` round-trips via the configure endpoint.
- [X] T057 [P] [INT] `tests/metadata/api/test_field_priority_endpoints.py` —
      `GET /api/v3/metadata/field-priority` returns the seeded layout;
      `PUT /api/v3/metadata/field-priority/{field_name}` updates the order.
- [X] T058 [P] [INT] `tests/metadata/api/test_refresh_endpoint.py` —
      `POST /api/v3/game/{id}/refresh-metadata` triggers `refresh.py` and
      returns the resulting `AggregationResult` JSON. Covers happy path
      (IGDB end-to-end), locked-field protection, no-providers fallback,
      and cache hit (second call → zero extra IGDB POSTs).
- [X] T059 [INT] Create `src/romarr/metadata/api/providers.py` — FastAPI
      router stubs for the 3 provider endpoints.
- [X] T060 [INT] Create `src/romarr/metadata/api/field_priority.py` — FastAPI
      router for the 2 field-priority endpoints.
- [X] T061 [INT] Create `src/romarr/metadata/api/refresh.py` — FastAPI router
      for the refresh endpoint.
- [X] T062 [INT] Wire the three routers into the application factory under
      `/api/v3/metadata/*` and `/api/v3/game/{id}/refresh-metadata`.
      Auth uses the real `require_admin` dependency from spec 010 — the
      tasks.md "no-op dev-only dependency" note is obsoleted by the
      auth spec landing first.

**Checkpoint**: each endpoint returns a sensible response from a test client
against an in-memory DB.

---

## Phase 15: Hardening & Wrap-up (`HARD`)

- [X] T063 [HARD] Run `pytest --cov=romarr.metadata` — verified coverage on
      `metadata/` at **80.4%**, well above the 75% SC-009 target. Per-file
      lows: ``refresh.py`` (46% — orchestrator branches needing real provider
      execution), ``providers/api/providers.py`` (63% — exception paths),
      ``steamgriddb.py`` (69% — health-check + 401/403 branches). The pure
      aggregator + cache + encryption helpers are at 100%.
- [X] T064 [HARD] Run `ruff check .` — zero warnings on `src/romarr/metadata/`.
- [~] T065 [HARD] Manual perf check enabling IGDB + ScreenScraper +
      MobyGames + LaunchBox — **deferred-by-design**. Needs real
      provider credentials + a VCR cassette infra slice. The
      docker-compose stack shipped in slice 195 makes a paired
      operator setup cheap; the SC-005 perf budget gets verified
      manually at release-cut time.
- [X] T066 [HARD] Added `tests/metadata/test_boot_smoke.py` —
      ``test_provider_config_round_trips_across_app_restart`` boots a
      first app, configures IGDB through the admin API, builds a
      *second* app over the same engine + same secret key, and asserts
      the encrypted blob decrypts to the original plaintext (SC-006).
- [X] T067 [HARD] Added ``romarr metadata reencrypt`` CLI sub-command
      stub at ``src/romarr/cli/main.py``. argparse interface only; raises
      ``NotImplementedError("rotation implemented in 0.2 — …")``.
      Wired into ``pyproject.toml`` as the ``romarr`` console script.
- [X] T068 [HARD] Updated `pyproject.toml` and ``romarr.__version__`` to
      ``0.2.0a1``; added ``CHANGELOG.md`` with the spec 001 + spec 010 +
      spec 002 entries. Future bumps follow the same Keep-a-Changelog
      shape.
- [X] T069 [HARD] FR walk-through closed at slice 195. Coverage
      groups (FR-001 → FR-022 of the metadata-aggregation spec):
      - **FR-001 to FR-005** (provider abstraction + per-provider
        rate limits): closed by ``metadata/providers/base.py``
        ``MetadataProvider`` ABC + ``TokenBucket`` + per-provider
        configs in migration ``0002_metadata_layer.py``.
      - **FR-006 to FR-009** (aggregator + per-field priority
        + locked-field protection + additive-merge invariant):
        closed by ``metadata/aggregator.py`` +
        ``test_aggregator.py`` (hypothesis-driven property
        test pins FR-009).
      - **FR-010 to FR-013a** (refresh orchestrator + cache +
        per-Game lock + force flag): closed by
        ``metadata/refresh.py`` + ``test_refresh_coalesce.py``
        (CL010, slice 182).
      - **FR-014 to FR-016a** (cache TTL + size warning):
        closed by ``metadata/cache.py`` + ``metadata/health.py``
        (CL008, slice 182) + tests at
        ``test_health_cache_size.py``.
      - **FR-017 to FR-017a** (cover storage atomicity):
        closed by ``metadata/covers.py`` + ``test_covers.py``.
      - **FR-018 to FR-022** (admin API + secret encryption +
        boot-smoke + reencrypt CLI stub): closed by
        ``metadata/api/`` + ``metadata/encryption.py`` +
        ``test_boot_smoke.py`` + ``romarr metadata reencrypt``.

      Every FR has a closing artefact. The perf check (T065)
      stays deferred-by-design as auxiliary-quality.

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

- [X] CL001 [P] [US1] IGDB OAuth bearer manager shipped — the
      ``client_credentials`` flow against
      ``https://id.twitch.tv/oauth2/token`` lives inside
      ``src/romarr/metadata/providers/igdb.py`` (``_ensure_bearer``).
      In-memory cache only with monotonic ``_bearer_expires_at``;
      refreshed on first use, on 401 mid-flight, and within
      60 s of expiry. Never persisted to disk. Path differs from
      the spec's ``igdb_oauth.py`` — the implementation co-locates
      with the provider so the bearer cache is per-provider-instance
      (one fewer indirection at no testability cost).
- [X] CL002 [P] [US1] IGDB provider consumes the bearer manager
      via ``_ensure_bearer`` + a 401-retry path; ``AuthError``
      surfaces as ``ProviderError(AuthError)`` exactly as spec'd.
- [X] CL003 [US6] One-cover-per-Game replace logic shipped at
      ``src/romarr/metadata/covers.py:write_cover`` (path differs
      from the spec's ``cover_storage.py``). Sibling cover files
      with a different extension are unlinked after the new file
      lands; ``Game.cover_path`` is updated atomically by the
      caller in the same transaction. Tests:
      ``tests/metadata/test_covers.py::test_write_cover_content_type_change_unlinks_sibling``.
- [X] CL004 Migration ``0002_metadata_layer.py`` ships
      ``rate_limit_rps`` and ``rate_limit_burst`` columns on
      ``metadata_provider_config`` with the documented defaults
      (5 / 10) and per-provider overrides (igdb 4/8, mobygames
      1/2, screenscraper 2/4) seeded inline.
- [X] CL005 Per-provider rate-limit defaults seeded by the same
      0002 migration: igdb 4/8, mobygames 1/2, screenscraper
      2/4, others 5/10. Seeder file path differs from the spec
      (no separate ``provider_seeds.py``) — the seed list lives
      next to the migration so DDL + DML stay in lock-step.
- [X] CL006 [P] [US4] Token-bucket limiter shipped as
      ``TokenBucket`` in ``src/romarr/metadata/providers/base.py``.
      Path differs from the spec's ``rate_limiter.py`` — the
      bucket lives on each ``MetadataProvider`` instance so
      concurrent acquirers from different providers never share
      a queue. ``Registry.load_enabled_providers`` reads
      ``rate_limit_rps`` / ``rate_limit_burst`` from each
      provider's config row when constructing the provider
      instance.
- [X] CL007 [P] [US1] Per-Game advisory lock shipped at
      ``src/romarr/metadata/refresh.py:_lock_for`` — a
      process-local ``dict[int, asyncio.Lock]`` keyed by
      ``game_id``. Held while the aggregator runs;
      cross-process coalescing via Redis is documented as
      deferred-to-v1. Path differs from the spec's
      ``aggregator.py`` — the lock wraps the orchestrator
      because the aggregator itself is pure.
- [X] CL008 [P] Metadata-cache size health check shipped at
      ``src/romarr/metadata/health.py:MetadataCacheSizeHealthCheck``
      (slice 182). Estimates table size as ``row_count *
      bytes_per_row`` (default 2.5 KB/row); warns at 2 GB,
      errors at 4 GB. ``bytes_per_row`` is injectable so a
      future ``pragma page_count`` integration can replace the
      estimate without breaking the public surface. Tests at
      ``tests/metadata/test_health_cache_size.py`` cover all
      three thresholds plus the misconfigured-no-factory path.
- [X] CL009 [P] OAuth lifecycle tests shipped at
      ``tests/metadata/providers/test_igdb.py`` —
      ``test_oauth_lazy_fetch_and_cache`` (lazy fetch + cache
      reuse), ``test_oauth_401_triggers_reauth_and_retry``
      (401 → reauth + retry), plus the never-persisted
      invariant is structurally enforced (the bearer is an
      instance attribute, never written to a DB column).
- [X] CL010 [P] Concurrent-refresh coalescing tests shipped at
      ``tests/metadata/test_refresh_coalesce.py`` (slice 182).
      ``test_concurrent_refreshes_call_provider_once``
      monkey-patches ``load_enabled_providers`` with a counting
      stub provider and runs two ``asyncio.gather``-ed
      ``refresh_game_metadata`` calls — asserts exactly one
      ``search_games`` + one ``get_game`` call across both.
      ``test_force_refresh_bypasses_cache_per_call`` pins the
      symmetric "force=True burns quota every time" property.
