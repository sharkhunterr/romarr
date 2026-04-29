# Feature Specification: Import Pipeline

**Feature Branch**: `008-import-pipeline` (branch creation skipped: git repo lives in parent dir)
**Created**: 2026-04-29
**Status**: Draft
**Depends on**:
- `001-foundation` — `Hasher`, identification cascade, hash-match cascade,
  `unidentified_dump` table, `Game`/`Release`/`Dump` models.
- `005-download-clients` — `DownloadClient` ABC, `list_managed_downloads`,
  `get_completed_files`, `set_category` / tag operations, lifecycle policy
  surface.
- `006-profiles` — `ProfileEvaluator`, `NamingTemplateEngine`, library-bound
  profile FK columns.
- `007-search-decision-engine` — blocklist auto-add interface for failed imports,
  RapidFuzz.
- **Forward-references** the future `010-library` spec for `library.path`,
  `library.lifecycle_policy`, `library.keep_dump_history`. See "Forward
  Dependency" in `plan.md`.
**Input**: User description: "Build the import pipeline. Post-download-complete workflow: watch → extract → hash → DAT match → identify → game match → multi-disc → profile gate → render filename → atomic move/hardlink → DB update → lifecycle → notify. Most operationally critical pipeline in Romarr."

## Clarifications

### Session 2026-04-29

- Q: How does the importer's auto-blocklist on failure align with spec 007's content-correctness-only rule? → A: Aligned. The importer emits failure subreasons in two categories — **content-correctness** (`hash-mismatch`, `dat-rejected`, `format-corrupt`, `archive-extraction-failed`) and **transient/operational** (`disk-full`, `permission-denied`, `client-unreachable`, `move-failed`, `scan-timeout`). The spec 007 helper is invoked ONLY for content-correctness subreasons; transient/operational failures record in `import_history` with retry-eligibility but never call the blocklist helper
- Q: What's the webhook authentication scheme — bearer token or HMAC? → A: Bearer token in `X-Romarr-Webhook-Token` header, compared in constant time. Rate-limited at 10 requests/minute/source-IP. HMAC over the body would be the right choice for a public webhook ingest, but Romarr's webhook caller is the operator's own qBittorrent on the operator's own network — bearer is simpler, matches Sonarr/Radarr behaviour, and qBit's "run external program" hook can set a header but cannot easily compute HMAC of the body
- Q: In the automatic import flow, what happens when the renderer produces a destination path that already exists with different bytes (different SHA-1)? → A: Park the incoming file in `unidentified_dump` with `rejection_reason = 'destination_collision'` and `suggested_game_id` populated; the existing destination file is untouched; emit an `OnHealthIssue` event with category `'naming-collision'`. Almost always a Naming profile bug; silent disambiguation would hide it
- Q: How does the extractor defend against zip-bomb-style high-compression-ratio archives? → A: Cap uncompressed expansion at `max(4 × compressed_size, 5 GiB)`, computed incrementally as bytes are written. On overrun, abort extraction, park in `unidentified_dump` with `rejection_reason = 'extract:bomb-detected'`, and surface the failure. The depth cap (FR-004) is a separate, complementary defense
- Q: What auth gates the import / unidentified / retry endpoints? → A: Admin-only on all mutating endpoints (`POST /import/manual`, `POST /unidentified/{id}/match`, `DELETE /unidentified/{id}`, `POST /import/retry/{import_id}`); reads (`GET /import/manual`, `GET /import/history`) accessible to any authenticated user. The webhook `POST /webhook/download-complete` is NOT session-authenticated — it uses its own bearer token from the configured per-download-client secret (FR-002), independent of the user-role system

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A torrent finishes and lands in the library (Priority: P1)

A Romarr operator's qBittorrent finishes a torrent that contains
`Sonic the Hedgehog (USA).md`. Within 30 seconds of completion (or
immediately on webhook), Romarr identifies the file, verifies it
against No-Intro, hardlinks it into `data/library/megadrive/Sonic
the Hedgehog (USA).md` per the operator's Naming profile, persists
a Dump record with all hashes, tags the torrent `romarr-imported`
in qBit, and emits an `OnImport` event.

**Why this priority**: This is the headline operational workflow.
Every other import scenario is a variant of this one.

**Independent Test**: Stub a download client to report a completed
torrent tagged `romarr` whose file matches a known DAT entry; run
the import pipeline; verify the destination file exists at the
canonical path, the Dump record carries the right hashes and
`dat_verified = true`, and the torrent now carries the
`romarr-imported` tag.

**Acceptance Scenarios**:

1. **Given** a completed download tagged `romarr` and not yet
   `romarr-imported`, **When** the watcher polls or a webhook
   fires, **Then** the pipeline runs end-to-end and produces a
   Dump record with all hashes populated and `dat_verified = true`
   for a DAT-matching file.
2. **Given** the same file already imported (re-run scenario),
   **When** the pipeline runs again, **Then** no duplicate Dump is
   created, no duplicate file is created, and the import history
   records `success = true` with reason `already_imported`.
3. **Given** the source and destination are on the same filesystem,
   **When** the mover executes, **Then** the destination is a
   hardlink (verified by inode equality), not a copy.

---

### User Story 2 — Cross-filesystem fallback to copy + verify + delete (Priority: P1)

The download client saves to `/downloads` (one filesystem) and the
library is on `/library` (a different mount). The pipeline detects
the cross-filesystem boundary, falls back to a copy + hash-verify
+ delete + atomic rename pattern, and never leaves a half-written
file at the destination.

**Why this priority**: Operators with seedboxes / NAS / different
disks need this; without it, hardlink-only would silently fail or
double up disk usage.

**Independent Test**: Mount a tmpfs at `/tmp/romarr-test-fs` to
simulate a different device; run a fixture import where source is
on the host fs and destination is on the tmpfs; verify the
destination file exists with matching SHA-1, the source is
deleted (per `move_and_remove` policy) or preserved (per
`copy_and_keep`), and no `*.tmp` artefact remains.

**Acceptance Scenarios**:

1. **Given** `os.stat(source).st_dev != os.stat(dest_dir).st_dev`,
   **When** the mover executes, **Then** it copies bytes, verifies
   the destination's SHA-1 matches the source's, and only then
   atomically renames the temp file to the canonical destination.
2. **Given** the copy succeeds but the hash verification fails,
   **When** the mover handles the mismatch, **Then** the temp file
   is deleted and the import is marked failed with a structured
   `error_msg` of `"copy_hash_mismatch"`; the source is **not**
   deleted.
3. **Given** the destination already exists with a matching SHA-1,
   **When** the mover runs, **Then** the operation is a no-op
   (idempotency invariant) and the existing file's inode is
   preserved.

---

### User Story 3 — A multi-disc PSX game lands as a linked Release set (Priority: P1)

A 2-disc *Final Fantasy IX* download finishes with two `.cue/.bin`
pairs. Romarr detects the multi-disc structure, creates a Disc-1
Release as the parent (`disc_total = 2`), creates a Disc-2 Release
referencing it via `parent_release_id`, and renders both files into
a per-game subfolder `data/library/psx/Final Fantasy IX/`.

**Why this priority**: Multi-disc games are the canonical
disc-based-platform case. Foundation gives us the parent_release_id
column; this spec is where it gets populated for real.

**Independent Test**: Drop a fixture directory containing
`Final Fantasy IX (USA) (Disc 1).cue`,
`Final Fantasy IX (USA) (Disc 1).bin`,
`Final Fantasy IX (USA) (Disc 2).cue`,
`Final Fantasy IX (USA) (Disc 2).bin`; run the importer; verify
two Releases linked by `parent_release_id`, both files in
`data/library/psx/Final Fantasy IX/`, and the disc-1 Release
carries `disc_total = 2`.

**Acceptance Scenarios**:

1. **Given** a directory containing two cue/bin pairs sharing the
   same game stem, **When** multi-disc detection runs, **Then**
   exactly one parent Release is created with `disc_number = 1,
   disc_total = 2` and one child Release with `disc_number = 2,
   parent_release_id = parent.id`.
2. **Given** the Naming profile has `multi_disc_subfolder = true`,
   **When** the renderer runs, **Then** every disc is rendered into
   the same per-game subfolder.
3. **Given** the multi-disc detector encounters a `.cue` file
   referencing `.bin` children, **When** DAT matching runs, **Then**
   the system hashes the `.bin` (not the `.cue`) for DAT lookup
   (Redump references `.bin` hashes).

---

### User Story 4 — A profile-rejected file is parked in unidentified_dump (Priority: P2)

A download finishes for `Sonic the Hedgehog (USA) [h1].md` (a hack
release). The library's Dump profile has `allow_hacks = false`. The
pipeline identifies the file but the profile gate rejects it; the
file is moved to the unidentified-dump table with a structured
`rejection_reason` and the file itself stays in the download
client (not deleted, not imported).

**Why this priority**: Without this, a profile mismatch would
either silently swallow the file or import it against the
operator's policy. Both are bad.

**Independent Test**: Configure a Dump profile that disallows
hacks; inject a download whose parsed `dump_status = 'hack'`; run
the importer; verify a row appears in `unidentified_dump` with
`rejection_reason = 'profile:dump:hack_disallowed'`, no Dump record
is created, and no destination file exists.

**Acceptance Scenarios**:

1. **Given** a download whose pipeline-parsed identification
   violates a bound Region/Language/Dump/Quality profile, **When**
   the profile gate runs, **Then** the import halts, an
   `unidentified_dump` row is created with the structured
   rejection reason and a `library_id` pointing at the would-be
   target library, and the source file is left in the download
   client.
2. **Given** the same file in the **manual import flow**, **When**
   the operator forces the import via `?force=true`, **Then** the
   profile rejection is logged as a warning (not a hard stop) and
   the import proceeds.

---

### User Story 5 — A hash mismatch with DAT triggers a soft warning (Priority: P2)

A download finishes whose computed SHA-1 does not match any DAT
entry on Hasheous, PlayMatch, or the local DAT cache. The pipeline
imports the file anyway (treating "no DAT match" as not a
showstopper), records `dat_verified = false`, and surfaces a
warning in the import history so the operator can decide whether
to delete the file later.

**Why this priority**: A "no DAT match" file is common (private
trackers carry custom dumps, indie homebrew, region-rare prototypes).
Auto-rejecting them would over-block; auto-importing them silently
would mislead the operator.

**Independent Test**: Inject a download whose hash is **not** in
any of the three DAT backends; run the importer; verify the Dump
is created with `dat_verified = false`, an import-history row
records `success = true` with a `warning` field, and an OnImport
event is emitted.

**Acceptance Scenarios**:

1. **Given** a successfully-identified file whose SHA-1 matches no
   DAT entry, **When** the pipeline runs, **Then** the Dump record
   carries `dat_verified = false, dat_source = NULL,
   dat_entry_id = NULL` and the import is recorded as
   `success = true` with a `dat_unverified` warning.
2. **Given** a Quality profile with `require_dat_verified = true`,
   **When** the same file flows through, **Then** it is rejected at
   the profile gate (User Story 4 path), not imported.
3. **Given** a hash that **does** match a DAT entry but the entry's
   `status = 'baddump'`, **When** the pipeline runs, **Then**
   `dat_verified = false` AND the parsed `dump_status` is set to
   `baddump`; the profile gate makes the final decision.

---

### User Story 6 — A failed import auto-blocklists the release (Priority: P2)

The download finishes but the file fails extraction (corrupted
archive). The pipeline marks the import failed, auto-adds the
release to the blocklist via the spec-007 helper with
`reason = 'import-failed:extract-error'`, and the file stays in the
download client for manual inspection.

**Why this priority**: Without auto-blocklist, the search engine
would re-grab the same broken release on the next scheduled run.

**Independent Test**: Inject a corrupted `.7z` fixture; run the
importer; verify the import-history row records `success = false,
error_msg = 'extract-error:bad-archive'` and a blocklist row
appears with the same `(indexer_id, indexer_guid)` and a structured
reason.

**Acceptance Scenarios**:

1. **Given** a download whose extraction fails, **When** the
   pipeline handles the error, **Then** the import is marked failed
   AND a blocklist entry is created via the spec-007 helper with
   `added_by = 'system'`.
2. **Given** the same release is queued for re-grab by the search
   engine, **When** the pre-grab blocklist check runs (spec 007
   step 8), **Then** the release is filtered.

---

### User Story 7 — Concurrent imports of the same release coalesce safely (Priority: P2)

Two operators (or two simultaneous polling cycles) trigger the
import of the same release within milliseconds of each other. The
pipeline serialises on `(release_id, source_hash_sha1)`; the second
runner becomes an idempotent no-op rather than racing and creating
a duplicate Dump or a duplicate destination file.

**Why this priority**: Race conditions on imports are how
collections get corrupted in *arr land. Locking is non-negotiable.

**Independent Test**: Spawn 5 concurrent `import_one(...)` calls
for the same fixture; verify exactly one Dump row exists, exactly
one destination file exists, and 4 of the 5 import-history rows
record `success = true` with the `coalesced` flag set.

**Acceptance Scenarios**:

1. **Given** 5 concurrent imports of the same `(release_id,
   source_hash_sha1)`, **When** they race, **Then** exactly one
   completes the move + DB update; the other 4 detect the
   pre-existing Dump and complete as idempotent no-ops.
2. **Given** the lock is held by runner A and runner B's wait
   exceeds the lock-acquisition timeout (60 s), **When** B times
   out, **Then** B records the import as failed with
   `error_msg = 'lock_timeout'` and **does not** retry within the
   same poll cycle.

---

### User Story 8 — Manual import of an unidentified file (Priority: P3)

The operator drops a file into the watch folder; identification
fails (filename garbled, no DAT match, no header recognition). The
file appears under `/api/v3/rom/unidentified`. The operator opens
the UI (later spec) or hits the API directly to assign the file to
a Game + Release manually; the importer re-runs starting at step 9
(render) and lands the file properly.

**Why this priority**: Manual override is the safety valve when
auto-identification fails. Useful but not blocking.

**Independent Test**: Inject a file whose filename and headers
yield no Game match; verify it lands in `unidentified_dump`; POST
to `/api/v3/rom/unidentified/{id}/match` with `game_id` +
`release_id`; verify a Dump is created and the destination file
exists at the canonical path.

**Acceptance Scenarios**:

1. **Given** a file in `unidentified_dump`, **When** the operator
   POSTs the manual-match endpoint with a Game + Release reference,
   **Then** the importer runs starting at the render step; the
   profile gate becomes a warning rather than a hard stop;
   destination is materialised; the unidentified row is deleted.
2. **Given** the operator DELETEs an unidentified row, **When**
   the deletion runs, **Then** the database row is removed but the
   source file is **not** deleted (DELETE only clears the queue
   entry).

---

### User Story 9 — Webhook callback skips polling for instant imports (Priority: P3)

The operator configures qBittorrent's "Run external program on
torrent finished" to call Romarr's webhook endpoint with a
shared-secret token. When a download finishes, the webhook fires
within milliseconds, the import runs immediately, and the polling
loop is bypassed for that download.

**Why this priority**: Polling adds 0–30 s latency. Webhooks make
the experience feel real-time. Useful but not blocking.

**Independent Test**: Configure a webhook secret; POST a sample
qBit-shaped payload to `/api/v3/webhook/download-complete` with the
matching `X-Romarr-Webhook-Token` header; verify the import
pipeline runs for that specific download_id without waiting for the
30-second poll cycle.

**Acceptance Scenarios**:

1. **Given** a configured webhook secret matching the request's
   `X-Romarr-Webhook-Token` header, **When** the webhook fires,
   **Then** the importer runs immediately for the documented
   download identifier.
2. **Given** an incorrect or missing token, **When** the webhook
   fires, **Then** the response is HTTP 401 and no import runs.
3. **Given** the webhook references a download_id the client cannot
   confirm is complete, **When** the importer probes the client,
   **Then** the import is deferred with state `awaiting_completion`
   and the polling loop will pick it up.

---

### Edge Cases

- Archive contains multiple ROMs (compilation pack) → each is imported as a
  separate Release; if filenames don't disambiguate any of them, the whole
  batch is parked in `unidentified_dump` for manual review.
- File is identified but profile rejects → not imported, parked in
  `unidentified_dump`, file stays in download client untouched.
- Filesystem permissions error during move → import fails gracefully,
  retried with exponential backoff (3 attempts, 30 s / 2 min / 5 min).
- Disk full → import fails, source NOT deleted, `OnHealthIssue` event
  emitted with category `'disk-space'`.
- Download client unavailable when polling → poll cycle is skipped for that
  client; an `OnHealthIssue` event is emitted only after 10 minutes of
  sustained unavailability.
- Webhook token mismatch → HTTP 401; no log entry that exposes the expected
  token; rate-limit at 10 requests/minute per source IP to prevent token
  brute-forcing.
- Two distinct files inside the same archive that hash to the same SHA-1
  (e.g., dupe file in a compilation pack) → the second one becomes an
  idempotent no-op via the same `(release_id, source_hash_sha1)` lock.
- A `.cue` referencing `.bin` files that do not exist on disk → the multi-disc
  detector falls back to filename-pattern detection; the broken `.cue` is
  logged but does not block the rest of the import.
- An import is in progress while the operator deletes the target Library →
  the in-flight import completes (the lock keeps the Library reference
  alive); the post-import Dump row carries the now-orphaned `library_id`
  with `ON DELETE SET NULL` cleaning up later.
- Recursive archive depth exceeds 3 levels → the deepest archive is left
  unextracted and the file is parked in `unidentified_dump` with reason
  `extract:depth-exceeded`.

## Requirements *(mandatory)*

### Functional Requirements

**Watcher (step 1)**

- **FR-001**: The system MUST poll every configured download client every 30
  seconds (configurable per client) for downloads tagged `romarr` whose state
  is `completed` AND that lack the `romarr-imported` tag.
- **FR-002**: The system MUST expose a webhook endpoint at
  `POST /api/v3/webhook/download-complete` accepting a structured payload
  identifying a specific download. Authentication MUST be a shared-secret
  bearer token presented in the `X-Romarr-Webhook-Token` HTTP header,
  compared to the configured per-download-client secret in **constant time**
  (e.g., `hmac.compare_digest`). Mismatched, missing, or empty tokens
  MUST return HTTP 401 with no error body that exposes any portion of
  the expected token. The endpoint MUST be rate-limited to 10
  requests/minute per source IP (Edge Case). The system MUST NOT
  implement HMAC body signing at MVP — bearer-in-header is sufficient
  for the Romarr-qBit local-network use case.
- **FR-003**: A failed poll cycle for one client MUST NOT block polling of
  other clients; failures of one client persisting > 10 minutes MUST emit an
  `OnHealthIssue` event.

**Extractor (step 2)**

- **FR-004**: The system MUST extract `.zip`, `.7z`, and `.rar` archives
  recursively up to 3 levels of nesting; deeper nesting parks the file in
  `unidentified_dump` with reason `extract:depth-exceeded`.
- **FR-004a**: The extractor MUST defend against zip-bomb-style
  high-compression-ratio archives by capping uncompressed total
  expansion at `max(4 × archive_compressed_size, 5 GiB)`. The cap MUST
  be enforced incrementally as bytes are written (i.e., the writer
  short-circuits the moment cumulative output exceeds the cap; it
  MUST NOT wait for the full extraction to finish before checking).
  On overrun the extractor MUST: (a) abort the extraction, (b) delete
  any partially-extracted files for this archive, (c) park the source
  archive in `unidentified_dump` with
  `rejection_reason = 'extract:bomb-detected'`, (d) leave the source
  file in the download client untouched, and (e) emit an
  `OnHealthIssue` event with `category = 'extract-bomb'`. Per-archive
  format-specific protections (e.g., `py7zr`'s memory limit,
  `zipfile`'s symlink rejection) MUST also be applied where the
  underlying library exposes them.
- **FR-005**: When the operator's library has `preserve_archive = false`
  (default), the source archive MUST be deleted after a successful import;
  when `true`, the archive remains alongside the library file.
- **FR-006**: A pre-existing extracted folder whose content hash matches the
  archive's expected hash MUST be re-used (no double-extract).

**Hasher (step 3)**

- **FR-007**: For every candidate ROM file in the (possibly extracted)
  directory, the system MUST compute CRC32, MD5, and SHA-1 in a single
  streaming pass (re-uses spec 001's `Hasher`).
- **FR-008**: Files smaller than the per-platform `min_size_bytes` MUST be
  skipped to avoid hashing readme/license noise.

**DAT match (step 4)**

- **FR-009**: The system MUST query the spec-001 hash-match cascade (local
  DAT → Hasheous → PlayMatch); first authoritative match wins.
- **FR-010**: A DAT match populates `dat_verified = true`, `dat_source`,
  `dat_entry_id` on the resulting Dump.
- **FR-011**: No DAT match MUST NOT block import; `dat_verified = false`,
  warning logged, pipeline continues.

**Identification (step 5)**

- **FR-012**: The full identification cascade MUST run with the grab record's
  Torznab attributes (when available), the foundation filename parser
  dispatcher, and the foundation header readers; sources are merged per the
  spec-001 matcher's rules.

**Game match (step 6)**

- **FR-013**: When DAT match yields an entry that links to a known IGDB ID,
  the Game is resolved by `(platform_id, igdb_id)`.
- **FR-014**: Otherwise, the system MUST fuzzy-match the parsed title against
  monitored Games on the inferred platform using RapidFuzz at threshold
  **90** (stricter than search engine's 85).
- **FR-015**: Multiple Game candidates MUST be tie-broken by: profile region
  intersection (any monitoring library) → lower `id` (oldest).
- **FR-016**: A file with no Game match MUST be parked in `unidentified_dump`
  with `suggested_game_id` populated when the DAT entry knew an IGDB ID for
  an unmonitored Game.

**Multi-disc (step 7)**

- **FR-017**: The system MUST detect multi-disc sets via three heuristics in
  order: (a) `.cue/.bin` parent-child relationship, (b) explicit filename
  patterns (`(Disc N)`, `(CD N)`, `(Side A/B)`), (c) same-stem-different-
  disc-number heuristic.
- **FR-018**: Disc 1 becomes the parent Release (`parent_release_id IS NULL,
  disc_total = N`). Discs 2..N reference the parent.
- **FR-019**: For `.cue/.bin` pairs, hashing for DAT lookup MUST target the
  `.bin` (Redump references `.bin` hashes).

**Profile gate (step 8)**

- **FR-020**: The system MUST run Region/Language/Dump/Quality profile
  evaluation via spec 006's `ProfileEvaluator`; rejection parks the file in
  `unidentified_dump` with structured `rejection_reason`.
- **FR-021**: In the manual import flow with `?force=true`, profile rejection
  MUST be a warning (not a hard stop); the import proceeds.

**Renamer (step 9)**

- **FR-022**: The system MUST render the destination filename via spec 006's
  `NamingTemplateEngine` using the target library's bound Naming profile.
- **FR-023**: The full destination path MUST honour `platform_subfolder`,
  `multi_disc_subfolder`, and `replace_illegal_chars` flags from the Naming
  profile.

**Mover (step 10)**

- **FR-024**: The mover MUST attempt a hardlink first; cross-filesystem
  detection (`os.stat(source).st_dev != os.stat(dest_dir).st_dev`) MUST
  fall back to copy + verify hash + atomic rename.
- **FR-025**: An existing destination file with a matching SHA-1 MUST be
  treated as an idempotent no-op (no re-write, no Dump duplicate).
- **FR-026**: Existing destination with mismatching SHA-1 MUST NOT be
  overwritten unless the manual flow's `?force=true` flag is supplied.
- **FR-026a**: In the **automatic** import flow (i.e., when no
  `?force=true` is in scope), encountering an existing destination
  file with the same path but a different SHA-1 MUST: (a) leave the
  existing destination file untouched (no overwrite, no rename, no
  disambiguator); (b) park the incoming file in `unidentified_dump`
  with `rejection_reason = 'destination_collision'` and
  `suggested_game_id` populated when known; (c) emit an
  `OnHealthIssue` event with `category = 'naming-collision'` whose
  payload identifies the conflicting destination path, the existing
  Dump's id (when present), and the incoming source path; (d) leave
  the source file in the download client untouched. Auto-disambiguation
  via a numeric suffix (`(2)`, `(copy)`, etc.) is FORBIDDEN — it would
  silently mask Naming profile bugs.

**DB update (step 11)**

- **FR-027**: A successful move MUST set `Release.status = 'imported'` and
  create a Dump record with all hashes, format, path, `dat_verified`,
  `dat_source`, `dat_entry_id`, `original_filename`, `imported_at`,
  `imported_via` populated.
- **FR-028**: When the library's `keep_dump_history = false` (default) and
  the Release had a previous Dump, the previous Dump row AND its file MUST
  be deleted as part of the same transaction.

**Lifecycle (step 12)**

- **FR-029**: The post-import lifecycle MUST follow the library's
  `lifecycle_policy`:
  - `hardlink_and_seed` — tag the download `romarr-imported` and leave it
    seeding.
  - `move_and_remove` — tag, then schedule removal from the client after a
    grace period (default 5 minutes, configurable per library).
  - `copy_and_keep` — tag, do nothing else.
- **FR-030**: Lifecycle execution MUST be async and MUST NOT block
  completion of the import pipeline.

**Notify (step 13)**

- **FR-031**: A successful import MUST emit an `OnImport` event consumed by
  the future Notifications spec.
- **FR-032**: An import that replaces an existing Dump MUST emit an
  `OnUpgrade` event in addition to `OnImport`.

**Concurrency**

- **FR-033**: The pipeline MUST serialise concurrent imports of the same
  `(release_id, source_hash_sha1)` via an in-process advisory lock; the
  second runner becomes an idempotent no-op.
- **FR-034**: Lock acquisition has a hard timeout of 60 seconds; timeouts
  record `error_msg = 'lock_timeout'` and do NOT retry within the same poll
  cycle.

**Auto-blocklist on failure**

- **FR-035**: A failed import MUST auto-add the release to the blocklist via
  spec 007's helper with `reason = 'import-failed:<sub-reason>'`,
  `added_by = 'system'` **only when the failure subreason is one of the
  content-correctness subreasons defined by spec 007 FR-021**:
  `hash-mismatch`, `dat-rejected`, `format-corrupt`,
  `archive-extraction-failed`. The pipeline MUST use exactly these
  subreason strings (no aliases, no synonyms) so spec 007's helper can
  match them deterministically.
- **FR-035a**: Transient or operational failure subreasons —
  `disk-full`, `permission-denied`, `client-unreachable`, `move-failed`,
  `scan-timeout` — MUST be recorded in `import_history` with the failure
  reason set, MUST trigger the per-import exponential backoff retry
  policy (3 attempts: 30 s / 2 min / 5 min, per Edge Case), and MUST
  NOT call the blocklist helper. The release remains eligible for
  re-grab on the next scheduled search round.

**Manual import**

- **FR-036**: The system MUST expose `GET /api/v3/rom/import/manual` to list
  candidate files in a folder with their per-file identification attempts.
- **FR-037**: The system MUST expose `POST /api/v3/rom/import/manual`
  accepting a list of `(path, game_id, release_id?)` to trigger import per
  file; profile rejection is a warning when `?force=true`.
- **FR-038**: The system MUST expose
  `POST /api/v3/rom/unidentified/{id}/match`,
  `DELETE /api/v3/rom/unidentified/{id}` (does NOT delete the file),
  `POST /api/v3/rom/import/retry/{import_id}`, and
  `GET /api/v3/rom/import/history` (paginated).
- **FR-038a**: All mutating endpoints in FR-036 / FR-037 / FR-038
  (`POST /api/v3/rom/import/manual`,
  `POST /api/v3/rom/unidentified/{id}/match`,
  `DELETE /api/v3/rom/unidentified/{id}`,
  `POST /api/v3/rom/import/retry/{import_id}`) MUST require the
  caller to hold the `admin` role provided by the Auth spec.
  Read endpoints (`GET /api/v3/rom/import/manual`,
  `GET /api/v3/rom/import/history`) MUST be accessible to any
  authenticated user. The webhook endpoint
  (`POST /api/v3/webhook/download-complete`) MUST NOT consult the
  user session / API-key auth chain — it MUST authenticate solely
  via the bearer token in `X-Romarr-Webhook-Token` (FR-002), which
  is a per-download-client credential independent of user roles.
  Same pattern as specs 003 / 004 / 005 / 006 / 007.

### Key Entities

- **Import Round**: a single invocation of the pipeline for one source file.
  Produces exactly one `import_history` row.
- **Multi-Disc Group**: an in-memory collection of sibling files that map to
  parent + N children Releases.
- **Lifecycle Action**: an async post-import operation (tag, scheduled
  remove) parameterised by the library's lifecycle policy.
- **Unidentified Dump (extended)**: an `unidentified_dump` row gains
  `rejection_reason`, `library_id` (FK), and `suggested_game_id` (FK) so
  manual-import surfaces actionable hints.
- **Import History Entry**: an immutable audit row of one import round.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A fixture import of a known DAT-matching ROM produces a Dump
  record with `dat_verified = true` and a destination file at the canonical
  path in 100% of test cases.
- **SC-002**: A re-import of the same file produces zero duplicate Dump rows
  and zero duplicate destination files in 100% of test cases.
- **SC-003**: On the same filesystem, the destination is a hardlink (verified
  by inode equality) in 100% of imports; on a different filesystem, the
  copy + verify + delete fallback succeeds with matching SHA-1 in 100% of
  test cases.
- **SC-004**: A multi-disc PSX fixture (2 cue/bin pairs) produces exactly two
  Releases linked by `parent_release_id` with the correct `disc_number` and
  `disc_total` values, and both files in the same per-game subfolder.
- **SC-005**: A file with no DAT match is imported with `dat_verified = false`
  AND a warning recorded in 100% of test cases; the same file under a
  Quality profile with `require_dat_verified = true` is rejected at the
  profile gate (parked in `unidentified_dump`) in 100% of test cases.
- **SC-006**: A failed import auto-creates a blocklist row with
  `added_by = 'system'` and the structured `import-failed:<reason>` reason
  in 100% of failure-injected tests.
- **SC-007**: Five concurrent imports of the same release produce exactly one
  Dump row and one destination file across 100 trial iterations.
- **SC-008**: A webhook call with a valid token triggers an immediate import
  in under 1 second p95 (excluding hash time on large files); an invalid
  token returns HTTP 401 with no log entry exposing the expected token.
- **SC-009**: An import that crashes mid-move (simulated via fault injection)
  leaves the source file intact and never produces a partially-written
  destination in 100% of fault-injection tests.
- **SC-010**: Test coverage on the importer module MUST be at least 75%.

## Assumptions

These resolve the OPEN CLARIFICATIONS supplied with the input, applying the
operator's proposals.

- **Grace period before `move_and_remove` deletes**: 5 minutes default,
  configurable per library, allowing post-move hash verification.
- **Cross-filesystem detection**: `os.stat(source).st_dev !=
  os.stat(dest_dir).st_dev` triggers the copy + verify + delete fallback.
- **Webhook authentication**: a shared-secret token configured per download
  client, compared in constant time. Header `X-Romarr-Webhook-Token`. Rate
  limit 10 requests/minute per source IP.
- **Unmonitored-Game DAT match**: parked in `unidentified_dump` with
  `suggested_game_id` populated; the operator decides whether to start
  monitoring that Game.
- **Multi-disc cue+bin DAT hash target**: hash the `.bin` (Redump references
  `.bin` hashes; the `.cue` is small text and is not the cue's payload).

Other assumptions:

- The forward-referenced `library` table (Library spec, scheduled as 010 in
  the roadmap) supplies `library.path`, `library.lifecycle_policy`,
  `library.keep_dump_history`, `library.preserve_archive`. The Import spec's
  migration is gated on the `library` table existing; if Import lands first,
  the migration is no-op until Library lands.
- `OnImport` / `OnUpgrade` events are emitted onto an in-process pub/sub
  channel that the future Notifications spec consumes; no broker is
  introduced here.
- Library exporters (RomM push, gamelist.xml regen) are stubbed via the same
  pub/sub channel; the Library spec wires the actual generators.
- The download-client tag/category operations re-use the helpers from spec
  005.

### Out of Scope

- IPS / BPS patch application (deferred to v1+ — PatchManager spec).
- CHD / RVZ / NKIT format conversion (deferred to v1+ — Converter spec).
- Polished multi-disc UX (UI spec; this spec ships structural support only).
- Library exporters' actual generators (Library spec; this spec ships event
  hooks).
- Save data import (firm out per constitution).
- Bulk re-import / re-organize existing library (deferred to v1).
- Per-user import permissions (Auth spec).
