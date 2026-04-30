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
- [ ] T013 [P] [PERS] Pydantic `IndexerRead/Create/Update` +
      `ApplicationRead/Create` + `IndexerSchema` schemas. **Deferred** to
      the API slice — schemas are only consumed by the routers.
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

- [ ] T028 [P] [CLIENT] `tests/indexers/test_client_caps.py::test_caps_happy_path`
      — respx-mocked `t=caps` returns `valid_full.xml`; assert the client
      returns the parsed capabilities.
- [ ] T029 [P] [CLIENT] `tests/indexers/test_client_search.py::test_search_with_extended`
      — respx-mocked `t=search&q=...&cat=1000`; assert results are parsed and
      extended attrs respected.
- [ ] T030 [P] [CLIENT] `tests/indexers/test_client_search.py::test_filename_fallback`
      — respx-mocked search returning vanilla XML; assert
      `SearchResult.region`/`languages`/`revision` populated from foundation's
      filename parser dispatcher with `*_provenance = FILENAME` (FR-004).
- [ ] T031 [P] [CLIENT] `tests/indexers/test_client_failure_modes.py::test_malformed_xml`
      — respx-mocked malformed XML response; assert no exception escapes the
      client; an `IndexerHealthIssue(category='parser')` is emitted; the
      result list is empty.
- [ ] T032 [P] [CLIENT] `tests/indexers/test_client_failure_modes.py::test_5xx`
      — respx-mocked 503; assert `IndexerProtocolError` raised, recorded in
      the breaker.
- [ ] T033 [P] [CLIENT] `tests/indexers/test_client_failure_modes.py::test_auth_error`
      — respx-mocked 401; assert `IndexerAuthError` raised distinctly from
      `IndexerProtocolError`.

### Implementation

- [ ] T034 [CLIENT] Create `src/romarr/indexers/client.py` — `NewznabClient`
      class with `caps()`, `search(q, categories)`, `rss(categories)`. Uses
      httpx async, decorated by tenacity (3 attempts, exponential backoff) and
      wrapped by the foundation circuit breaker. The search method post-
      processes results with foundation filename parsing for any field
      missing from extended attrs.
- [ ] T035 [CLIENT] Wire `IndexerHealthIssue` emission into the client's
      exception paths via `health.py` (Phase 9 stub for now; producer here).

**Checkpoint**: client tests green; client gracefully handles every documented
failure mode without crashing.

---

## Phase 5: Rate Limiter & Circuit Breaker Reuse (`RATE`)

**Purpose**: per-indexer monotonic-clock rate limiter; confirm reuse of the
foundation circuit breaker.

### Tests

- [ ] T036 [P] [RATE] `tests/indexers/test_rate_limiter.py::test_minimum_gap_enforced`
      — configure 5 s; record outbound timestamps for 2 sequential calls;
      assert the gap is ≥ 5 s (SC-005).
- [ ] T037 [P] [RATE] `tests/indexers/test_rate_limiter.py::test_no_delay_when_zero`
      — `rate_limit_seconds = 0`; back-to-back calls dispatch immediately.
- [ ] T038 [P] [RATE] `tests/indexers/test_rate_limiter.py::test_monotonic_clock_used`
      — patch `time.time()` to jump backward; the limiter still enforces the
      gap (FR-009).
- [ ] T039 [P] [RATE] `tests/indexers/test_rate_limiter.py::test_per_indexer_isolation`
      — two indexers, each with a 5 s rate limit; calls to indexer A do not
      affect indexer B's gap.
- [ ] T040 [P] [RATE] `tests/indexers/test_circuit_breaker_reuse.py` — assert
      that `from romarr.identification.hashmatch.circuit_breaker import CircuitBreaker`
      is the ONLY breaker import in the indexers module; no second
      implementation exists (Constitution Article III).
- [ ] T041 [P] [RATE] `tests/indexers/test_circuit_breaker_reuse.py::test_isolation_between_indexers`
      — open the breaker for indexer A; confirm calls to indexer B are
      unaffected (SC-004).

### Implementation

- [ ] T042 [RATE] Create `src/romarr/indexers/rate_limiter.py` — async
      `RateLimiter(seconds)` with `await acquire()` that enforces the
      monotonic-clock gap; one instance per indexer id, cached in the
      `IndexerRegistry`.

**Checkpoint**: rate limiter tests green; isolation guarantees verified
across indexers and across rate-limit + breaker.

---

## Phase 6: Connectivity & Registry (`CONN`)

**Purpose**: indexer registry that loads enabled indexers, decrypts API keys,
and exposes a connectivity tester.

### Tests

- [ ] T043 [P] [CONN] `tests/indexers/test_registry.py::test_loads_enabled_only`
      — disabled indexers excluded from the registry's enumeration.
- [ ] T044 [P] [CONN] `tests/indexers/test_registry.py::test_decrypts_api_key`
      — encrypt a key, persist it, load via the registry, assert the in-
      memory client carries the plaintext.
- [ ] T045 [P] [CONN] `tests/indexers/test_connectivity.py::test_caps_only_when_no_search_block`
      — a caps response with no search block reports success only on caps;
      operator is asked to enable search manually (FR-006 + edge case).
- [ ] T046 [P] [CONN] `tests/indexers/test_connectivity.py::test_caps_then_search`
      — caps reports search support; the system also runs `t=search&q=test&cat=1000`
      and confirms search works before declaring success.

### Implementation

- [ ] T047 [CONN] Create `src/romarr/indexers/registry.py` — async
      `IndexerRegistry` with `load_enabled(session) -> list[NewznabClient]`,
      `get(session, indexer_id)`, `save(session, IndexerCreate)` (encrypts
      api_key on the way in), `delete(session, id)`.
- [ ] T048 [CONN] Create `src/romarr/indexers/connectivity.py` —
      `test_connectivity(client) -> ConnectivityTestResult` (caps + minimal
      search if caps include search; structured result, never raises).

**Checkpoint**: registry tests green; connectivity tester correctly handles
both happy and degraded responses.

---

## Phase 7: Prowlarr Surface (`PROW`)

**Purpose**: implement the endpoints Prowlarr expects from a downstream *arr.

### Tests

- [ ] T049 [P] [PROW] `tests/indexers/api/test_applications_endpoints.py::test_register_returns_token_once`
      — POST a Prowlarr-style payload to `/api/v3/applications`; assert
      response carries the plaintext app_token; second GET on the row never
      returns the plaintext.
- [ ] T050 [P] [PROW] `tests/indexers/api/test_applications_endpoints.py::test_duplicate_url_409`
      — POST a second registration with the same `prowlarr_url`; assert
      HTTP 409.
- [ ] T051 [P] [PROW] `tests/indexers/api/test_applications_endpoints.py::test_delete_unregisters`
      — DELETE the Application; subsequent inbound calls bearing its token
      are rejected (token hash gone).
- [ ] T052 [P] [PROW] `tests/indexers/api/test_indexer_schema_endpoint.py`
      — GET `/api/v3/indexer/schema`; assert the response carries the
      Newznab + Torznab schema entries Prowlarr expects.
- [ ] T053 [P] [PROW] `tests/indexers/api/test_indexer_crud_endpoints.py::test_prowlarr_pushes_indexer`
      — POST an indexer with `source = 'prowlarr'` and a valid app_token;
      assert it materializes with the expected provenance.
- [ ] T054 [P] [PROW] `tests/indexers/api/test_indexer_crud_endpoints.py::test_prowlarr_indexer_not_editable_manually`
      — attempt to PUT a Prowlarr-pushed indexer without the app_token;
      assert HTTP 403 with a clear message.
- [ ] T055 [P] [PROW] `tests/indexers/test_prowlarr_callbacks.py::test_local_delete_notifies_prowlarr`
      — delete a Prowlarr-pushed indexer locally; respx-assert a callback
      hits Prowlarr's expected endpoint; respx-assert callback failure
      logs a warning but does NOT block the local delete (FR-016).

### Implementation

- [ ] T056 [PROW] Create `src/romarr/indexers/api/applications.py` —
      FastAPI router for `GET/POST/DELETE /api/v3/applications`. The POST
      handler: encrypts `prowlarr_api_key`, generates the token, stores its
      hash, returns the plaintext exactly once.
- [ ] T057 [PROW] Create `src/romarr/indexers/prowlarr.py` —
      `notify_prowlarr_change(application, change)` async helper that calls
      back into Prowlarr's expected endpoint with best-effort error handling.

**Checkpoint**: every Prowlarr-shape fixture under
`tests/fixtures/prowlarr_payloads/` round-trips through the registration +
indexer-push flow.

---

## Phase 8: Indexer CRUD API (`IDXAPI`)

**Purpose**: the endpoints operators (and Prowlarr) use to manage indexers.

### Tests

- [ ] T058 [P] [IDXAPI] `tests/indexers/api/test_indexer_crud_endpoints.py::test_post_with_test_true`
      — POST `/api/v3/indexer?test=true`; happy-path success persists the
      row; failed connectivity (respx-mocked 401) returns HTTP 400 and zero
      rows are written (FR-007).
- [ ] T059 [P] [IDXAPI] `tests/indexers/api/test_indexer_crud_endpoints.py::test_put_re_encrypts_when_api_key_present`
      — PUT with a plaintext `api_key`; assert the stored ciphertext
      changes; PUT without `api_key`; assert the stored ciphertext is
      preserved (FR-022).
- [ ] T060 [P] [IDXAPI] `tests/indexers/api/test_indexer_crud_endpoints.py::test_post_duplicate_409`
      — POST a second indexer with the same `(implementation, url)`; assert
      HTTP 409.
- [ ] T061 [P] [IDXAPI] `tests/indexers/api/test_indexer_test_endpoint.py`
      — `POST /api/v3/indexer/{id}/test` runs caps + sample search and
      returns a structured `ConnectivityTestResult`.

### Implementation

- [ ] T062 [IDXAPI] Create `src/romarr/indexers/api/indexers.py` — FastAPI
      router for `GET/POST/PUT/DELETE /api/v3/indexer*` and the
      `/api/v3/indexer/schema` GET. Authentication continues to use the
      development-only no-op admin dependency until the Auth spec lands.
- [ ] T063 [IDXAPI] Create `src/romarr/indexers/api/tests.py` —
      `POST /api/v3/indexer/{id}/test` — re-uses `connectivity.py`.

**Checkpoint**: every endpoint exercised; HTTP status codes match the spec;
encrypted blobs never leak in responses.

---

## Phase 9: RSS Sync & Health (`RSSHEALTH`)

**Purpose**: ship the RSS-sync orchestration class and the health-issue
producer (the `/api/v3/health` endpoint is in the Notifications spec).

### Tests

- [ ] T064 [P] [RSSHEALTH] `tests/indexers/test_rss.py::test_sync_all_iterates_enabled`
      — three indexers, two enabled; `sync_all_enabled_indexers()` calls
      exactly the two and returns their parsed results.
- [ ] T065 [P] [RSSHEALTH] `tests/indexers/test_rss.py::test_sync_indexer_isolated`
      — `sync_indexer(id)` only touches that one.
- [ ] T066 [P] [RSSHEALTH] `tests/indexers/test_rss.py::test_failures_do_not_propagate`
      — one of the three indexers raises; `sync_all` returns the other
      two's results; the failing indexer produces an `IndexerHealthIssue`.
- [ ] T067 [P] [RSSHEALTH] `tests/indexers/test_health.py::test_issue_recorded_in_db`
      — `IndexerHealthIssue` produced; the indexer row's
      `last_health_at`, `last_health_ok`, `last_health_error` columns
      reflect the issue (FR-024).

### Implementation

- [ ] T068 [RSSHEALTH] Create `src/romarr/indexers/rss.py` —
      `IndexerRssSync` class with `sync_all_enabled_indexers()` and
      `sync_indexer(id)`. Uses `asyncio.gather(..., return_exceptions=True)`
      to isolate failures.
- [ ] T069 [RSSHEALTH] Create `src/romarr/indexers/health.py` — async
      `record_health_issue(session, issue)` writes the indexer row's
      health columns and emits a structured log; `clear_health(session,
      indexer_id)` resets on next success.

**Checkpoint**: RSS sync isolates failures; health producer touches only
the failing indexer's row.

---

## Phase 10: Hardening (`HARD`)

- [ ] T070 [HARD] Run `pytest --cov=romarr.indexers` — verify ≥ 75% coverage
      (SC-009). Add targeted tests for any uncovered branch.
- [ ] T071 [HARD] Run `ruff check .` — zero warnings on
      `src/romarr/indexers/`.
- [ ] T072 [HARD] Add a CI smoke test that asserts the foundation circuit
      breaker module is the ONLY breaker imported by `indexers/` (Constitution
      Article III: no duplicated implementation). A simple `git grep`
      assertion in CI suffices.
- [ ] T073 [HARD] Add a manual perf check in
      `specs/004-indexers/research.md`: parsing a 200-result Torznab
      response in < 200 ms; record the median over 10 trials.
- [ ] T074 [HARD] Update `pyproject.toml` `version = "0.4.0a1"`; add a
      one-line note to `CHANGELOG.md`: "0.4.0a1 — Indexers (Prowlarr-first):
      Newznab/Torznab client, application registration, rate-limit + breaker."
- [ ] T075 [HARD] Final review: open `specs/004-indexers/spec.md` and tick
      every Functional Requirement (FR-001 → FR-026) against a task ID;
      record any gaps as follow-up items.

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
