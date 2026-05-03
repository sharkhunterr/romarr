---

description: "Granular task list for indexers — Newznab/Torznab client, Prowlarr registration, rate limiting, circuit breaker"
---

# Tasks: Indexers (Prowlarr-First)

**Input**: Design documents from `specs/004-indexers/`
**Prerequisites**: `001-foundation`, `002-metadata-aggregation`, `003-platform-packs` shipped
**Tests**: MANDATORY (Constitution Article XVI; SC-009: ≥ 75% on indexers/)

**Organization**: 10 phases. Scaffolding → persistence → parser → client → rate-limit/breaker
→ connectivity/registry → Prowlarr surface → indexer CRUD API → RSS+health → hardening.

## Format: `[ID] [P?] [Phase] Description`

- `[P]` = parallelizable with other `[P]` tasks in the same phase.
- Phase tag short codes: `SCAF`, `PERS`, `PARSE`, `CLIENT`, `RATE`, `CONN`, `PROW`,
  `IDXAPI`, `RSSHEALTH`, `HARD`.

---

## Phase 1: Scaffolding (`SCAF`)

**Purpose**: bring up the module skeleton, dependencies, types, and shared errors.

- [X] T001 [SCAF] `bcrypt` already shipped via foundation + auth deps; direct
      ``bcrypt`` is available so the app-token hashing path uses it directly
      (passlib has a known incompatibility with bcrypt>=4.0). No pyproject
      change needed.
- [X] T002 [P] [SCAF] Created `src/romarr/indexers/__init__.py` re-exporting
      types + parsers + tokens + errors. Client / registry / RSS land in the
      next slice and will be added to the package surface there.
- [X] T003 [P] [SCAF] Created `src/romarr/indexers/errors.py` —
      `IndexerError`, `IndexerAuthError`, `IndexerProtocolError`,
      ``CircuitOpenError`` re-exported from foundation (Article III),
      ``RateLimitDelayed`` informational marker (NOT raised).
- [X] T004 [P] [SCAF] Created `src/romarr/indexers/types.py` —
      `FieldProvenance`, `DatSource`, `ParsedTorznabAttr`,
      `IndexerCapabilities`, `SearchResult`, `RssResult`,
      `IndexerHealthIssue` Pydantic models from `data-model.md`.
- [X] T005 [SCAF] Created `tests/indexers/conftest.py` with the
      `torznab_response(name)` fixture loader.

**Checkpoint**: imports work; lint+types green; no behaviour added.

---

## Phase 2: Persistence (`PERS`)

**Purpose**: 2 new tables, SQLAlchemy models, Pydantic schemas, encryption + token
helpers, and the Alembic migration.

### Tests (write first; must fail)

- [X] T006 [P] [PERS] `tests/indexers/test_models.py::test_indexer_round_trip`
      — column round-trip + default values (priority=25, timeout_seconds=30,
      result_limit=100).
- [X] T007 [P] [PERS] `tests/indexers/test_models.py::test_unique_url_per_impl`
      — second insertion of `(implementation, url)` raises an `IntegrityError`.
- [X] T008 [P] [PERS] `tests/indexers/test_models.py::test_application_unique_prowlarr_url`
      — second insertion of the same `prowlarr_url` raises.
- [X] T009 [P] [PERS] `tests/indexers/test_tokens.py::test_token_format`
      — URL-safe base64 of 32 random bytes; consecutive calls differ.
- [X] T010 [P] [PERS] `tests/indexers/test_tokens.py::test_hash_and_verify_round_trip`
      + companion negative tests cover wrong-token / empty / garbage-hash /
      per-call salt.
- [X] T011 [P] [PERS] `tests/indexers/test_migration_0004.py` — applying the
      migration creates both tables with the documented constraints; the
      `indexer.download_client_id` column exists but has no FK yet (the FK
      arrives in spec 005).

### Implementation

- [X] T012 [PERS] Created `src/romarr/indexers/models.py` — `Indexer` +
      `Application` SQLAlchemy 2.0 models matching `data-model.md` with
      every CHECK constraint and the unique indexes.
- [X] T013 [P] [PERS] Pydantic schemas shipped at
      ``src/romarr/indexers/schemas.py`` —
      ``IndexerRead`` / ``IndexerCreate`` / ``IndexerUpdate``,
      ``ApplicationRead`` / ``ApplicationCreate``, and
      ``IndexerSchema``. Consumed by the spec-013 routers
      (``indexers/api/indexers.py``,
      ``indexers/api/applications.py``).
- [X] T014 [P] [PERS] Created `src/romarr/indexers/tokens.py` — uses
      ``bcrypt`` directly (passlib's ``bcrypt_sha256`` backend has a
      known incompatibility with modern ``bcrypt>=4.0``); the
      ``token_urlsafe(32)`` token is 43 chars, well under bcrypt's
      72-byte input cap, so no SHA256 prehash bridge is needed.
- [X] T015 [PERS] Authored
      `src/romarr/db/alembic/versions/0004_indexers.py` — DDL for both
      tables, the (implementation, url) + prowlarr_url uniques, and the
      ``indexer.download_client_id`` column without an FK (the FK arrives
      in spec 005).

**Checkpoint**: `alembic upgrade head` is clean; PERS tests green.

---

## Phase 3: XML Parsers (`PARSE`)

**Purpose**: pure-Python parsers for `t=caps` and `t=search` plus extended-attribute
extraction with provenance, plus same-GUID dedup. No HTTP; no DB.

### Tests

- [X] T016 [P] [PARSE] `tests/indexers/parser/test_caps.py::test_valid_full_caps`
      + companion ``test_no_search_block_returns_empty_searching`` and
      noise-tolerance test.
- [X] T017 [P] [PARSE] `tests/indexers/parser/test_caps.py::test_no_search_block_returns_empty_searching`
      — caps without ``<searching>`` returns an empty searching map.
- [X] T018 [P] [PARSE] `tests/indexers/parser/test_search.py::test_vanilla_no_extended_attrs_leaves_provenance_null`
      — vanilla RSS leaves every ``*_provenance`` NULL (filename fallback
      will fill these in the CLIENT slice).
- [X] T019 [P] [PARSE] `tests/indexers/parser/test_extended_attrs.py::test_torznab_namespace_region_normalised`
      — region in ``torznab:`` namespace round-trips with
      ``provenance = TORZNAB``.
- [X] T020 [P] [PARSE] `tests/indexers/parser/test_extended_attrs.py::test_grabarr_namespace_region_overrides_torznab`
      — when both namespaces emit the same attr, ``grabarr:`` wins with
      ``provenance = GRABARR``.
- [X] T021 [P] [PARSE] `tests/indexers/parser/test_extended_attrs.py::test_unknown_region_value_dropped`
      — unknown region (``ZZ``) is dropped silently; the field stays
      NULL.
- [X] T022 [P] [PARSE] `tests/indexers/parser/test_dedup.py::test_same_guid_collapsed_with_union_categories`
      — same GUID across two ``<item>`` rows collapses with the union of
      categories on the survivor (FR-026, SC-008).
- [X] T023 [P] [PARSE] `tests/indexers/parser/test_search.py::test_property_parser_tolerates_random_bytes`
      — hypothesis fuzz: random bytes either parse to a list or raise
      ``IndexerProtocolError``; never any other exception type.

### Implementation

- [X] T024 [PARSE] Created `src/romarr/indexers/parser/caps.py` — pure
      ``parse_caps(xml_bytes: bytes) -> IndexerCapabilities``.
- [X] T025 [PARSE] Created `src/romarr/indexers/parser/extended_attrs.py` —
      ``extract_extended_attrs`` walks ``{*}attr`` children; namespace URI
      drives provenance; ``normalize_region`` + ``normalize_languages``
      ship a built-in dictionary (foundation didn't ship a translate-
      regions helper after all, so we ship our own dictionary scoped to
      what indexer payloads actually emit).
- [X] T026 [PARSE] Created `src/romarr/indexers/parser/dedup.py` — pure
      ``dedup_by_guid`` collapses same-GUID rows with category union.
- [X] T027 [PARSE] Created `src/romarr/indexers/parser/search.py` — pure
      ``parse_search(xml_bytes, indexer_id) -> list[SearchResult]``;
      every extended attr name → SearchResult slot mapping (region /
      languages / revision / dump_tags / hash_sha1 / hash_crc32 /
      naming_convention / dat_source / size / seeders / peers / files /
      info_hash / magnet_url / category) with provenance preserved.
      Calls ``dedup_by_guid`` before returning.

**Checkpoint**: every parser test green including the dedup and namespace
crossover; the parser is importable and exercisable from a REPL.

---

## Phase 4: Newznab/Torznab Client (`CLIENT`)

**Purpose**: HTTP layer + filename-fallback orchestration.

### Tests

- [X] T028 [P] [CLIENT] `tests/indexers/test_client_caps.py::test_caps_happy_path`
      + companion ``test_caps_includes_apikey_in_query`` and
      ``test_caps_omits_apikey_when_none``.
- [X] T029 [P] [CLIENT] `tests/indexers/test_client_search.py::test_search_with_extended_attrs`
      — extended attrs respected; companion ``test_search_carries_query_and_categories``
      asserts the outbound URL params (``t=search&q=...&cat=...&limit=100``).
- [X] T030 [P] [CLIENT] `tests/indexers/test_client_search.py::test_filename_fallback_fills_missing_provenance`
      — vanilla RSS → the dispatcher fills region / convention with
      ``*_provenance = FILENAME`` (FR-004).
- [X] T031 [P] [CLIENT] `tests/indexers/test_client_failure_modes.py::test_malformed_xml_in_search_returns_empty_with_health_issue`
      — malformed XML returns ``[]`` instead of escalating; lxml's
      ``recover=True`` is forgiving so the parser-error path is also
      exercised by truncated input under the property-based test.
- [X] T032 [P] [CLIENT] `tests/indexers/test_client_failure_modes.py::test_5xx_raises_protocol_error`
      — 503 → ``IndexerProtocolError`` after retries; a
      ``protocol``-category health issue is recorded.
- [X] T033 [P] [CLIENT] `tests/indexers/test_client_failure_modes.py::test_401_raises_auth_error_distinctly`
      + ``test_403_also_raises_auth_error`` — auth errors map to
      ``IndexerAuthError`` and are recorded with category=``auth``,
      distinct from protocol failures.

### Implementation

- [X] T034 [CLIENT] Created `src/romarr/indexers/client.py` —
      ``NewznabClient`` with ``caps()`` / ``search()`` / ``rss()``. Uses
      httpx async; tenacity 3-attempt retry with exponential-jitter
      backoff for ``IndexerProtocolError``; wrapped by the foundation
      ``CircuitBreaker``. The search method post-processes parsed
      results with the default filename-parser dispatcher for any
      field whose ``*_provenance is None`` (FR-004).
- [X] T035 [CLIENT] Wired ``IndexerHealthIssue`` emission into every
      exception path via ``_record_issue``. Each issue is also logged
      via structlog-style ``extra`` so even tests without direct
      access to ``health_issues`` see the structured record. The
      ``message`` LogRecord-reserved key is renamed to ``detail`` to
      avoid Python's logging-framework collision.

**Checkpoint**: client tests green; client gracefully handles every documented
failure mode without crashing.

---

## Phase 5: Rate Limiter & Circuit Breaker Reuse (`RATE`)

**Purpose**: per-indexer monotonic-clock rate limiter; confirm reuse of the
foundation circuit breaker.

### Tests

- [X] T036 [P] [RATE] `tests/indexers/test_rate_limiter.py::test_minimum_gap_enforced`
      — second acquire is delayed roughly the gap (SC-005). The test
      uses 0.05 s instead of 5 s for speed; the invariant is the same.
- [X] T037 [P] [RATE] `tests/indexers/test_rate_limiter.py::test_no_delay_when_zero`
      — ``seconds=0`` makes ``acquire`` a true no-op.
- [X] T038 [P] [RATE] `tests/indexers/test_rate_limiter.py::test_monotonic_clock_used`
      — injecting a clock that jumps backward still enforces the gap
      (FR-009).
- [X] T039 [P] [RATE] `tests/indexers/test_rate_limiter.py::test_per_indexer_isolation`
      — two ``RateLimiter`` instances don't share state; companion
      ``test_concurrent_acquires_serialized`` covers the same-limiter
      multi-acquire path.
- [X] T040 [P] [RATE] `tests/indexers/test_circuit_breaker_reuse.py::test_breaker_class_is_the_foundation_one`
      — every module under ``romarr.indexers`` that imports
      ``CircuitBreaker`` references the foundation's class object, NOT
      a re-defined one (Constitution Article III). Companion
      ``test_circuit_open_error_re_exported`` confirms the same for
      the exception type.
- [X] T041 [P] [RATE] `tests/indexers/test_circuit_breaker_reuse.py::test_breaker_isolation_between_indexers`
      — opening one breaker leaves the other untouched (SC-004).

### Implementation

- [X] T042 [RATE] Created `src/romarr/indexers/rate_limiter.py` — async
      ``RateLimiter(seconds, clock=time.monotonic)`` with
      ``await acquire()`` returning the actual delay (used by tests +
      structured logging). The internal lock serializes concurrent
      acquirers so the gap calculation stays consistent. The registry
      will cache one instance per indexer id (Phase 6).

**Checkpoint**: rate limiter tests green; isolation guarantees verified
across indexers and across rate-limit + breaker.

---

## Phase 6: Connectivity & Registry (`CONN`)

**Purpose**: indexer registry that loads enabled indexers, decrypts API keys,
and exposes a connectivity tester.

### Tests

- [X] T043 [P] [CONN] `tests/indexers/test_registry.py::test_loads_only_enabled_indexers`
      — disabled indexers (every enable_* False) excluded.
- [X] T044 [P] [CONN] `tests/indexers/test_registry.py::test_decrypts_api_key`
      + ``test_rate_limiter_cached_across_calls`` covers the
      registry's cache invariant.
- [X] T045 [P] [CONN] `tests/indexers/test_connectivity.py::test_caps_only_when_search_block_absent`
      — caps with no ``<searching>`` reports caps_ok=True / search_ok=None
      (operator-actionable signal, FR-006).
- [X] T046 [P] [CONN] `tests/indexers/test_connectivity.py::test_caps_then_search_full_success`
      + ``test_caps_failure_returns_structured_result`` +
      ``test_caps_succeeds_search_fails_with_auth`` cover the full
      decision tree.

### Implementation

- [X] T047 [CONN] Created `src/romarr/indexers/registry.py` — async
      ``IndexerRegistry`` with ``load_enabled(session)`` and
      ``get(session, indexer_id)``. Per-indexer ``RateLimiter`` +
      ``CircuitBreaker`` cached on the registry so gap-enforcement +
      failure-window state survive across calls. ``save`` / ``delete``
      will live in the API slice.
- [X] T048 [CONN] Created `src/romarr/indexers/connectivity.py` —
      ``test_connectivity(client) -> ConnectivityTestResult`` (caps
      + minimal search if caps advertises search). Structured result,
      never raises.

**Checkpoint**: registry tests green; connectivity tester correctly handles
both happy and degraded responses.

---

## Phase 7: Prowlarr Surface (`PROW`)

**Purpose**: implement the endpoints Prowlarr expects from a downstream *arr.

### Tests

- [X] T049 [P] [PROW] `tests/indexers/api/test_applications_endpoints.py::test_register_returns_token_once`.
- [X] T050 [P] [PROW] `tests/indexers/api/test_applications_endpoints.py::test_duplicate_url_returns_409`.
- [X] T051 [P] [PROW] `tests/indexers/api/test_applications_endpoints.py::test_delete_unregisters`.
- [X] T052 [P] [PROW] `tests/indexers/api/test_indexer_crud_endpoints.py::test_schema_endpoint_returns_known_implementations`.
- [ ] T053 [P] [PROW] Inbound Prowlarr-pushed indexer with X-App-Token
      verification. **Deferred** — the inbound auth path uses
      ``X-App-Token`` header verification; spec 010's cookie-based
      auth chain doesn't yet expose a token-header alternative.
      A follow-up slice ties the bcrypt-verify path into the auth
      chain. The DB-side ``source='prowlarr'`` + ``prowlarr_app_id``
      FK is wired and tested.
- [ ] T054 [P] [PROW] PUT a Prowlarr-pushed indexer without the
      app_token → HTTP 403. **Deferred** alongside T053.
- [X] T055 [P] [PROW] The Prowlarr-callback path is exercised
      indirectly by ``test_delete_removes_indexer``. The
      ``notify_prowlarr_change`` helper is best-effort: failures log
      but never block the local delete (FR-016).

### Implementation

- [X] T056 [PROW] Created `src/romarr/indexers/api/applications.py` —
      FastAPI router for ``GET/POST/DELETE /api/v3/applications`` and
      ``GET /{id}``. POST encrypts ``prowlarr_api_key``, generates the
      token, stores its bcrypt hash, returns the plaintext exactly once
      via :class:`ApplicationCreateResult`.
- [X] T057 [PROW] Created `src/romarr/indexers/prowlarr.py` —
      ``notify_prowlarr_change`` POSTs to the Prowlarr instance's
      ``/api/v1/applications/notify`` endpoint with a best-effort
      contract (returns False on failure; never raises).

**Checkpoint**: every Prowlarr-shape fixture under
`tests/fixtures/prowlarr_payloads/` round-trips through the registration +
indexer-push flow.

---

## Phase 8: Indexer CRUD API (`IDXAPI`)

**Purpose**: the endpoints operators (and Prowlarr) use to manage indexers.

### Tests

- [X] T058 [P] [IDXAPI] `tests/indexers/api/test_indexer_crud_endpoints.py::test_post_with_test_true_runs_connectivity_first`.
- [X] T059 [P] [IDXAPI] `tests/indexers/api/test_indexer_crud_endpoints.py::test_put_re_encrypts_when_api_key_present`.
- [X] T060 [P] [IDXAPI] `tests/indexers/api/test_indexer_crud_endpoints.py::test_post_duplicate_returns_409`.
- [X] T061 [P] [IDXAPI] `tests/indexers/api/test_indexer_crud_endpoints.py::test_test_endpoint_runs_connectivity`
      + ``test_create_persists_indexer`` + ``test_delete_removes_indexer``
      + ``test_list_and_get_round_trip``.

### Implementation

- [X] T062 [IDXAPI] Created `src/romarr/indexers/api/indexers.py` —
      FastAPI router for ``GET/POST/PUT/DELETE /api/v3/indexer*``,
      ``GET /api/v3/indexer/schema``, and ``POST /api/v3/indexer/{id}/test``.
      Auth uses the real ``require_admin`` from spec 010 (FR-026a).
- [X] T063 [IDXAPI] The connectivity-test endpoint is folded into
      ``api/indexers.py``; a separate ``api/tests.py`` would be a
      one-route file, so we kept it inline alongside the other
      indexer endpoints.

**Checkpoint**: every endpoint exercised; HTTP status codes match the spec;
encrypted blobs never leak in responses.

---

## Phase 9: RSS Sync & Health (`RSSHEALTH`)

**Purpose**: ship the RSS-sync orchestration class and the health-issue
producer (the `/api/v3/health` endpoint is in the Notifications spec).

### Tests

- [X] T064 [P] [RSSHEALTH] `tests/indexers/test_rss.py::test_sync_all_iterates_only_rss_enabled`
      — three indexers, two with ``enable_rss=True``; only those two
      are called.
- [X] T065 [P] [RSSHEALTH] `tests/indexers/test_rss.py::test_sync_indexer_isolated`
      — ``sync_indexer(id)`` only touches that one.
- [X] T066 [P] [RSSHEALTH] `tests/indexers/test_rss.py::test_failures_do_not_propagate`
      — one indexer's 503 doesn't cancel the other; the failing
      indexer's ``last_health_ok=False`` row is stamped.
- [X] T067 [P] [RSSHEALTH] `tests/indexers/test_health.py::test_record_health_issue_writes_columns`
      + ``test_clear_health_resets_columns`` cover the round-trip.

### Implementation

- [X] T068 [RSSHEALTH] Created `src/romarr/indexers/rss.py` —
      ``IndexerRssSync`` with ``sync_all_enabled_indexers()`` and
      ``sync_indexer(id)``. ``asyncio.gather(..., return_exceptions=True)``
      isolates failures (FR-019a). Per-task health writes use
      ``commit=False``; the orchestrator commits once after gather to
      avoid SQLAlchemy's ``IllegalStateChangeError`` from concurrent
      ``session.commit()`` on a shared AsyncSession.
- [X] T069 [RSSHEALTH] Created `src/romarr/indexers/health.py` —
      ``record_health_issue(session, issue, *, commit=True)`` writes
      ``last_health_at`` / ``last_health_ok`` / ``last_health_error``;
      ``clear_health(session, *, indexer_id, commit=True)`` resets on
      next success. Both helpers expose a ``commit`` toggle so the
      RSS orchestrator can stage writes without colliding on commits.

**Checkpoint**: RSS sync isolates failures; health producer touches only
the failing indexer's row.

---

## Phase 10: Hardening (`HARD`)

- [X] T070 [HARD] Coverage on ``romarr.indexers`` measured at
      **84.1%** (863/1026 stmts), comfortably above the 75% SC-009
      target. Per-file weak spots: ``prowlarr.py`` (33% — the
      callback path is best-effort by design and only exercised
      indirectly by the indexer-delete test), ``api/indexers.py``
      (62% — exception branches), ``api/applications.py`` (68% —
      same).
- [X] T071 [HARD] ``ruff check src/ tests/`` clean.
- [X] T072 [HARD] Article III invariant pinned by
      ``tests/indexers/test_circuit_breaker_reuse.py::test_breaker_class_is_the_foundation_one``
      (added in CLIENT + RATE slice). Walks every
      ``romarr.indexers.*`` module and asserts ``CircuitBreaker``
      references resolve to the foundation's class object.
- [ ] T073 [HARD] Manual 200-result perf check. **Deferred** —
      needs a 200-item Torznab fixture; the test infra to record
      one is parallel work to the perf-cassette deferred from
      spec 002.
- [X] T074 [HARD] Bumped ``pyproject.toml`` and
      ``romarr.__version__`` to ``0.4.0a1``; CHANGELOG entry
      records the full Spec 004 manifest.
- [ ] T075 [HARD] Formal FR-001 → FR-026 walk-through. **Deferred**
      alongside the spec 002 + spec 003 parallel deferrals; every
      FR has a task-checked artifact above already.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (SCAF)**: depends on the three prerequisite specs being shipped.
- **Phase 2 (PERS)**: depends on Phase 1.
- **Phase 3 (PARSE)**: depends on Phase 1 only — pure functions, no DB.
- **Phase 4 (CLIENT)**: depends on Phases 1, 3, and the foundation
  identification module.
- **Phase 5 (RATE)**: depends on Phase 1 and the foundation breaker.
- **Phase 6 (CONN)**: depends on Phases 2, 4, 5.
- **Phase 7 (PROW)**: depends on Phase 6.
- **Phase 8 (IDXAPI)**: depends on Phase 6.
- **Phase 9 (RSSHEALTH)**: depends on Phase 4.
- **Phase 10 (HARD)**: depends on Phases 7, 8, 9.

### Within-Phase Parallelism

- Phase 1: T002–T004 in parallel.
- Phase 2: T006–T011 (tests) in parallel; T012–T014 (implementation
  files) in parallel.
- Phase 3: T016–T023 (tests) in parallel; T024–T027 (implementation files)
  sequential because they layer.
- Phase 4: T028–T033 (tests) in parallel.
- Phase 5: T036–T041 (tests) in parallel.
- Phase 6: T043–T046 in parallel.
- Phase 7: T049–T055 in parallel.
- Phase 8: T058–T061 in parallel.
- Phase 9: T064–T067 in parallel.

### Critical Path

`SCAF → PERS → PARSE → CLIENT → CONN → IDXAPI → HARD`. The Prowlarr
phase (PROW) and the RSS+health phase (RSSHEALTH) can run in parallel
once CONN and CLIENT are stable, respectively.

### Implementation Strategy

- **Day 1**: Phases 1–2 (scaffolding + persistence + tokens + migration).
- **Day 2**: Phase 3 (parsers) — pure functions, fast iteration; the ≥30
  Torznab fixtures pay back here.
- **Day 3**: Phase 4 (client) + Phase 5 (rate-limit / breaker reuse) in
  parallel by one developer.
- **Day 4**: Phase 6 (registry + connectivity) + Phase 9 (RSS + health)
  in parallel.
- **Day 5**: Phase 7 (Prowlarr surface) + Phase 8 (indexer CRUD API) in
  parallel — they touch different routers.
- **Day 6**: Phase 10 (hardening).

This sizing assumes one developer working full-time. With two, Phases 7
and 8 split cleanly.

---

## Notes

- `[P]` tasks change different files only.
- Tests are written BEFORE implementation in every phase.
- Stop at any phase checkpoint — the indexer layer is delivered
  incrementally; each phase is independently shippable.
- Avoid: implementing indexer-specific protocols (Constitution Article
  VII forbids it); building a search engine (Search spec); scheduling
  RSS sync (Tasks/Scheduler spec); cookie-based or captcha-protected
  indexers (out of scope); duplicating circuit-breaker code from
  `identification/hashmatch/`.
- Constitutional invariant under test (SC-004 + T040 + T041): there is
  exactly ONE circuit-breaker implementation in the codebase, and the
  indexer module reuses it from foundation.

## Phase: Clarification Tasks (Session 2026-04-29)

- [ ] CL001 Migration `0004_indexers.py` adds two columns to `indexer`: `timeout_seconds INTEGER NOT NULL DEFAULT 30 CHECK (5..120)` and `result_limit INTEGER NOT NULL DEFAULT 100 CHECK (1..500)`
- [ ] CL002 [P] [US1] Apply per-indexer `timeout_seconds` to every outbound call in `src/romarr/indexers/client.py` (`t=caps`, `t=search`, `t=rss`); timeout counts as a circuit-breaker failure (FR-009a)
- [ ] CL003 [P] [US1] Implement concurrent search fan-out via `asyncio.gather(..., return_exceptions=True)` in `src/romarr/indexers/search.py` — per-indexer failures isolated; surfaced as `IndexerHealthIssue`; merged result list = union of successful responses (FR-019a)
- [ ] CL004 [P] [Admin] Wire admin-role gate on `POST /api/v3/applications`, `GET /api/v3/applications`, `DELETE /api/v3/applications/{id}` in `src/romarr/indexers/api.py` (FR-013a)
- [ ] CL005 [P] [US7] Apply per-indexer `result_limit` in `src/romarr/indexers/parser.py` — pass `limit=…` to indexer when caps advertise pagination support; otherwise truncate after parsing with INFO log (FR-026a)
- [ ] CL006 [P] Add tests in `tests/indexers/test_timeout.py` covering: in-budget call succeeds; over-budget timeout trips breaker; sibling indexers unaffected
- [ ] CL007 [P] Add tests in `tests/indexers/test_concurrent_search.py` covering: 3 indexers in parallel, 1 fails — other 2 results returned; total wall-clock ≈ slowest healthy
- [ ] CL008 [P] Add tests in `tests/indexers/test_application_auth.py` covering: registration without admin → 401; with admin → 201 + app token returned once; subsequent indexer push → uses app token only; deleted app → token rejected
- [ ] CL009 [P] Add tests in `tests/indexers/test_result_limit.py` covering: 100-row default cap; configurable up to 500; over-cap truncation with INFO log
