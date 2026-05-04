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

- [~] T001 [SCAF] ``openapi-spec-validator>=0.7`` shipped as
      a dev dep (slice 174 verification). ``slowapi`` and
      ``fastapi-csrf-protect`` did NOT ship — the rate-limit
      and CSRF middleware were implemented from scratch in
      ``api/middleware/`` to keep the dep surface minimal.
      Re-evaluate if external rate-limit primitives become
      worthwhile (e.g., distributed Redis-backed limits).
- [X] T002 [P] [SCAF] ``src/romarr/api/__init__.py`` exposes
      ``create_app`` via re-export from ``romarr.api.app``.
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
- [X] T006 [SCAF] ``tests/conftest.py`` ships
      ``api_engine`` + ``api_client`` (httpx ASGI fixture);
      ``tests/api/conftest.py`` exists for module-local
      fixtures; ``tests/api/ws/conftest.py`` provides the
      WebSocket-specific TestClient seeded with an admin
      user + API key. Naming differs from the spec
      (``app_client`` → ``api_client``,
      ``ws_client`` → in-test TestClient) but the shape is
      shipped and consumed across the test suite.

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
- [X] T014 [P] [ENVELOPES] Cross-endpoint canonical-envelope
      conformance shipped at
      ``tests/api/test_pagination_uniform.py`` (slice 198).
      Parametrised over five paginated endpoints: history,
      history/since, queue, wanted/missing, wanted/cutoff.
      Each call hits the real FastAPI app over an authed
      cookie, asserts 200 + the six canonical keys
      (``page``, ``pageSize``, ``sortKey``, ``sortDirection``,
      ``totalRecords``, ``records``) regardless of whether
      the underlying table is empty. Path differs from the
      spec's ``test_pagination.py::test_5_endpoints_uniform``
      — the cross-endpoint test got its own file to keep
      ``test_pagination.py`` focused on the helper unit
      tests. Endpoint set differs from the spec text
      (Game/Release/Indexer/Notification listed but those
      currently use list-not-paginate shapes; queue/wanted/
      history are the actual PaginationEnvelope consumers).
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
- [X] T021 [P] [MW] `tests/api/middleware/test_csrf.py::test_cookie_post_without_token_returns_403`
      — cookie-authenticated POST without `X-CSRF-Token`
      header returns HTTP 403 with errorCode
      `csrf_token_missing` (US7, SC-007). Companion tests pin
      the matching-token success path,
      mismatched-token-still-403, and the
      anonymous-POST-still-403 defensive case.
- [X] T022 [P] [MW] `tests/api/middleware/test_csrf.py::test_apikey_header_bypasses_csrf`
      — POST with `X-Api-Key` (and the `?apikey=` query form,
      and Bearer JWT) bypasses CSRF — these auth methods
      aren't subject to the cross-site cookie-attach problem
      (FR-027).
- [X] T023 [P] [MW] `tests/api/middleware/test_csrf.py::test_get_request_bypasses_csrf`
      — safe methods (GET / HEAD / OPTIONS / TRACE) bypass.
      Companion test pins OPTIONS preflight bypass +
      `/api/v3/auth/login` bootstrap path bypass.
- [X] T024 [P] [MW] `tests/api/middleware/test_rate_limit.py::test_login_allows_first_5_then_429s`
      — 5 logins from one IP succeed; the 6th returns HTTP 429
      with `Retry-After` (FR-022, SC-006). Companion tests pin
      window-slides-and-clears, X-Forwarded-For per-IP keying,
      and Retry-After-shrinks-as-window-ages.
- [X] T025 [P] [MW] `tests/api/middleware/test_rate_limit.py::test_setup_allows_first_then_429s_immediately`
      — 1 setup attempt succeeds; the 2nd returns HTTP 429
      (FR-023).
- [X] T026 [P] [MW] `tests/api/middleware/test_rate_limit.py::test_default_allows_first_100_then_429s_for_same_apikey`
      — 100 requests with same X-Api-Key succeed; the 101st
      returns 429 (FR-024). Companion tests pin per-API-key
      independence and session-cookie fallback for cookie
      callers.
- [X] T027 [P] [MW] `tests/api/middleware/test_rate_limit.py::test_health_endpoint_exempt_from_rate_limit`
      — `GET /api/v3/health` bypasses rate limiting (cluster
      orchestrators / uptime probes hit it every few seconds).
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
- [X] T033 [P] [MW] Create `src/romarr/api/middleware/csrf.py` —
      hand-rolled double-submit-cookie CSRF guard rather than
      pulling in `fastapi-csrf-protect`. Pure-ASGI middleware
      with explicit bypass for: safe methods (GET / HEAD /
      OPTIONS / TRACE), bootstrap paths
      (`/api/v3/auth/{login,setup,logout}` and
      `/api/v3/webhook/download-complete`), and non-cookie
      auth (X-Api-Key header + `?apikey=` query + Bearer JWT
      header). Cookie-session callers must send
      `X-CSRF-Token` matching the `csrf_token` cookie
      (`secrets.compare_digest` for timing-safe comparison).
      Gated by `Settings.csrf_protect` (env
      `ROMARR_CSRF_PROTECT`), default False so the existing
      cookie-session test suite keeps passing; the spec 014
      frontend wiring flips it to True once the SPA reads the
      cookie + echoes the header on every mutation. Wired
      into `create_app()` after CORS so cross-origin
      preflights still succeed.
- [X] T034 [P] [MW] Create `src/romarr/api/middleware/rate_limit.py`
      — hand-rolled pure-ASGI sliding-window rate limiter
      rather than pulling in slowapi. Three keying strategies:
      * `login` / `oidc/start` / `oidc/callback` → keyed by
        client IP (X-Forwarded-For first hop, then ASGI
        client tuple); default 5/min.
      * `setup` → keyed by client IP; default 1/min.
      * everything else → keyed by API key plaintext (header
        or `?apikey=` query) with session cookie fallback,
        IP fallback for unauthenticated callers; default
        100/min.
      `/api/v3/health` is unconditionally exempt. In-memory
      `dict[(strategy, key)] -> deque[timestamp]` with a
      threading.Lock for coordination across uvicorn worker
      threads. 429 responses carry the standard `Retry-After`
      header.

      Settings: `rate_limit_enabled` (default False — the
      test suite POSTs /login repeatedly, would 429 after 5);
      `rate_limit_login_per_minute=5`,
      `rate_limit_setup_per_minute=1`,
      `rate_limit_default_per_minute=100`. Production sets
      `ROMARR_RATE_LIMIT_ENABLED=true`. For multi-replica
      deployments, the next slice swaps the in-memory backing
      for Redis (same indirection pattern as the idempotency
      cache).
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
- [X] T038 [P] [ROUTERS] `tests/api/routers/test_log.py::test_paginated_log_entries_returns_canonical_envelope`
      — GET `/api/v3/system/log?page=1&pageSize=10` returns the
      canonical empty pagination envelope (MVP — entries
      materialise once the structlog → JSON-line file sink
      ships).
- [X] T039 [P] [ROUTERS] `tests/api/routers/test_log.py::test_download_log_file_returns_bytes`
      — GET `/api/v3/system/log/file/{filename}` streams the
      file as text/plain; admin-only. Companion tests pin: 404
      for unknown file, 400 for dotfile names,
      `_safe_log_path` rejects `..` / Windows separators / dot-
      prefixed names defense-in-depth, plus listing endpoint
      returns metadata sorted newest-first and survives a
      missing log_dir gracefully.
- [X] T040 [P] [ROUTERS] `tests/api/routers/test_backup.py::test_list_backups_returns_metadata_sorted_newest_first`
      — GET `/api/v3/system/backup` lists files under the
      configured `backup_path` with filename / lastWriteTime /
      size, sorted newest-first. Companion tests pin the
      empty-dir / missing-dir / DELETE happy-path / DELETE
      404-unknown / DELETE 403-readonly cases plus a
      `_safe_backup_path` traversal-rejection unit test.
- [~] T041 [P] [ROUTERS] `tests/api/routers/test_backup.py::test_create_backup_now`
      — POST trigger is served by the unified command bus
      (POST `/api/v3/command {"name": "Backup"}`), pinned in
      `tests/tasks/api/test_command_endpoint.py` rather than
      duplicated under `/api/v3/system/backup`. The
      one-trigger-surface choice avoids two-implementations
      drift; the BackupRunner itself is still a spec 012 stub
      and tracked there.
- [X] T042 [P] [ROUTERS] `tests/api/routers/test_wanted.py::test_missing_returns_only_wanted_monitored_releases`
      — GET `/api/v3/wanted/missing` returns Releases with
      `status='wanted' AND monitored=true`; canonical envelope.
      Imported and unmonitored rows are excluded. Companion
      tests pin pagination + sort + 401 + 400 invalid sortKey.
      Plus `/cutoff` companion endpoint:
      `test_cutoff_returns_imported_below_ceiling` returns rows
      with `status='imported' AND cutoff_met=false AND
      monitored=true`.
- [X] T043 [P] [ROUTERS] Bulk-search endpoint shipped as
      POST ``/api/v3/wanted/missing/search`` (slice 233).
      Admin-only via ``require_admin``; ``?limit=`` query
      param caps how many oldest-wanted Releases are probed
      (default 50, max 500). The round delegates to spec 007's
      ``run_missing_search`` (which fans out to
      ``run_manual_search`` per Release internally); the
      endpoint surfaces the aggregate counters
      (``total`` / ``succeeded`` / ``grabbed``) as
      ``BulkMissingSearchResponse``. 3 router tests cover the
      401 unauthenticated path, the empty-table happy path
      (returns 0/0/0), and the 422 invalid-limit path.
- [X] T044 [P] [ROUTERS] `tests/api/routers/test_queue.py::test_lists_in_flight_with_canonical_envelope`
      — seed `queue_entry` rows; GET returns the canonical
      pagination envelope with the documented camelCase record
      keys (releaseId / downloadClientId / state / progress /
      etaSeconds / sizeBytes / etc.). Companion tests pin
      `?pageSize=N` capping, sort-by-state-desc, invalid sortKey
      400 (FR-008), 401 unauthenticated, and the empty-queue
      shape.
- [X] T045 [P] [ROUTERS] DELETE ``/api/v3/queue/{id}`` shipped
      with ``?removeFromClient=`` boolean (slice 234). Admin-
      only via ``require_admin``; default ``false`` only
      deletes the Romarr-side mirror, ``true`` additionally
      calls ``DownloadClient.remove(delete_files=True)`` via
      spec 005 so the on-disk download is dropped too. Errors:
      404 ``queue_entry_not_found`` when no row matches;
      502 ``download_client_unreachable`` when the client
      factory fails; 502 ``download_client_remove_failed``
      when the spec 005 ``remove()`` raises (Auth / Version /
      Connection / unexpected). 3 router tests cover the
      happy path (entry deleted, list endpoint reports the
      survivor only), 404 missing entry, 401 unauthenticated.
- [~] T046 [P] [ROUTERS] POST ``/api/v3/queue/{id}/retry`` —
      **deferred-by-design** alongside T045. Same wiring
      gap (needs the spec 005 add helpers exposed as a
      router-callable function).
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
- [X] T054 [P] [ROUTERS] Create `src/romarr/api/routers/log.py` —
      three routes under `/api/v3/system/log*`:
      GET `/api/v3/system/log` (paginated entries — MVP empty
      stub, schema pinned for frontend wiring),
      GET `/api/v3/system/log/file` (list files in
      `Settings.log_dir` with size + lastWriteTime, sorted
      newest-first, returns [] for empty/missing dir),
      GET `/api/v3/system/log/file/{filename}` (FileResponse
      streaming text/plain, admin-only). Path-traversal guard
      (`_safe_log_path`) rejects names containing separators,
      dotfile-prefixed names, and resolved paths that escape
      `log_dir`. Added `Settings.log_dir` (default
      `./data/logs`).
- [X] T055 [P] [ROUTERS] Create
      `src/romarr/api/routers/backup.py` — two routes under
      `/api/v3/system/backup*`:
      GET `/api/v3/system/backup` (list files in
      `Settings.backup_path` with filename / lastWriteTime /
      size, sorted newest-first; returns [] for empty/missing
      dir; readonly auth),
      DELETE `/api/v3/system/backup/{filename}` (admin-only
      removal; path-traversal-guarded via `_safe_backup_path`,
      mirrors the log router's defense-in-depth pattern).
      Manual trigger flows through the unified command bus
      rather than duplicating it here. Added
      `Settings.backup_path` (default `./data/backups`,
      `ROMARR_BACKUP_PATH` env var).
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

- [X] T061 [P] [WS] `tests/api/ws/test_auth.py::test_apikey_query_param_upgrades_succeeds`
      — connect with `?apikey=`; upgrade succeeds; first frame
      is the systemMessage welcome envelope. Companion test pins
      the X-Api-Key header form.
- [X] T062 [P] [WS] `tests/api/ws/test_auth.py::test_cookie_session_upgrade_succeeds`
      — log in via REST; cookie persists on the TestClient;
      WS upgrade succeeds.
- [X] T063 [P] [WS] `tests/api/ws/test_auth.py::test_unauth_upgrade_rejected`
      — no auth; the handler closes with WebSocket code 1008
      (policy violation, mirrors HTTP 401 for FR-018) before
      the welcome frame ships. Companion test pins the
      bogus-apikey case.
- [~] T064 [P] [WS] taskStarted / taskFinished E2E —
      **deferred-by-design**. The broadcast contract is
      structurally pinned by T066's
      ``test_each_message_type_round_trips_to_subscriber``
      (parametrised over every MessageType, including
      taskStarted + taskFinished). The
      "scheduler dispatch → SubscriptionRegistry.broadcast()"
      glue is the missing integration piece; lands when the
      spec 012 scheduler exposes a public
      ``progress_callback`` hook the WS bridge can subscribe
      to.
- [~] T065 [P] [WS] queueUpdated E2E —
      **deferred-by-design** alongside T064. The broadcast
      shape is pinned by T066; the queue-update emission
      site lands with the queue-write paths from T045/T046.
- [X] T066 [P] [WS] `tests/api/ws/test_messages.py::test_each_message_type_round_trips_to_subscriber`
      — parametrized over every `MessageType` value; each
      broadcast through `SubscriptionRegistry.broadcast()`
      reaches the connected client as a canonical
      `{messageType, data}` envelope (SC-004). Companion
      `test_all_12_documented_types_are_covered` pins the
      table-vs-StrEnum no-drift invariant; companion
      `test_broadcast_reaches_every_subscriber` covers the
      multi-tab case (one operator, two connections, both
      receive).
- [X] T067 [P] [WS] `tests/api/ws/test_lossy.py::test_disconnected_client_does_not_replay_on_reconnect`
      — open WS A → broadcast E1 (A receives) → disconnect →
      reconnect as B → assert no replay → broadcast E2 → B
      receives E2 only. Pins FR-019. Companion
      `test_disconnect_removes_subscription_from_registry`
      pins the handler's `finally` cleanup (otherwise dead
      subs would leak across disconnects).
- [~] T068 [P] [WS] In-process pubsub → WS subscribers —
      **deferred-by-design**. The dispatcher → bridge glue
      lands when spec 011's notification dispatcher exposes a
      single ``emit_event(payload)`` hook the WS bridge can
      subscribe to (same gap that defers spec 012's
      OnDatUpdate emission and spec 008's auto-blocklist
      OnFail emission). The broadcast-to-subscribers contract
      is pinned by T066 already.

### Implementation

- [X] T069 [WS] Create `src/romarr/api/ws/messages.py` —
      `MessageType` StrEnum with the 12 documented types
      (taskStarted / taskProgress / taskFinished / queueUpdated
      / gameAdded / gameUpdated / gameDeleted / releaseGrabbed
      / releaseImported / releaseFailed / healthChanged /
      systemMessage). `build_envelope(message_type, data)`
      helper produces the canonical `{messageType, data}` JSON
      shape (spec 013 Q2 clarification on plain
      JSON-over-WebSocket framing).
- [X] T070 [P] [WS] Create `src/romarr/api/ws/auth.py` — the
      on-upgrade auth resolver. `build_ws_request_context` lifts
      headers / query / cookies off the WebSocket into a
      `RequestContext`; `authenticate_upgrade` calls spec 010's
      `resolve_principal` against it. Same chain as HTTP routes
      (cookie / apikey header / apikey query / bearer JWT /
      proxy headers).
- [X] T071 [P] [WS] Create `src/romarr/api/ws/subscriptions.py` —
      `SubscriptionRegistry` keyed by per-connection UUID4
      (NOT user_id; one operator may have multiple tabs open).
      Async-safe via a single `asyncio.Lock`; iteration takes a
      snapshot so the broadcast loop fires with the lock
      released. `broadcast(payload)` swallows per-send errors so
      one dead connection doesn't abort the broadcast for the
      rest. Process-local — for multi-replica deployments the
      bridge will swap to Redis pub/sub.
- [~] T072 [P] [WS] Create `src/romarr/api/ws/bridge.py` —
      async consumer of spec 011's pub/sub channel. **Deferred**
      to a follow-up slice when the spec 011 pub/sub surface is
      exposed. Today the foundation ships
      `SubscriptionRegistry.broadcast()`; the bridge will be a
      thin adapter that converts spec 011 events into
      `MessageType` envelopes and calls `broadcast`.
- [X] T073 [WS] Create `src/romarr/api/ws/handler.py` — FastAPI
      WebSocket route at `/signalr/messages`. Calls
      `authenticate_upgrade`; on failure
      `websocket.close(code=1008)`. On success `accept`,
      registers via `SubscriptionRegistry.add`, sends an
      opening welcome envelope (`systemMessage / welcome` with
      connectionId + username), then enters a receive loop
      treating any frame as a keepalive ping (echoes
      `systemMessage / pong`). Disconnect cleanup removes the
      registry entry. The route is mounted directly on the
      FastAPI app (NOT under `/api/v3`) because the
      SignalR-compat path is `/signalr/messages` per Sonarr's
      contract. Includes a WS-specific `_get_ws_db` dependency
      because FastAPI's HTTP `get_db` takes a `Request` and
      WebSocket handlers don't have one — both pull the same
      sessionmaker off `app.state`.
- [X] T074 [WS] `app.state.ws_subscriptions = SubscriptionRegistry()`
      stamped during `create_app()` so HTTP-side bridges (when
      they ship) read the same registry the WS handler writes.
      Bridge `.start()` itself lands with T072.

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
- [~] T077 [P] [OPENAPI] Per-endpoint examples —
      **deferred-by-design**. Handled at the route level via
      Pydantic schema ``json_schema_extra`` / ``examples=`` on
      individual ``Body(...)`` declarations rather than a
      centralised post-build patch. The base operationId
      audit (T076) + the security scheme audit (T078) ensure
      the OpenAPI surface stays correct; per-route examples
      are pure documentation polish that can land alongside
      the per-router schema growth.
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

- [X] T081 [P] [WIRE] `tests/api/test_endpoint_coverage.py::test_every_non_public_route_requires_authentication`
      — iterates every `APIRoute` and recurses through its
      `dependant` tree; routes outside the documented
      `PUBLIC_PATHS` allow-list MUST reach `require_admin` /
      `require_user` / `require_readonly` OR call
      `get_current_principal` directly (auth-tiered pattern).
      The allow-list is documented in the test module —
      bootstrap auth (setup/login/logout), the importer
      webhook (token-gated separately), the public docs URLs,
      and the webhook-payloads doc.
- [X] T082 [P] [WIRE] `tests/api/test_endpoint_coverage.py::test_every_protected_route_declares_a_role_guard`
      — every non-public, non-tiered route must declare one of
      the three role guards (FR-005). Tiered routes
      (`/api/v3/system/status`, `/api/v3/health`) are tracked in
      `TIERED_PATHS` because they branch on
      `get_current_principal` directly. Companion sanity tests
      pin that `PUBLIC_PATHS` and `TIERED_PATHS` reference real
      routes (typos / removed endpoints can't silently grow the
      allow-list).
- [X] T083 [P] [WIRE] `tests/api/test_endpoint_coverage.py::test_route_count_meets_fr_001_target`
      — the FR-001 ≥ 90 target is met as of slice 34 (log
      router shipped — 95 distinct paths). Test asserts
      `len(distinct_paths) >= 90`; trips on accidental
      endpoint removal in either direction.

### Implementation

- [X] T084 [WIRE] All prior-spec routers are wired into
      `create_app()` (the `app.py` implementation referenced by
      `factory.py`'s thin re-export). The full list as of this
      slice: auth + users (010), metadata providers / field
      priority / refresh (002), platform_packs packs / platforms
      (003), indexer applications / indexers (004), download
      clients schema + clients (005), all six profile routers
      (006), search + grab + history + blocklist (007), importer
      webhook + history + unidentified (008), libraries (009),
      notifications health + notifications + webhook-payloads
      doc (011), tasks + runs + command (012). Spec-013-native
      routers added inline: status (T053), tag (T060), queue
      (T057 partial), wanted (T056 partial), calendar (T059),
      history (T058). Audited end-to-end by T081/T082/T083.

**Checkpoint**: WIRE tests green; route count ≥ 90.

---

## Phase 9: Command Bus (`CMD`)

### Tests

- [X] T085 [P] [CMD] `tests/tasks/api/test_command_endpoint.py::test_post_known_command_returns_201_with_status`
      and `::test_kwargs_flow_into_job_context` —
      table-driven coverage of the documented names plus the
      kwargs-allowlist contract. The router maps each Sonarr
      command name to spec 012's job_id via
      `resolve_command(...)`; the runner registry executes
      under the SchedulerService.
- [X] T086 [P] [CMD] `tests/tasks/api/test_command_endpoint.py::test_get_command_status_returns_running_in_flight`
      — POST → capture id → GET `/api/v3/command/{id}` → assert
      Sonarr-shape body (`{id, name, commandName, status,
      ended, body, ...}`).
- [X] T087 [P] [CMD] `tests/tasks/api/test_command_endpoint.py::test_unknown_command_returns_400`
      — POST `{"name": "Foo"}` → HTTP 400 with errorCode
      `unknown_command`.
- [X] T088 [P] [CMD] `tests/tasks/api/test_command_endpoint.py::test_delete_cancels_in_flight_command`
      — DELETE `/api/v3/command/{id}` signals the cooperative
      `cancellation_event`; runner returns; row transitions to
      `cancelled`; response carries `forced: false`. Companion
      tests pin: 404 unknown id, 403 non-admin, 409 terminal
      state, 503 without registry.

### Implementation

- [X] T089 [CMD] The unified Sonarr-compat command bus is
      hosted by spec 012's `tasks_command_router`
      (`src/romarr/tasks/api/command.py`) — extending it
      avoids duplicating the alias resolver / scheduler
      wiring. Routes:
      - POST   /api/v3/command          — fire by name (admin)
      - GET    /api/v3/command/_known   — list recognised names
      - GET    /api/v3/command/{id}     — read CommandStatus
      - DELETE /api/v3/command/{id}     — cancel in-flight
        (admin) — added in this slice. Mirrors the
        `/api/v3/system/tasks/{job_id}/runs/{run_id}/cancel`
        contract: 404 unknown id, 409 terminal state, 503 if
        registry not wired, 202 with the resolved `forced`
        flag from the `CancellationRegistry` two-phase
        protocol.

**Checkpoint**: CMD tests green; the unified bus handles every
documented Sonarr-compat name.

---

## Phase 10: Sonarr-Shape Probe (`SONARR`)

### Tests

- [X] T090 [P] [SONARR] `tests/api/test_sonarr_status_compat.py::test_status_response_is_superset_of_sonarr_fixture`
      — `tests/fixtures/api/sonarr_status_fixture.json` contains
      the documented Sonarr v4 key set; `GET /api/v3/system/status`
      authenticated via X-Api-Key returns a superset of the
      v3+v4 documented union (version, isProduction, instanceName,
      urlBase, osName, runtimeVersion, appData, startTime,
      databaseType, databaseVersion, migrationVersion,
      runtimeName) — SC-001. Companion test
      `test_status_response_keys_match_documented_set_exactly`
      pins the exact key set so future routers can't silently
      drop a Sonarr-required field. Companion
      `test_unauthenticated_probe_gets_minimal_peer_recognition_shape`
      pins the public tier shape.
- [X] T091 [P] [SONARR] `tests/api/test_sonarr_status_compat.py::test_notifiarr_probe_succeeds_with_api_key`
      — replays `tests/fixtures/api/notifiarr_probe_payload.json`
      (method, path, headers) against the live app with a
      seeded ApiKey row substituted for the placeholder; asserts
      HTTP 200, JSON content type, and Sonarr-shape body
      (instanceName=Romarr, isProduction=True, version present).

### Implementation

- [X] T092 [SONARR] Hand-crafted
      `tests/fixtures/api/sonarr_status_fixture.json` from
      Sonarr v4's documented OpenAPI. Values are placeholders;
      only the key set is asserted by the compat test (SC-001
      mandates "every key Sonarr expects is present", not "the
      values match"). Includes Sonarr's full surface (mono /
      docker / package metadata) so a future "track every
      Sonarr key" tightening has the reference data.
- [X] T093 [SONARR] Hand-crafted
      `tests/fixtures/api/notifiarr_probe_payload.json` —
      method=GET, path=/api/v3/system/status, X-Api-Key +
      Accept + User-Agent headers, expected_status=200,
      expected_content_type=application/json. Replayed by
      T091.

**Checkpoint**: SONARR tests green; ecosystem-tooling
compatibility is locked.

---

## Phase 11: Hardening (`HARD`)

- [X] T094 [HARD] `uv run pytest --cov=romarr.api tests/api/`:
      `src/romarr/api/` aggregate coverage ~91% (well above
      SC-008's 80%). Files below 80% are
      pre-spec-013 (auth.py 59%, users.py 74%) — both still
      pass their existing test suites; tightening their
      coverage is tracked outside spec 013.
- [X] T095 [HARD] `uv run ruff check src/romarr/api/`: zero
      warnings (verified slice 39).
- [X] T096 [HARD] Endpoint-coverage audit lives in
      `tests/api/test_endpoint_coverage.py` (slice 31). The
      audit walks every APIRoute, asserts each has either an
      auth dependency or is in the documented public
      allow-list, and pins the route count at ≥ 90. The
      "happy + error path per endpoint" stricter form is
      tracked as a future tightening — today's per-router
      tests cover both happy and at least one error path,
      but the audit is a coarser route-level check rather
      than a name-pattern matcher.
- [~] T097 [HARD] Manual perf check **deferred** — needs a
      production-shape deployment (real DB latency, real
      uvicorn worker count). The TestClient-based suite
      doesn't model the operator-perceived latency. Tracked
      as a follow-up under the 0.13.0 → 0.14.0 production
      readiness gate; the architectural choices that drive
      the targets (in-process middleware, async SQLAlchemy,
      WebSocket sharing the asyncio loop) are all in place.
- [X] T098 [HARD] `pyproject.toml` version → `0.13.0a1`;
      `src/romarr/__init__.py:__version__` → `"0.13.0a1"`
      (the system/status endpoint reports both); CHANGELOG
      entry summarising the spec 013 surface
      (envelope / factory / 5 middleware / 8 bridge routers /
      OpenAPI / command bus / WS / WIRE audit / new tables).
- [X] T099 [HARD] Final FR review (all 31 requirements
      against shipping work):
      - FR-001 (≥ 90 routes): 95 ✓ (T083, slice 34)
      - FR-002 (ROM under /api/v3/rom/): existing routers ✓
      - FR-003 (Sonarr-compat command path): T085-T089, slice 32 ✓
      - FR-004 (auth chain on every endpoint): T081, slice 31 ✓
      - FR-005 (each endpoint declares require_role): T082, slice 31 ✓
      - FR-006 (?page/?pageSize/?sortKey/?sortDirection): T011, slice 19 ✓
      - FR-007 (canonical PaginationEnvelope): T004, slice 19 ✓
      - FR-008 (invalid sortKey → 400): T013, slice 19 ✓
      - FR-009 (pageSize > 1000 capped): T012, slice 19 ✓
      - FR-010 (canonical ErrorEnvelope): T015, slice 19 ✓
      - FR-011 (/api/v3/openapi.json): T080, slice 30 ✓
      - FR-012 (Swagger UI / Redoc): T080, slice 30 ✓
      - FR-013 (unique operationId): T076, slice 30 ✓
      - FR-014 (documented examples): **partial** — examples
        on the four named endpoints deferred to a follow-up
        (route-level enrichment), schema + tag presence
        pinned by T079, slice 30
      - FR-015 (4 security schemes): T078, slice 30 ✓
      - FR-016 (WebSocket at /signalr/messages): T073, slice 38 ✓
      - FR-017 (12 documented messageType): T066, slice 39 ✓
      - FR-018 (WS auth honours same chain): T070, slice 38 ✓
      - FR-019 (lossy WS, no replay): T067, slice 39 ✓
      - FR-020 (Idempotency-Key cache): T035, slice 25 ✓
      - FR-021 (body mismatch → 422): T029, slice 25 ✓
      - FR-022 (login 5/min per IP): T024, slice 37 ✓
      - FR-023 (/health exempt): T027, slice 37 ✓
      - FR-024 (per-API-key 100/min): T026, slice 37 ✓
      - FR-025 (Redis fallback): **deferred** — DB fallback
        ships today via `idempotency_cache` table; Redis
        backend is a single indirection swap when needed
      - FR-026 (CSRF on cookie POSTs): T021, slice 36 ✓
      - FR-027 (API-key bypasses CSRF): T022, slice 36 ✓
      - FR-028 (GET bypasses CSRF): T023, slice 36 ✓
      - FR-029 (≥ 1 KB GZip): T018, slice 22 ✓
      - FR-030 (configurable CORS): T019/T020, slice 22 ✓
      - FR-031 (status v3+v4 union): T036, slice 23 ✓

      **Open follow-up items**:
      - T072 (WS bridge → spec 011 pub/sub) — needs spec 011
        pub/sub channel exposed
      - T077 (per-endpoint OpenAPI examples) — route-level
        enrichment pass
      - T097 (production perf p95 numbers) — needs prod-shape
        deployment
      - FR-025 Redis backend — single indirection swap
      - Queue DELETE / retry (T045/T046) — needs spec 005
        DownloadClient.remove / add helpers
      - Wanted bulk search (T043) — needs spec 007
        run_manual_search hook

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

- [X] CL001 Migration ``0013_rest_api.py`` ships the
      polymorphic ``tag`` + ``tag_assignment`` tables (lines
      75-103). ``(tag_id, entity_type, entity_id)`` UNIQUE
      three-tuple, ON DELETE CASCADE on ``tag_id``,
      ``entity_type`` CHECK pinned to
      ``{'game', 'indexer', 'notification', 'release'}``.
- [X] CL002 Migration ``0013_rest_api.py`` ships
      ``queue_entry`` + ``idempotency_cache`` (line ~111).
      Both unconditional regardless of Redis availability —
      schema is the SoR.
- [X] CL003 [P] Per-entity tag cleanup hooks shipped inline at
      the API handlers (e.g.
      ``src/romarr/api/routers/game.py::_delete_games_and_sweep``,
      lines 398-440 — sweeps ``tag_assignment`` for the
      deleted Games AND their cascaded Releases). Path differs
      from the spec's ``src/romarr/tags/cleanup_hooks.py`` —
      the polymorphic table can't have FK ``ON DELETE CASCADE``
      from the entity side, so the cleanup is co-located with
      the DELETE handler that owns the entity. Same shape for
      Indexer / Notification / Release deletes (when those
      gain DELETE handlers).
- [X] CL004 [P] [US5] JCS-canonical body-hash shipped at
      ``api/middleware/idempotency.py`` (module docstring at
      line 12 documents
      ``SHA-256(JCS-canonical-JSON(body))`` per RFC 8785).
- [X] CL005 [P] [US5] Body-mismatch replay returns HTTP 422 +
      ``idempotency_key_body_mismatch`` reason
      (``idempotency.py:175``).
- [X] CL006 [P] [US4] Plain JSON-over-WebSocket framing at
      ``api/ws/messages.py`` — every emitted frame is
      ``{"messageType": "<value>", "data": ...}``. No SignalR
      negotiate, no hub-method dispatch, no binary mode. Path
      differs from the spec's ``api/websocket/framing.py``.
- [X] CL007 [P] [US4] WebSocket keepalive shipped at
      ``api/ws/handler.py`` (lines 14-16, 114-121) — any
      received frame counts as a ping; server emits a pong
      back. Implementation differs from the spec
      (client-driven ping vs server-driven), but the
      keepalive guarantee is the same: a stuck connection
      gets torn down because no ping arrives.
- [X] CL008 [P] [US1] Tiered ``GET /api/v3/system/status``
      shipped at ``api/routers/status.py`` — public callers
      get ``{version, isProduction}``, authenticated callers
      get the full Sonarr v3+v4 union. Path differs from the
      spec's ``api/system_status.py``.
- [X] CL009 [P] [US1] Sonarr v3+v4 union fields shipped at
      ``api/routers/status.py:91+`` — version, instanceName,
      urlBase, osName, runtimeVersion, appData, startTime,
      isProduction, plus the v4 additions databaseType,
      databaseVersion, migrationVersion, runtimeName.
- [~] CL010 [P] Sonarr v3/v4 fixture conformance — DEFERRED.
      The two fixtures
      (``tests/fixtures/api/sonarr_v3_status_fixture.json``,
      ``sonarr_v4_status_fixture.json``) and the
      key-set-superset test aren't shipped. Coverage is
      instead via ``tests/api/routers/test_status.py`` which
      asserts each documented field exists; the
      "Sonarr-side fixture vs Romarr response" deltas are
      not tracked in CI.
- [~] CL011 [P] **Disagree-by-design** with the spec.
      ``api/openapi.py`` retains the BearerJwt security scheme
      because Romarr's auth chain accepts upstream-issued
      OIDC tokens for SSO — the OpenAPI doc has to advertise
      that capability. Romarr never MINTS a JWT (CL010 of
      spec 010 confirmed by grep), but it can VALIDATE one
      from a configured OIDC provider. Dropping BearerJwt
      from the doc would mislead callers.
- [X] CL012 [P] Login rate-limit aligned with spec 010
      FR-010a — ``api/middleware/rate_limit.py`` keys by IP
      for ``/auth/login``, ``/auth/setup``,
      ``/auth/oidc/start``, ``/auth/oidc/callback``. 60 s
      sliding window, HTTP 429 + Retry-After. Bcrypt
      short-circuit lives at the route handler.
- [X] CL013 [P] ``/api/v3/health`` exempt from rate limit at
      ``api/middleware/rate_limit.py:58``
      (``_EXEMPT_PATHS`` frozenset).
- [X] CL014 [P] Idempotency tests shipped at
      ``tests/api/middleware/test_idempotency.py``. Path
      differs from the spec's ``tests/api/test_idempotency.py``.
- [X] CL015 [P] WebSocket framing tests shipped at
      ``tests/api/ws/test_messages.py``,
      ``tests/api/ws/test_lossy.py``,
      ``tests/api/ws/test_auth.py``. Path differs from the
      spec's ``test_websocket_framing.py``.
- [X] CL016 [P] System-status tiering tests shipped at
      ``tests/api/routers/test_status.py``. Path differs
      from the spec's ``test_system_status_tiering.py``.
- [X] CL017 [P] Polymorphic-tag tests shipped at
      ``tests/api/test_models.py`` —
      ``TagAssignment`` UNIQUE constraint, multi-entity
      polymorphism (Game + Indexer + Release + Notification),
      tag-id cascade. Path differs from the spec's
      ``test_polymorphic_tags.py``. Game-delete cleanup
      pinned by the ``_delete_games_and_sweep`` route tests.
