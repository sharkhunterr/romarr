# Implementation Plan: Library Management & Exporters

**Branch**: `009-library-exporters` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification at `specs/009-library-exporters/spec.md`
**Depends on**: `001-foundation`, `002-metadata-aggregation`, `006-profiles`,
`008-import-pipeline`. **Closes the forward-dependency** that spec 008
flagged on the `library` table.

## Summary

The Library subsystem materialises five things on top of the existing
foundation + profiles + import-pipeline scaffolding:

1. **A `library` table** with five required profile FKs, exporter
   toggles, the lifecycle policy field, the per-library
   `min_disk_free_gb` floor, and the heartbeat status. Plus a
   `library_platform` m2m and a NULLable `Release.library_id` FK on the
   foundation `release` table.
2. **A deterministic multi-library router** (pure function) that picks
   the right library for each inferred platform.
3. **A scanner** with two modes — full (manual / scheduled) and
   incremental (inotify via `watchdog`, polling fallback) — composing
   the foundation hasher, identifier, and DAT cascade.
4. **Four exporters**: RomM push (best-effort HTTP), ES-DE / Batocera /
   Recalbox `gamelist.xml` (atomic XML rewrite), Pegasus
   `metadata.txt`, LaunchBox-compatible XML.
5. **A manual import flow** for bulk-importing existing collections.

The library spec does NOT introduce any new HTTP-direct protocol code
(Constitution Article VIII): the only outbound HTTP is the RomM push,
which uses the existing `httpx.AsyncClient` and the encryption helper.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: SQLAlchemy 2.0 (async), Pydantic v2,
Alembic, `watchdog>=4.0` (inotify on Linux + polling fallback),
`lxml` (already a dep, used for XML emission), httpx (already a dep,
used for RomM push), structlog. **No new HTTP client.**
**Storage**: SQLite default / PostgreSQL 15+ optional. One new table
(`library`) + one m2m (`library_platform`). One column addition
(`Release.library_id`). Cover assets materialised under
`<library_path>/<platform_slug>/media/covers/`.
**Testing**: pytest, pytest-asyncio, pytest-cov, respx (RomM mocks),
freezegun (heartbeat windows), `tmp_path` + tmpfs (cross-fs cover
materialisation), TestClient (FastAPI endpoints), an ES-DE schema
fixture for SC-005 validation.
**Target Platform**: Linux server in the Romarr Docker image. The
Docker image already installs `unrar` for the import pipeline; the
library spec adds no system-level dependencies.
**Project Type**: Backend Python module added under
`src/romarr/libraries/`.
**Performance Goals**:
- Full scan of 10 000 ROMs in < 5 min on local SSD (Constitution
  Article XVI; SC-003).
- Incremental detection latency < 5 s on inotify-capable systems
  (SC-004).
- gamelist.xml regeneration of a 1 000-game library in < 2 s.
- Heartbeat probe in < 100 ms p95 against a healthy local path.
**Constraints**:
- Library deletion never deletes files (FR-026; SC-006).
- gamelist.xml emission atomic via temp + replace (FR-017).
- RomM push never blocks import success (FR-015).
- Unavailable library skipped by router (FR-008).
- Multi-disc parent/child relationship preserved during scan
  (foundation Article XIII).
**Scale/Scope**:
- Libraries per instance: typically 1-5; up to 10 plausible.
- Files per library: tens of thousands.
- Exporter output sizes: gamelist.xml is small (a few hundred KB
  for ~1 000 games); cover folder mirrors `data/covers/` so size
  matches the cover cache.

## Constitution Check

*Gate: must pass before Phase 0 research and again after Phase 1 design.*

| Article | Gate | Status |
|---------|------|--------|
| III — Technology Stack (Locked) | SQLAlchemy 2.0 async, Pydantic v2, Alembic, lxml, httpx, watchdog. No new HTTP-direct client. | ✅ Conformant. |
| V — Profile-Driven Decisions | Library inherits five profile FKs from spec 006; routing tie-break uses Quality + Region profile match before falling back to lower id. | ✅ Conformant — encoded in FR-001, FR-006. |
| XII — Library Discipline | Hardlinks default for media-subfolder mirror (FR-018); deletion never cascades to files (FR-026 + SC-006); per-Release status updates on orphan detection (FR-011). | ✅ Conformant. |
| XVI — Quality Gates | ≥ 75% coverage on `libraries/`; perf targets above; zero ruff warnings. | ✅ Conformant — encoded in SC-010 + Hardening phase. |
| XVII — Idempotency & Safety | Idempotent re-scan via `(path, size, mtime)` (FR-010); atomic gamelist.xml rewrite (FR-017); library deletion blocked by HTTP 409 with explicit force flag (FR-025–FR-027); heartbeat debounced (FR-029). | ✅ Conformant. |

**Result**: GREEN. No constitutional violations; **Complexity
Tracking** stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/009-library-exporters/
├── plan.md              # this file
├── spec.md              # user-value specification
├── data-model.md        # library + library_platform + Release.library_id FK + value types
├── tasks.md             # 14-phase task list
└── checklists/
    └── requirements.md  # spec-quality checklist
```

### Source Code (additions to the existing repo)

```text
src/romarr/
├── libraries/                           # NEW — top-level module
│   ├── __init__.py                       # public re-exports: LibraryRegistry, route_to_library, scan_full, scan_incremental, ExporterRegistry
│   ├── types.py                          # LibrarySnapshot, ScanProgress, RoutingChoice, ExporterOutcome, LibraryStatus enum
│   ├── errors.py                         # LibraryError, PathUnwritable, NoEligibleLibrary, LibraryUnavailable, DiskFullError
│   ├── routing.py                        # PURE route_to_library(platform_slug, libraries) -> RoutingChoice
│   ├── heartbeat.py                      # async heartbeat loop + status transition + OnHealthIssue debounce
│   ├── disk_space.py                     # PURE check_min_disk_free(path, min_gb) helper
│   ├── scanner/
│   │   ├── __init__.py
│   │   ├── full.py                       # full_scan(library) — walk + hash + identify + link/create/orphan
│   │   ├── incremental.py                # watchdog-based observer + polling fallback
│   │   └── progress.py                   # progress events (every 100 files)
│   ├── exporters/
│   │   ├── __init__.py                   # ExporterRegistry, ExporterBase ABC
│   │   ├── romm.py                       # POST <romm_url>/api/platforms/<id>/scan
│   │   ├── esde.py                       # gamelist.xml + media/covers/ mirror
│   │   ├── pegasus.py                    # metadata.txt
│   │   └── launchbox.py                  # launchbox-export.xml
│   ├── manual_import.py                  # GET listing + POST bulk handler (delegates per-entry to spec 008)
│   ├── models.py                         # Library + LibraryPlatform SQLAlchemy 2.0 models
│   ├── schemas.py                        # Pydantic *Read/*Create/*Update + ScanRequest, ExporterRunRequest, ManualImportRequest
│   └── api/                              # FastAPI router stubs
│       ├── __init__.py
│       ├── libraries.py                  # /api/v3/rom/library*
│       ├── scan.py                       # /api/v3/rom/library/{id}/scan*
│       ├── exporters.py                  # /api/v3/rom/library/{id}/exporters*
│       └── manual_import.py              # /api/v3/rom/manual-import*
├── domain/
│   └── models/
│       └── release.py                    # MODIFIED: add Mapped[int|None] library_id with FK
└── db/
    └── alembic/
        └── versions/
            └── 0009_libraries.py          # NEW migration

tests/
├── libraries/
│   ├── conftest.py                       # tmp_library, sample profiles, mock RomM
│   ├── test_models.py
│   ├── test_migration_0009.py
│   ├── test_routing.py                   # SC-002 30-release fixture corpus
│   ├── test_heartbeat.py                 # debounce + 5-min event window
│   ├── test_disk_space.py                # min_disk_free_gb gate
│   ├── scanner/
│   │   ├── test_full_scan.py             # 100 + 10k files (SC-003)
│   │   ├── test_full_scan_idempotent.py  # (path, size, mtime) skip
│   │   ├── test_full_scan_orphan.py      # missing-file → wanted + warning
│   │   ├── test_incremental.py           # inotify happy path
│   │   ├── test_incremental_polling.py   # fallback path
│   │   └── test_progress_events.py
│   ├── exporters/
│   │   ├── test_romm.py                  # respx happy + 503; never blocks
│   │   ├── test_esde_gamelist.py         # ES-DE fixture parse (SC-005)
│   │   ├── test_esde_media_mirror.py     # hardlink covers, refresh on update
│   │   ├── test_esde_atomic_rewrite.py   # mid-write crash preserves prior file
│   │   ├── test_pegasus.py
│   │   └── test_launchbox.py
│   ├── test_manual_import_listing.py     # GET endpoint never modifies DB
│   ├── test_manual_import_bulk.py        # POST endpoint runs spec-008 import per entry
│   ├── test_force_delete.py              # SC-006: 409 vs ?force=true
│   └── api/
│       ├── test_library_endpoints.py
│       ├── test_scan_endpoints.py
│       ├── test_exporter_endpoints.py
│       └── test_manual_import_endpoints.py
└── fixtures/
    ├── libraries/
    │   ├── esde_gamelist_known_good.xml      # known-good ES-DE fixture for SC-005
    │   ├── routing_corpus_30_releases.jsonl
    │   ├── full_scan_100_files/             # 100 fixture ROMs with known hashes
    │   ├── full_scan_10k_synthetic/         # generated at test time, not committed
    │   ├── manual_import_50_files/
    │   └── covers/
    │       └── sonic.jpg                    # used by ES-DE media tests
```

**Structure Decision**: keep the routing module **pure** (no I/O), the
heartbeat in its own async loop, and one Python module per exporter so
each can be tested in isolation. The scanner is split between
`full.py` (synchronous walk in a threadpool) and
`incremental.py` (async event-driven watchdog + polling fallback) —
they share helpers in `progress.py`.

The exporters all implement a small `ExporterBase` ABC with a single
async `run(library, platform_slug)` method; the registry in
`exporters/__init__.py` enumerates them by name.

## Phase 0 — Research

Three small research items resolved before code; results captured in
`research.md` if confirmation is needed at code time.

1. **`watchdog` reliability** — `watchdog`'s `Observer` honours inotify
   on Linux and polls on systems without it (e.g., NFS mounts that
   don't propagate kernel events). We default to inotify and log a
   single fallback warning when the observer reports a degraded
   start. The polling fallback uses a 1-hour interval to avoid
   hammering remote storage.
2. **ES-DE schema validation** — ES-DE's `gameList` XML is documented
   informally; rather than chase an external schema, we ship a
   committed fixture (`esde_gamelist_known_good.xml`) under tests/
   captured from a real ES-DE installation. SC-005's parse-with-ES-DE
   gate is met by matching the fixture's structure with `lxml.etree`.
3. **Atomic XML rewrite + hardlink-mirror covers** — `os.replace()` on
   a `*.tmp` sibling guarantees atomicity. For the cover mirror, we
   use `os.link()` first; on `OSError(EXDEV)` we fall back to
   `shutil.copy2` with mtime preservation.

No further research items.

## Phase 1 — Design Outputs

- `data-model.md` — DDL for `library`, `library_platform`,
  `Release.library_id` column addition; the `LibraryStatus` enum;
  value types `RoutingChoice`, `ScanProgress`, `ExporterOutcome`.
- No `contracts/` — endpoint stubs only; full payload schemas live
  in the API spec.
- No `quickstart.md` — a REPL one-liner for
  `await full_scan(library)` lives in the wrap-up phase of
  `tasks.md`.

### Re-check: Constitution after design

Same table as above; nothing in the design pulls a constraint.
**Result**: GREEN.

## Complexity Tracking

> *Empty.* No constitutional violations. No deviations to justify.

## Clarification Deltas (Session 2026-04-29)

The 5 clarifications recorded in `spec.md` add the following architectural
constraints to this plan:

- **`Release.library_id` backfill on first library creation** (FR-003a)
  — every successful library creation runs a one-shot backfill UPDATE
  matching `Release` rows whose Dump path is under the new library's
  `path` (canonicalized prefix match). Rows whose path matches no
  library remain NULL and surface as a one-time `OnHealthIssue` with
  `category = 'orphan-releases'` (only emitted when count > 0). The
  same path-prefix rule applies in the regular full-scan flow.
- **Multi-library routing tie-breaker formula** (FR-006 rewritten) —
  explicit scalar `routing_score = region_score + quality_bonus` where
  `region_score` is the spec 006 FR-013 formula
  (`len(priorities) − index`, fallback = 0) and `quality_bonus` is `1`
  when the library's Quality profile evaluates `ACCEPT`, `0` for
  `NEUTRAL`. Higher wins; ties → lower `library.id`. Custom Format
  scores are explicitly NOT included in the routing decision.
- **gamelist.xml absent-cover handling** (FR-018a) — exporter omits the
  `<image>` element entirely when the underlying `data/covers/` file
  doesn't exist. Same rule for `<thumbnail>` and `<marquee>`. Forbidden:
  empty elements, paths to nonexistent files, Romarr-shipped placeholder
  images. ES-DE handles missing assets via its own theme.
- **Filesystem-based emitter advisory lock** (FR-017a) — gamelist.xml
  emission for a (library, platform) pair serialises across processes
  via `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on
  `<library_path>/<platform_slug>/.gamelist.lock`. Same lock pattern for
  Pegasus `metadata.txt` and LaunchBox XML. Lock unavailable → coalesce
  (skip; the in-flight emission already covers latest state).
- **Admin-only mutations + folder-walk read** (FR-033a) — POST/PUT/
  DELETE on libraries; scan triggers; exporter run; POST `/manual-import`
  ALL require admin. `GET /manual-import?folder=…` is also admin-only
  (path-traversal surface). Other reads accessible to any authenticated
  user.

### Migration delta

`0009_library.py` performs **all** library-related schema work:
- Creates `library` table with full column set per `data-model.md`.
- Creates `library_platform` m2m.
- Adds `Release.library_id INTEGER NULLABLE` FK with `ON DELETE SET NULL`.
- Adds the **five Library → Profile FKs** to the `library` table that
  spec 006 FR-004 declared as forward references.
- Adds the **`library_id` FK** to `library_custom_format` (the m2m table
  spec 006 created without it) and the unique constraint
  `(library_id, custom_format_id)`.
- After commit, the post-migration hook runs the orphan-Release
  `OnHealthIssue` summarisation if any rows remain `library_id IS NULL`.
