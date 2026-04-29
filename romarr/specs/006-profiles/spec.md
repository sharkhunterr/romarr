# Feature Specification: Profiles (Quality, Region, Dump, Language, Naming, Custom Format)

**Feature Branch**: `006-profiles` (branch creation skipped: git repo lives in parent dir)
**Created**: 2026-04-29
**Status**: Draft
**Depends on**: `001-foundation` — uses `Game`, `Release`, `Dump`, `Platform`, the `DumpStatus` and `NamingConvention` enums, and the `ParsedFilename` value type.
**Input**: User description: "Six profile types that drive every grab/upgrade/import decision. No business logic is hardcoded. Quality, Region, Dump, Language, Naming, Custom Format. Default profiles seeded on first boot. Pure evaluator. Sandboxed Jinja2 naming template engine. CRUD API per profile type."

## Clarifications

### Session 2026-04-29

- Q: How are Custom Format `matches_regex` patterns defended against catastrophic backtracking? → A: Same pattern as spec 003 FR-005a. At Custom Format save time the system compiles every regex AND runs it against a 256-byte adversarial input on a worker thread with a 50 ms wall-clock budget; any regex that exceeds the budget causes the save to be rejected with HTTP 400. Runtime evaluation needs no per-match timeout because patterns are already vetted at save time
- Q: This spec references Library FK columns but the Library table doesn't exist until spec 009. Which spec actually adds them? → A: Spec 009 (Library + Exporters) adds the five profile FK columns and the `library_id` FK on `library_custom_format`. Spec 006 ships only the six profile tables. This forward-reference pattern mirrors how spec 005 (Download Clients) backfills `indexer.download_client_id`
- Q: How does the seeder identify a default profile row as "user-touched" so it doesn't overwrite the operator's edit on restart? → A: Each seeded row carries a stable `seed_key` column (unique per profile type) plus an `is_user_modified` boolean (default `false`). Any UPDATE that mutates a non-FK column flips `is_user_modified` to `true`. The seeder upserts by `seed_key` only when `is_user_modified = false`; rows where the operator made any change are left alone
- Q: What is the Region priority scoring formula? → A: `score = len(priorities) − index` (1-based). For `priorities = [USA, EUR, JPN]`: USA=3, EUR=2, JPN=1. Releases outside `priorities` with fallback enabled receive score `0`. Excluded regions are rejected outright (no score). The integer form sums cleanly with Custom Format scores in the search engine
- Q: What role is required to invoke the profile CRUD and naming-preview endpoints? → A: Admin-only on all mutating endpoints (`POST` / `PUT` / `DELETE` on every profile type and on `custom_format`) AND on `POST /api/v3/rom/namingprofile/preview` (template preview is server-side evaluation, gated for consistency); reads (`GET` on lists / details / `/schema`) accessible to any authenticated user. Same pattern as specs 003 / 004 / 005

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Default profiles ready out of the box (Priority: P1)

A Romarr operator launches a fresh instance. Without lifting a
finger they find a sensible set of pre-configured profiles for each
of the six profile types — enough to bind a library and start
grabbing immediately.

**Why this priority**: Without seeded defaults the first-boot
experience is "empty list of profiles, can't bind a library, can't
grab anything." The constitution mandates that profiles drive
every decision; the operator has to have something to drive
**from**.

**Independent Test**: Boot a fresh database; query the catalog of
each profile type; verify that the documented defaults are present
with the documented field values.

**Acceptance Scenarios**:

1. **Given** a fresh database, **When** the application starts,
   **Then** the catalog contains the documented default profiles
   for every type: 3 Quality, 3 Region, 3 Dump, 3 Language, 3
   Naming, and the 11 default Custom Formats.
2. **Given** seeded defaults already exist, **When** the
   application restarts, **Then** the seeder MUST NOT duplicate
   them; counts are unchanged after a second startup.
3. **Given** the operator has edited a default profile (e.g.,
   renamed "Preservation" to "Archive"), **When** the application
   restarts, **Then** the operator's edit is preserved (no
   overwrite of user-touched rows).

---

### User Story 2 — Profiles drive grab/upgrade/import decisions (Priority: P1)

A Romarr operator binds a Quality, Region, Dump, Language, and
Naming profile to a library, plus a few Custom Formats. Whenever
Romarr evaluates a candidate release, the decision (accept, reject,
score) flows from those profiles only — never from hardcoded rules.

**Why this priority**: This is the constitutional core of the
project (Article V — Profile-Driven Decisions). Without it,
Romarr is just another *arr with hardcoded preferences.

**Independent Test**: Construct a library bound to specific
profiles; pass a fixed `ParsedFilename` + dump metadata through the
evaluator; verify each evaluator function (`evaluate_quality`,
`evaluate_region`, `evaluate_dump`, `evaluate_language`,
`compute_custom_format_score`) returns the documented decision and
that calling them twice with the same input gives the same output
with no side effects.

**Acceptance Scenarios**:

1. **Given** a parsed release whose format matches the Quality
   profile's `allowed_formats`, **When** `evaluate_quality` runs,
   **Then** the decision is `ACCEPT`.
2. **Given** the same release whose format is NOT allowed,
   **When** `evaluate_quality` runs, **Then** the decision is
   `REJECT` with a structured reason naming the offending format.
3. **Given** a Region profile with priorities `[USA, EUR, World,
   JPN]` and `allow_fallback_outside_priorities = false`, **When**
   `evaluate_region` is called for a release whose region is
   `KOR`, **Then** the decision is `REJECT`.
4. **Given** a Custom Format with score `-10000` whose conditions
   match a release, **When** `compute_custom_format_score` runs,
   **Then** the returned score is `-10000` and the search engine
   (consumer of this feature) treats this as outright rejection.
5. **Given** any combination of inputs to any evaluator function,
   **When** the function is called twice in succession, **Then**
   the outputs are byte-for-byte identical and no database write
   has occurred (purity invariant).

---

### User Story 3 — Naming template renders the canonical filename (Priority: P1)

A Romarr operator imports *Sonic the Hedgehog (USA) (Rev A)* and
the Naming profile is "No-Intro Standard". The rendered filename is
exactly `Sonic the Hedgehog (USA) (Rev A).md` — and `(Rev A)` would
have disappeared if the release had no revision, while `(USA)` would
have been substituted by `(World)` for a multi-region release.

**Why this priority**: Filename is the user-visible surface of every
imported file. Wrong rendering (extra spaces, dangling brackets, a
crash on missing field) is what the operator sees first.

**Independent Test**: Run each documented convention (no-intro,
redump, tosec, es-de, romm) against a fixture corpus of at least 10
releases per convention; verify the rendered filename matches the
golden expected output exactly.

**Acceptance Scenarios**:

1. **Given** a No-Intro release with `revision = "Rev A"` and
   `languages = ["En", "Fr"]`, **When** the No-Intro template
   renders, **Then** the output is
   `<Title> (USA) (En,Fr) (Rev A).md` with no extra spaces.
2. **Given** the same release with `languages = []` and
   `revision = ""`, **When** the No-Intro template renders,
   **Then** the optional bracketed groups disappear cleanly:
   `<Title> (USA).md`.
3. **Given** a template containing `{Game.SomeForbiddenAttribute}`,
   **When** the operator submits it, **Then** validation fails at
   save time with a clear "unknown token" error and the profile is
   NOT persisted.
4. **Given** a template that tries `{{ release.__class__ }}` or
   any other sandbox escape attempt, **When** it is rendered,
   **Then** the engine raises a sandbox-violation error rather
   than evaluating the expression.
5. **Given** `replace_illegal_chars = true` and a Game title
   containing `:` `/` `\` `*` `?` `"` `<` `>` `|`, **When** the
   template renders, **Then** every illegal character is replaced
   with `_`.

---

### User Story 4 — Custom Format scoring ranks releases (Priority: P2)

A Romarr operator wants `[!]` (verified) releases preferred,
`[h]`/`[t]`/`[b]`/`[o]` outright rejected, and `[T+Fr]` slightly
boosted. They enable the corresponding Custom Formats and bind them
to their library. The search engine receives a deterministic score
per candidate release.

**Why this priority**: Custom Formats are the sharp tool for
preference expression beyond the four pass/fail filters.

**Independent Test**: Build a fixture of 50 mixed releases (clean,
hacks, trainers, bad, FR-translated, etc.); run
`compute_custom_format_score` against the default-seeded Custom
Formats; verify each release receives the expected score.

**Acceptance Scenarios**:

1. **Given** a release tagged `[!]`, **When** the scorer runs with
   the "Verified Dump" Custom Format active, **Then** the
   contribution is `+100`.
2. **Given** a release tagged `[h2]` (hack v2), **When** the
   "Hack" Custom Format is active, **Then** the contribution is
   `-10000` and the search engine treats the result as rejected.
3. **Given** two Custom Formats whose conditions both match,
   **When** the scorer runs, **Then** the returned score is the
   sum of their individual scores.
4. **Given** a Custom Format whose conditions are an OR-group of
   two sub-conditions, **When** either sub-condition matches, the
   format contributes its score; when neither matches, it
   contributes 0.
5. **Given** the same release evaluated twice, **When** the scorer
   runs, **Then** the returned score is identical (purity).

---

### User Story 5 — A library blocks profile deletion (Priority: P2)

A Romarr operator tries to delete the "USA First" Region profile
that is currently bound to the "Retro Cartridges" library. The
delete is rejected with a clear message naming the blocking library.
The operator can override with an explicit `?force=true` query
parameter, which automatically unbinds the profile from the library.

**Why this priority**: Silent profile deletion would leave a library
in a broken state where new grabs fail with cryptic errors.

**Independent Test**: Bind a profile to a library; attempt to
delete the profile; assert HTTP 409 with the library name; retry
with `?force=true`; assert the profile is gone and the library's
foreign key is set to NULL.

**Acceptance Scenarios**:

1. **Given** a profile bound to one or more libraries, **When**
   the operator DELETEs the profile, **Then** the response is
   HTTP 409 with a body listing the blocking library names.
2. **Given** the same situation, **When** the operator DELETEs
   the profile with `?force=true`, **Then** the response is
   HTTP 204 (success); the libraries' FK columns are set to NULL
   (the library will need to bind a new profile of that type
   before its next grab attempt).
3. **Given** a profile NOT bound to any library, **When** the
   operator DELETEs it, **Then** the response is HTTP 204 with no
   special handling.

---

### User Story 6 — Schema endpoint drives UI form generation (Priority: P3)

The frontend UI (later spec) wants to render a profile editor
without hardcoding field shapes. Each profile type exposes a
`/schema` endpoint that returns its JSON Schema; the UI renders
the form dynamically.

**Why this priority**: Useful but not blocking — the UI can hardcode
forms initially. Schema endpoints just keep the UI honest as
profiles evolve.

**Independent Test**: Hit each profile type's `/schema` endpoint;
assert the response is a valid JSON Schema document that documents
every field of the underlying entity.

**Acceptance Scenarios**:

1. **Given** the QualityProfile schema endpoint, **When** queried,
   **Then** it returns a JSON Schema with the documented fields,
   types, defaults, and (where applicable) enums.
2. **Given** the CustomFormat schema endpoint, **When** queried,
   **Then** it returns a JSON Schema describing the
   `conditions[].field`, `conditions[].operator`, and
   `conditions[].values` shape, including the OR-group structure.

---

### User Story 7 — Naming template preview (Priority: P3)

The operator is editing a Naming profile and wants to preview what
a sample release would look like before saving. A preview endpoint
accepts a candidate profile shape plus a sample release reference
and returns the rendered string.

**Why this priority**: Preview is a quality-of-life feature for the
template editor in the UI; not blocking but very valuable.

**Independent Test**: POST to the preview endpoint with a candidate
profile and an existing release id; verify the rendered string
matches the offline output of the same template against the same
release.

**Acceptance Scenarios**:

1. **Given** a candidate profile shape and a sample release id,
   **When** the operator POSTs to the preview endpoint, **Then**
   the response is the rendered string with no database mutation.
2. **Given** the candidate profile contains an unknown token,
   **When** the operator POSTs, **Then** the response is HTTP 400
   with a clear "unknown token" error.

---

### Edge Cases

- A Quality profile with `allowed_formats = []` → rejected at
  validation as "must allow at least one format".
- A Region profile with `priorities = []` AND
  `allow_fallback_outside_priorities = false` → rejected as
  "configuration would reject everything".
- A Naming profile whose `convention = 'custom'` but `template = null`
  → rejected as "custom convention requires an explicit template".
- A Custom Format with `conditions = []` → rejected as "must have
  at least one condition".
- A Custom Format with a malformed regex in `matches_regex` →
  rejected at save time with a regex compile-error message.
- A Naming template referencing `{Game.Year}` when the underlying
  Game has no `release_date` populated → renders empty; bracketed
  groups containing only the empty value collapse cleanly.
- A condition uses `release_size` operator `greater_than` with a
  release whose size is unknown → the condition does NOT match
  (treated as if the field were absent); never raises.
- The same Custom Format is bound twice to the same library
  (m2m duplicate) → rejected at save time as duplicate; the m2m
  table has a unique constraint on `(library_id, custom_format_id)`.
- A Library deletion cascades the m2m rows; the Custom Format
  itself is untouched.
- An operator provides a Jinja template with a syntax error (e.g.
  unclosed `{%`) → rejected at save time with a clear error message
  pointing to the line/column of the parse failure.
- An operator provides a template using a function not in the
  approved list (only `lower`, `upper`, `replace`, `truncate(N)`
  are allowed) → rejected at save time with the offending function
  name.

## Requirements *(mandatory)*

### Functional Requirements

**Persistence**

- **FR-001**: The system MUST persist six profile tables
  (`quality_profile`, `region_profile`, `dump_profile`,
  `language_profile`, `naming_profile`, `custom_format`) plus a
  many-to-many `library_custom_format` association.
- **FR-002**: The migration MUST seed the documented default
  profiles for each type (3 each for Quality / Region / Dump /
  Language / Naming and 11 Custom Formats).
- **FR-003**: Re-running the seeder MUST be idempotent — no
  duplicate rows; user-edited rows MUST be preserved.
- **FR-003a**: Every profile table (six core tables plus
  `custom_format`) MUST carry two columns supporting safe
  re-seeding: `seed_key` (`VARCHAR`, NULL for operator-created
  rows, NOT NULL for system-seeded rows; unique per profile type
  when not NULL) and `is_user_modified` (`BOOLEAN`, default
  `false`). The seeder MUST identify the row to upsert by
  `seed_key`. An UPDATE through any API endpoint or admin path
  that mutates a non-FK column MUST flip `is_user_modified` to
  `true` in the same transaction. The seeder MUST skip any row
  whose `is_user_modified = true`. A future "reset to defaults"
  operation (out of scope for this spec; tracked under v1+
  Profile export/import) MAY clear the flag and re-run the
  seeder. The same flag mechanism MUST be applied to
  `custom_format` and the m2m bindings created by the seeder.

**Library binding**

- **FR-004**: The five Library → Profile FK columns
  (`quality_profile_id`, `region_profile_id`, `dump_profile_id`,
  `language_profile_id`, `naming_profile_id`) MUST exist on the
  Library row when a library is bound to profiles. This spec
  (006) does NOT add those columns — it declares the contract
  only. Spec 009 (Library + Exporters) owns the `library` table
  DDL and is responsible for creating the five FK columns
  (with `ON DELETE SET NULL`) in its own migration. This
  forward-reference pattern mirrors the `indexer.download_client_id`
  → `download_client.id` FK that spec 005 backfills onto the
  earlier-introduced `indexer` table.
- **FR-005**: A Custom Format MAY be associated with multiple
  libraries; a library MAY associate any number of Custom Formats.
  The association is m2m via `library_custom_format`. This spec
  creates the m2m table with `custom_format_id` FK only; the
  `library_id` FK is added by spec 009's migration once the
  `library` table exists. The unique constraint
  `(library_id, custom_format_id)` is created at the same time
  spec 009 adds the missing FK.

**Profile evaluator (pure)**

- **FR-006**: The evaluator MUST expose pure static functions:
  `evaluate_quality(profile, parsed, dump_data) -> Decision`,
  `evaluate_region(profile, parsed) -> RegionScore`,
  `evaluate_dump(profile, parsed) -> Decision`,
  `evaluate_language(profile, parsed) -> Decision`,
  `compute_custom_format_score(formats, parsed, indexer_meta) -> int`,
  `render_naming_template(profile, game, release, dump) -> str`.
- **FR-007**: Every evaluator function MUST be deterministic: same
  inputs ⇒ same outputs, no I/O, no database access, no logging
  side effects beyond a pure return value plus a structured
  reason field.
- **FR-008**: `Decision` MUST be one of `ACCEPT`, `REJECT`, or
  `NEUTRAL`. Each rejecting evaluator MUST attach a structured
  reason naming the failing field.

**Quality evaluation rules**

- **FR-009**: A release whose detected file format is not in the
  profile's `allowed_formats` MUST be rejected.
- **FR-010**: When `require_dat_verified = true` and the dump's
  `dat_verified = false`, the release MUST be rejected.
- **FR-011**: When the release's format equals
  `upgrade_until_format`, the release MUST be flagged as "cutoff
  met" so the future search engine stops looking for upgrades.

**Region evaluation rules**

- **FR-012**: A release whose region is in `exclude_regions` MUST
  be rejected.
- **FR-013**: A release whose region is in `priorities` MUST be
  scored using the formula `score = len(priorities) − index`
  with `index` being the 0-based position in the priorities
  list (so the first priority scores `len(priorities)` and the
  last scores `1`). The score MUST be an integer so it sums
  cleanly with Custom Format scores in the downstream Search &
  Decision Engine.
- **FR-014**: A release whose region is outside `priorities` AND
  `allow_fallback_outside_priorities = false` MUST be rejected.
- **FR-015**: A release whose region is outside `priorities` AND
  `allow_fallback_outside_priorities = true` MUST receive a
  fallback score of `0` (strictly less than the lowest
  in-priorities score, which is `1` per FR-013).

**Dump evaluation rules**

- **FR-016**: A release whose `dump_status` is not in
  `allowed_dump_status` MUST be rejected unless one of the
  permissive flags applies (`allow_proto_beta`, `allow_hacks`,
  `allow_trainers`, `allow_translations`).
- **FR-017**: `prefer_revision` is informational at evaluator
  level — it produces a tiebreaker score, never a rejection.

**Language evaluation rules**

- **FR-018**: When `required_languages` is non-empty, a release
  whose `languages` set has no intersection with
  `required_languages` MUST be rejected.
- **FR-019**: When `exclude_japanese_only = true` and the release's
  languages set is exactly `["ja"]`, the release MUST be rejected.

**Custom Format scoring**

- **FR-020**: Each condition MUST be evaluated against the
  parsed release data using the documented operator
  (`matches_regex`, `equals`, `in`, `contains`, `not_in`,
  `greater_than`, `less_than`).
- **FR-021**: A Custom Format's conditions list is implicit AND.
  A condition MAY contain an `or` field listing alternate
  conditions; the condition matches when the primary or any
  `or` member matches.
- **FR-022**: A Custom Format whose conditions all match MUST
  contribute its `score` to the overall score; otherwise it
  contributes 0.
- **FR-023**: A regex that fails to compile at save time MUST
  cause the Custom Format to be rejected.
- **FR-023a**: At Custom Format save time, after each
  `matches_regex` pattern compiles successfully, the validator
  MUST execute the compiled pattern against a fixed 256-byte
  adversarial input on a worker thread bounded by a 50 ms
  wall-clock budget. Any pattern whose match attempt exceeds the
  budget MUST cause the Custom Format save to fail with HTTP 400
  and a structured error citing the offending condition's index.
  This mirrors spec 003 FR-005a and ensures the evaluator hot
  path can rely on already-vetted patterns without a per-match
  runtime timeout.

**Naming template engine**

- **FR-024**: The template engine MUST be a sandboxed evaluator
  that exposes only the documented tokens
  (`{Game.Title}`, `{Game.SortTitle}`, `{Game.IGDBId}`,
  `{Release.Region}`, `{Release.Languages}`, `{Release.Revision}`,
  `{Release.Tags}`, `{Release.Name}`, `{Release.OriginalName}`,
  `{Dump.Extension}`, `{Dump.Format}`, `{Platform.Slug}`,
  `{Platform.Name}`, `{Platform.ShortName}`, plus
  `{Game.Year}`, `{Game.Publisher}` for TOSEC).
- **FR-025**: The engine MUST allow only the function set
  `lower`, `upper`, `replace`, `truncate`. Any other callable
  used in the template MUST raise a sandbox-violation error.
- **FR-026**: When `replace_illegal_chars = true`, characters in
  the set `: / \ * ? " < > |` MUST be replaced with `_` in the
  rendered string.
- **FR-027**: The engine MUST collapse consecutive whitespace,
  trim trailing whitespace, and remove empty bracketed groups
  (e.g. " ()", " ( )", " [ ]") so optional fields disappear cleanly.
- **FR-028**: Template syntax errors and unknown-token errors
  MUST be detected at save time and produce a structured error
  pointing to the line and column of the offending text.

**API**

- **FR-029**: For each of the six profile types, the system MUST
  expose CRUD endpoints under `/api/v3/qualityprofile`,
  `/api/v3/rom/regionprofile`, `/api/v3/rom/dumpprofile`,
  `/api/v3/rom/languageprofile`, `/api/v3/rom/namingprofile`,
  `/api/v3/customformat`.
- **FR-030**: Each profile type MUST expose a `/schema` endpoint
  returning a JSON Schema describing its fields.
- **FR-031**: The system MUST expose
  `POST /api/v3/rom/namingprofile/preview` which accepts a
  candidate profile shape plus a sample release id and returns
  the rendered string without database mutation.
- **FR-032**: A DELETE that would orphan a library binding MUST
  return HTTP 409 with the blocking library names. A
  `?force=true` query parameter MUST allow the delete to proceed
  by setting the affected libraries' FK columns to NULL.
- **FR-032a**: Every mutating endpoint introduced by FR-029
  (`POST` / `PUT` / `DELETE` on the six profile-type routes and
  on `/api/v3/customformat`) AND the naming-preview endpoint
  (`POST /api/v3/rom/namingprofile/preview`) MUST require the
  caller to hold the `admin` role provided by the Auth spec.
  Read endpoints (`GET` lists, `GET /{id}`, `GET /schema`) MUST
  be accessible to any authenticated user. Unauthenticated
  requests MUST be rejected with HTTP 401; authenticated
  non-admin requests on a mutating or preview endpoint MUST be
  rejected with HTTP 403. This matches the pattern used by
  specs 003 / 004 / 005.

### Key Entities

- **Quality Profile**: declares the acceptable file formats and
  the cutoff (preferred end state).
- **Region Profile**: declares the preference order across
  regions plus an optional blacklist.
- **Dump Profile**: declares which dump-status values are
  acceptable plus permissive flags for hacks, trainers,
  translations, proto/beta.
- **Language Profile**: declares required and preferred languages.
- **Naming Profile**: declares how imported files are renamed and
  organised.
- **Custom Format**: declares a named condition expression that
  contributes a score (positive or negative) to a release.
- **Decision**: an enum returned by each evaluator —
  `ACCEPT` / `REJECT` / `NEUTRAL` — plus an optional structured
  reason.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After a fresh boot, the catalog contains all
  documented default profiles for every profile type. The
  documented counts match exactly: 3 Quality, 3 Region, 3 Dump, 3
  Language, 3 Naming, 11 Custom Formats.
- **SC-002**: Every evaluator function returns identical output
  for identical input across 1 000 randomized property-based test
  iterations (purity invariant).
- **SC-003**: Across a fixture corpus of at least 50 releases, the
  Custom Format scorer produces the documented expected score in
  100% of cases.
- **SC-004**: For each of the 5 named conventions (no-intro,
  redump, tosec, es-de, romm), the naming template engine
  produces the golden expected filename in 100% of at least 10
  fixtures per convention.
- **SC-005**: A template containing an unknown token, a
  syntax error, or a sandbox-escape attempt is rejected at save
  time with a structured error in 100% of attempts across an
  injected-bad-template fixture corpus of at least 10 cases.
- **SC-006**: Deleting a profile that is bound to one or more
  libraries returns HTTP 409 in 100% of test cases; deleting the
  same profile with `?force=true` succeeds and leaves the
  affected libraries with a NULL FK in 100% of test cases.
- **SC-007**: Test coverage on the profiles module MUST be at
  least 80%.

## Assumptions

These resolve the OPEN CLARIFICATIONS supplied with the input,
applying the operator's proposals.

- **`release_group` extraction**: extracted from the filename
  using the foundation's filename parsers (e.g.,
  `Sonic.USA-DEMENT.iso` → group `DEMENT`). The list of common
  ROM scene groups is maintained as a JSON config file shipped
  with the application; operators can extend it via a
  configuration override.
- **OR / AND grouping in Custom Format conditions**: the
  conditions list is implicit AND. Each condition may carry an
  `or` field listing alternate conditions; the condition matches
  when the primary or any `or` member matches. Examples are
  documented in the API schema.
- **Template syntax errors**: caught at profile save time. The
  HTTP 400 response includes the line and column of the parse
  error and the offending fragment.
- **Sandboxed function set**: `lower`, `upper`, `replace`,
  `truncate(N)`. Other Jinja built-ins (loops, conditionals
  beyond simple booleans, attribute access outside the token
  whitelist) are blocked.
- **`release_size` condition**: supported as a
  `greater_than` / `less_than` numeric comparison. Used to filter
  oversized re-encodes (e.g., reject Wii ISOs over 8 GB when NKIT
  is preferred).

Other assumptions:

- All evaluators run on the **identification result**'s
  `ParsedFilename` plus the optional dump metadata; they do NOT
  consume the raw release name. This keeps them deterministic
  and decoupled from filename-parsing changes.
- Default profiles are sourced from a JSON fixture under
  `src/romarr/profiles/seeds/` so a future "reset to defaults"
  operation can re-read them.
- The library schema is owned by the future Library spec; this
  feature only adds the five profile FK columns and the
  `library_custom_format` m2m. The actual `library` table is
  introduced in a later spec.

### Out of Scope

- UI for editing profiles (UI spec).
- Profile recommendation engine (deferred to v1+).
- Profile export/import à la Recyclarr (deferred to v1+; the
  schema endpoint already paves the way for round-trip JSON).
- Multi-profile per library (different profiles per platform
  inside the same library) — out; operators wanting that should
  use multiple libraries.
- Search-engine consumption of profile decisions (Search &
  Decision Engine spec).
- Importer-side renaming and moving (Importer spec). This feature
  ships the *renderer*; the Importer ships the *file mover*.
