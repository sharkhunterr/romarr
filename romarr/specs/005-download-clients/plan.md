# Implementation Plan: Download Clients

**Branch**: `005-download-clients` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification at `specs/005-download-clients/spec.md`
**Depends on**:
- `001-foundation` — Library lifecycle policy field that downstream specs read.
- `002-metadata-aggregation` — Fernet encryption helper reused for credentials.
- `004-indexers` — `indexer.download_client_id` column exists; this spec
  finally adds the FK constraint to it.

## Summary

The download-client subsystem ships:

1. **A common `DownloadClient` ABC** plus value types
   (`TorrentSource`, `NzbSource`, `DownloadStatus`,
   `ConnectivityTestResult`) that the rest of Romarr consumes
   through one stable surface.
2. **Two MVP implementations**: qBittorrent (via the official
   `qbittorrent-api` library) and SABnzbd (direct `httpx` against
   the simple SAB endpoint set).
3. **Three v1 stubs** (Transmission, Deluge, NZBGet) wired through
   the ABC and the schema-discovery endpoint with
   `available = false` until their real implementations land in v1.
4. **A deterministic routing module** that picks the right client
   per release, applying indexer-pinned overrides and source-type
   eligibility before falling back to priority-based selection.
5. **A stuck-grab retry policy** that survives transient client
   outages without operator intervention: 5-minute retries up to a
   1-hour ceiling, then a failure notification.

Technical approach: every client implementation lives behind the
ABC; the qBittorrent path uses the maintained `qbittorrent-api`
library (Constitution Article VIII: official or well-maintained
Python libraries — no custom protocol code); SAB uses raw `httpx`
because its API is small and a heavyweight client library is not
warranted. Encryption reuses the existing helper. Routing is a
**pure function** consumed by the future search/grab engine.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: SQLAlchemy 2.0 (async), Pydantic v2,
Alembic, httpx (async, used directly for SAB and indirectly via
qbittorrent-api), `qbittorrent-api>=2024.1` (well-maintained,
PyPI-published, async-friendly), structlog. **No new HTTP library
beyond what's already in the codebase.**
**Storage**: SQLite default / PostgreSQL 15+ optional. One new
table: `download_client`. One deferred FK added on the existing
`indexer.download_client_id` column.
**Testing**: pytest, pytest-asyncio, pytest-cov, respx (SAB +
qBit HTTP mocks), freezegun (5-minute / 1-hour retry windows),
TestClient (FastAPI endpoints). Optional VCR-style cassettes are
deferred — respx is enough for the MVP.
**Target Platform**: Linux server in the Romarr Docker image.
**Project Type**: Backend Python module added under
`src/romarr/downloaders/`.
**Performance Goals**:
- Connectivity test (auth + category check) returns in < 3 s p95
  against a healthy local client.
- `add_torrent` / `add_nzb` returns within 5 s p95 once the client
  has accepted the payload.
- Routing decision (pure function) returns in < 1 ms.
**Constraints**:
- No custom protocol implementations (Constitution Article VIII).
- Encrypted credentials at rest (Constitution Article IX/XVII).
- Deterministic routing — same inputs ⇒ same client (FR-014..016).
- Retry policy bounded; no infinite stuck grabs (FR-022).
**Scale/Scope**:
- Tens of clients per instance plausible for power users (e.g.,
  one local qBit + several seedboxes).
- Downloads per client: hundreds concurrently is normal for a
  retro-collection power user.
- One `download_client` row per configured instance — small table.

## Constitution Check

*Gate: must pass before Phase 0 research and again after Phase 1 design.*

| Article | Gate | Status |
|---------|------|--------|
| III — Technology Stack (Locked) | httpx async + the explicit qbittorrent-api well-maintained library; no `requests`/`urllib3`. | ✅ Conformant. |
| VIII — Download Client Strategy | qBittorrent + SABnzbd in MVP via official/well-maintained Python libraries; per-library lifecycle policy stored on Library; auto-managed `romarr` category and `romarr` / `romarr-{platform-slug}` / `romarr-imported` tags. | ✅ Conformant — encoded in FR-001 to FR-013, FR-017. |
| XVI — Quality Gates | ≥ 75% coverage on `downloaders/`; performance targets above; zero ruff warnings. | ✅ Conformant — encoded in SC-009 + Hardening phase. |
| XVII — Idempotency & Safety | qBit deduplicates on info-hash; routing is pure; encrypted credentials; no destructive auto-actions on stuck grabs; retry has a hard ceiling. | ✅ Conformant — encoded in FR-019, FR-021, FR-022. |

**Result**: GREEN. No constitutional violations; **Complexity
Tracking** stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/005-download-clients/
├── plan.md              # this file
├── spec.md              # user-value specification
├── data-model.md        # download_client table + indexer FK + routing types
├── tasks.md             # 10-phase task list
└── checklists/
    └── requirements.md  # spec-quality checklist
```

### Source Code (additions to the existing repo)

```text
src/romarr/
├── downloaders/                          # NEW — top-level module
│   ├── __init__.py                       # public re-exports: DownloadClientRegistry, route_release, get_implementation
│   ├── types.py                          # TorrentSource, NzbSource, DownloadStatus, DownloadState, ConnectivityTestResult, ClientType
│   ├── errors.py                         # DownloaderError hierarchy: ConnectionError, AuthError, CategoryWarning, VersionError, TLSError, NoEligibleClientError
│   ├── tls.py                            # is_local_host(), build_httpx_verify_arg(setting, host)
│   ├── tags.py                           # TAG_ROMARR, TAG_PLATFORM, TAG_IMPORTED constants + helpers
│   ├── routing.py                        # pure route_release(release, indexers, clients) -> RoutingDecision
│   ├── retry.py                          # stuck-grab retry: state machine + scheduler hook (the actual cron is in the Tasks spec)
│   ├── registry.py                       # async load_enabled_clients(session); also tracks "available" stubs
│   ├── connectivity.py                   # test_connectivity wrapper around each impl
│   ├── models.py                         # DownloadClient SQLAlchemy 2.0 model
│   ├── schemas.py                        # Pydantic *Read/*Create/*Update + ConnectivityTestResult + RoutingDecision
│   ├── base.py                           # DownloadClient ABC + metadata helpers
│   ├── implementations/
│   │   ├── __init__.py                   # registry of class objects keyed by ClientType
│   │   ├── qbittorrent.py                # MVP — uses qbittorrent-api
│   │   ├── sabnzbd.py                    # MVP — direct httpx
│   │   ├── transmission.py               # STUB — NotImplementedError
│   │   ├── deluge.py                     # STUB — NotImplementedError
│   │   └── nzbget.py                     # STUB — NotImplementedError
│   └── api/                              # FastAPI router stubs
│       ├── __init__.py
│       ├── clients.py                    # /api/v3/downloadclient* endpoints
│       └── schema.py                     # GET /api/v3/downloadclient/schema
└── db/
    └── alembic/
        └── versions/
            └── 0005_download_clients.py  # NEW migration: table + indexer FK

tests/
├── downloaders/
│   ├── conftest.py                       # respx fixtures for qBit + SAB; sample DB rows
│   ├── test_models.py
│   ├── test_migration_0005.py
│   ├── test_tls.py
│   ├── test_tags.py
│   ├── test_routing.py                   # pure-function routing tests + property-based corpus
│   ├── test_retry.py                     # 5-min / 1-hour state-machine
│   ├── test_registry.py
│   ├── test_connectivity.py
│   ├── implementations/
│   │   ├── test_qbittorrent.py           # respx-mocked qBit
│   │   ├── test_sabnzbd.py               # respx-mocked SAB
│   │   ├── test_transmission_stub.py     # NotImplementedError raised
│   │   ├── test_deluge_stub.py
│   │   └── test_nzbget_stub.py
│   └── api/
│       ├── test_client_endpoints.py
│       └── test_schema_endpoint.py
└── fixtures/
    ├── downloaders/
    │   ├── qbit/
    │   │   ├── auth_login_ok.txt
    │   │   ├── auth_login_fail.txt
    │   │   ├── torrents_add_ok.json
    │   │   ├── torrents_info_ok.json
    │   │   ├── torrents_files_ok.json
    │   │   ├── categories_list.json
    │   │   └── version.txt
    │   └── sab/
    │       ├── addurl_ok.json
    │       ├── queue_ok.json
    │       ├── history_ok.json
    │       ├── delete_ok.json
    │       └── invalid_apikey.json
    └── routing/
        ├── corpus_30_releases.jsonl      # mixed torrents/magnets/NZBs with expected client
        └── corpus_indexer_overrides.jsonl
```

**Structure Decision**: keep `routing.py` as a **pure function**.
Routing must be deterministic and unit-testable without a database;
the registry passes loaded clients in as arguments. The retry
policy is also a pure state machine (`retry.py`); the actual cron
lives in the Tasks/Scheduler spec, which calls `retry.tick()` on
its 5-minute job.

The qBittorrent implementation wraps `qbittorrent-api` async
methods; SABnzbd uses `httpx.AsyncClient` directly because the SAB
API is small and homogeneous (`mode=...`).

## Phase 0 — Research

Three small research items resolved before code; results captured
in `research.md` if confirmation is needed at code time.

1. **`qbittorrent-api` async support** — the library is sync by
   default. Wrap each call in `asyncio.to_thread(...)` or use the
   library's `Client(...)` with `aiohttp` adapter when available.
   Confirmed: `to_thread` is the simplest, deterministic path; the
   blocking calls are short (auth + RPC), and the threadpool keeps
   the event loop free.
2. **SAB API surface** — confirmed minimal: `addurl`, `addfile`
   (multipart), `queue`, `history`, `delete`, `pause`, `resume`,
   `change_cat`. JSON output is sufficient (`output=json`); XML is
   not used.
3. **TLS local-host detection** — `ipaddress.ip_address(host).is_private`
   handles RFC 1918 and RFC 4193; we add explicit checks for
   `127.0.0.1`, `::1`, and `localhost`. Hostname → IP resolution is
   optional (the test mode disables verification only when the
   target is unambiguously local).

No further research items.

## Phase 1 — Design Outputs

- `data-model.md` — DDL for `download_client`; the deferred FK on
  `indexer.download_client_id`; the `RoutingDecision` /
  `DownloadStatus` value types.
- No `contracts/` — endpoint stubs only; full payload schemas live
  in the API spec.
- No `quickstart.md` — operator quickstart belongs to API + UI;
  a REPL one-liner showing `route_release(...)` lives in the
  wrap-up phase of `tasks.md`.

### Re-check: Constitution after design

Same table as above; nothing in the design pulls a constraint.
**Result**: GREEN.

## Complexity Tracking

> *Empty.* No constitutional violations. No deviations to justify.

## Clarification Deltas (Session 2026-04-29)

The 5 clarifications recorded in `spec.md` add the following architectural
constraints to this plan:

- **`add_torrent` idempotent on existing info-hash** (FR-004a) — when
  qBittorrent already holds the torrent, return the existing info-hash
  as `client_id` and additively add the `romarr` and `romarr-{platform_slug}`
  tags via qBit's `add tags` API (no overwrite). The same idempotent
  contract applies to `add_nzb` against SAB on matching source URL.
- **Source preference order** (FR-003a) — routing layer selects forms
  in order: `.torrent` URL > raw `.torrent` bytes > magnet URL (and
  symmetrically for NZB). The selected form is recorded on the grab
  event for visibility.
- **Minimum qBittorrent API version** (FR-005a) — connectivity test
  queries `/api/v2/app/webapiVersion` and rejects below 2.8.3
  (qBittorrent 4.4.0+) with a structured `VersionError`. SABnzbd is
  unaffected.
- **Per-client circuit breaker** (FR-022a) — adds a circuit breaker
  mirroring the indexer pattern (5 failures / 60 s opens; auto half-open
  after 60 s). Auth errors and 5xx count as failures. The stuck-grab
  retry policy (FR-021/022) respects the breaker — when open, retries
  bump `last_attempt_at` without an outbound call.
- **Admin-only `/api/v3/downloadclient/*`** (FR-026a) — POST / PUT /
  DELETE / `/test` require admin. The connectivity-test endpoint is
  admin-gated due to its SSRF surface (operator-supplied URL).
  Encrypted credentials NEVER appear in any read-endpoint response.

No schema changes from this delta. The breaker state is in-memory only.
