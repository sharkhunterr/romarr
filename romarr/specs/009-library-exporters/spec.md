# Feature Specification: Library Management & Exporters

**Feature Branch**: `009-library-exporters` (branch creation skipped: git repo lives in parent dir)
**Created**: 2026-04-29
**Status**: Draft
**Depends on**:
- `001-foundation` — `Game`, `Release`, `Dump`, `Platform`, identification cascade,
  `Hasher`, `unidentified_dump` table.
- `002-metadata-aggregation` — encryption helper for the RomM exporter API key.
- `006-profiles` — five profile FK columns (this spec turns those columns into
  hard FKs on a real `library` table).
- `008-import-pipeline` — consumes the `library` rows this spec creates;
  closes the forward-dependency that the Import spec flagged.
**Input**: User description: "Library management is the user-facing concept of 'where my ROMs live and how they're organized.' Multi-library is supported from MVP. Each library has its own root path, its own profiles, its own platform restrictions, its own downstream exporters. Plus a full+incremental scanner, a manual import flow, RomM push, ES-DE/Batocera/Recalbox gamelist.xml, Pegasus metadata.txt, LaunchBox XML."

## Clarifications

### Session 2026-04-29

- Q: How are existing Releases with `library_id = NULL` handled when this spec lands? → A: One-shot backfill pass on first library creation: every `Release` whose Dump path is under the new library's `path` is bound to that library (`library_id` set in a single UPDATE). Releases whose Dump path matches no existing library after the pass remain `library_id = NULL` and surface as a one-time `OnHealthIssue` event with `category = 'orphan-releases'` summarizing the count. The same path-matching rule applies in the regular full-scan flow (FR-009)
- Q: How is the multi-library routing tie-breaker scored when two or more libraries are eligible for the same file? → A: Sum of `region_score` (per spec 006 FR-013, `len(priorities) − index`) + `1` when the library's Quality profile evaluates the file as ACCEPT (else 0). Higher total wins; ties broken by lower `library.id`. Reuses spec 006's scoring math so routing is composable with the search-engine's score (spec 007)
- Q: What does the ES-DE `gamelist.xml` exporter emit when a Game has no cover file? → A: Omit the `<image>` element entirely (and `<thumbnail>` / `<marquee>` when their underlying assets aren't present). ES-DE renders its theme's placeholder for missing assets — emitting an empty element or a path to a nonexistent file would create phantom warnings; shipping a Romarr placeholder would tie us to ES-DE's theme conventions
- Q: What synchronisation primitive prevents concurrent gamelist.xml emissions on the same (library, platform) pair? → A: Filesystem-based advisory lock at `<library_path>/<platform_slug>/.gamelist.lock` acquired via `fcntl.flock` (LOCK_EX | LOCK_NB). Works across processes (uvicorn workers + APScheduler), no Redis dependency, auto-releases on process death. Concurrent emissions either coalesce (skip when lock unavailable, knowing another process is regenerating) or queue (block briefly with a short timeout)
- Q: What auth gates the library / scan / exporter / manual-import endpoints? → A: Admin-only on all mutating endpoints (POST/PUT/DELETE on libraries; scan triggers; exporter run trigger; `POST /manual-import`) AND on `GET /manual-import?folder=...` (the folder argument is a path-traversal surface). Other reads (`GET /library`, `GET /library/{id}`, `GET /library/{id}/exporters`) accessible to any authenticated user. Same pattern as specs 003 / 004 / 005 / 006 / 007 / 008

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Operator creates a library and starts importing (Priority: P1)

A Romarr operator creates their first library: name `Cartridges`, path
`/mnt/cartridges`, restricted to NES/SNES/Mega Drive/Game Boy/GBA/N64,
bound to the "Preservation" Quality profile and "USA First" Region
profile. The path is validated as existing and writable; the library
becomes the default target for any download whose platform is in the
allowlist.

**Why this priority**: Without a configured library, every download
falls into the unidentified bucket. This is the most basic operator
workflow.

**Independent Test**: POST a valid library payload; verify the library
materialises with the documented FK bindings; trigger an import for an
NES file; verify it lands at `/mnt/cartridges/nes/<filename>`.

**Acceptance Scenarios**:

1. **Given** valid configuration (path exists and is writable, all five
   profile FKs reference existing rows), **When** the operator POSTs the
   library, **Then** the library is persisted and a successful test of
   write access is recorded.
2. **Given** an invalid path (does not exist OR not writable), **When**
   the operator POSTs, **Then** the response is HTTP 400 with a
   structured error naming the failing check; no library row is
   created.
3. **Given** a missing profile FK (e.g., `quality_profile_id` does not
   exist), **When** the operator POSTs, **Then** the response is HTTP
   400 referencing the offending FK.

---

### User Story 2 — Multi-library routing dispatches to the right library (Priority: P1)

The operator runs three libraries: `Cartridges`, `CD-Based`, `Handheld
Modern`. A PSX `.cue/.bin` finishes downloading; the import-pipeline
asks "which library accepts this?" and Romarr routes it deterministically
to `CD-Based`. A 3DS `.3ds` similarly goes to `Handheld Modern`. An NES
`.nes` to `Cartridges`. The operator never has to choose manually.

**Why this priority**: The whole point of multi-library is removing
manual routing. If routing is wrong even 1% of the time, operators stop
trusting it.

**Independent Test**: Configure 3 libraries with their respective
platform allowlists; trigger imports of fixtures on different platforms;
verify each lands in the correct library.

**Acceptance Scenarios**:

1. **Given** exactly one library has the inferred platform in its
   allowlist (or has no restriction), **When** routing runs, **Then**
   that library is chosen.
2. **Given** multiple eligible libraries, **When** routing runs,
   **Then** the choice is the one whose Quality + Region profile match
   the parsed file best; ties are broken by lower `id` (oldest).
3. **Given** no eligible library, **When** routing runs, **Then** the
   file is parked in `unidentified_dump` with reason
   `routing:no_library_for_platform`.
4. **Given** a library is marked `status = 'unavailable'` (path
   heartbeat failed), **When** routing runs, **Then** that library is
   skipped and routing falls back to the next eligible library.

---

### User Story 3 — ES-DE gamelist.xml regenerates on every import (Priority: P1)

After every successful import, Romarr regenerates
`<library_path>/<platform_slug>/gamelist.xml` containing every imported
Game on that platform with its metadata, cover path, rating, release
date, developer, publisher, and genre. ES-DE picks up the file on its
next scan and renders the catalog with cover art.

**Why this priority**: ES-DE is the most popular retro frontend; if the
gamelist.xml export is wrong, operators can't use Romarr alongside ES-DE
— a major regression vs. RomM-only setups.

**Independent Test**: Import 5 fixture games on Mega Drive into a
library with `exporter_esde_enabled = true`; assert
`<lib>/megadrive/gamelist.xml` exists, is well-formed XML, parses
against the documented ES-DE schema fixture, and contains exactly 5
`<game>` entries with the expected fields.

**Acceptance Scenarios**:

1. **Given** the library has `exporter_esde_enabled = true`, **When**
   an import succeeds, **Then** `gamelist.xml` is fully rewritten
   (not appended) with every Imported Release on that platform.
2. **Given** the same import, **When** the operator inspects the
   library, **Then** cover images have been copied (or hardlinked) into
   `<lib>/<platform_slug>/media/covers/<slug>.<ext>` and the XML's
   `<image>` field uses the relative path `./media/covers/<slug>.<ext>`.
3. **Given** an import targeting a library whose
   `exporter_esde_enabled = false`, **When** the import runs, **Then**
   no gamelist.xml is touched.

---

### User Story 4 — Library full scan reconciles the catalog (Priority: P2)

The operator's library was populated outside Romarr (older imports, or
a fresh install onto an existing collection). They run a full scan;
Romarr walks the path, hashes every recognised ROM, links each file to
an existing Release if a hash matches, creates new Game/Release records
when files don't match anything, and reports orphaned Dumps (DB rows
whose files have disappeared).

**Why this priority**: Most operators arrive at Romarr with a
pre-existing collection; without a scanner they'd have to re-import
everything.

**Independent Test**: Pre-populate `/lib` with 100 fixture ROMs whose
hashes correspond to known DAT entries; run full scan; verify all 100
are linked to Game/Release rows; modify one file path on disk; rerun
scan; verify the orphaned Dump is detected.

**Acceptance Scenarios**:

1. **Given** a library path containing files that match existing DAT
   entries, **When** the operator runs a full scan, **Then** each file
   is hashed once and linked to a Release; identical re-scans skip
   files whose `(path, size, mtime)` already match a known Dump
   (idempotent).
2. **Given** a Dump whose file no longer exists at its path, **When**
   the scan visits the (missing) path, **Then** the Dump is flagged as
   orphaned and the parent Release returns to `status = 'wanted'`; a
   structured warning is logged.
3. **Given** a 10 000-ROM library, **When** the operator runs a full
   scan, **Then** completion happens in under 5 minutes (constitution
   Article XVI), and progress events are emitted via WebSocket every
   100 files.

---

### User Story 5 — Incremental scan picks up changes in real-time (Priority: P2)

The operator copies a new ROM into the library path manually. Within
seconds, Romarr detects the new file via inotify, identifies it,
and creates the Release record. No full scan needed.

**Why this priority**: Without incremental scan, operators have to
trigger a full scan after every manual file drop. Friction.

**Independent Test**: Watch a fixture path; copy a known ROM into it;
verify within 5 seconds a Release record materialises with the file
linked.

**Acceptance Scenarios**:

1. **Given** the incremental watcher is running on a library path,
   **When** a new file is copied into the path that matches a known
   platform format extension, **Then** within 5 seconds the file is
   processed via the identification cascade and a Dump is created.
2. **Given** inotify is not available (e.g., a non-Linux container or a
   filesystem that does not support it), **When** the incremental
   watcher initialises, **Then** it falls back to polling (default
   every hour, configurable per library) and logs the fallback once.
3. **Given** a file is renamed (rather than created), **When** the
   watcher fires, **Then** the existing Dump's `path` is updated
   without a re-hash; if the destination is outside the library path,
   the Dump is treated as orphaned (User Story 4 path).

---

### User Story 6 — Library deletion blocked when Releases exist (Priority: P2)

The operator tries to delete a library that has 200 imported Releases
attached. The DELETE returns HTTP 409 with the count of attached
Releases; the operator must explicitly pass `?force=true` to override.
Even with `?force=true`, the **files on disk are NOT deleted** —
Romarr only forgets about the library row and unlinks Releases via FK
SET NULL.

**Why this priority**: Auto-cascading a library delete to the file
system would be a one-keystroke way to lose hundreds of GB of curated
content. Block by default.

**Independent Test**: Bind a library with 5 Releases; DELETE → HTTP
409; DELETE with `?force=true` → HTTP 204; verify the files still
exist on disk; verify the Releases' `library_id` is now NULL.

**Acceptance Scenarios**:

1. **Given** a library with one or more attached Releases, **When**
   the operator DELETEs it, **Then** the response is HTTP 409 with the
   list of blocking Release counts (per platform).
2. **Given** the same library, **When** the operator DELETEs it with
   `?force=true`, **Then** the library row is removed; files on disk
   are unchanged; Releases' `library_id` columns are set to NULL.
3. **Given** a library with `keep_dump_history = true` and historical
   Dumps still referencing it, **When** the operator attempts DELETE
   with `?force=true`, **Then** the response is HTTP 409 with the
   message instructing the operator to first delete or move the
   historical Dumps.

---

### User Story 7 — Library path becomes unavailable mid-operation (Priority: P2)

The operator's NAS unmounts unexpectedly. Romarr's heartbeat detects
the path is no longer accessible, marks the library
`status = 'unavailable'`, suspends imports targeting it, emits an
`OnHealthIssue` event, and resumes automatically when the path
reappears.

**Why this priority**: Partial-failure paths matter more than
happy-paths in storage land. A NAS unmount mid-import must not corrupt
state.

**Independent Test**: Configure a library on a path; remove the path;
wait one heartbeat cycle (30 s); verify the library's `status` is
`'unavailable'` and an `OnHealthIssue` event was emitted; restore the
path; verify status returns to `'ok'` on the next heartbeat.

**Acceptance Scenarios**:

1. **Given** a heartbeat fails (cannot stat the library path), **When**
   the heartbeat loop runs, **Then** the library transitions to
   `status = 'unavailable'`, all in-progress imports targeting it are
   parked with `error_msg = 'library_unavailable'`, and an
   `OnHealthIssue` event is emitted.
2. **Given** the library is unavailable, **When** routing runs for a
   new download, **Then** that library is skipped and routing tries
   the next eligible library; if none, the file is parked in
   `unidentified_dump`.
3. **Given** the library returns to availability, **When** the next
   heartbeat fires, **Then** `status = 'ok'` and a single
   `OnHealthIssue` recovery event is emitted.

---

### User Story 8 — Manual import of an existing collection (Priority: P3)

The operator has a folder `/imports/incoming/` containing a couple of
hundred ROM files acquired outside Romarr. They use the manual import
flow: GET lists every file with its identification attempt; the
operator picks which ones to import; POST runs each through the import
pipeline.

**Why this priority**: Most new operators arrive with a collection.
Without manual import, onboarding is painful. Useful but not blocking
day-1.

**Independent Test**: Drop 50 ROMs into a fixture folder; GET the
manual-import endpoint with `?folder=`; verify the response lists 50
candidates with per-file identification confidence; POST a subset with
target library_id; verify each runs through the import pipeline.

**Acceptance Scenarios**:

1. **Given** a folder containing ROM files, **When** the operator hits
   `GET /api/v3/rom/manual-import?folder=...`, **Then** the response
   lists each candidate with its identification result and does NOT
   modify the database.
2. **Given** the same listing, **When** the operator POSTs a subset
   with their per-file `(file_path, game_id, release_id, library_id,
   action)` choices, **Then** each entry runs through the import
   pipeline; the response carries per-entry success/failure.
3. **Given** an entry whose `action = 'skip'`, **When** the bulk
   import runs, **Then** that entry is recorded as skipped (not
   failed) in `import_history`.

---

### User Story 9 — RomM push runs in the background (Priority: P3)

The operator uses RomM as their playback frontend. Each library has
RomM exporter enabled with the RomM URL + API key. After every
successful import, Romarr POSTs to RomM's scan endpoint so RomM
re-indexes the platform. The push is best-effort: a RomM outage does
NOT block the import.

**Why this priority**: A nice-to-have for the RomM-using subset of
operators. Non-blocking by design.

**Independent Test**: Configure a library with `exporter_romm_enabled =
true` and a respx-mocked RomM URL; trigger an import; verify a POST is
made to `<romm_url>/api/platforms/<id>/scan` with the API key; mock
RomM to return 503; verify the import still succeeds and a structured
warning is recorded.

**Acceptance Scenarios**:

1. **Given** RomM is reachable and the library has it enabled, **When**
   an import succeeds, **Then** the RomM scan endpoint is called with
   the configured API key.
2. **Given** RomM returns a 5xx error, **When** the export runs,
   **Then** the import is recorded as `success = true` with a
   `warning = 'romm_export_failed'`, no retry beyond the in-call
   tenacity policy, and the operator gets a `OnHealthIssue` event after
   3 sustained failures.

---

### Edge Cases

- A library is created with `platforms_restricted = true` but
  `library_platform` m2m is empty → rejected at validation as "must
  list at least one platform when restricted".
- Two libraries claim the same platform with overlapping profile fits
  → routing chooses the lower `id` (oldest).
- Disk space drops below `min_disk_free_gb` mid-import → import fails
  with `error_msg = 'min_disk_free_gb'`, source intact, `OnHealthIssue`
  emitted.
- Operator changes `library.path` post-creation while files exist on
  disk at the old path → existing Dumps' paths are NOT auto-rewritten;
  the operator must either run a full scan against the new path or
  manually move files.
- Operator changes `library.naming_profile_id` while files exist →
  existing files are NOT auto-renamed; new imports use the new naming
  profile; an `OnHealthIssue` warns about the inconsistency.
- ES-DE expects covers at `./media/covers/<slug>.jpg`; when a Game's
  cover is updated mid-day, the exporter MUST refresh the `media/`
  copy.
- A scan finds a file whose hash matches an existing Release but whose
  filename does not match the Naming profile → file is linked to the
  Release but a `library_inconsistency` warning is emitted; the operator
  can trigger a rename via a future tool (out of scope here).
- Two Releases linked by `parent_release_id` (multi-disc) are scanned
  in different orders → the parent Release is created on the first
  disc encountered; the second disc waits to find/create its parent.
- gamelist.xml emission fails partway (e.g., disk full) → the existing
  gamelist.xml is preserved (write to `gamelist.xml.tmp` then atomic
  rename); a structured error is logged.
- Manual-import targets a `library_id` whose `platforms_restricted`
  excludes the file's platform → the per-entry result is failure with
  reason `routing:platform_not_in_library_allowlist`.

## Requirements *(mandatory)*

### Functional Requirements

**Library entity**

- **FR-001**: The system MUST persist a `library` table per `data-model.md`
  with all the documented columns including the five profile FKs (NOT
  NULL), the four exporter toggles, the lifecycle policy field, the
  per-library `min_disk_free_gb`, and the heartbeat status.
- **FR-002**: The system MUST persist a `library_platform` m2m
  association.
- **FR-003**: The system MUST add a NULLable `Release.library_id` FK
  column to the foundation `release` table; existing Releases retain
  `NULL` until the first scan or import assigns them.
- **FR-003a**: On every successful library creation (the first one
  AND any subsequent one), the system MUST run a one-shot backfill
  pass that, in a single UPDATE statement, sets
  `Release.library_id = <new_library>.id` for every Release whose
  associated Dump's `path` is contained under `<new_library>.path`
  (string-prefix match against the canonicalized absolute path) and
  whose current `library_id IS NULL`. After the pass, the system
  MUST count Releases whose `library_id` remains NULL and emit a
  single `OnHealthIssue` event with `category = 'orphan-releases'`
  carrying that count when it is non-zero (no event when zero). The
  pass MUST be idempotent: re-running it produces no new updates if
  the catalog state is unchanged. The same path-prefix rule MUST
  apply when the regular full-scan path (FR-009) discovers files.
- **FR-004**: A library configuration MUST validate that
  `path` exists and is writable AT save time and fails the save with
  HTTP 400 otherwise.
- **FR-005**: A library with `platforms_restricted = true` MUST have at
  least one row in `library_platform`; validation rejects the empty
  case.

**Multi-library routing**

- **FR-006**: The router MUST select the unique eligible library when
  exactly one matches the inferred platform; ties (multiple eligibles)
  MUST be resolved by computing, for each candidate library, the
  scalar `routing_score = region_score + quality_bonus` where
  `region_score` is the spec 006 FR-013 formula
  (`len(priorities) − index`, 0-based; 0 when fallback applies; the
  release is excluded outright when its region is on the library's
  Region profile `exclude_regions`) and `quality_bonus` is `1` when
  the library's Quality profile evaluates the file as `ACCEPT` and
  `0` when `NEUTRAL`. The candidate with the highest `routing_score`
  wins; final ties are broken deterministically by lower `library.id`
  (oldest). The router MUST NOT include Custom Format scores in the
  routing decision — those are search-engine concerns.
- **FR-007**: When no library is eligible, the file MUST be parked in
  `unidentified_dump` with reason
  `routing:no_library_for_platform`.
- **FR-008**: An `'unavailable'` library MUST be skipped by routing
  regardless of platform match.

**Library scanner**

- **FR-009**: The full scan MUST walk `library.path` recursively and
  hash every file matching a known platform-format extension.
- **FR-010**: The full scan MUST skip files whose `(path, size, mtime)`
  already match an existing Dump record (idempotent re-scan).
- **FR-011**: A Dump whose file no longer exists at its `path` MUST be
  flagged as orphaned; its parent Release MUST transition to
  `status = 'wanted'` and a structured warning MUST be emitted.
- **FR-012**: Long scans MUST emit progress events on the in-process
  pub/sub channel every 100 files; the future Notifications spec
  forwards them to WebSocket.
- **FR-013**: The incremental scan MUST use Linux `inotify`-style
  watches via the `watchdog` library when available, with a polling
  fallback (default every hour, configurable per library).
- **FR-014**: New files found via scan that don't match any existing
  Release MUST run through the foundation identification cascade. If
  identification yields a Game match within the library's profiles, a
  new Release is created; otherwise the file is parked in
  `unidentified_dump` with `library_id` populated.

**Exporters**

- **FR-015**: When `exporter_romm_enabled = true`, after each
  successful import targeting the library, the system MUST POST to
  `<romm_url>/api/platforms/<id>/scan` with the encrypted API key
  decrypted at call time. Failures MUST NOT block the import.
- **FR-016**: When `exporter_esde_enabled = true`, after each
  successful import targeting the library, the system MUST regenerate
  `<library_path>/<platform_slug>/gamelist.xml` containing every
  Imported Release on that platform per the documented ES-DE schema.
- **FR-017**: gamelist.xml emission MUST be atomic: write to
  `gamelist.xml.tmp` then `os.replace(...)`. A failure mid-write MUST
  preserve the previous file unchanged.
- **FR-017a**: gamelist.xml emission for a given
  (library, platform) pair MUST be serialised across processes via
  a filesystem-based advisory lock at
  `<library_path>/<platform_slug>/.gamelist.lock` acquired with
  `fcntl.flock(fd, LOCK_EX | LOCK_NB)` (or platform equivalent).
  When the lock is unavailable (another process is currently
  regenerating), the emitter MUST coalesce (return without
  re-emitting; the in-flight emission already covers the latest
  catalog state at lock-release time) rather than block
  indefinitely. The same lock pattern MUST be used for every
  per-platform-per-library exporter output (Pegasus `metadata.txt`,
  LaunchBox XML), each with its own lock file. The lock MUST
  auto-release on process death (a property `fcntl.flock` provides
  natively). The remote RomM exporter does not require this lock —
  HTTP requests are independently dispatchable.
- **FR-018**: ES-DE cover assets MUST be materialised under
  `<library_path>/<platform_slug>/media/covers/<slug>.<ext>` (hardlinked
  from the `data/covers/` cache when on the same filesystem, copied
  otherwise) and referenced from gamelist.xml as
  `./media/covers/<slug>.<ext>` (relative path).
- **FR-018a**: When a Game has no cover file in `data/covers/` (the
  metadata aggregation layer never returned one, or the cover file
  was deleted), the gamelist.xml exporter MUST OMIT the `<image>`
  element from that Game's `<game>` entry entirely. The same rule
  applies to `<thumbnail>` and `<marquee>` when their underlying
  assets aren't present (these are extension elements ES-DE supports
  but Romarr does not actively materialise at MVP). The `<game>`
  element MUST still be emitted with all its other fields. The
  exporter MUST NOT (a) emit empty `<image></image>` placeholders,
  (b) emit paths to nonexistent files, or (c) ship a Romarr-supplied
  placeholder image — ES-DE's own theme handles missing assets.
- **FR-019**: When `exporter_pegasus_enabled = true`, the system MUST
  emit a `<library_path>/<platform_slug>/metadata.txt` per the
  documented Pegasus format, regenerated on each successful import.
- **FR-020**: When `exporter_launchbox_enabled = true`, the system MUST
  emit a LaunchBox-compatible XML; the per-platform vs. global toggle
  defaults to per-platform (`<library_path>/<platform_slug>/launchbox-export.xml`).
- **FR-021**: All exporters MUST be re-runnable on demand via
  `POST /api/v3/rom/library/{id}/exporters/{name}/run`.

**Manual import flow**

- **FR-022**: The system MUST expose
  `GET /api/v3/rom/manual-import?folder=<path>` which walks the folder
  and returns per-file identification attempts WITHOUT modifying the
  database.
- **FR-023**: The system MUST expose
  `POST /api/v3/rom/manual-import` accepting a list of
  `(file_path, game_id, release_id, library_id, action)` triples. Each
  entry runs through the import pipeline (spec 008); the response
  carries per-entry success/failure.
- **FR-024**: A manual-import entry whose `library_id` does not accept
  the file's platform MUST fail per-entry with reason
  `routing:platform_not_in_library_allowlist`.

**Library deletion**

- **FR-025**: `DELETE /api/v3/rom/library/{id}` MUST return HTTP 409
  when the library has any attached Releases (or historical Dumps when
  `keep_dump_history = true`).
- **FR-026**: `DELETE /api/v3/rom/library/{id}?force=true` MUST remove
  the library row, set `Release.library_id` to NULL on every attached
  Release, and **NOT** delete any file on disk.
- **FR-027**: When `keep_dump_history = true` and historical Dumps
  reference the library, even `?force=true` MUST be rejected with HTTP
  409 instructing the operator to delete or move the historical Dumps
  first.

**Path heartbeat**

- **FR-028**: The system MUST run a per-library heartbeat every 30
  seconds (configurable) that stats `library.path` and updates
  `library.status` to `'ok'` or `'unavailable'`.
- **FR-029**: A transition from `'ok'` to `'unavailable'` MUST emit an
  `OnHealthIssue` event. A transition back to `'ok'` MUST emit a
  recovery event. Repeated transitions MUST NOT emit duplicate events
  within a 5-minute window.

**Disk space**

- **FR-030**: Before each import targeting a library, the system MUST
  verify free disk space at `library.path`; below `min_disk_free_gb`
  the import fails with `error_msg = 'min_disk_free_gb'` and an
  `OnHealthIssue` is emitted.

**API**

- **FR-031**: The system MUST expose CRUD endpoints
  (`GET / GET / POST / PUT / DELETE`) under `/api/v3/rom/library`.
- **FR-032**: The system MUST expose
  `POST /api/v3/rom/library/{id}/scan` and
  `POST /api/v3/rom/library/{id}/scan/incremental` for triggering
  scans on demand. Returns a command id consumed by the future
  `POST /api/v3/command` polling endpoint.
- **FR-033**: The system MUST expose
  `GET /api/v3/rom/library/{id}/exporters` returning per-exporter
  status (last-run timestamp, last-run outcome, file count emitted)
  and `POST /api/v3/rom/library/{id}/exporters/{name}/run` to trigger
  one on demand.
- **FR-033a**: All mutating endpoints introduced by FR-022 / FR-023 /
  FR-031 / FR-032 / FR-033 MUST require the caller to hold the
  `admin` role provided by the Auth spec — specifically:
  `POST /api/v3/rom/library`, `PUT /api/v3/rom/library/{id}`,
  `DELETE /api/v3/rom/library/{id}` (with or without `?force=true`),
  `POST /api/v3/rom/library/{id}/scan`,
  `POST /api/v3/rom/library/{id}/scan/incremental`,
  `POST /api/v3/rom/library/{id}/exporters/{name}/run`,
  `POST /api/v3/rom/manual-import`. The folder-walking read
  endpoint `GET /api/v3/rom/manual-import?folder=<path>` MUST also
  be admin-only because the `folder` query parameter is a
  path-traversal surface (a non-admin user could otherwise
  enumerate the host filesystem). Other read endpoints
  (`GET /api/v3/rom/library`, `GET /api/v3/rom/library/{id}`,
  `GET /api/v3/rom/library/{id}/exporters`) MUST be accessible to
  any authenticated user. Same pattern as specs 003 / 004 / 005 /
  006 / 007 / 008.

**Encryption**

- **FR-034**: `exporter_romm_api_key` MUST be encrypted at rest using
  the same Fernet helper introduced by spec 002.

### Key Entities

- **Library**: A configured root path + per-library policy bundle that
  tells Romarr where to put a file and how to name it. Owns five
  profile FKs, four exporter toggles, lifecycle policy, heartbeat
  status.
- **Library Platform Association**: A m2m row that gates which
  platforms are accepted by a library (when `platforms_restricted` is
  true).
- **Library Routing Decision**: The (deterministic) result of choosing
  a library for a given inferred platform — recorded in the
  `import_history` row produced by spec 008.
- **Library Scan Round**: A single full-scan or incremental-scan
  invocation; emits progress events and produces a structured outcome
  (count of new / linked / orphaned).
- **Exporter Output**: A regenerated artefact under `library.path`
  (gamelist.xml, metadata.txt, launchbox-export.xml) or a remote API
  call (RomM scan).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new library can be configured (path validation +
  profile binding + first heartbeat) in under 60 seconds of operator
  time.
- **SC-002**: With three libraries each restricted to a different
  platform set, routing produces the correct library in 100% of test
  cases across a fixture corpus of at least 30 mixed releases.
- **SC-003**: A full scan of 100 fixture files completes in under 5
  seconds; a 10 000-file scan completes in under 5 minutes
  (Constitution Article XVI).
- **SC-004**: An incremental scan via inotify detects a newly-copied
  file and creates the corresponding Dump in under 5 seconds in 100%
  of test cases.
- **SC-005**: A regenerated gamelist.xml is parseable by ES-DE
  (validated against a known-good fixture schema) with every imported
  Game on the platform, in 100% of test cases.
- **SC-006**: Library deletion is blocked by HTTP 409 in 100% of test
  cases when attached Releases exist; `?force=true` succeeds and
  leaves all files on disk untouched in 100% of cases.
- **SC-007**: Path-heartbeat detection of an unavailable library
  occurs within 30 seconds of the path becoming unstable; recovery
  detection occurs within 30 seconds of the path returning.
- **SC-008**: A manual import of 50 fixture files completes in under
  30 seconds (excluding hash time on large files).
- **SC-009**: Inspecting the database file shows zero plaintext RomM
  API keys in `library.exporter_romm_api_key_encrypted` columns.
- **SC-010**: Test coverage on the libraries module MUST be at least
  75%.

## Assumptions

These resolve the OPEN CLARIFICATIONS supplied with the input,
applying the operator's proposals.

- **Path heartbeat**: every 30 seconds (configurable), `os.stat` on
  `library.path`. Failure → `status = 'unavailable'` + `OnHealthIssue`
  event; recovery → `status = 'ok'` + recovery event. Debounced 5 min
  to avoid event storms.
- **ES-DE media subfolder**: yes, materialise covers under
  `<library_path>/<platform_slug>/media/covers/<slug>.<ext>` (hardlink
  if same filesystem as `data/covers/`, copy otherwise). Refresh on
  metadata change via the existing import-pipeline `OnImport`/`OnUpgrade`
  events.
- **Library deletion with `keep_dump_history = true`**: blocked even
  with `?force=true` until the operator explicitly deletes or moves
  the historical Dumps. This is the safest default — operators can
  always temporarily flip `keep_dump_history` to false if they want
  the cascade.
- **Multi-library + same Game**: NOT supported in MVP. A Release
  belongs to exactly one library via the new `Release.library_id` FK.
  v1+ may relax this with a m2m, but the MVP cost of supporting
  per-library Game duplication is not justified.

Other assumptions:

- The library scanner uses the `watchdog` Python library for inotify
  on Linux; on systems without inotify, it falls back to polling at
  `library.scan_poll_seconds` intervals (default 3600 = 1 hour).
- gamelist.xml emission is best-effort under load; if a regeneration
  is in flight when a new import arrives, the new emission queues and
  coalesces — only one emission per platform-library pair runs at a
  time.
- The RomM exporter calls `<romm_url>/api/platforms/<platform_id>/scan`
  with the API key in an `Authorization: Bearer <key>` header; we
  follow RomM's documented contract verbatim.
- Cover assets are managed under the existing `data/covers/` directory
  introduced by spec 002. The Library spec only adds the per-library
  per-platform `media/covers/` mirror.

### Out of Scope

- UI for library management (UI spec).
- Bidirectional sync with RomM (only push, never pull, in MVP).
- Save data migration (firm out per Constitution).
- Library splitting / merging tools (deferred to v1+).
- Per-game library moves (deferred to v1+).
- Bulk file rename when the operator changes a Naming profile
  (deferred to v1+; current behaviour preserves existing filenames).
