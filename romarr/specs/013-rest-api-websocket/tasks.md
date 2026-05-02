---

description: "Granular task list for REST API & WebSocket — application factory, middleware, new bridge routers, WS, OpenAPI"
---

# Tasks: REST API & WebSocket

**Input**: Design documents from `specs/013-rest-api-websocket/`
**Prerequisites**: every prior spec shipped — this is the unified surface.
**Tests**: MANDATORY (Constitution Article XVI; SC-008: ≥ 80% on api/)

**Organization**: 11 phases. Scaffolding → app factory → pagination + error
envelope → middleware (GZip / CORS / CSRF / rate-limit / idempotency) →
new bridge routers → WebSocket → OpenAPI customisation → endpoint
integration tests → command bus → Sonarr-shape probe → hardening.

## Format: `[ID] [P?] [Phase] Description`

- `[P]` = parallelizable with other `[P]` tasks in the same phase.
- Phase tag short codes: `SCAF`, `FACTORY`, `ENVELOPES`, `MW`, `ROUTERS`,
  `WS`, `OPENAPI`, `WIRE`, `CMD`, `SONARR`, `HARD`.

---

## Phase 1: Scaffolding (`SCAF`)

- [ ] T001 [SCAF] Update `pyproject.toml` — add runtime deps
      `slowapi>=0.1.9` and `fastapi-csrf-protect>=0.3`; add dev dep
      `openapi-spec-validator>=0.7`.
- [ ] T002 [P] [SCAF] Create `src/romarr/api/__init__.py` exposing
      `create_app`.
- [X] T003 [P] [SCAF] Create `src/romarr/api/models.py` — `Tag`,
      `TagAssignment`, `QueueEntry`, `IdempotencyCache` SQLAlchemy
      2.0 models matching the inline data-model in `plan.md`. Brand
      default `tag.color = #9BBC0F` (spec 014). Round-trip tests
      live in `tests/api/test_models.py` (Tag uniqueness,
      TagAssignment CHECK + cascade, QueueEntry state CHECK +
      native-id uniqueness, IdempotencyCache composite PK).
- [X] T004 [P] [SCAF] Create `src/romarr/api/envelopes.py` —
      `PaginationEnvelope`, `ErrorEnvelope` Pydantic models.
- [X] T005 [SCAF] Author `src/romarr/db/alembic/versions/0013_rest_api.py`
      — DDL for the four new tables (`tag`, `tag_assignment`,
      `queue_entry`, `idempotency_cache`). Reversible. Smoke-tested
      via `tests/api/test_migration_0013.py` (table creation,
      reversibility, documented columns, composite PK on
      `idempotency_cache`, brand-default `tag.color`).
- [ ] T006 [SCAF] Extend `tests/conftest.py` with `app_client`
      (TestClient) and `ws_client` (websockets test helper);
      create `tests/api/conftest.py` for module-local fixtures.

**Checkpoint**: imports work; lint+types green; migration applies.

---

## Phase 2: Application Factory (`FACTORY`)

### Tests

- [X] T007 [P] [FACTORY] `tests/api/test_factory.py::test_creates_app_returns_fastapi_with_documented_shape`
      — `create_app()` returns a FastAPI instance with the documented
      title/version/description and `/api/v3/{docs,redoc,openapi.json}`
      URLs. Plus `test_factory_module_reexports_create_app` pinning
      that `romarr.api.factory.create_app` is the same callable as
      `romarr.api.create_app`.
- [X] T008 [P] [FACTORY] `tests/api/test_factory.py::test_lifespan_starts_scheduler_when_enabled`
      — startup wires the scheduler from spec 012 + the
      `CancellationRegistry` when `app.state._enable_scheduler=True`
      is set before the lifespan starts. Watcher (spec 008),
      heartbeat (spec 009), and health-engine (spec 011) wiring
      remain stubbed (`start_watcher` raises `NotImplementedError`
      until WATCH ships) — added incrementally in their owning
      slices. Companion `test_lifespan_skips_scheduler_when_default`
      pins the test-suite-friendly OFF default.
- [X] T009 [P] [FACTORY] `tests/api/test_factory.py::test_lifespan_shutdown_stops_scheduler`
      — exiting the lifespan triggers the four-phase
      `graceful_shutdown` protocol (FR-021); scheduler's `_started`
      flag flips back to False. The "subsequent requests return
      HTTP 503" half is deferred to the WIRE phase — needs a
      production middleware gate that checks
      `app.state.scheduler` and short-circuits with 503 before
      routes resolve. Tracked as a follow-up under T101+.

### Implementation

- [X] T010 [FACTORY] `src/romarr/api/factory.py` re-exports
      `create_app` from `romarr.api.app` (the implementation lives
      there from earlier slices to avoid the rename churn across
      the seven existing import sites). Today's wiring covers:
      ✓ error-format handlers (existing
      `register_error_handlers`); ✓ all routers from prior specs;
      ✓ lifespan startup: spec 012 scheduler +
      `CancellationRegistry` when `_enable_scheduler=True`;
      ✓ lifespan shutdown: four-phase `graceful_shutdown`
      protocol. Forward-looking pieces extend this factory
      in place:
      1. ❎ MW middleware (Phase 4 — slice TBD)
      2. ❎ bridge routers (Phase 5)
      3. ❎ WebSocket handler (Phase 6)
      4. ❎ OpenAPI customiser (Phase 7)
      5. ❎ watcher / heartbeat / health-engine startup
         (depends on those modules exposing
         `async def start/stop` — currently
         `start_watcher` raises `NotImplementedError`).

**Checkpoint**: FACTORY tests green; the application boots and
shuts down cleanly.

---

## Phase 3: Pagination & Error Envelope (`ENVELOPES`)

### Tests

- [X] T011 [P] [ENVELOPES] `tests/api/test_pagination.py::test_default_params`
      — list endpoint with no params returns
      `{page:1, pageSize:50, sortKey:"id", sortDirection:"asc",
      totalRecords:N, records:[...]}`.
- [X] T012 [P] [ENVELOPES] `tests/api/test_pagination.py::test_pageSize_capped_at_1000`
      — `?pageSize=2000` returns `pageSize=1000` (FR-009).
- [X] T013 [P] [ENVELOPES] `tests/api/test_pagination.py::test_invalid_sortKey_400`
      — `?sortKey=NotARealField` returns HTTP 400 with the canonical
      error envelope (FR-008).
- [ ] T014 [P] [ENVELOPES] `tests/api/test_pagination.py::test_5_endpoints_uniform`
      — table-driven over Game, Release, History, Indexer,
      Notification; assert each accepts the canonical params and
      returns the canonical envelope (SC-003).
- [X] T015 [P] [ENVELOPES] `tests/api/test_envelopes.py` —
      exercises canonical envelope shapes and the existing global
      `HTTPException` handler that produces
      `{errorMessage, errorCode}` for both string + dict details.

### Implementation

- [X] T016 [ENVELOPES] Create `src/romarr/api/pagination.py` —
      `paginate(query, params, *, sortable_keys: dict[str, ...]) ->
      PaginationEnvelope` helper used by every list router.
- [X] T017 [ENVELOPES] The project's existing
      `register_error_handlers` (`src/romarr/api/error_handlers.py`)
      already renders the canonical `ErrorEnvelope` shape for
      `HTTPException` (string + dict detail forms) and pinned by
      `tests/api/test_envelopes.py::test_existing_error_handler_envelope`.
      No new middleware module needed — kept as-is to avoid
      double-registration; will be wired through `factory.py`
      in the FACTORY phase.

**Checkpoint**: ENVELOPES tests green.

---

## Phase 4: Middleware (`MW`)

### Tests

- [X] T018 [P] [MW] `tests/api/middleware/test_gzip.py` —
      4 cases: < 1 KB body uncompressed; > 1 KB body
      `Content-Encoding: gzip`; `Accept-Encoding: identity`
      bypasses; `min_size_bytes=0` opts in to compress every
      response (FR-029, operator-tunable).
- [X] T019 [P] [MW] `tests/api/middleware/test_cors.py::test_default_same_origin_only`
      — empty `ROMARR_CORS_ALLOWED_ORIGINS`; cross-origin request
      reaches the route but the
      `Access-Control-Allow-Origin` header is omitted, so the
      browser rejects the response (FR-030). Companion preflight
      test pins HTTP 400 for OPTIONS from an unknown origin.
- [X] T020 [P] [MW] `tests/api/middleware/test_cors.py::test_configured_origin_*`
      — env var set; matching origin gets the CORS header
      echoed back; non-matching origin gets the header omitted;
      preflight succeeds with `Access-Control-Allow-Credentials`
      for the matching origin.
- [ ] T021 [P] [MW] `tests/api/middleware/test_csrf.py::test_cookie_post_blocked_without_token`
      — cookie-authenticated POST without `X-CSRF-Token` header
      returns HTTP 403 reason `csrf_token_missing` (US7, SC-007).
- [ ] T022 [P] [MW] `tests/api/middleware/test_csrf.py::test_apikey_bypass`
      — POST with `X-Api-Key`; no CSRF token; succeeds (FR-027).
- [ ] T023 [P] [MW] `tests/api/middleware/test_csrf.py::test_get_bypass`
      — GET request; no CSRF check (FR-028).
- [ ] T024 [P] [MW] `tests/api/middleware/test_rate_limit.py::test_login_5_per_minute`
      — 6 logins from one IP in 60 s; 6th returns HTTP 429 with
      `Retry-After` (FR-022, SC-006).
- [ ] T025 [P] [MW] `tests/api/middleware/test_rate_limit.py::test_setup_1_per_minute`
      — 2 setup attempts in 60 s; 2nd returns HTTP 429 (FR-023).
- [ ] T026 [P] [MW] `tests/api/middleware/test_rate_limit.py::test_apikey_100_per_minute`
      — 101st request with same API key in 60 s returns HTTP 429
      (FR-024).
- [ ] T027 [P] [MW] `tests/api/middleware/test_rate_limit.py::test_health_exempt`
      — `GET /api/v3/health` not subject to per-IP rate limit.
- [X] T028 [P] [MW] `tests/api/middleware/test_idempotency.py::test_replay_returns_cached_response`
      — POST /api/v3/tag with `Idempotency-Key`; replay with same
      body; assert second response body and status match the
      first byte-for-byte. The cache short-circuits the
      duplicate-name guard at the handler level (would have been
      409 without the middleware). Replay is tagged with
      `X-Idempotent-Replay: true` so callers can detect it
      (FR-020, SC-005). Companion
      `test_no_idempotency_key_passes_through` proves the
      middleware is a no-op without the header.
- [X] T029 [P] [MW] `tests/api/middleware/test_idempotency.py::test_body_mismatch_returns_422`
      — replay with same key + different body; HTTP 422 with
      errorCode `idempotency_key_body_mismatch` (FR-021). The
      original cached response is *not* served.
- [X] T030 [P] [MW] `tests/api/middleware/test_idempotency.py::test_expired_cache_row_is_treated_as_miss`
      — write the cache row's `expires_at` to one hour ago
      (deterministic equivalent of freezegun-advancing 25 h);
      replay; assert the handler runs (returns 409 from the
      duplicate-name guard, proving the cache wasn't served).
      Companion `test_get_request_with_idempotency_key_bypasses`
      pins the safe-method bypass; companion
      `test_canonical_json_normalisation` pins JCS-style
      key-reordering equivalence (re-ordered JSON serialises to
      the same body hash).

### Implementation

- [X] T031 [MW] Create `src/romarr/api/middleware/gzip.py` — wraps
      FastAPI's `GZipMiddleware` with the 1 KB threshold from
      `Settings.gzip_min_size_bytes` (operator-tunable via
      `ROMARR_GZIP_MIN_SIZE_BYTES`). Wired into `create_app()`
      ahead of CORS so it lands on the outermost layer.
- [X] T032 [P] [MW] Create `src/romarr/api/middleware/cors.py` —
      reads `ROMARR_CORS_ALLOWED_ORIGINS` JSON env via
      `Settings.cors_allowed_origins` (`list[str]`, default empty
      = same-origin only). `allow_credentials=True` for the
      cookie-session SPA flow; methods/headers wildcarded so the
      operator decides ORIGIN, the rest is pass-through. Wired
      into `create_app()` after GZip.
- [ ] T033 [P] [MW] Create `src/romarr/api/middleware/csrf.py` —
      `fastapi-csrf-protect` integration; bypass when the resolved
      `AuthMethod` from spec 010 is `API_KEY` / `JWT` / `PROXY`.
- [ ] T034 [P] [MW] Create `src/romarr/api/middleware/rate_limit.py`
      — slowapi setup with three keying strategies:
      `login`/`setup`/`oidc` keyed by IP, default keyed by API key
      id (or session user id).
- [X] T035 [P] [MW] Create `src/romarr/api/middleware/idempotency.py`
      — pure-ASGI middleware (NOT BaseHTTPMiddleware, which would
      consume the body and break downstream readers). Reads
      Idempotency-Key, hashes the body via JCS-style canonical
      JSON serialisation (sort_keys + tight separators) for
      `application/json` bodies and raw SHA-256 for binary /
      multipart, looks up `(endpoint, key)` in the
      IdempotencyCache table from spec 013 data-model. Hit +
      matching body hash → replays cached status / headers / body
      with `X-Idempotent-Replay: true`. Hit + differing body →
      HTTP 422 + errorCode `idempotency_key_body_mismatch`.
      Hit + expired (`expires_at < now`) → delete row, run
      handler. Miss → run handler with replayed body, capture
      response, write cache row when status < 500 (5xx server
      errors aren't cached so transient issues stay retryable).
      Wired into `create_app()` after CORS so it's the innermost
      MW layer — closest to the routes. Redis backend swap
      stays narrow (single `_lookup_cache` / `_write_cache` /
      `_delete_cache` indirection).

**Checkpoint**: MW tests green.

---

## Phase 5: New Bridge Routers (`ROUTERS`)

### Tests (one suite per router)

- [X] T036 [P] [ROUTERS] `tests/api/routers/test_status.py::test_status_authenticated_returns_full_sonarr_shape`
      — `GET /api/v3/system/status` with a session cookie returns
      the v3 baseline (version / instanceName / urlBase / osName /
      runtimeVersion / appData / startTime / isProduction) plus
      the v4 additions (databaseType / databaseVersion /
      migrationVersion / runtimeName) per the spec 013
      clarification — emit the UNION (FR-031, SC-001).
- [X] T037 [P] [ROUTERS] `tests/api/routers/test_status.py::test_status_unauthenticated_returns_minimal_shape`
      — no auth; HTTP 200 returning `{version, isProduction}`
      only. Companion `test_status_public_tier_does_not_leak_topology`
      pins that no v3/v4 field beyond those two leaks to
      unauthenticated scanners (FR-004 + auth-tiered
      clarification).
- [ ] T038 [P] [ROUTERS] `tests/api/routers/test_log.py::test_paginated_log_entries`
      — GET `/api/v3/system/log?page=1&pageSize=10`; canonical
      envelope.
- [ ] T039 [P] [ROUTERS] `tests/api/routers/test_log.py::test_download_log_file`
      — GET `/api/v3/system/log/file/{filename}` returns the file
      bytes; admin-only.
- [ ] T040 [P] [ROUTERS] `tests/api/routers/test_backup.py::test_list_backups`
      — GET `/api/v3/system/backup` lists files in the configured
      backup_path.
- [ ] T041 [P] [ROUTERS] `tests/api/routers/test_backup.py::test_create_backup_now`
      — POST triggers spec 012's `BackupRunner` and returns the
      command id; admin-only.
- [X] T042 [P] [ROUTERS] `tests/api/routers/test_wanted.py::test_missing_returns_only_wanted_monitored_releases`
      — GET `/api/v3/wanted/missing` returns Releases with
      `status='wanted' AND monitored=true`; canonical envelope.
      Imported and unmonitored rows are excluded. Companion
      tests pin pagination + sort + 401 + 400 invalid sortKey.
      Plus `/cutoff` companion endpoint:
      `test_cutoff_returns_imported_below_ceiling` returns rows
      with `status='imported' AND cutoff_met=false AND
      monitored=true`.
- [ ] T043 [P] [ROUTERS] `tests/api/routers/test_wanted.py::test_bulk_search`
      — POST `/api/v3/wanted/missing/search` with
      `{releaseIds: [...]}` triggers a one-shot search per release
      via spec 007's `run_manual_search`; admin or user.
- [X] T044 [P] [ROUTERS] `tests/api/routers/test_queue.py::test_lists_in_flight_with_canonical_envelope`
      — seed `queue_entry` rows; GET returns the canonical
      pagination envelope with the documented camelCase record
      keys (releaseId / downloadClientId / state / progress /
      etaSeconds / sizeBytes / etc.). Companion tests pin
      `?pageSize=N` capping, sort-by-state-desc, invalid sortKey
      400 (FR-008), 401 unauthenticated, and the empty-queue
      shape.
- [ ] T045 [P] [ROUTERS] `tests/api/routers/test_queue.py::test_delete_with_remove_from_client`
      — DELETE `?removeFromClient=true` calls spec 005's
      `DownloadClient.remove(...)` and removes the queue row.
- [ ] T046 [P] [ROUTERS] `tests/api/routers/test_queue.py::test_retry_endpoint`
      — POST `/api/v3/queue/{id}/retry` resets the queue row to
      `state='queued'` and re-fires spec 005's add helpers.
- [X] T047 [P] [ROUTERS] `tests/api/routers/test_history.py::test_paginated_history_unions_all_three_tables`
      — GET `/api/v3/history` aggregates `import_history`,
      `search_history`, `job_run` rows into the unified
      `HistoryEvent` shape (eventType / id / date / gameId /
      releaseId / successful). Companion tests pin the
      successful-derivation per source: ImportHistory.success,
      SearchHistory.results_count > 0, JobRun.status == 'success'.
      Plus empty-feed, 401, and invalid-sortKey 400 cases.
- [X] T048 [P] [ROUTERS] `tests/api/routers/test_history.py::test_since_filters_to_events_after_threshold`
      — GET `/api/v3/history/since?date=...` filters to
      events with `date >= since`. Companion
      `test_since_returns_all_when_threshold_in_past` pins the
      "everything after the past" case.
- [X] T049 [P] [ROUTERS] `tests/api/routers/test_calendar.py::test_returns_empty_list_with_valid_range`
      — GET `/api/v3/calendar?start=...&end=...` returns `[]`
      (MVP — data sources TBD). Companion tests pin: required
      `start` + `end` query params (422), inverted-range 400
      with errorCode `calendar_invalid_range`, equal-range 400
      (empty range is a bug not a feature), invalid ISO-8601
      422, and unauthenticated 401.
- [X] T050 [P] [ROUTERS] `tests/api/routers/test_tag.py::test_post_get_put_delete_round_trip`
      — POST/GET (list + single)/PUT/DELETE round-trip on
      `/api/v3/tag*`. Default colour matches the brand
      `#9BBC0F`. Companion validation tests for the slug-pattern
      `name`, hex-pattern `color`, and unique-name 409 with
      `errorCode tag_name_conflict`.
- [X] T051 [P] [ROUTERS] `tests/api/routers/test_tag.py::test_delete_in_use_*`
      — tag in use by a Game-typed assignment; DELETE returns
      HTTP 409 with `errorCode tag_in_use`. With `?force=true`,
      cascades the assignment rows and returns HTTP 204 — pinned
      by `test_delete_in_use_with_force_cascades`.
- [X] T052 [P] [ROUTERS] `tests/api/routers/test_tag.py::test_detail_lists_resources_grouped_by_entity_type`
      — GET `/api/v3/tag/detail/{id}` returns the documented
      Sonarr-shape `{id, label, gameIds, indexerIds,
      notificationIds, releaseIds}` envelope, with each list
      sorted ascending. The `/detail/{id}` route is registered
      before the `{tag_id}` catch-all in the router so FastAPI's
      path matcher hits the literal first.

### Implementation

- [X] T053 [ROUTERS] Create
      `src/romarr/api/routers/status.py` — Sonarr-shape JSON
      mounted under `/api/v3/system/status`. Tiered by auth via
      `get_current_principal`: public callers get
      `{version, isProduction}`; authenticated callers (any role)
      get the v3+v4 union. `app.state._start_time` is stamped
      during `create_app()` so the `startTime` field reflects the
      process boot moment. `databaseType` derived from the
      configured `database_url` (sqLite / postgreSQL).
- [ ] T054 [P] [ROUTERS] Create `src/romarr/api/routers/log.py` —
      paginated log reader + file listing + download.
- [ ] T055 [P] [ROUTERS] Create
      `src/romarr/api/routers/backup.py` — list backups + manually
      trigger spec 012's `BackupRunner`.
- [~] T056 [P] [ROUTERS] Create
      `src/romarr/api/routers/wanted.py` — `/missing` and `/cutoff`
      paginated reads shipped: GET `/api/v3/wanted/missing`
      returns Releases with `status='wanted' AND
      monitored=true`; GET `/api/v3/wanted/cutoff` returns
      `status='imported' AND cutoff_met=false AND
      monitored=true`. Both use the canonical pagination
      envelope with the Sonarr-shape camelCase release fields
      (gameId / dumpStatus / namingConvention / cutoffMet /
      libraryId / discNumber / discTotal / parentReleaseId).
      Read-only via `require_readonly`. **Deferred to a
      follow-up slice**: POST `/wanted/missing/search` bulk
      search trigger (T043) — needs the spec 007
      `run_manual_search` integration.
- [~] T057 [P] [ROUTERS] Create
      `src/romarr/api/routers/queue.py` — list endpoint shipped:
      GET `/api/v3/queue` returns the canonical pagination
      envelope of `queue_entry` rows, sortable by
      `last_updated_at` / `state` / `progress` / `created_at` /
      `id`, with the Sonarr-shape camelCase JSON field set.
      Read-only via `require_readonly`. **Deferred to a follow-up
      slice**: DELETE `?removeFromClient=true` (needs spec 005's
      `DownloadClient.remove`) and POST `/{id}/retry` (needs
      spec 005's add helpers). Tasks T045 / T046 stay open.

      As part of this slice, `PaginationEnvelope.model_config`
      now sets `populate_by_name=True` so FastAPI's response_model
      revalidation accepts both snake_case Python names and the
      camelCase aliases — needed for any router that returns
      `PaginationEnvelope[X]` directly via `response_model=`.
- [X] T058 [P] [ROUTERS] Create
      `src/romarr/api/routers/history.py` — UNION query across
      `import_history`, `search_history`, `job_run`. Each branch
      projects to a common 6-column shape (event_type, id, date,
      game_id, release_id, successful) so the UNION is type-clean
      across SQLite + PostgreSQL. Sortable whitelist: date
      (default), event_type, id. Sonarr-shape camelCase JSON
      response. Companion `/since` endpoint filters on
      `date >= since` for cheap operator polling.

      As part of this slice, `paginate()` gained a `scalars: bool
      = True` kwarg — projection queries (UNION subqueries, raw
      column selects) need `scalars=False` so the helper returns
      full Row objects whose columns are addressable as
      attributes. ORM-mapped queries still get the default
      `.scalars().all()` extraction for backwards compat.
- [X] T059 [P] [ROUTERS] Create
      `src/romarr/api/routers/calendar.py` — MVP empty list
      backed by the `CalendarEvent` schema (id / title /
      platformId / kind / releaseDate (YYYY-MM-DD) /
      releaseDateUtc (ISO-8601) / monitored / summary /
      sourceUrl). The schema is pinned so the frontend
      month-view can wire against it now; a future data-source
      slice will populate without contract churn. Read-only
      via `require_readonly`. Range validation: `end > start` —
      a future data-source slice replaces the empty-list return
      with the matching events query.
- [X] T060 [P] [ROUTERS] Create `src/romarr/api/routers/tag.py` —
      full CRUD + force-delete + `/detail/{id}` polymorphic
      lookup. Read endpoints gated by `require_readonly`; write
      endpoints gated by `require_admin`. Slug-pattern + hex
      colour validation at the Pydantic schema layer; unique-name
      conflict surfaces as HTTP 409 with errorCode
      `tag_name_conflict`. The 409 + cascade flow on DELETE
      (FR-013) checks for any existing `TagAssignment` row before
      removal; `?force=true` cascades the assignments via a
      single `DELETE FROM tag_assignment` statement. Wired into
      `create_app()` after the system status router.

**Checkpoint**: ROUTERS tests green.

---

## Phase 6: WebSocket (`WS`)

### Tests

- [ ] T061 [P] [WS] `tests/api/ws/test_auth.py::test_apikey_query_param`
      — connect with `?apikey=`; upgrade succeeds.
- [ ] T062 [P] [WS] `tests/api/ws/test_auth.py::test_cookie_session`
      — log in via REST; reuse cookie on WS upgrade; succeeds.
- [ ] T063 [P] [WS] `tests/api/ws/test_auth.py::test_unauth_rejected`
      — no auth; HTTP 401 before upgrade completes (FR-018).
- [ ] T064 [P] [WS] `tests/api/ws/test_messages.py::test_taskstarted_taskfinished`
      — trigger a job; assert client receives `taskStarted` then
      `taskFinished` with documented JSON shape (SC-004).
- [ ] T065 [P] [WS] `tests/api/ws/test_messages.py::test_queueupdated`
      — populate a queue entry; update it; assert
      `queueUpdated` event sent.
- [ ] T066 [P] [WS] `tests/api/ws/test_messages.py::test_12_message_types`
      — table-driven over the 12 documented `messageType` strings;
      each is emittable from the bridge.
- [ ] T067 [P] [WS] `tests/api/ws/test_lossy.py::test_no_replay_on_reconnect`
      — disconnect during a job; reconnect; assert no missed events
      replayed (FR-019).
- [ ] T068 [P] [WS] `tests/api/ws/test_bridge.py::test_pubsub_to_subscribers`
      — emit an event onto the in-process channel from spec 011;
      assert WS subscribers receive it.

### Implementation

- [ ] T069 [WS] Create `src/romarr/api/ws/messages.py` —
      `MessageType` StrEnum with the 12 documented types; canonical
      JSON shape `{messageType, data}`.
- [ ] T070 [P] [WS] Create `src/romarr/api/ws/auth.py` — the on-
      upgrade auth resolver (cookie / apikey query / bearer
      header).
- [ ] T071 [P] [WS] Create `src/romarr/api/ws/subscriptions.py` —
      in-memory subscriber registry keyed by user_id; tear down on
      disconnect.
- [ ] T072 [P] [WS] Create `src/romarr/api/ws/bridge.py` — async
      consumer of spec 011's pub/sub channel; forwards each event
      to all subscribers with the documented `messageType`.
- [ ] T073 [WS] Create `src/romarr/api/ws/handler.py` — FastAPI
      WebSocket route at `/signalr/messages`; calls
      `auth.authenticate_upgrade(...)`; if ok, registers the client
      with `subscriptions`; awaits ping/pong loop.
- [ ] T074 [WS] Wire `WebSocketBridge.start()` into the lifespan
      startup (Phase 2) so it consumes events as soon as the
      application is ready.

**Checkpoint**: WS tests green; bridge events forward end-to-end.

---

## Phase 7: OpenAPI Customisation (`OPENAPI`)

### Tests

- [X] T075 [P] [OPENAPI] `tests/api/test_openapi_valid.py::test_openapi_version_is_3_1_0`
      and `::test_openapi_validates_against_3_1_schema` —
      `app.openapi()` returns `openapi: "3.1.0"` and validates
      via `openapi_spec_validator.validate(schema)` with zero
      errors (SC-002, FR-013).
- [X] T076 [P] [OPENAPI] `tests/api/test_openapi_valid.py::test_operation_ids_are_unique`
      — every endpoint has a unique `operationId` (FR-013).
      Walks all paths × methods × operationId and asserts no
      duplicates.
- [ ] T077 [P] [OPENAPI] `tests/api/test_openapi_examples.py::test_required_examples`
      — per-endpoint examples (POST /api/v3/game, POST
      /api/v3/rom/release/grab, POST /api/v3/command, POST
      /api/v3/rom/platform-pack/upload). **Deferred** — handled
      at the route level rather than centrally; tracked as a
      follow-up when the router schemas grow `examples=[...]`
      arrays.
- [X] T078 [P] [OPENAPI] `tests/api/test_openapi_valid.py::test_security_schemes_advertise_all_four_methods`
      — spec lists ApiKeyHeader / ApiKeyQuery / CookieSession /
      BearerJwt under `components.securitySchemes` plus the
      top-level `security` array advertising them as OR-equivalent
      (FR-015). Companion
      `test_top_level_security_lists_alternatives` pins the
      array shape.
- [X] T079 [P] [OPENAPI] `tests/api/test_openapi_valid.py::test_every_operation_has_a_tag`
      — every operation carries a non-empty `tags` array.
      Operations without an explicit tag get the documented
      `Misc` fallback rather than an empty / missing array
      (FR-014).

### Implementation

- [X] T080 [OPENAPI] Create `src/romarr/api/openapi.py` —
      `customize_openapi(app)` installed as `app.openapi`. The
      function:
      1. ✓ forces `openapi: "3.1.0"`;
      2. ✓ injects ApiKeyHeader / ApiKeyQuery / CookieSession /
         BearerJwt under `components.securitySchemes` and a
         top-level `security` array advertising them as
         OR-equivalent;
      3. ❎ enriches the four named endpoints with examples —
         deferred (tracked under T077);
      4. ~ ensures every endpoint has a tag — applies the `Misc`
         fallback rather than raising at startup. Kept lenient so
         third-party plugin routers can't brick the app; fail-
         fast variant tracked as a follow-up;
      5. ✓ caches via `app.openapi_schema` (FastAPI's standard
         hook).
      Wired into `create_app()` after every router is registered
      so the customizer sees the full route set. Added
      `openapi-spec-validator>=0.7` to dev deps for the
      validation tests.

**Checkpoint**: OPENAPI tests green; the spec validates 3.1
clean and the documented examples are present.

---

## Phase 8: Wire All Existing Routers (`WIRE`)

### Tests

- [ ] T081 [P] [WIRE] `tests/api/test_endpoint_coverage.py::test_every_route_authenticated`
      — iterate `app.routes`; assert every route NOT in the public
      set requires auth via the chain from spec 010 (FR-004).
- [ ] T082 [P] [WIRE] `tests/api/test_endpoint_coverage.py::test_required_role_declared`
      — every route has a documented `require_role` dependency
      (FR-005).
- [ ] T083 [P] [WIRE] `tests/api/test_endpoint_coverage.py::test_route_count_at_least_90`
      — count distinct routes; assert ≥ 90 (FR-001).

### Implementation

- [ ] T084 [WIRE] In `src/romarr/api/factory.py`, import every
      router from prior specs and `app.include_router(...)` each
      under its documented path. The list:
      - `metadata.api.providers`, `metadata.api.field_priority`,
        `metadata.api.refresh` (spec 002)
      - `platform_packs.api.packs`, `platform_packs.api.platforms` (spec 003)
      - `indexers.api.applications`, `indexers.api.indexers`,
        `indexers.api.tests` (spec 004)
      - `downloaders.api.clients`, `downloaders.api.schema` (spec 005)
      - `profiles.api.{quality,region,dump,language,naming,custom_format}`
        (spec 006)
      - `search.api.{search,grab,history,blocklist}` and
        `search.api.command` (spec 007 — replaced here by Phase 9's
        unified command bus)
      - `importer.api.{manual,history,unidentified,webhook}` (spec 008)
      - `libraries.api.{libraries,scan,exporters,manual_import}` (spec 009)
      - `auth.api.{auth,setup,api_keys,oidc,users}` (spec 010)
      - `notifications.api.{notifications,health}` (spec 011)
      - `tasks.api.{tasks,runs}` (spec 012; the command router from
        spec 012 is replaced by Phase 9's unified bus).

**Checkpoint**: WIRE tests green; route count ≥ 90.

---

## Phase 9: Command Bus (`CMD`)

### Tests

- [ ] T085 [P] [CMD] `tests/api/routers/test_command.py::test_known_names`
      — table-driven over the documented names
      (`MissingSearch`, `CutoffSearch`, `RssSync`, `RefreshGame`,
      `RescanLibrary`, `DownloadDats`, `IndexerSearch`, `Backup`,
      `ApplicationUpdate`, `RefreshMetadata`, `ExporterRun`); each
      maps to spec 012's job runner.
- [ ] T086 [P] [CMD] `tests/api/routers/test_command.py::test_get_command_status`
      — POST → capture id → GET `/api/v3/command/{id}` → assert
      Sonarr-shape body (US8, FR-003).
- [ ] T087 [P] [CMD] `tests/api/routers/test_command.py::test_unknown_command_400`
      — POST `{"name": "Foo"}` → HTTP 400 reason
      `unknown_command`.
- [ ] T088 [P] [CMD] `tests/api/routers/test_command.py::test_delete_cancels`
      — DELETE `/api/v3/command/{id}` sets the underlying
      `cancellation_event` (spec 012).

### Implementation

- [ ] T089 [CMD] Create `src/romarr/api/routers/command.py` —
      thin router over spec 012's `command_aliases` mapping. POST
      accepts the Sonarr-shape body; GET returns the
      `CommandStatus` JSON.

**Checkpoint**: CMD tests green; the unified bus handles every
documented Sonarr-compat name.

---

## Phase 10: Sonarr-Shape Probe (`SONARR`)

### Tests

- [ ] T090 [P] [SONARR] `tests/api/test_sonarr_status_compat.py::test_status_fixture_match`
      — fixture `tests/fixtures/api/sonarr_status_fixture.json`
      contains the canonical key set; assert
      `GET /api/v3/system/status` returns a superset (every key
      Sonarr expects is present; Romarr may add extra
      ROM-specific keys) (SC-001).
- [ ] T091 [P] [SONARR] `tests/api/test_sonarr_status_compat.py::test_notifiarr_probe`
      — replay the captured Notifiarr probe payload
      (`tests/fixtures/api/notifiarr_probe_payload.json`) against
      the running app; assert HTTP 200 and the Sonarr-shaped
      body validates against the fixture.

### Implementation

- [ ] T092 [SONARR] Capture `sonarr_status_fixture.json` from a
      real Sonarr v4 installation (or use a documented snapshot)
      and commit it under `tests/fixtures/api/`.
- [ ] T093 [SONARR] Capture or hand-craft a
      `notifiarr_probe_payload.json` representing the request
      Notifiarr sends when adding a Sonarr-compat *arr.

**Checkpoint**: SONARR tests green; ecosystem-tooling
compatibility is locked.

---

## Phase 11: Hardening (`HARD`)

- [ ] T094 [HARD] Run `pytest --cov=romarr.api` — verify ≥ 80%
      coverage (SC-008).
- [ ] T095 [HARD] Run `ruff check .` — zero warnings on
      `src/romarr/api/`.
- [ ] T096 [HARD] CI smoke test asserts every documented route
      has at least one happy-path test AND one error-path test
      (SC-009). A simple `pytest --collect-only` pattern matcher
      suffices.
- [ ] T097 [HARD] Manual perf check —
      `GET /api/v3/system/status` p95 < 50 ms;
      list endpoints p95 < 200 ms;
      WebSocket emit→receive p95 < 100 ms.
      Record in `specs/013-rest-api-websocket/research.md`.
- [ ] T098 [HARD] Update `pyproject.toml` `version = "0.13.0a1"`;
      add a one-line note to `CHANGELOG.md`: "0.13.0a1 — REST
      API & WebSocket: Sonarr-compat surface, OpenAPI 3.1, 90+
      routes, WebSocket /signalr/messages, idempotency, rate
      limiting, CSRF, GZip."
- [ ] T099 [HARD] Final review: open
      `specs/013-rest-api-websocket/spec.md` and tick every
      Functional Requirement (FR-001 → FR-031) against a task
      ID; record gaps as follow-up items.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (SCAF)**: prerequisite specs merged.
- **Phase 2 (FACTORY)**: depends on Phase 1.
- **Phase 3 (ENVELOPES)**: depends on Phase 1; helpers consumed by
  Phases 5–9.
- **Phase 4 (MW)**: depends on Phase 2.
- **Phase 5 (ROUTERS)**: depends on Phases 2, 3, 4.
- **Phase 6 (WS)**: depends on Phase 2; can run in parallel with
  Phase 5.
- **Phase 7 (OPENAPI)**: depends on Phase 8 (routers must be
  registered before customisation runs).
- **Phase 8 (WIRE)**: depends on Phases 2, 3, 4.
- **Phase 9 (CMD)**: depends on Phase 8 (uses spec 012 wired in
  Phase 8).
- **Phase 10 (SONARR)**: depends on Phase 5 (status router) +
  Phase 8 (full surface).
- **Phase 11 (HARD)**: depends on Phase 10.

### Within-Phase Parallelism

- Phase 1: T002–T004 in parallel.
- Phase 2: T007–T009 in parallel.
- Phase 3: T011–T015 in parallel; T016 + T017 sequential.
- Phase 4: T018–T030 in parallel; T031–T035 in parallel.
- Phase 5: T036–T052 in parallel; T053–T060 in parallel.
- Phase 6: T061–T068 in parallel; T069–T072 in parallel; T073 +
  T074 sequential.
- Phase 7: T075–T079 in parallel.
- Phase 8: T081–T083 in parallel; T084 sequential.
- Phase 9: T085–T088 in parallel.
- Phase 10: T090–T091 in parallel.

### Critical Path

`SCAF → FACTORY → ENVELOPES → MW → WIRE → OPENAPI → SONARR →
HARD`. ROUTERS, WS, and CMD develop in parallel once FACTORY is
up.

### Implementation Strategy

- **Day 1**: Phase 1 (SCAF) + Phase 2 (FACTORY) + Phase 3
  (ENVELOPES).
- **Day 2**: Phase 4 (MW) — six middleware modules with their
  tests.
- **Day 3**: Phase 5 (ROUTERS) + Phase 6 (WS) in parallel.
- **Day 4**: Phase 8 (WIRE) — actually wire every prior spec's
  routers.
- **Day 5**: Phase 7 (OPENAPI) + Phase 9 (CMD) + Phase 10 (SONARR).
- **Day 6**: Phase 11 (HARD).

This sizing assumes one developer working full-time. With two
contributors, ROUTERS and WS split cleanly across them on Day 3.

---

## Notes

- `[P]` tasks change different files only.
- Tests are written BEFORE implementation in every phase.
- Stop at any phase checkpoint — the API surface is delivered
  incrementally; each phase is independently shippable.
- Avoid: implementing GraphQL (firm out); implementing gRPC
  (firm out); streaming responses for large lists (deferred to
  v1+); webhook signing (deferred to v1+); Sonarr v2 endpoint
  aliases under `/api/` (firm out); per-resource fine-grained
  permissions (deferred — current RBAC is the three-tier model).
- Constitutional invariants under test:
  - **Article IV (API Conventions & Compatibility Surface)** —
    Sonarr v3 conventions wherever resources overlap (T036, T090);
    ROM-specific endpoints under `/api/v3/rom/*` (T083);
    `/signalr/messages` WebSocket (T064-T067); OpenAPI 3.1 with
    Swagger and ReDoc (T075-T079).
  - **Article XVI (Quality Gates)** — ≥ 80% coverage (T094);
    zero ruff warnings (T095); endpoint coverage SC-009 (T096);
    perf budgets (T097).
  - **Article XVII (Idempotency & Safety)** — Idempotency-Key
    cache (T028-T030); CSRF on cookie POSTs (T021-T023); rate
    limiting on auth (T024-T025); body-mismatch detection
    (T029).
  - **Article III (Locked Stack)** — FastAPI + slowapi +
    fastapi-csrf-protect; no new HTTP client; no GraphQL/gRPC.

## Phase: Clarification Tasks (Session 2026-04-29)

- [ ] CL001 Migration `0013_api.py` creates the polymorphic `tag` + `tag_assignment` tables per `data-model.md` — `tag (id PK, name UNIQUE, color, label, timestamps)` and `tag_assignment (tag_id FK, entity_type ENUM, entity_id, UNIQUE three-tuple)` with cascade on `tag_id` and the documented entity-type enum `{'game', 'indexer', 'notification', 'release'}`
- [ ] CL002 Migration `0013_api.py` creates `queue_entry` and `idempotency_cache` tables per `data-model.md`. `idempotency_cache` exists as the Redis fallback; the schema MUST be present unconditionally
- [ ] CL003 [P] Implement per-entity tag-assignment cleanup hooks in `src/romarr/tags/cleanup_hooks.py`:
  - `Game.before_delete` → DELETE FROM tag_assignment WHERE entity_type='game' AND entity_id=?
  - `Indexer.before_delete` → same with 'indexer'
  - `Notification.before_delete` → same with 'notification'
  - `Release.before_delete` → same with 'release'
- [ ] CL004 [P] [US5] Implement JCS-canonical body-hash idempotency comparison in `src/romarr/api/middleware/idempotency.py` — JSON bodies: `SHA-256(JCS(canonicalize(body)))` per RFC 8785; multipart/binary: `SHA-256(raw bytes)`. Store as hex on `idempotency_cache.request_body_hash` (FR-021)
- [ ] CL005 [P] [US5] On replay with mismatching hash → HTTP 422 reason `idempotency_key_body_mismatch`. Constant-time hash comparison
- [ ] CL006 [P] [US4] Implement plain JSON-over-WebSocket framing at `/signalr/messages` in `src/romarr/api/websocket/framing.py` — one message per frame `{messageType: string, body: object}`. NO SignalR negotiate / NO hub-method dispatch / NO binary mode (FR-016)
- [ ] CL007 [P] [US4] Implement WebSocket ping/pong in `src/romarr/api/websocket/keepalive.py` — server sends `{messageType: "ping"}` every 30 s; clients respond `{messageType: "pong"}` within 10 s or connection torn down
- [ ] CL008 [P] [US1] Implement tiered `GET /api/v3/system/status` in `src/romarr/api/system_status.py` — public callers receive `{version, isProduction}` ONLY; authenticated callers receive the full Sonarr-shaped body (FR-031 amended)
- [ ] CL009 [P] [US1] Add Sonarr v3+v4 union fields to authenticated-tier `system/status` response: `version`, `instanceName`, `urlBase`, `osName`, `runtimeVersion`, `appData`, `startTime`, `isProduction` (v3) PLUS `databaseType`, `databaseVersion`, `migrationVersion`, `runtimeName` (v4 additions)
- [ ] CL010 [P] Add fixtures `tests/fixtures/api/sonarr_v3_status_fixture.json` and `tests/fixtures/api/sonarr_v4_status_fixture.json`; conformance test asserts the response key set is a superset of both
- [ ] CL011 [P] **Cross-spec consistency**: drop `Authorization: Bearer JWT` from FR-015 security schemes documented in `src/romarr/api/openapi_generator.py` — only API key (header / query) and cookie session
- [ ] CL012 [P] **Cross-spec consistency**: align login rate-limit with spec 010 FR-010a — 10 req/min/source-IP on `/auth/login`, `/auth/setup`, `/auth/oidc/callback` in `src/romarr/api/middleware/rate_limit.py`. HTTP 429 + `Retry-After`. Bcrypt MUST NOT run when limit exceeded
- [ ] CL013 [P] Exempt `GET /api/v3/health` from per-IP rate limit in `src/romarr/api/middleware/rate_limit.py` per FR-023 (Uptime-Kuma probe-friendly)
- [ ] CL014 [P] Add tests in `tests/api/test_idempotency.py` covering: same body, same key → cached response returned; semantically-equal-but-formatted-differently body → cached response (JCS canonical equivalence); different body → 422
- [ ] CL015 [P] Add tests in `tests/api/test_websocket_framing.py` covering: connect → send subscribe message → server emits taskStarted/taskFinished envelopes; ping every 30 s; missing pong → connection torn down at 40 s
- [ ] CL016 [P] Add tests in `tests/api/test_system_status_tiering.py` covering: unauthenticated → only `{version, isProduction}`; authenticated → full v3+v4 union
- [ ] CL017 [P] Add tests in `tests/api/test_polymorphic_tags.py` covering: same tag applied to Game and Indexer → both rows in `tag_assignment`; tag delete cascades; Game delete fires cleanup hook; UNIQUE constraint prevents duplicate `(tag, entity_type, entity_id)`
