# Feature Specification: Platform Packs

**Feature Branch**: `003-platform-packs` (branch creation skipped: git repo lives in parent dir)
**Created**: 2026-04-29
**Status**: Draft
**Depends on**: `001-foundation` — uses `Platform`, `PlatformFormat`, `PlatformNamingToken`, `platform_pack` from the foundation domain model
**Input**: User description: "Build the Platform Pack system. Platforms are data, not code. A pack is a date-versioned YAML file that defines platforms in bulk: slugs, names, metadata IDs, formats, header signatures, naming tokens, parsing strategies. The system makes Romarr forward-compatible — new consoles ship as YAML packs without schema migrations or code changes."

## Clarifications

### Session 2026-04-29

- Q: How does pack validation defend against catastrophic-backtracking regexes in `platform_naming_token` patterns and `parsing_strategies`? → A: Compile every pack-defined regex AND time-bound it against a 256-byte adversarial test input with a 50 ms budget; any regex whose match exceeds the budget is rejected at validation time before any DB write
- Q: What's the YAML deserializer + upload-size policy for community packs? → A: `yaml.SafeLoader` mandatory (no Python tag execution), 1 MB body cap (HTTP 413 on overrun), 200-platform-per-pack cap (HTTP 400 on overrun). Both caps are non-configurable hard limits
- Q: When two packs define the same slug at different times, what does "latest wins" mean? → A: `pack_version` order. A pack whose `pack_version` is older than what's currently recorded for any of its platform slugs MUST be rejected with HTTP 409 (downgrade rejected). The `pack_source = 'user'` override mechanism remains the legitimate path for keeping older-style behaviour on a specific slug
- Q: What role is required to invoke the platform-pack and override / format-CRUD endpoints? → A: Admin-only on all mutating endpoints (pack upload / re-apply / override / format CRUD); reads (`GET`) accessible to any authenticated user. The Auth spec's `admin` / `user` role model is the granularity used; no per-endpoint ACL
- Q: Where does the `parsing_strategies` table live and who owns its migration? → A: Spec 003 (Platform Packs) owns it. Its DDL is documented in 003's `data-model.md` and its migration ships in `0003_platform_packs.py`. Spec 001's "nine tables" wording was scoped to the foundation layer and is unchanged

## User Scenarios & Testing *(mandatory)*

### User Story 1 — First-boot operator gets a usable platform catalog (Priority: P1)

A Romarr operator launches the container for the first time. The
`platform_pack` table is empty. The application MUST detect this and
auto-apply the built-in Platform Pack, leaving the operator with a
ready catalog of approximately 20 platforms (cartridge, disc-based,
handheld modern, modern) before they touch any settings.

**Why this priority**: Without a seeded catalog the application is
unusable; a user opening the UI to a blank platform list would not
know what to do next.

**Independent Test**: Boot a fresh instance with an empty database;
verify that, by the time the application is ready to serve traffic,
the `platform_pack` table holds one row (the built-in pack), the
`platform` table holds approximately 20 rows marked
`pack_source = 'builtin'`, and an audit-log row records the
application as `applied`.

**Acceptance Scenarios**:

1. **Given** a fresh database and the built-in pack file present at
   the documented path, **When** the application starts, **Then**
   the built-in pack is applied within 5 seconds and the catalog
   contains the documented platforms with their formats and naming
   tokens.
2. **Given** a database that already records the built-in pack as
   applied with the same `contents_hash`, **When** the application
   starts, **Then** the pack is **not** re-applied and the boot
   completes without DB writes related to platforms.
3. **Given** a database that records an older built-in pack version,
   **When** the application starts with a newer built-in pack file,
   **Then** the newer pack is applied and an audit-log row is
   recorded.

---

### User Story 2 — Community pack upload extends the catalog (Priority: P1)

A Romarr operator wants to upload a community-authored YAML pack
(e.g., one that adds Atari Lynx and Vectrex). The pack is validated
against the JSON Schema before any database write happens; on
success, new platforms are added without disturbing existing ones.

**Why this priority**: This is the core forward-compatibility
mechanism. Without it, every new console requires a code release.

**Independent Test**: Build a small valid YAML pack adding two new
platforms; upload it via the API; verify the platforms appear, marked
`pack_source = 'community'`, with their formats and naming tokens.

**Acceptance Scenarios**:

1. **Given** a valid community pack YAML, **When** the operator
   uploads it, **Then** the pack is validated, applied
   transactionally, and an audit-log row records the application
   with the list of platforms added/updated.
2. **Given** a YAML file with bad syntax (e.g., truncated mid-document),
   **When** the operator uploads it, **Then** the response is HTTP 400
   with an explicit YAML-parse error message and **zero** database
   rows are written.
3. **Given** a YAML file that parses but violates the schema (e.g.,
   missing the required `pack_version` field, or `format_type` outside
   the allowed enum), **When** the operator uploads it, **Then** the
   response is HTTP 400 with a structured list of schema violations
   citing the offending JSON path, and **zero** database rows are
   written.

---

### User Story 3 — User override protects local edits (Priority: P1)

A Romarr operator has manually edited the Mega Drive platform — added
a custom format, renamed the platform, set a custom IGDB ID. They
mark it as user-overridden. A later pack update arrives that would
modify the Mega Drive platform; their edits are preserved.

**Why this priority**: Operator trust depends on the system never
silently overwriting curated configuration.

**Independent Test**: Apply pack A defining `megadrive`; mark
`megadrive` as user-overridden; apply pack B (newer version, also
defining `megadrive` with different fields); verify `megadrive` rows
are unchanged.

**Acceptance Scenarios**:

1. **Given** a Platform with `pack_source = 'user'`, **When** a pack
   defining the same `slug` is applied, **Then** the platform row
   and its formats and naming tokens are unchanged; an audit-log row
   records the platform as `skipped`.
2. **Given** an overridden platform, **When** the operator releases
   the override (pack_source flips back to `'community'` or
   `'builtin'`), **Then** the next pack apply updates the platform
   normally.
3. **Given** an overridden platform, **When** the operator adds a
   custom format via the format-CRUD endpoints, **Then** the new
   format inherits `pack_source = 'user'` and is exempt from pack
   replacement.

---

### User Story 4 — Re-apply same pack is a no-op (Priority: P2)

A Romarr operator re-uploads the exact same pack YAML they applied
yesterday. The system detects identical version + contents hash and
short-circuits without any DB writes.

**Why this priority**: Idempotency is a must-have for safe re-runs
during operator experimentation and for downstream automation.

**Independent Test**: Apply a pack; capture the
`platform.updated_at` timestamps; re-apply the same pack; verify
timestamps are unchanged and the audit log records `skipped`.

**Acceptance Scenarios**:

1. **Given** a pack with version V and contents hash H is already in
   `platform_pack`, **When** the same YAML is uploaded again,
   **Then** the response is HTTP 200 with a "no changes" indicator
   and zero rows in `platform`, `platform_format`, or
   `platform_naming_token` are touched.
2. **Given** a pack with version V already applied, **When** a YAML
   with the same version V but a **different** contents hash is
   uploaded, **Then** the response is HTTP 409 with a clear
   "version-conflict" message; the operator is asked to bump the
   pack version.

---

### User Story 5 — Pack with bad references is rejected (Priority: P2)

A Romarr operator uploads a pack whose `parent_platform_slug` points
to a slug that does not exist (or forms a cycle). The validator
detects the bad reference before any write and returns a structured
error.

**Why this priority**: The platform table has a self-FK; a cyclic or
dangling parent reference would produce a corrupted graph that's
expensive to recover from.

**Independent Test**: Build a pack where Platform A's
`parent_platform_slug = 'b'` and Platform B's
`parent_platform_slug = 'a'`; upload; verify HTTP 400 with a clear
"cycle in parent_platform_slug" message.

**Acceptance Scenarios**:

1. **Given** a pack containing `parent_platform_slug` referring to a
   slug that is neither in the pack nor already in the database,
   **When** uploaded, **Then** validation fails with a
   "dangling parent reference" error citing the bad slug.
2. **Given** a pack whose platforms form a cycle in
   `parent_platform_slug`, **When** uploaded, **Then** validation
   fails with a "cycle detected" error citing the cycle members.

---

### User Story 6 — Validate without applying (Priority: P3)

A Romarr operator wants to see what a pack would change **before**
applying it. They use a validate-only endpoint that returns the
diff (would-be inserts, updates, skips) without touching the
database.

**Why this priority**: This is the "git status before git push" of
pack uploads. Useful for confidence but not blocking the basic flow.

**Independent Test**: Apply pack A; upload pack B (which updates one
platform from A) to the validate-only endpoint; verify the response
lists exactly the changed fields without writing anything.

**Acceptance Scenarios**:

1. **Given** a database with state S and a candidate pack P, **When**
   the operator hits the validate-only endpoint with P, **Then** the
   response includes a structured diff of would-be changes and
   `database_state_unchanged = true`.

---

### User Story 7 — Audit trail of pack applications (Priority: P3)

A Romarr operator wants to know who applied which pack when, and
which platforms changed in each application.

**Why this priority**: Important for support and debugging but not
in the critical path for daily operation.

**Independent Test**: Apply 3 packs over time; query the audit log;
verify each pack has one row with the right action, timestamps,
status, and `platforms_affected` list.

**Acceptance Scenarios**:

1. **Given** the operator has applied 3 packs, **When** they query
   the audit-log endpoint, **Then** they see 3 rows ordered most
   recent first with action, status, started/finished timestamps,
   and the list of platforms touched.
2. **Given** a pack application that failed mid-transaction, **When**
   the operator queries the audit log, **Then** the failed run is
   recorded with `status = 'failed'`, the error message, and the
   transaction is rolled back so the database is in its
   pre-application state.

---

### Edge Cases

- Pack file with an extra unknown top-level key → schema validation
  rejects (additionalProperties = false) with a clear error.
- Pack with two platforms sharing the same `slug` → rejected at
  validation time as "duplicate slug within pack".
- Pack with two formats sharing the same `extension` for the same
  platform → rejected at validation time as "duplicate extension on
  platform <slug>".
- Pack-defined `parsing_strategy` whose `apply_to_platforms` lists a
  slug not present anywhere → warning logged, the strategy is still
  inserted (the orphan is treated as benign).
- Two packs apply over time, both define the same slug as
  `pack_source = 'community'` → the higher `pack_version` wins
  (FR-013a); a pack with an older version than what's currently
  recorded is rejected with HTTP 409 ("downgrade rejected"); the
  operator bumps the version or releases the override on the
  specific slugs they want to rewind. An audit-log row records
  every accepted update.
- A pack tries to **delete** a platform → not supported (packs are
  add/update only). Removing a platform that has user Games would
  break referential integrity.
- The application starts but the built-in pack file is missing from
  the image → application starts, logs a structured warning, and
  serves traffic with whatever was previously seeded; the operator
  can remediate by uploading a pack via the API.
- Built-in pack file present but its `schema_version` is greater
  than the application's supported `schema_version` → the
  application refuses to apply it and logs a clear "upgrade Romarr
  to apply this pack" message.
- Operator marks a platform as user-overridden, then later releases
  the override → the platform's `pack_source` reverts to whatever
  pack last touched it (`'builtin'` or `'community'`), and the next
  matching pack apply will be allowed to update it.

## Requirements *(mandatory)*

### Functional Requirements

**Pack format & validation**

- **FR-001**: A Platform Pack MUST be a single YAML document
  conforming to the documented JSON Schema (see `data-model.md`).
- **FR-001a**: All pack YAML MUST be deserialized with
  `yaml.SafeLoader` (PyYAML) or an equivalent safe loader. The
  default unsafe loader (which permits arbitrary Python object
  construction via `!!python/object/apply` and similar tags) MUST
  NOT be used for any pack input — built-in or community-uploaded.
- **FR-001b**: A pack upload MUST be rejected before YAML parsing
  when the request body exceeds 1 MiB; the response MUST be
  HTTP 413 (Payload Too Large) with a clear size-limit message.
  This cap MUST NOT be configurable.
- **FR-001c**: A pack whose top-level `platforms` list contains
  more than 200 entries MUST be rejected with HTTP 400 and a
  clear platform-count-limit message. This cap MUST NOT be
  configurable.
- **FR-002**: A pack MUST carry `pack_version` (date-based,
  `YYYY.MM.NNN`), `schema_version` (integer), and `platforms` (list).
  `description`, `author`, `source_url`, and `parsing_strategies` are
  optional.
- **FR-003**: Each platform definition MUST carry `slug`, `name`,
  `manufacturer`, and `formats`. Other fields (metadata IDs, naming
  tokens, parent-platform reference, icon URL) are optional.
- **FR-004**: Each format definition MUST carry `extension` and
  `format_type`. The `format_type` value MUST be one of
  `cartridge | disc | compressed | archive | package`.
- **FR-005**: Validation MUST reject:
  - YAML parse errors (HTTP 400, structured error).
  - JSON-Schema violations (HTTP 400, list of violations with JSON paths).
  - Duplicate `slug` within a single pack.
  - Duplicate `extension` for the same platform.
  - Dangling `parent_platform_slug` references (slug not present in
    the pack and not in the database).
  - Cycles in `parent_platform_slug` references.
- **FR-005a**: Validation MUST defend against catastrophic-backtracking
  regexes contained in pack-defined `platform_naming_token.pattern`
  values and in `parsing_strategies` regex templates. For every
  pack-defined regex, validation MUST: (a) compile it (rejection on
  `re.error`); (b) execute the compiled pattern against a 256-byte
  adversarial test input on a worker thread with a 50 ms wall-clock
  budget; (c) reject the pack with HTTP 400 and a structured error
  identifying the offending regex's JSON path if any single regex
  exceeds the budget. The adversarial test input MUST be a fixed
  byte string designed to provoke quadratic/exponential backtracking
  in common bad patterns (e.g., long runs of `a` followed by `!`).
  No DB write occurs before all regexes pass.
- **FR-006**: A pack with `schema_version` greater than the
  application's supported version MUST be rejected with a clear
  upgrade-required message.

**Pack ingestion**

- **FR-007**: Pack ingestion MUST be transactional. Any failure
  during application MUST roll back the entire pack — no partial
  state shall survive.
- **FR-008**: The system MUST compute a `contents_hash` (SHA-256)
  over a canonicalized form of the pack body and persist it on the
  `platform_pack` row.
- **FR-009**: Ingestion MUST be **fully idempotent**: re-applying a
  pack with identical `pack_version` and `contents_hash` MUST not
  touch any platform/format/naming-token row and MUST record an
  audit-log row with `action = 'skipped'`.
- **FR-010**: A pack with the same `pack_version` but a different
  `contents_hash` MUST be rejected with HTTP 409 and a "bump the
  version" message.

**Per-platform application rules**

- **FR-011**: For each platform in a pack: if the slug does not
  exist in the database, the system MUST INSERT a new platform with
  its formats and naming tokens, marking each row's `pack_source`
  with the pack's origin (`'builtin'` for the shipped pack,
  `'community'` for an uploaded pack).
- **FR-012**: If the slug exists with `pack_source = 'user'`, the
  system MUST SKIP that platform entirely (no row touched), record
  it in the audit log as `skipped`, and emit a structured warning.
- **FR-013**: If the slug exists with `pack_source` of `'builtin'`
  or `'community'`, the system MUST UPDATE the platform's mutable
  fields, **REPLACE** its formats and naming tokens (delete old,
  insert new), and bump `pack_version` on the platform row.
- **FR-013a**: A pack MUST be rejected with HTTP 409 (Conflict) and
  a structured "downgrade rejected" error citing the offending
  slug(s) when its `pack_version` is older than the
  currently-recorded `pack_version` on any non-user-overridden
  platform row whose slug appears in the pack. Comparison uses the
  pack's documented `YYYY.MM.NNN` lexical ordering (which equals
  date order). Slugs marked `pack_source = 'user'` are out of
  scope for this check (they're skipped per FR-012). The operator's
  remediation paths are: bump the pack's `pack_version`, or release
  the override on the specific platforms they want rewound and
  apply the older pack with the override flow.
- **FR-014**: Pack-defined parsing strategies MUST be inserted into
  the `parsing_strategies` table; if an existing strategy has the
  same `id`, it MUST be REPLACED (delete + insert).
- **FR-014a**: The `parsing_strategies` table is owned by this spec
  (003 — Platform Packs), not by the foundation spec. Its DDL MUST
  be defined in this spec's `data-model.md` and its creation MUST
  ship in this spec's Alembic migration (e.g., `0003_platform_packs.py`).
  Spec 001's FR-001 list of nine tables is scoped to the foundation
  layer and remains unchanged; later specs are permitted to add
  their own tables via their own migrations.
- **FR-015**: Packs MUST NOT delete platforms. Removal is out of
  scope; operators wanting to drop a platform must do so via a
  separate explicit operation in a future spec.

**Built-in pack & first-boot behaviour**

- **FR-016**: The application MUST ship a built-in pack at the
  documented path inside the container image; this file MUST be
  read-only.
- **FR-017**: On startup, when the `platform_pack` table is empty
  (or no row matches the built-in pack's version + contents_hash),
  the application MUST auto-apply the built-in pack with
  `applied_by = 'system'`.
- **FR-018**: The built-in pack MUST contain the documented
  approximately-twenty MVP+ platforms (cartridge, disc-based,
  handheld modern, modern) with their proper IGDB and ScreenScraper
  IDs, format extensions, parser strategies, and naming tokens.
- **FR-019**: If the built-in pack file is missing or unreadable,
  the application MUST start, log a structured warning, and
  continue serving traffic. It MUST NOT crash.

**User override flow**

- **FR-020**: An operator MUST be able to mark a platform as
  user-overridden, which sets `pack_source = 'user'` on the
  platform row and on every row of `platform_format` and
  `platform_naming_token` belonging to that platform.
- **FR-021**: An operator MUST be able to release the override on
  a previously-overridden platform; the next pack application is
  allowed to touch that platform again.
- **FR-022**: When a platform is user-overridden, the operator MUST
  be able to add, edit, and remove formats on it via the formats
  CRUD endpoints; new and edited formats are tagged
  `pack_source = 'user'` and exempt from pack replacement.

**Audit trail**

- **FR-023**: Every pack application attempt (success, skip, or
  failure) MUST produce a row in `platform_pack_application_log`
  with `pack_version`, `action`, `platforms_affected` (list of
  slugs), `started_at`, `finished_at`, `status`, and an optional
  `error_message`.
- **FR-024**: Failed pack applications MUST roll back the database
  to its pre-application state and the audit-log row's `status`
  MUST be `'failed'` with the error captured.

**API surface (full implementation in API spec; this feature
delivers wired stubs)**

- **FR-025**: The system MUST expose endpoint stubs at:
  - `POST /api/v3/rom/platform-pack/upload` (multipart YAML upload, validates and applies)
  - `GET /api/v3/rom/platform-pack` (list applied packs)
  - `GET /api/v3/rom/platform-pack/{version}` (detail)
  - `POST /api/v3/rom/platform-pack/{version}/apply` (re-apply a stored pack)
  - `POST /api/v3/rom/platform-pack/validate` (dry-run validation)
  - `POST /api/v3/rom/platform/{id}/override` (mark user-overridden)
  - `DELETE /api/v3/rom/platform/{id}/override` (release override)
  - `GET /api/v3/rom/platform/{id}/formats` (list formats)
  - `POST /api/v3/rom/platform/{id}/formats` (add format on overridden platform)
  - `PUT /api/v3/rom/platform/{id}/formats/{format_id}` (edit format on overridden platform)
  - `DELETE /api/v3/rom/platform/{id}/formats/{format_id}` (remove format on overridden platform)
- **FR-026**: Format mutation endpoints (POST/PUT/DELETE on
  `/formats`) MUST refuse to mutate a format whose underlying
  platform is NOT user-overridden, and MUST return HTTP 409 with a
  clear message instructing the operator to mark the platform as
  user-overridden first.
- **FR-026a**: Every mutating endpoint in FR-025 (pack upload,
  re-apply, validate, override set/release, format CRUD) MUST
  require the caller to hold the `admin` role provided by the Auth
  spec. Read endpoints (`GET /api/v3/rom/platform-pack`,
  `GET /api/v3/rom/platform-pack/{version}`,
  `GET /api/v3/rom/platform/{id}/formats`) MUST be accessible to
  any authenticated user. Unauthenticated requests on any of
  these endpoints MUST be rejected with HTTP 401; authenticated
  but non-admin requests on a mutating endpoint MUST be rejected
  with HTTP 403. No per-endpoint ACL is introduced — the
  admin / user binary from Auth is the granularity used.

### Key Entities

- **Platform Pack**: A versioned YAML document describing a set of
  platforms, their formats, naming tokens, and optional parsing
  strategies. Identified by `pack_version` + `contents_hash`.
- **Parsing Strategy**: A reusable named regex template that
  platforms can reference. Stored in a dedicated table because
  multiple platforms may share the same strategy and a strategy
  may outlive any individual platform definition.
- **Platform Pack Application Log**: An immutable audit row per
  ingestion attempt. Stores the action, status, error, and the
  list of platforms touched.
- **User Override Marker**: A row state (`pack_source = 'user'`)
  on platform / format / naming-token records that prevents future
  pack applications from modifying those rows.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On first boot of a fresh instance, the built-in pack
  is auto-applied within 5 seconds and produces approximately
  twenty platforms ready for use.
- **SC-002**: Re-uploading an unchanged pack produces zero database
  writes related to platforms / formats / naming tokens, and one
  audit-log row with `action = 'skipped'`.
- **SC-003**: A user-overridden platform survives every pack apply
  in a 100-iteration test loop unchanged in 100% of iterations.
- **SC-004**: Validation rejects 100% of malformed-YAML and
  schema-violating inputs in a fixture corpus of at least 20
  intentionally-broken packs, each with a clear error message
  citing the offending location.
- **SC-005**: Ingestion of a 100-platform pack on local SQLite
  completes in under 5 seconds end-to-end.
- **SC-006**: Failed pack applications leave the database in its
  pre-application state in 100% of injected-failure tests.
- **SC-007**: Test coverage on the platform-packs module is at
  least 80%.

## Assumptions

These resolve the OPEN CLARIFICATIONS supplied with the input,
applying the operator's proposals.

- **Built-in pack location**: Read-only at
  `/opt/romarr/builtin-packs/builtin-2026.04.001.yaml` inside the
  container image. Operators can never modify it; they can only
  override individual platforms.
- **Platform deletion**: Packs cannot delete platforms. A platform
  that has user Games attached cannot be removed safely; explicit
  delete-with-cascade is out of scope for this spec.
- **Effect on existing Games**: A pack update on a platform does
  not touch Game rows. Game records reference `platform_id` and
  carry their own metadata. Adding new formats simply enables new
  files to be recognized in future imports.
- **Multi-pack collisions on the same slug**: The higher
  `pack_version` wins (FR-013a). A pack older than the currently
  recorded version on any of its slugs is rejected with HTTP 409
  ("downgrade rejected"). The operator bumps `pack_version` or
  releases the user override on individual slugs they want
  rewound. The audit log records every accepted update.

Other assumptions:

- The pack ecosystem is git-distributed in v1+; this spec ships
  the manual-upload + built-in paths only.
- Pack signing and verification are deferred to v2.
- Pack diff visualization in the UI is deferred to the UI spec;
  the validate-only endpoint here provides the JSON diff that the
  UI will later render.
- The built-in pack's `pack_version` increases monotonically with
  each Romarr release that updates platform definitions; the
  date-based scheme guarantees ordering.

### Out of Scope

- Pulling packs from a public Git repository (deferred to v1+;
  the API is designed around a future `PackSource` interface so
  this drops in cleanly).
- Conflict-resolution UI when an upload would overwrite an
  overridden platform (UI spec — backend already enforces the
  user-wins rule).
- Pack signing and signature verification (v2).
- Visual pack-diff renderer (UI spec).
- Legacy `schema_version = 0` migration (we start at
  `schema_version = 1`; older synthetic packs are not supported).
- Per-platform deletion as part of a pack (operators wishing to
  remove a platform must do so via a separate explicit operation
  in a future spec).
