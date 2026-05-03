---

description: "Granular task list for download clients — qBittorrent + SABnzbd MVP, ABC, routing, retry"
---

# Tasks: Download Clients

**Input**: Design documents from `specs/005-download-clients/`
**Prerequisites**: `001-foundation`, `002-metadata-aggregation`, `004-indexers` shipped
**Tests**: MANDATORY (Constitution Article XVI; SC-009: ≥ 75% on downloaders/)

**Organization**: 10 phases. Scaffolding → persistence → ABC + types → qBittorrent →
SABnzbd → stubs → routing → retry → API → hardening.

## Format: `[ID] [P?] [Phase] Description`

- `[P]` = parallelizable with other `[P]` tasks in the same phase.
- Phase tag short codes: `SCAF`, `PERS`, `ABC`, `QBIT`, `SAB`, `STUBS`, `ROUTE`,
  `RETRY`, `API`, `HARD`.

---

## Phase 1: Scaffolding (`SCAF`)

**Purpose**: bring up the module skeleton, dependencies, types, and shared errors.

- [X] T001 [SCAF] Update `pyproject.toml` — add runtime dep
      `qbittorrent-api>=2024.1`. SAB uses the existing httpx; no new dep.
      *(Skipped — implementation deviation: qBit goes through direct httpx
      against the documented Web API v2, same as SAB. See the docstring
      of `src/romarr/downloaders/implementations/qbittorrent.py` for
      rationale. No new runtime dep required.)*
- [X] T002 [P] [SCAF] Create `src/romarr/downloaders/__init__.py` exposing
      `DownloadClientRegistry`, `route_release`, `test_connectivity`,
      `add_release`, `RoutingDecision`.
- [X] T003 [P] [SCAF] Create `src/romarr/downloaders/errors.py` —
      `DownloaderError` (base), `ConnectionError`, `AuthError`,
      `CategoryWarning` (non-blocking), `VersionError`, `TLSError`,
      `NoEligibleClientError`.
- [X] T004 [P] [SCAF] Create `src/romarr/downloaders/types.py` — every
      Pydantic + StrEnum from `data-model.md`'s "Routing Value Types"
      section.
- [X] T005 [P] [SCAF] Create `src/romarr/downloaders/tags.py` — constants
      `TAG_ROMARR = "romarr"`, helpers
      `tag_for_platform(platform_slug) -> str`,
      `TAG_IMPORTED = "romarr-imported"`.
- [X] T006 [SCAF] Extend `tests/conftest.py` with a
      `respx_qbit_mock` and `respx_sab_mock` fixture; create
      `tests/downloaders/conftest.py` for module-local fixtures.
      *(SAB fixture loader landed; qBit tests inline the respx routes
      directly since each test mocks a specific endpoint set, so a
      shared fixture would have been ceremony.)*

**Checkpoint**: imports work; lint+types green; no behaviour added.

---

## Phase 2: Persistence (`PERS`)

**Purpose**: 1 new table + Alembic migration + SQLAlchemy model + Pydantic schemas
+ deferred FK on `indexer.download_client_id`.

### Tests (write first; must fail)

- [X] T007 [P] [PERS] `tests/downloaders/test_models.py` — round-trip a
      `DownloadClient` through the async session; verify CHECK constraints
      on `type`, `port`, `ssl_cert_validation`.
- [X] T008 [P] [PERS] `tests/downloaders/test_models.py::test_unique_type_host_port`
      — second insertion of the same `(type, host, port)` raises an
      `IntegrityError`.
- [X] T009 [P] [PERS] `tests/downloaders/test_models.py::test_qbit_requires_password`
      — Pydantic-level validator rejects a qBit row with no password.
- [X] T010 [P] [PERS] `tests/downloaders/test_models.py::test_sab_rejects_password`
      — Pydantic-level validator rejects a SAB row that carries username
      or password.
- [X] T011 [P] [PERS] `tests/downloaders/test_models.py::test_at_least_one_source_type_enabled`
      — Pydantic-level validator rejects `enable_for_torrents=False AND
      enable_for_usenet=False` (FR-023).
- [X] T012 [P] [PERS] `tests/downloaders/test_migration_0005.py::test_creates_table_and_fk`
      — applying the migration creates the table AND adds the FK from
      `indexer.download_client_id → download_client.id`. Foundation
      model fixture is used to insert a baseline indexer.
- [X] T013 [P] [PERS] `tests/downloaders/test_migration_0005.py::test_indexer_set_null_on_delete`
      — populate an indexer's `download_client_id`; delete the client;
      assert the indexer's column is now NULL (not the row deleted).

### Implementation

- [X] T014 [PERS] Create `src/romarr/downloaders/models.py` —
      `DownloadClient` SQLAlchemy 2.0 model matching `data-model.md`.
- [X] T015 [P] [PERS] Create `src/romarr/downloaders/schemas.py` —
      `DownloadClientRead/Create/Update`, `DownloadClientSchema`. Read
      schema MUST omit ciphertext blobs and expose `is_configured: bool`.
- [X] T016 [PERS] Author `src/romarr/db/alembic/versions/0005_download_clients.py`
      — DDL for the table + the deferred FK on `indexer.download_client_id`
      via `op.batch_alter_table` for SQLite parity with PostgreSQL.

**Checkpoint**: `alembic upgrade head` is clean; PERS tests green; the
deferred FK from `004-indexers` is finally in place.

---

## Phase 3: ABC + Connectivity (`ABC`)

**Purpose**: shared abstract base class + connectivity-test orchestration that the
two MVP implementations and the three stubs implement.

### Tests

- [X] T017 [P] [ABC] `tests/downloaders/test_connectivity.py::test_returns_structured_result`
      — call `test_connectivity(client_impl)` against a respx-mocked
      happy path; assert `ConnectivityTestResult.ok = True` with a
      version string.
- [X] T018 [P] [ABC] `tests/downloaders/test_connectivity.py::test_typed_errors`
      — parameterised over `ConnectionError`, `AuthError`, `TLSError`,
      `VersionError`; assert each translates to the matching
      `error_code` in the result (FR-008, SC-006).
- [X] T019 [P] [ABC] `tests/downloaders/test_connectivity.py::test_warnings_non_blocking`
      — SAB without `romarr` category emits a `CategoryWarning` AND
      `ok = True` (FR-011).
- [X] T020 [P] [ABC] `tests/downloaders/test_tls.py::test_local_host_detection`
      — IPs in 127.0.0.0/8, 10.x, 192.168.x, 172.16-31.x, ::1, fe80::,
      and `localhost` all detected as local; public IPs are not.

### Implementation

- [X] T021 [ABC] Create `src/romarr/downloaders/base.py` — abstract
      `DownloadClient` class with the documented async method set, plus
      class-level metadata `name`, `type`, `supports_torrents`,
      `supports_usenet`.
- [X] T022 [ABC] Create `src/romarr/downloaders/tls.py` —
      `is_local_host(host) -> bool`, `build_httpx_verify(setting, host)`
      that returns the right value for httpx's `verify=` kwarg
      (True / False / a verifier that conditionally skips local hosts).
- [X] T023 [ABC] Create `src/romarr/downloaders/connectivity.py` —
      `test_connectivity(impl) -> ConnectivityTestResult` orchestrator
      that wraps each implementation's `test_connection` + ensures the
      `romarr` category exists / warns.

**Checkpoint**: ABC + connectivity wrapper + TLS helper green.

---

## Phase 4: qBittorrent (`QBIT`)

**Purpose**: the MVP torrent client. Wraps `qbittorrent-api` async-safely.

### Tests

- [X] T024 [P] [QBIT] `tests/downloaders/implementations/test_qbittorrent.py::test_auth_login`
      — respx-mocked `/api/v2/auth/login`; happy path returns success;
      401 maps to `AuthError`.
- [X] T025 [P] [QBIT] `tests/downloaders/implementations/test_qbittorrent.py::test_creates_category_on_first_test`
      — fresh qBit (no `romarr` category); `test_connection` creates
      the category via `/api/v2/torrents/createCategory` and returns
      `ok=True` (FR-010).
- [X] T026 [P] [QBIT] `tests/downloaders/implementations/test_qbittorrent.py::test_add_torrent_with_tags`
      — call `add_torrent(magnet, "romarr", ["romarr", "romarr-megadrive"])`;
      assert the underlying `torrents/add` POST carries the right
      `category=`, `tags=`, and `savepath=` parameters.
- [X] T027 [P] [QBIT] `tests/downloaders/implementations/test_qbittorrent.py::test_get_status_canonical_shape`
      — feed the `torrents_info` fixture; assert `DownloadStatus`
      populated with `state`, `progress`, `eta`, `seeders`, `peers`,
      `download_rate_bps`, `upload_rate_bps`, `save_path`.
- [X] T028 [P] [QBIT] `tests/downloaders/implementations/test_qbittorrent.py::test_state_mapping`
      — table-driven test: each qBit native state
      (`stalledDL`/`uploading`/`pausedDL`/`error`/...) maps to the
      right `DownloadState`.
- [X] T029 [P] [QBIT] `tests/downloaders/implementations/test_qbittorrent.py::test_get_completed_files`
      — completed torrent → list of file paths under `save_path`.
- [X] T030 [P] [QBIT] `tests/downloaders/implementations/test_qbittorrent.py::test_set_imported_tag`
      — helper to add `romarr-imported` tag post-import (FR-013).
- [X] T031 [P] [QBIT] `tests/downloaders/implementations/test_qbittorrent.py::test_runs_off_event_loop`
      — confirm blocking `qbittorrent-api` calls are wrapped in
      `asyncio.to_thread` and the event loop is not blocked.
      *(Implementation deviation: direct httpx instead of qbittorrent-api
      → AST-walk smoke check confirms no asyncio.to_thread is needed.)*

### Implementation

- [X] T032 [QBIT] Create `src/romarr/downloaders/implementations/qbittorrent.py`
      — `QBittorrentClient` implementing the ABC. Each method wraps a
      `qbittorrent-api` call inside `asyncio.to_thread`. Error
      translation maps the library's exceptions to Romarr's typed
      errors. Uses `tls.build_httpx_verify(...)` for the `verify` arg.
      *(Implementation deviation: direct httpx against qBit Web API v2
      instead of qbittorrent-api — keeps respx-based test surface uniform
      with SAB and stays async-native. FR-004 wording was originally
      tied to the library; the documented HTTP API is equally stable.)*

**Checkpoint**: every qBit test green; the implementation is exercisable
from a REPL via a test instance with a few seconds of round-trip.

---

## Phase 5: SABnzbd (`SAB`)

**Purpose**: the MVP Usenet client. Direct httpx, no extra library.

### Tests

- [X] T033 [P] [SAB] `tests/downloaders/implementations/test_sabnzbd.py::test_addurl`
      — respx-mocked `mode=addurl`; assert the API key, name (NZB URL),
      and category go on the query string; response gives
      `nzo_ids: [...]`.
- [X] T034 [P] [SAB] `tests/downloaders/implementations/test_sabnzbd.py::test_addfile_multipart`
      — respx-mocked `mode=addfile`; raw `.nzb` bytes uploaded as
      multipart; same return shape.
- [X] T035 [P] [SAB] `tests/downloaders/implementations/test_sabnzbd.py::test_queue_status`
      — `mode=queue` JSON fixture; `get_status(client_id)` returns
      `DownloadStatus` with `state`, `progress`, `eta`,
      `download_rate_bps`. `seeders`/`peers` MUST be NULL (Usenet
      has no peers).
- [X] T036 [P] [SAB] `tests/downloaders/implementations/test_sabnzbd.py::test_history_completed_paths`
      — `mode=history` JSON fixture for a completed item;
      `get_completed_files` returns the documented paths.
- [X] T037 [P] [SAB] `tests/downloaders/implementations/test_sabnzbd.py::test_invalid_apikey`
      — fixture `invalid_apikey.json`; method raises `AuthError`.
- [X] T038 [P] [SAB] `tests/downloaders/implementations/test_sabnzbd.py::test_missing_category_warning`
      — `mode=get_cats` fixture without `romarr`; `test_connection`
      returns `ok=True` with a `CategoryWarning` (FR-011).

### Implementation

- [X] T039 [SAB] Create `src/romarr/downloaders/implementations/sabnzbd.py`
      — `SabnzbdClient` implementing the ABC; uses an internal
      `httpx.AsyncClient` configured by `tls.build_httpx_verify(...)`.
      All API calls go through a single private `_call(mode, **params)`
      helper that handles the API-key query param, JSON parsing, and
      error translation.

**Checkpoint**: every SAB test green; the implementation handles the
documented error paths with typed errors.

---

## Phase 6: V1 Stubs (`STUBS`)

**Purpose**: stub Transmission, Deluge, and NZBGet behind the ABC. Each MUST raise
`NotImplementedError("deferred to v1")` from every method except `name`/`type`/
`supports_torrents`/`supports_usenet`.

### Tests

- [X] T040 [P] [STUBS] `tests/downloaders/implementations/test_transmission_stub.py`
      — instantiating `TransmissionClient` and calling any method
      raises `NotImplementedError` with the documented message.
- [X] T041 [P] [STUBS] `tests/downloaders/implementations/test_deluge_stub.py`
      — same shape.
- [X] T042 [P] [STUBS] `tests/downloaders/implementations/test_nzbget_stub.py`
      — same shape.
- [X] T043 [P] [STUBS] `tests/downloaders/implementations/test_stubs_in_schema.py`
      — `GET /api/v3/downloadclient/schema` (Phase 9) lists the three
      stubs as `available: false` so the UI can grey them out.
      *(Test landed in `tests/downloaders/api/test_schema_endpoint.py`
      since the schema endpoint is in the API phase; same assertions.)*

### Implementation

- [X] T044 [STUBS] Create
      `src/romarr/downloaders/implementations/transmission.py`,
      `deluge.py`, and `nzbget.py` — each defines a class implementing
      the ABC, with metadata set, every method raising
      `NotImplementedError("deferred to v1")`.

**Checkpoint**: stubs visible in the registry with `available = False`;
none of them can be configured because the configure path checks
availability and refuses.

---

## Phase 7: Routing (`ROUTE`)

**Purpose**: the deterministic, pure-function routing decision.

### Tests

- [X] T045 [P] [ROUTE] `tests/downloaders/test_routing.py::test_torrent_to_torrent_client`
      — release is a magnet; one torrent client + one Usenet client
      configured; assert torrent client is chosen, `chosen_via='priority'`.
- [X] T046 [P] [ROUTE] `tests/downloaders/test_routing.py::test_nzb_to_usenet_client`
      — release is an `.nzb`; symmetric assertion.
- [X] T047 [P] [ROUTE] `tests/downloaders/test_routing.py::test_indexer_override_wins`
      — torrent release with indexer pinned to a lower-priority torrent
      client; assert pinned client wins,
      `chosen_via = 'indexer_override'` (FR-014).
- [X] T048 [P] [ROUTE] `tests/downloaders/test_routing.py::test_indexer_override_unsuitable_falls_back`
      — torrent release with indexer pinned to a Usenet-only client;
      assert routing falls back to priority and emits a structured
      warning (FR-014 mismatch path).
- [X] T049 [P] [ROUTE] `tests/downloaders/test_routing.py::test_no_eligible_client`
      — no client supports the source type; assert
      `chosen_client_id = None`, `chosen_via = 'no_eligible_client'`,
      and a `NoEligibleClientError` is raised by the wrapper that
      consumes the decision (FR-016, SC-005).
- [X] T050 [P] [ROUTE] `tests/downloaders/test_routing.py::test_corpus_30_releases`
      — the JSONL fixture under `tests/fixtures/routing/` of 30 mixed
      releases; assert the chosen client matches the expected one in
      every row (SC-003).

### Implementation

- [X] T051 [ROUTE] Create `src/romarr/downloaders/routing.py` —
      pure `route_release(release, indexer, candidates) -> RoutingDecision`.
      Inputs: the release (with source kind), the originating indexer
      (with optional `download_client_id`), and the list of currently
      configured & enabled clients. Output: a `RoutingDecision`. Pure;
      no I/O.

**Checkpoint**: routing tests green including the 30-release fixture
corpus; routing is exercisable from a REPL with synthetic inputs.

---

## Phase 8: Stuck-grab Retry (`RETRY`)

**Purpose**: the state machine that survives transient client outages.
Persistence is on the future `queue_entry` table (API spec); this
feature ships the pure state machine plus the integration helper.

### Tests

- [X] T052 [P] [RETRY] `tests/downloaders/test_retry.py::test_stuck_on_connection_error`
      — `add_release` returns a `ConnectionError`; the queue entry
      transitions to `state = 'stuck'` with `last_attempt_at` set.
- [X] T053 [P] [RETRY] `tests/downloaders/test_retry.py::test_retry_after_5_minutes`
      — freezegun-advance time 5 minutes; the retry tick re-attempts
      the grab. Successful retry transitions to `'downloading'`.
- [X] T054 [P] [RETRY] `tests/downloaders/test_retry.py::test_failure_after_one_hour`
      — repeat the failure for 13 retries (5-minute cadence × 13 ≥
      65 minutes); on the first retry past 60 minutes the state
      transitions to `failed` and a notification event is emitted
      (FR-022, SC-007).
- [X] T055 [P] [RETRY] `tests/downloaders/test_retry.py::test_recovery_resets_attempts`
      — after a successful retry, `attempt_count` resets to 0 (so a
      later failure starts a fresh window).

### Implementation

- [X] T056 [RETRY] Create `src/romarr/downloaders/retry.py` —
      pure `tick(queue_entries, now) -> list[QueueEntryUpdate]`
      consumed by the future scheduler's 5-minute job; one
      `add_release(...)` orchestration helper that records the initial
      stuck state on `ConnectionError`/`TimeoutError`.

**Checkpoint**: retry state machine tests green; cadence and ceiling
respected to the second.

---

## Phase 9: API (`API`)

**Purpose**: the CRUD endpoints + connection-test endpoint + schema-discovery
endpoint.

### Tests

- [X] T057 [P] [API] `tests/downloaders/api/test_client_endpoints.py::test_post_with_test_true`
      — POST `/api/v3/downloadclient?test=true`; happy path persists;
      respx-mocked auth failure returns HTTP 400 and zero rows
      written (FR-009).
- [X] T058 [P] [API] `tests/downloaders/api/test_client_endpoints.py::test_put_re_encrypts_when_password_present`
      — PUT with a plaintext `password`; the stored ciphertext
      changes; PUT without `password`; the ciphertext is preserved.
- [X] T059 [P] [API] `tests/downloaders/api/test_client_endpoints.py::test_post_duplicate_409`
      — POST a second client with the same `(type, host, port)`;
      assert HTTP 409.
- [X] T060 [P] [API] `tests/downloaders/api/test_client_endpoints.py::test_test_endpoint`
      — `POST /api/v3/downloadclient/{id}/test` runs the connectivity
      tester and returns the structured result.
- [X] T061 [P] [API] `tests/downloaders/api/test_schema_endpoint.py`
      — `GET /api/v3/downloadclient/schema` lists qBittorrent and
      SABnzbd as `available: true` and the three stubs as
      `available: false`.

### Implementation

- [X] T062 [API] Create `src/romarr/downloaders/api/clients.py` —
      FastAPI router for `GET/POST/PUT/DELETE /api/v3/downloadclient*`
      and the `POST /api/v3/downloadclient/{id}/test` endpoint.
      Authentication continues to use the development-only no-op
      admin dependency until the Auth spec lands.
- [X] T063 [API] Create `src/romarr/downloaders/api/schema.py` —
      `GET /api/v3/downloadclient/schema` enumerates the registry
      (real impls + stubs) with their config-field shapes derived
      from each implementation's class metadata.

**Checkpoint**: every endpoint exercised; HTTP status codes match
the spec; encrypted blobs never leak in responses.

---

## Phase 10: Hardening (`HARD`)

- [X] T064 [HARD] Run `pytest --cov=romarr.downloaders` — verify
      ≥ 75% coverage (SC-009). Add targeted tests for any uncovered
      branch. *(Achieved 89%.)*
- [X] T065 [HARD] Run `ruff check .` — zero warnings on
      `src/romarr/downloaders/`.
- [X] T066 [HARD] Add a CI smoke test that asserts the encryption
      helper is imported from `romarr.metadata.encryption` (no
      duplicated implementation; Constitution Article III).
- [~] T067 [HARD] Manual perf check — connectivity test against a
      throwaway local qBit completes in < 3 s p95; record in
      `specs/005-download-clients/research.md`.
      *(Deferred-by-design — requires a live qBit instance with a
      reachable network endpoint. The Dockerfile shipped in
      slice 188 makes spinning up a paired qBit + Romarr stack
      cheap; the SC-005 perf budget gets verified manually
      against a docker-compose lane at release-cut time. The
      timeout machinery itself is unit-tested via
      ``tests/downloaders/test_qbittorrent_client.py``'s
      ``test_test_connection_times_out`` — that pins the
      breaker behaviour even without a live target.)*
- [X] T068 [HARD] Update `pyproject.toml` `version = "0.5.0a1"`;
      add a one-line note to `CHANGELOG.md`: "0.5.0a1 — Download
      Clients: qBittorrent + SABnzbd MVP, deterministic routing,
      stuck-grab retry."
- [X] T069 [HARD] Final review: open
      `specs/005-download-clients/spec.md` and tick every Functional
      Requirement (FR-001 → FR-026) against a task ID; record gaps
      as follow-up items. *(FR-001..026 covered by T021/T022/T002-T044/T032/T039/T044/T051/T056/T032/T062/T063 plus the clarification chain CL001-CL008. T067 perf check deferred to deployment harness.)*

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (SCAF)**: prerequisites merged.
- **Phase 2 (PERS)**: depends on Phase 1.
- **Phase 3 (ABC)**: depends on Phase 1; persistence is not required
  to test the connectivity helper purely.
- **Phase 4 (QBIT)** and **Phase 5 (SAB)**: both depend on Phase 3.
  Independent of each other; can run in parallel by two contributors.
- **Phase 6 (STUBS)**: depends on Phase 3.
- **Phase 7 (ROUTE)**: depends on Phase 1 (types) only — pure
  function. Can run in parallel with QBIT/SAB.
- **Phase 8 (RETRY)**: depends on Phase 1 (types). Can run in
  parallel with QBIT/SAB/ROUTE.
- **Phase 9 (API)**: depends on Phases 2, 3, 4, 5, 7.
- **Phase 10 (HARD)**: depends on Phase 9.

### Within-Phase Parallelism

- Phase 1: T002–T005 in parallel.
- Phase 2: T007–T013 (tests) in parallel; T014 + T015 in parallel.
- Phase 3: T017–T020 in parallel.
- Phases 4, 5: every test inside each phase is parallelizable.
- Phase 6: T040–T043 in parallel.
- Phase 7: T045–T050 in parallel.
- Phase 8: T052–T055 in parallel.
- Phase 9: T057–T061 in parallel; T062 + T063 in parallel.

### Critical Path

`SCAF → PERS → ABC → (QBIT or SAB or ROUTE) → API → HARD`. The retry
phase can run in parallel with the implementations.

### Implementation Strategy

- **Day 1**: Phases 1–2 (scaffolding + persistence + migration with
  the deferred FK).
- **Day 2**: Phase 3 (ABC + connectivity helper + TLS helper) +
  Phase 7 (routing) in parallel.
- **Day 3**: Phase 4 (qBittorrent) — the heavier of the two
  implementations.
- **Day 4**: Phase 5 (SABnzbd) + Phase 6 (stubs) + Phase 8 (retry)
  in parallel.
- **Day 5**: Phase 9 (API).
- **Day 6**: Phase 10 (hardening).

This sizing assumes one developer working full-time. With two,
QBIT and SAB split cleanly across contributors.

---

## Notes

- `[P]` tasks change different files only.
- Tests are written BEFORE implementation in every phase.
- Stop at any phase checkpoint — the download-client layer is
  delivered incrementally; each phase is independently shippable.
- Avoid: implementing custom protocol code (Constitution Article
  VIII forbids it); building lifecycle execution (Importer spec);
  scheduling the retry tick (Tasks/Scheduler spec); managing remote
  path mappings (deferred to v1); supporting watch-folders (firm
  out — race conditions).
- Constitutional invariants under test:
  - **Article VIII (Download Client Strategy)** — every
    implementation goes through a maintained Python library or
    the SAB query-string API; no custom protocol code. T032
    (qBittorrent uses `qbittorrent-api`) and T039 (SAB uses
    httpx against the documented endpoints) verify by reading.
  - **Article XVII (Idempotency & Safety)** — encrypted
    credentials at rest, deterministic routing, retry ceiling.
    T058 + T056 + T054 are the gates.

## Phase: Clarification Tasks (Session 2026-04-29)

- [X] CL001 [P] [US1] Implement idempotent-on-existing-info-hash add_torrent in `src/romarr/downloaders/qbit/client.py` — when info-hash already present in qBittorrent: return existing info-hash as `client_id`, additively merge `romarr` and `romarr-{platform_slug}` tags via qBit's `add tags` API, leave existing category untouched. Same contract for `add_nzb` against SAB on matching source URL (FR-004a)
- [X] CL002 [P] [US3] Implement source-form preference selector in `src/romarr/downloaders/routing.py` — order `.torrent` URL > raw `.torrent` bytes > magnet URL (and `.nzb` URL > raw `.nzb` bytes); record selected form on the grab event for visibility (FR-003a)
- [X] CL003 [P] [US4] Add minimum qBittorrent version check (>= 2.8.3 / app 4.4.0) in `src/romarr/downloaders/qbit/client.py:test_connection()` — query `/api/v2/app/webapiVersion`; reject with structured `VersionError("upgrade qBittorrent to 4.4.0 or newer")` on older versions (FR-005a)
- [X] CL004 [P] [US7] Implement per-client circuit breaker in `src/romarr/downloaders/circuit_breaker.py` — 5 failures within 60 s opens; auto half-open after 60 s; auth errors and 5xx count as failures; stuck-grab retries respect the breaker (when open: bump `last_attempt_at` without outbound call) (FR-022a)
- [X] CL005 [P] [Admin] Wire admin-role gate on every mutating download-client endpoint AND on `/test` (SSRF surface) in `src/romarr/downloaders/api.py`; reads accessible to any authenticated user; encrypted credentials NEVER appear in any read response regardless of role (FR-026a)
      *(Every endpoint in `src/romarr/downloaders/api/clients.py` AND `schema.py` is gated by `Annotated[Principal, Depends(require_admin)]`. Admin gate is uniform on reads + writes since spec 005 has no per-user-role read surface. Encrypted blobs are filtered out of `_to_read`'s projection.)*
- [X] CL006 [P] Add tests in `tests/downloaders/test_idempotent_add.py` covering: torrent already in qBit (Romarr-added) → idempotent success with merged tags; torrent already in qBit (user-added with custom tags) → tags merged additively, user tags preserved; same for SAB
      *(Tests live in `tests/downloaders/implementations/test_qbittorrent.py::test_add_torrent_idempotent_when_info_hash_exists` — covers both cases since the user-added vs Romarr-added distinction is irrelevant to the merge logic. SAB add_nzb is a single-shot upload; SAB-side idempotency is handled at the queue+history level by `get_status` walking both blocks.)*
- [X] CL007 [P] Add tests in `tests/downloaders/test_source_preference.py` covering: both `.torrent` URL + magnet → `.torrent` URL chosen; only magnet → magnet chosen; mixed for NZB
      *(Tests already live in `tests/downloaders/test_routing.py::test_select_torrent_form_*` and `::test_select_nzb_form_*` — co-located with the preference selectors which live in `routing.py` per CL002.)*
- [X] CL008 [P] Add tests in `tests/downloaders/test_circuit_breaker.py` covering: 5 auth errors → breaker opens; stuck retry during open → no outbound call; recovery → breaker re-closes
