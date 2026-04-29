# Feature Specification: Foundation — Domain Model and Identification Pipeline

**Feature Branch**: `001-foundation` (branch creation skipped: git repo is in parent dir; spec dir created in-place)
**Created**: 2026-04-29
**Status**: Draft
**Input**: User description: "Build the foundation layer for Romarr: the domain model and the multi-source ROM identification pipeline. This is the bedrock layer — every other module (metadata, indexers, search, importer) will depend on it."

## Clarifications

### Session 2026-04-29

- Q: When the same SHA-1 matches DAT entries from multiple sources, which DAT's metadata wins on the merged Identification? → A: Fixed authority order **No-Intro > Redump > TOSEC**, first match wins; the other matches are recorded as supporting matches in the conflict log. Different ROM versions still produce different hashes and therefore separate Releases — this question only governs naming/tagging when the *same* hash is present in two DATs
- Q: How does the ISO9660 header reader disambiguate which disc-based platform an unknown ISO belongs to? → A: File-presence signature cascade: `SYSTEM.CNF` → PSX/PS2; `IP.BIN` boot sector → Mega CD / Saturn / Dreamcast; `default.xbe` → Xbox; unknown ISOs are queued in `unidentified_dump` for operator review (no guessing from volume identifier alone)
- Q: What auth model do the Hasheous and PlayMatch hash-match calls use? → A: Anonymous public endpoints, no key required (matches current production behaviour). HTTP 429 responses trip the per-service circuit breaker (FR-027). The base URL AND an optional bearer token are overridable via Romarr-prefixed environment variables, so a future requirement of authenticated access is a config change, not a code change
- Q: How does the conflict-confidence penalty stack when multiple conflicts fire on a single Identification? → A: Capped at a single 10% reduction regardless of conflict count. The conflict log records every pair so nothing is hidden, but the penalty itself does not stack; this prevents otherwise-trustworthy files from collapsing into `unidentified_dump` purely because three sources disagree on tagging
- Q: What threshold on the merged Identification confidence sends a file to `unidentified_dump`? → A: 0.5 — "more likely than not". A hash match alone (≈ 1.0), a clean No-Intro filename (≈ 0.85), and a header-only read (≈ 0.6) all clear the bar; pure-filename guesses below 0.5 fall into the unidentified queue for operator review

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Add a Game and keep multiple regions side by side (Priority: P1)

A Romarr operator wants to add *Sonic the Hedgehog* (Mega Drive) to a library
and later keep the USA, EUR, JPN, and a hack release simultaneously. The user
wants USA Rev 0 to remain the primary file even after Rev A becomes available,
because that is the version they played as a child.

**Why this priority**: Without the canonical Platform → Game → Release → Dump
hierarchy, no other Romarr capability has a place to live.

**Independent Test**: Create a Mega Drive Platform, attach a Game named *Sonic
the Hedgehog*, then add four Releases (USA, EUR, JPN, hack). Each Release is
independently addressable; cutoff and upgrade decisions evaluate per-Release.

**Acceptance Scenarios**:

1. **Given** the Mega Drive Platform exists and no Game named "Sonic the
   Hedgehog" exists for it, **When** the operator creates that Game, **Then**
   exactly one Game record is created bound to that Platform with a unique
   slug per Platform.
2. **Given** "Sonic the Hedgehog" exists on Mega Drive, **When** the operator
   creates a Game with the same title on Game Boy Advance, **Then** a second,
   distinct Game record is created — the two Games never share state.
3. **Given** "Sonic the Hedgehog" exists on Mega Drive, **When** the operator
   adds USA, EUR, JPN, and hack Releases, **Then** four Releases coexist;
   marking one as `cutoff_met` does not affect the others.

---

### User Story 2 — Verify a downloaded file against the No-Intro DAT (Priority: P1)

A Romarr operator wants `Sonic the Hedgehog (USA).md` to be hashed and
verified against the locally cached No-Intro DAT before it is treated as a
trusted Dump.

**Why this priority**: DAT verification is the highest-authority
identification source. Every downstream feature (search, grab, import) needs
it to be reliable before it can promise the user that a file is genuine.

**Independent Test**: Ingest a known-good No-Intro Mega Drive DAT into the
local cache; hash a fixture file whose hashes match a DAT entry; confirm the
identification reports `dat_verified = true`, the matching DAT source, and
the canonical name.

**Acceptance Scenarios**:

1. **Given** the No-Intro Mega Drive DAT is ingested, **When** the operator
   identifies a file whose SHA-1 matches a DAT entry, **Then** the
   identification result reports a positive DAT match, the canonical name,
   the source `no-intro`, and `dump_status = verified`.
2. **Given** the same DAT is re-ingested unchanged, **When** ingestion runs,
   **Then** no duplicate DAT entries are created and the operation is
   idempotent.
3. **Given** a 1 GB ROM on local SSD, **When** the operator triggers hashing,
   **Then** all of CRC32, MD5, and SHA-1 are produced from a single pass in
   under 10 seconds.

---

### User Story 3 — Identify a file with a useless filename via header bytes (Priority: P2)

A Romarr operator drops `game_001.bin` into a watch folder. The filename
parser yields nothing useful, but the header reader recognizes the file as a
Mega Drive ROM and surfaces the in-cartridge serial.

**Why this priority**: Header reading is the safety net when filenames are
useless. Required to keep recall high on imported third-party collections.

**Independent Test**: Provide a fixture file with a valid Mega Drive header
and a non-informative filename; verify the identification reports the
platform, region byte from the header, and a non-zero confidence even though
the filename parser failed.

**Acceptance Scenarios**:

1. **Given** a Mega Drive ROM with a recognizable header and a useless
   filename, **When** identification runs, **Then** the result includes
   header-derived data (region byte, in-cart serial) and explicitly records
   `header-read` as the contributing source.
2. **Given** an iNES file (4E 45 53 1A magic), **When** identification runs,
   **Then** mapper number, PRG size, and CHR size are extracted.
3. **Given** an ISO9660 image with a Primary Volume Descriptor, **When**
   identification runs, **Then** system identifier and volume identifier are
   extracted; if `SYSTEM.CNF` is present, the PSX game serial is extracted.

---

### User Story 4 — Identify and flag a known bad dump (Priority: P2)

A Romarr operator drops `sth_e_b.bin` (a GoodTools-style filename meaning
European bad dump of *Sonic the Hedgehog*). The system recognizes the
GoodTools convention and the bad-dump status.

**Why this priority**: Mis-identifying a bad dump as a verified release would
silently poison the library.

**Independent Test**: Run the GoodTools parser on `sth_e_b.bin`; verify it
yields region `EUR`, dump status `baddump`, naming convention `goodtools`,
confidence ≥ 0.7.

**Acceptance Scenarios**:

1. **Given** the filename `sth_e_b.bin`, **When** the parser dispatcher runs,
   **Then** the GoodTools parser wins and the result reports
   `dump_status = baddump`.
2. **Given** the No-Intro filename `Super Mario World (USA) (Rev A).sfc`,
   **When** the dispatcher runs, **Then** the No-Intro parser wins with
   confidence above 0.7, region `USA`, revision `Rev A`.
3. **Given** a filename that no parser recognizes with confidence above 0.7,
   **When** the dispatcher runs, **Then** the convention is reported as
   `unknown` and the file is queued in the unidentified-dump table.

---

### User Story 5 — Resolve identification conflicts deterministically (Priority: P2)

A Romarr operator wants the system to be predictable when sources disagree:
filename says `(USA)` but DAT says `(EUR)` → the file is treated as EUR and
the conflict is logged for review, not swallowed.

**Why this priority**: Quiet disagreement between sources is exactly how
silent corruption sneaks into a collection.

**Independent Test**: Construct a scenario where the filename parser yields
USA and the DAT match yields EUR; verify the merged identification reports
EUR, includes a recorded conflict, and reduces overall confidence by 10%.

**Acceptance Scenarios**:

1. **Given** filename = USA and DAT = EUR, **When** the matcher merges,
   **Then** EUR wins, a conflict entry is added, and the final confidence is
   reduced by 10%.
2. **Given** filename has `[h]` (hack tag) but DAT identifies the file as
   verified, **When** the matcher merges, **Then** `dump_status = verified`
   wins and the discrepancy is logged.
3. **Given** all four sources (hash, Torznab, header, filename) agree on
   region and dump status, **When** the matcher merges, **Then** confidence
   is taken as the maximum across sources with no penalty applied.

---

### User Story 6 — Recognize a multi-disc set structurally (Priority: P3)

A Romarr operator wants Disc 2 of a two-disc PlayStation game linked to
Disc 1 via `parent_release_id`, even before any grouping UI exists.

**Why this priority**: Storing the structural link now prevents data backfill
later. The grouping UX is deferred but the column must exist and be populated.

**Independent Test**: Create a Disc 1 Release with `disc_number = 1,
disc_total = 2`, then a Disc 2 Release with `disc_number = 2,
parent_release_id` pointing to Disc 1; verify the invariant
"`disc_number > 1` implies `parent_release_id` is set" is enforced.

**Acceptance Scenarios**:

1. **Given** a parent Release with `disc_number = 1, disc_total = 2`, **When**
   a child Release is created with `disc_number = 2` and `parent_release_id`
   pointing to the parent, **Then** the create succeeds.
2. **Given** the same parent, **When** a child Release is created with
   `disc_number = 2` but no `parent_release_id`, **Then** the create is
   rejected by the invariant.

---

### Edge Cases

- DAT entry with no hashes at all → rejected at ingestion.
- DAT entry whose `platform_id` does not match the file's identified
  platform → flagged as conflict, not silently merged.
- Operator deletes a Platform with Games attached → blocked
  (`ON DELETE RESTRICT`).
- Operator deletes a Game with Releases → cascades through Releases and
  Dumps.
- Two Dumps with the same absolute path → second insertion rejected by the
  unique-path constraint.
- Hasheous and PlayMatch unreachable → local DAT cache continues to serve;
  circuit breaker opens after 5 failures within 60 s.
- Filename parser tied with confidence ≥ 0.7 → first parser in dispatcher
  order wins (No-Intro → Redump → TOSEC → GoodTools → Scene); tie recorded.
- Header reader for an unsupported platform (3DS, NDS, PSP, …) → returns a
  clear "not yet supported" signal.
- Re-ingest of an unchanged DAT file → zero new rows (idempotent via
  `contents_hash`).

## Requirements *(mandatory)*

### Functional Requirements

**Domain model**

- **FR-001**: The system MUST persist nine domain tables: `platform`,
  `platform_format`, `platform_naming_token`, `game`, `release`, `dump`,
  `dat_entry`, `unidentified_dump`, `platform_pack`.
- **FR-002**: A Game MUST be bound to exactly one Platform.
- **FR-003**: A Game MUST be allowed any number of Releases; cutoff and
  upgrade decisions MUST operate per-Release, not per-Game.
- **FR-004**: A Release with `disc_number > 1` MUST have `parent_release_id`
  set; a Release referenced as a parent MUST have `disc_total > 1`.
- **FR-005**: A Dump MUST have a globally unique absolute `path` and MUST
  reference a Release whose Game's Platform matches the file's platform.
- **FR-006**: A `dat_entry` MUST have at least one of CRC32, MD5, or SHA-1.
- **FR-007**: Platform `slug` MUST be globally unique, lowercase, kebab-case.
- **FR-008**: For each domain entity, the system MUST expose three
  data-transfer schemas: Read, Create, Update.
- **FR-009**: The initial schema migration MUST seed five platforms (`nes`,
  `snes`, `megadrive`, `gameboy`, `gba`) with their format extensions.

**Identification pipeline**

- **FR-010**: The system MUST expose a single Identifier entry point that
  produces a structured Identification combining inputs from up to four
  sources: hash match, Torznab extended attributes, header read, filename
  parse.
- **FR-011**: The merger MUST resolve field-level conflicts using the
  authority order **hash-match > Torznab-attribute > header-read >
  filename-parse**.
- **FR-012**: The merger MUST log every conflict it resolves; the
  presence of one or more conflicts MUST reduce overall confidence by
  a flat 10% — the penalty MUST NOT stack regardless of how many
  pairwise conflicts fire on a single Identification. The conflict log
  records every pair so the operator retains full visibility.
- **FR-013**: When the filename indicates `[h]` (hack) but the DAT match
  reports a verified entry, the DAT MUST win and the discrepancy MUST be
  logged.

**Hashing**

- **FR-014**: The hasher MUST compute CRC32, MD5, and SHA-1 in a single
  pass; SHA-256 MUST be optional and disabled by default.
- **FR-015**: The hasher MUST stream with a configurable buffer (default
  1 MiB).
- **FR-016**: When invoked from an asynchronous context, the hasher MUST run
  off the event loop.

**DAT manager**

- **FR-017**: The DAT manager MUST ingest Logiqx-XML DATs in a streaming
  fashion sufficient to handle ~200 MB inputs without exhausting memory.
- **FR-018**: The DAT manager MUST expose lookups scoped to a Platform:
  `lookup_by_sha1`, `lookup_by_crc32`, `lookup_by_md5`, `lookup_by_name`.
- **FR-019**: DAT ingestion MUST be idempotent via a stored `contents_hash`.
- **FR-020**: MVP MUST ingest No-Intro DATs. Redump and TOSEC interfaces
  MUST be defined in code; their actual ingestion is deferred.
- **FR-020a**: When a single hash (CRC32 / MD5 / SHA-1) matches entries
  from multiple DAT sources, the merged Identification MUST carry the
  metadata (canonical name, region, dump_status, naming convention) of
  the first match in the fixed authority order **No-Intro > Redump >
  TOSEC**. The other matches MUST be recorded as supporting matches in
  the conflict log so no information is lost. This rule applies only to
  cross-DAT collisions on a single hash; multiple Releases of the same
  Game (different revisions, regions, or hacks) have different hashes
  and remain stored as distinct Releases per FR-003.

**Filename parsers**

- **FR-021**: Four parsers MUST be implemented behind a common interface:
  No-Intro, GoodTools, TOSEC, Scene.
- **FR-022**: Each parser MUST emit a structured `ParsedFilename`
  (title, regions, languages, revision, dump_status, tags, convention,
  confidence ∈ [0.0, 1.0]).
- **FR-023**: A dispatcher MUST try parsers in fixed order, accept the
  first whose confidence > 0.7, and fall back to convention `unknown`
  otherwise.

**Header readers**

- **FR-024**: Three header readers MUST be implemented in MVP behind a
  common interface: iNES, Mega Drive, ISO9660.
- **FR-024a**: The ISO9660 reader MUST disambiguate the disc-based
  platform via a file-presence signature cascade evaluated against the
  mounted image, in order:
  1. `SYSTEM.CNF` at the volume root → PSX or PS2 (further disambiguated
     by the `BOOT2 =` line in `SYSTEM.CNF`: `cdrom0:\SLPS_…` / `SCUS_…`
     hints PSX; `cdrom0:\SLES_…` / `SCES_…` may be PSX or PS2 — the PS2
     `SYSTEM.CNF` carries a `VER =` line that PSX does not).
  2. `IP.BIN` boot sector at LBA 0 with a recognizable system identifier
     string (`SEGA SEGASATURN`, `SEGA MEGADRIVE`, `SegaDiscSystem`,
     `SEGA SEGAKATANA` for Dreamcast) → Mega CD / Saturn / Dreamcast,
     respectively.
  3. `default.xbe` at the volume root → original Xbox.
  4. None of the above → the reader returns `platform = unknown`; the
     dump is queued in `unidentified_dump` (FR-029) with the volume
     identifier and any extracted serial preserved for operator review.
  The reader MUST NOT guess the platform from the Primary Volume
  Descriptor's volume identifier string alone (homebrew and unofficial
  discs frequently carry misleading identifiers).
- **FR-025**: Header readers for 3DS, NDS, PSP, Vita, Switch, Wii,
  GameCube, and GBA MUST exist as stubs raising a clear "not yet
  supported" error.

**Hash-match cascade**

- **FR-026**: The hash-match cascade MUST query, in parallel, three
  backends: local DAT cache, Hasheous remote API, PlayMatch remote API.
- **FR-026a**: Hasheous and PlayMatch MUST be called as anonymous public
  endpoints by default (no API key required). The base URL and an
  optional bearer token MUST be overridable via Romarr-prefixed
  environment variables (`ROMARR_HASHEOUS_BASE_URL`,
  `ROMARR_HASHEOUS_TOKEN`, `ROMARR_PLAYMATCH_BASE_URL`,
  `ROMARR_PLAYMATCH_TOKEN`); when a token is set, the client MUST send
  it as `Authorization: Bearer …`. No per-user, per-instance, or
  Settings-UI key surface is introduced in this spec.
- **FR-027**: Each remote backend MUST be guarded by a per-service circuit
  breaker that opens after 5 failures within a 60-second window. HTTP
  429 (Too Many Requests) responses MUST count as failures for the
  purpose of breaker tripping.
- **FR-028**: When all remote backends are down, the local DAT cache MUST
  continue to serve.

**Unknown / unidentified files**

- **FR-029**: A file whose merged Identification confidence (post the
  flat 10% conflict penalty when applicable) is **below 0.5** MUST be
  recorded in `unidentified_dump` with discovery time, path, size,
  attempted hashes, attempt count, and last error. Files at or above
  0.5 proceed downstream as identified — this admits hash-only matches
  (≈ 1.0), clean No-Intro filenames (≈ 0.85), and header-only reads
  (≈ 0.6), while keeping pure low-confidence parser guesses out of
  the trusted set.

### Key Entities

- **Platform**: A console or handheld system. Holds external metadata
  provider IDs and visual identity. Owns its formats and naming tokens.
- **Platform Format**: A file extension recognized for a Platform.
- **Platform Naming Token**: A regex pattern + meaning enabling
  per-platform filename interpretation.
- **Game**: A title bound to exactly one Platform.
- **Release**: A region/revision/dump-status variant of a Game.
- **Dump**: The actual file on disk for a Release, with hashes.
- **DAT Entry**: A canonical record from a No-Intro / Redump / TOSEC /
  Hasheous / PlayMatch authoritative database.
- **Unidentified Dump**: A file the pipeline could not match with
  confidence above threshold; queued for retry or manual review.
- **Platform Pack**: A versioned bundle applied without schema migration.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Operators can create a new Game on a seeded Platform and
  attach four distinct Releases (USA, EUR, JPN, hack) in under 60 seconds
  of operator time, without cross-Release side-effects.
- **SC-002**: Hashing a 1 GB ROM on local SSD completes in under 10 seconds.
- **SC-003**: The filename parser dispatcher correctly identifies at least
  95% of a fixture corpus of approximately 100 filenames per convention
  (≈400 fixtures total).
- **SC-004**: The header reader correctly identifies 100% of a fixture set
  covering iNES, Mega Drive, and ISO9660 inputs (including a PSX disc with
  `SYSTEM.CNF` serial extraction).
- **SC-005**: The matcher produces the expected Identification on five
  representative scenarios (clean No-Intro DAT-matched file; garbage
  filename with DAT match; no DAT, clean filename; filename/DAT region
  conflict; multi-disc detection) with conflict logs and confidence
  adjustments matching FR-011 and FR-012.
- **SC-006**: Re-ingesting an unchanged DAT produces zero new database
  rows and completes in under 5 seconds.
- **SC-007**: When both Hasheous and PlayMatch are reachable, an
  end-to-end hash lookup of a known SHA-1 returns a match in under 2
  seconds at p95; with both unreachable, the local DAT cache returns a
  match in under 200 ms at p95.
- **SC-008**: All foundation modules (domain entities and identification
  pipeline) MUST be importable from a Python REPL without booting the
  HTTP layer.
- **SC-009**: Backend test coverage MUST be ≥ 80% on the domain layer,
  ≥ 80% on the identification pipeline layer, and ≥ 70% overall.
- **SC-010**: Strict static type checking and linting on the foundation
  layers MUST produce zero warnings on the integration branch.

## Assumptions

These resolve the four open clarifications with the proposals supplied in
the feature description; they may be revisited in future amendments.

- **Region codes**: Stored in ISO-3166-1 alpha-2 form (`US`, `JP`, `EU`).
  No-Intro forms (`USA`, `JPN`, `EUR`) and other surface forms are
  accepted on input via a translation table maintained inside the
  identification layer.
- **Language codes**: Stored in ISO-639-1 form (`en`, `fr`, `ja`).
- **Confidence aggregation**: The matcher uses `max()` across contributing
  sources for the initial implementation, with a 10% reduction applied
  when conflicts are detected.
- **Remote hash-match endpoints**: Hasheous and PlayMatch base URLs are
  hardcoded to public defaults and overridable via Romarr-prefixed
  environment variables.

Other assumptions:

- The 5 MVP platforms (NES, SNES, Mega Drive, Game Boy, Game Boy Advance)
  are sufficient to exercise every code path. Adding more platforms later
  is a Platform Pack operation, not a new spec.
- The DAT release cadence is weekly; this feature does not schedule
  refreshes — that belongs to a later spec on background scheduling.
- Operators run Romarr on local storage with conventional Linux
  filesystem semantics. Performance targets assume local SSD storage.

### Out of Scope (Deferred to Other Specs)

- REST API endpoints (deferred to the API spec).
- UI for managing DATs.
- Background scheduling of DAT updates.
- Metadata enrichment after identification.
- Integration with indexers and download clients.
- TOSEC and Redump DAT ingestion (interfaces defined; ingestion deferred).
- Header readers for: 3DS, NDS, PSP, Vita, Switch, Wii, GameCube
  (stubbed).
- Multi-disc grouping logic (only structural support here).
- Patch detection (IPS / BPS file recognition).
- Format-conversion side effects on identification.
