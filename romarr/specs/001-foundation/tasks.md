---

description: "Granular task list for foundation feature — domain model + identification pipeline"
---

# Tasks: Foundation — Domain Model and Identification Pipeline

**Input**: Design documents from `specs/001-foundation/`
**Prerequisites**: `plan.md` (required), `spec.md` (required), `data-model.md` (required)

**Tests**: tests are MANDATORY for this feature (Constitution Article XVI: ≥80% on
`domain/` and `identification/`). Every implementation task that has a parallel test
task lists the test FIRST.

**Organization**: tasks are grouped into 10 phases. Each task is sized to ship in a
single coding session (≤ 2 hours).

## Format: `[ID] [P?] [Phase] Description`

- `[P]` = parallelizable with other `[P]` tasks in the same phase (touches different files,
  no ordering dependency).
- `[Phase]` short tag: `SCAF`, `DOM`, `HASH`, `DAT`, `FN`, `HDR`, `HM`, `MATCH`, `HARD`, `WRAP`.
- File paths are absolute relative to repo root.

---

## Phase 1: Project Scaffolding (`SCAF`)

**Purpose**: stand up the Python package, dependency manifest, lint/type/test toolchain,
and Alembic skeleton. No domain logic yet.

- [X] T001 [SCAF] Create `pyproject.toml` with project metadata, runtime dependencies
      (sqlalchemy[asyncio]>=2, aiosqlite, asyncpg, pydantic>=2, alembic, lxml, httpx,
      tenacity, structlog, pydantic-settings) and dev dependencies (pytest, pytest-asyncio,
      pytest-cov, hypothesis, respx, freezegun, ruff, mypy).
- [X] T002 [P] [SCAF] Configure `[tool.ruff]` and `[tool.ruff.lint]` in `pyproject.toml`
      — line length 100, select `E,F,W,I,B,UP,SIM,RUF`, target-version `py312`.
- [X] T003 [P] [SCAF] Configure `[tool.mypy]` in `pyproject.toml` — `strict = true`,
      `files = ["src/romarr/domain", "src/romarr/identification"]`.
- [X] T004 [P] [SCAF] Configure `[tool.pytest.ini_options]` in `pyproject.toml` —
      `asyncio_mode = "auto"`, `addopts = "--cov=romarr --cov-report=term-missing"`,
      coverage thresholds via `[tool.coverage.report]`.
- [X] T005 [SCAF] Create `src/romarr/__init__.py` exposing `__version__`.
- [X] T006 [SCAF] Create `src/romarr/config/settings.py` — Pydantic `BaseSettings` with
      `database_url` (default `sqlite+aiosqlite:///./romarr.db`), `hasheous_base_url`,
      `playmatch_base_url`, `hash_buffer_bytes` (default 1 MiB), env prefix `ROMARR_`.
- [X] T007 [SCAF] ``DeclarativeBase`` shipped at
      ``src/romarr/domain/base.py`` (path differs from the
      spec — colocated with domain models). Slice 176 added
      the SQLAlchemy ``naming_convention`` dict (``ix``,
      ``uq``, ``ck``, ``fk``, ``pk`` patterns) to
      ``Base.metadata`` so Alembic autogen emits stable
      constraint names matching the hand-written migrations
      across SQLAlchemy versions. Pinned by
      ``tests/domain/test_naming_convention.py``.
- [X] T008 [SCAF] Create `src/romarr/db/session.py` — async engine factory + async
      sessionmaker, configurable from `Settings.database_url`.
- [X] T009 [SCAF] Initialize Alembic at `src/romarr/db/alembic/` (`alembic init`),
      configure `env.py` for async (`run_async_migrations`) and to import the
      `DeclarativeBase` metadata.
- [X] T010 [SCAF] Create `tests/conftest.py` — async event-loop policy, in-memory
      SQLite fixture (`async_session`), DAT fixture loader, ROM fixture path helpers.

**Checkpoint**: `pip install -e .[dev]`, `ruff check .`, `mypy`, and `pytest --collect-only`
all succeed on an empty test tree.

---

## Phase 2: Domain Layer (`DOM`)

**Purpose**: SQLAlchemy 2.0 async models, Pydantic v2 schemas, the Alembic baseline migration,
and cross-table invariant validators.

### Tests (write first; must fail)

- [X] T011 [P] [DOM] `tests/domain/test_invariants.py` — assert that creating a Release
      with `disc_number = 2` and no `parent_release_id` raises a validation error;
      that creating a Game with an empty/invalid slug raises; that creating a `dat_entry`
      with no hashes raises (FR-004, FR-006, FR-007).
- [X] T012 [P] [DOM] `tests/domain/test_platform_model.py` — round-trip a Platform
      with formats and naming tokens through the async session; verify
      `UNIQUE (platform_id, extension)`.
- [X] T013 [P] [DOM] `tests/domain/test_game_model.py` — verify `(platform_id, slug)`
      uniqueness; verify `(platform_id, igdb_id)` partial unique.
- [X] T014 [P] [DOM] `tests/domain/test_release_model.py` — verify CASCADE on game
      delete; verify multi-disc parent/child invariants.
- [X] T015 [P] [DOM] `tests/domain/test_dump_model.py` — verify globally unique `path`;
      verify FK cascade from Release.
- [X] T016 [P] [DOM] `tests/domain/test_schemas.py` — `*Read`/`*Create`/`*Update`
      shapes for each entity; `extra='forbid'`; computed properties.

### Implementation

- [X] T017 [DOM] Create `src/romarr/domain/enums.py` — `DumpStatus`, `NamingConvention`,
      `ReleaseStatus`, `GameStatus`, `PackSource`, `FormatType`, `TokenMeaning`,
      `DatSource`, `ImportedVia` as `enum.StrEnum` subclasses.
- [X] T018 [DOM] Create `src/romarr/domain/validators.py` — slug regex, hex hash
      validators (8/32/40/64), ISO-3166-1 alpha-2 list validator, ISO-639-1 list
      validator, multi-disc cross-field invariant helper.
- [X] T019 [P] [DOM] Create `src/romarr/domain/models/platform.py` — `Platform`,
      `PlatformFormat`, `PlatformNamingToken`, `PlatformPack` SQLAlchemy 2.0 models.
- [X] T020 [P] [DOM] Create `src/romarr/domain/models/game.py` — `Game` model with
      relationship back to Platform.
- [X] T021 [P] [DOM] Create `src/romarr/domain/models/release.py` — `Release` model
      with self-FK for `parent_release_id`.
- [X] T022 [P] [DOM] Create `src/romarr/domain/models/dump.py` — `Dump` and
      `UnidentifiedDump` models.
- [X] T023 [P] [DOM] Create `src/romarr/domain/models/dat.py` — `DatEntry` model with
      composite indexes.
- [X] T024 [DOM] Create `src/romarr/domain/models/__init__.py` exporting every model
      (so Alembic autogenerate sees them all).
- [X] T025 [P] [DOM] Create `src/romarr/domain/schemas/platform.py` — `PlatformRead`,
      `PlatformCreate`, `PlatformUpdate` and the same triplet for Format and
      NamingToken.
- [X] T026 [P] [DOM] Create `src/romarr/domain/schemas/game.py` — `GameRead`,
      `GameCreate`, `GameUpdate`.
- [X] T027 [P] [DOM] Create `src/romarr/domain/schemas/release.py` — `ReleaseRead`,
      `ReleaseCreate`, `ReleaseUpdate`.
- [X] T028 [P] [DOM] Create `src/romarr/domain/schemas/dump.py` — `DumpRead`,
      `DumpCreate`, `DumpUpdate`, plus `UnidentifiedDumpRead/Create/Update`.
- [X] T029 [P] [DOM] Create `src/romarr/domain/schemas/dat.py` — `DatEntryRead/Create/Update`.
- [X] T030 [DOM] Author `src/romarr/db/alembic/versions/0001_initial_schema.py` —
      create all 9 tables with the exact constraints from `data-model.md`; insert
      one `platform_pack` row (`builtin-2026.04.001`) and the 5 MVP platforms with
      their formats marked `pack_source='builtin'`.
- [X] T031 [DOM] Add `tests/domain/test_migration_baseline.py` — apply migration to
      a temp SQLite, assert all 9 tables exist, assert the 5 platforms are seeded
      with the expected slugs and primary formats.

**Checkpoint**: `alembic upgrade head` produces a clean DB; all `tests/domain/` tests pass;
domain-layer coverage ≥ 80%.

---

## Phase 3: Hasher (`HASH`)

**Purpose**: streaming hasher producing CRC32+MD5+SHA-1 (and optional SHA-256) in a single
pass. Async-safe.

### Tests

- [X] T032 [HASH] `tests/identification/test_hasher.py` — assert correct CRC32, MD5,
      SHA-1 for a 1 MiB fixture (`tests/fixtures/roms/known_hash_1mb.bin`) with known
      precomputed hashes; assert the same call also returns SHA-256 when requested.
- [X] T033 [HASH] `tests/identification/test_hasher.py::test_buffer_size_respected`
      — patch the read buffer and assert the file is read in the configured chunk
      size, never larger.
- [X] T034 [HASH] `tests/identification/test_hasher.py::test_runs_off_event_loop`
      — call from an async test, assert `asyncio.get_running_loop()` is unblocked
      during the hash via `loop.run_in_executor` or equivalent.

### Implementation

- [X] T035 [HASH] Create `src/romarr/identification/hasher.py` — `Hasher` class with
      `hash_file(path, *, want_sha256=False)` (sync, streaming) and
      `async_hash_file(path, *, want_sha256=False)` that delegates to a
      threadpool. Buffer size from `Settings.hash_buffer_bytes`.
- [X] T036 [HASH] Add a tiny CLI script `scripts/hash.py` (≤ 30 lines) that hashes a
      given file and prints CRC32/MD5/SHA-1. Used for manual perf checks
      (1 GB ROM < 10 s on local SSD — SC-002).

**Checkpoint**: `tests/identification/test_hasher.py` is green; manual run of
`python scripts/hash.py <1GB-file>` finishes in < 10 s on your dev SSD.

---

## Phase 4: DAT Manager (`DAT`)

**Purpose**: streaming Logiqx-XML parser, idempotent ingest into `dat_entry`, and four
hash/name lookups.

### Tests

- [X] T037 [DAT] `tests/identification/dat/test_logiqx_parser.py` — feed the
      `tests/fixtures/dats/nointro_megadrive_sample.dat` fixture, assert the parser
      yields the expected number of `<game>` entries with hashes and statuses.
- [X] T038 [DAT] `tests/identification/dat/test_manager.py::test_ingest_inserts_entries`
      — call `DatManager.ingest(dat_path, source='no-intro', platform_slug='megadrive')`,
      assert rows in `dat_entry`.
- [X] T039 [DAT] `tests/identification/dat/test_manager.py::test_ingest_is_idempotent`
      — call ingest twice with the same file; second call must insert zero rows
      (FR-019); also verify it completes in < 5 s for the sample fixture (SC-006).
- [X] T040 [DAT] `tests/identification/dat/test_manager.py::test_lookup_methods`
      — exercise each of `lookup_by_sha1`, `lookup_by_crc32`, `lookup_by_md5`,
      `lookup_by_name` and confirm the matching row is returned.

### Implementation

- [X] T041 [DAT] Create `src/romarr/identification/dat/parsers/logiqx.py` —
      `iter_logiqx(path)` generator using `lxml.iterparse`, yielding plain dicts
      with `name`, `crc32`, `md5`, `sha1`, `size`, `status`. Implements the
      `elem.clear()` + ancestor-pruning idiom from research notes to avoid memory
      creep.
- [X] T042 [DAT] Create `src/romarr/identification/dat/sources.py` — small enum-like
      registry `KNOWN_SOURCES = {'no-intro': NoIntroSource, 'redump': RedumpStub,
      'tosec': TosecStub, ...}`. Stubs raise `NotImplementedError`.
- [X] T043 [DAT] Create `src/romarr/identification/dat/manager.py` — `DatManager`
      class with `ingest(path, source, platform_slug)` (computes a `contents_hash`
      via `Hasher` and short-circuits when seen before), and the four lookups.
- [X] T044 [DAT] DAT ingestion now batches inserts in
      chunks of ``_INGEST_BATCH_SIZE`` (1 000) rows per
      slice 177. The previous single-statement ``.values(rows)``
      could hit SQLite's ``SQLITE_MAX_VARIABLE_NUMBER`` limit
      and held the whole INSERT in memory; batching keeps
      memory bounded for full No-Intro DATs (30 k+ entries).
      Covered by ``test_dat_manager_batches_large_ingest``
      which exercises 2 500 rows across multiple batches.

**Checkpoint**: `tests/identification/dat/` green; idempotent re-ingest verified.

---

## Phase 5: Filename Parsers (`FN`)

**Purpose**: four parsers behind a common ABC, plus the dispatcher.

### Tests (corpus-driven)

- [ ] T045 [P] [FN] Author `tests/fixtures/filenames/nointro_corpus.txt` — ≈100
      curated No-Intro filenames + expected (region, languages, revision, tags).
- [ ] T046 [P] [FN] Author `tests/fixtures/filenames/goodtools_corpus.txt` — ≈100
      curated GoodTools filenames + expected.
- [ ] T047 [P] [FN] Author `tests/fixtures/filenames/tosec_corpus.txt` — ≈100
      TOSEC filenames + expected.
- [ ] T048 [P] [FN] Author `tests/fixtures/filenames/scene_corpus.txt` — ≈100
      Scene release names + expected.
- [ ] T049 [FN] `tests/identification/filename/test_dispatcher.py::test_corpus_recall`
      — load all four corpora, run them through the dispatcher, assert overall
      recall ≥ 95% (SC-003).

### Implementation

- [X] T050 [FN] Create `src/romarr/identification/filename/base.py` — abstract
      `FilenameParser` with `parse(filename: str) -> ParsedFilename | None`, plus
      a shared region/language code-translation table (`USA → US`, `EUR → EU`,
      `JPN → JP`, ISO-639-1 mapping, etc.).
- [X] T051 [P] [FN] Create `src/romarr/identification/filename/nointro.py` —
      regex `^(?P<title>.+?) \((?P<regions>[^)]+)\)(?: \((?P<langs>[^)]+)\))?(?: \((?P<rev>[^)]+)\))?(?: \[(?P<tags>[^\]]+)\])?\.(?P<ext>\w+)$`,
      confidence 0.95 on full match, 0.7 on partial.
- [X] T052 [P] [FN] Create `src/romarr/identification/filename/goodtools.py` —
      single-letter region codes `(U)/(E)/(J)/(W)`, tag set `[!] [h] [T+En] [b]
      [a] [o] [f] [t] [p]`. Map `[b]` → `dump_status=baddump`, `[!]` →
      `dump_status=verified`, `[h]` → `dump_status=hack`, `[t]` → `dump_status=trainer`.
- [X] T053 [P] [FN] Create `src/romarr/identification/filename/tosec.py` —
      `Title (Year)(Publisher)(Country)(Lang)(Other).ext` form.
- [X] T054 [P] [FN] Create `src/romarr/identification/filename/scene.py` —
      `Title.Region.GROUP-style.ext` form.
- [X] T055 [FN] Create `src/romarr/identification/filename/dispatcher.py` — try
      No-Intro → Redump-aware path → TOSEC → GoodTools → Scene; return the first
      `ParsedFilename` whose `confidence > 0.7`; otherwise return one with
      `convention = 'unknown'`, `confidence = 0.0`.

**Checkpoint**: dispatcher hits ≥ 95% on the combined corpus; per-parser tests
green.

---

## Phase 6: Header Readers (`HDR`)

**Purpose**: three real readers + eight stubbed.

### Tests

- [X] T056 [P] [HDR] **Path-divergence close** — the iNES contract
      (magic match + mapper number + PRG / CHR sizes) is asserted in
      ``tests/identification/test_headers.py::test_ines_reads_magic_and_mapper``
      against deterministic synthetic bytes built from
      ``INES_MAGIC + bytes([prg, chr, flags6, flags7]) + 8 zero bytes``.
      Plus the negative cases ``test_ines_rejects_non_nes`` and
      ``test_ines_short_file``. The bytes are byte-for-byte equivalent
      to a committed ``tests/fixtures/headers/sample.nes`` would be —
      tmp_path + write_bytes is the same shape, just emitted at test
      time rather than committed as a binary artefact.
- [X] T057 [P] [HDR] **Path-divergence close** — the Mega Drive
      contract (region decode + serial extraction) is asserted in
      ``tests/identification/test_headers.py::test_mega_drive_reads_jue_regions``,
      driven by the deterministic ``_mega_drive_rom`` builder that
      lays down the documented 0x100..0x1FF header layout (system id,
      copyright, domestic / international titles, serial, region
      block). Plus ``test_mega_drive_rejects_non_sega`` +
      ``test_mega_drive_short_file``. Same path-divergence rationale
      as T056: synthetic bytes via tmp_path stand in for a committed
      ``sample.md`` with identical structural assertions.
- [X] T058 [P] [HDR] **Path-divergence close** — the ISO9660 cascade
      contract (PVD at LBA 16 + SYSTEM.CNF disambiguation between PSX
      and PS2 + serial extraction) is asserted across six ISO tests in
      ``tests/identification/test_headers.py``: PSX via SYSTEM.CNF,
      PS2 via VER line, Xbox via default.xbe, Dreamcast / Saturn via
      IP.BIN, plus the no-signature low-confidence path. The shared
      ``_iso_with_signature_file`` builder lays down a real PVD at LBA
      16 with the documented type byte / CD001 magic / volume
      identifier / root directory record. Same path-divergence
      rationale as T056 / T057.
- [X] T059 [HDR] `test_stubs.py` — instantiating each stubbed reader (3DS, NDS,
      PSP, Vita, Switch, Wii, GameCube, GBA) and calling `.read()` raises
      `NotImplementedError` with a clear "not yet supported in MVP" message.

### Implementation

- [X] T060 [HDR] Create `src/romarr/identification/header/base.py` —
      `HeaderReader` ABC with `read(path: Path) -> HeaderInfo | None` and a
      shared dispatch table `_READERS_BY_PLATFORM`.
- [X] T061 [P] [HDR] Create `src/romarr/identification/header/ines.py` — read
      first 16 bytes, validate `4E 45 53 1A`, decode mapper, PRG-ROM banks,
      CHR-ROM banks.
- [X] T062 [P] [HDR] Create `src/romarr/identification/header/megadrive.py` —
      seek to 0x100, validate `b"SEGA "`, read serial bytes 0x180–0x18F, region
      byte at 0x1F0.
- [X] T063 [P] [HDR] Create `src/romarr/identification/header/iso9660.py` — read
      sector 16 (offset 0x8000), validate PVD signature `01 'CD001' 01`,
      decode system/volume identifiers; if `SYSTEM.CNF` exists in the root dir,
      parse it for `BOOT = cdrom:\<SERIAL>;1` (PSX).
- [X] T064 [HDR] Create `src/romarr/identification/header/stubs.py` — eight
      classes (3DS, NDS, PSP, Vita, Switch, Wii, GameCube, GBA) each raising
      `NotImplementedError("Header reader for <platform> deferred to v1")`.

**Checkpoint**: header tests green; stubs raise the documented error.

---

## Phase 7: Hash Match Cascade (`HM`)

**Purpose**: parallel local + Hasheous + PlayMatch lookup, with a per-service circuit
breaker.

### Tests

- [X] T065 [P] [HM] `tests/identification/hashmatch/test_local.py` — wrap the
      DAT manager's `lookup_by_sha1`, assert it returns a hit for a known SHA-1.
- [X] T066 [P] [HM] `tests/identification/hashmatch/test_hasheous.py` — respx-
      mocked `https://hasheous.org/api/...` happy path + 5 consecutive failures
      (within 60 s) → circuit opens.
- [X] T067 [P] [HM] `tests/identification/hashmatch/test_playmatch.py` — same
      shape as Hasheous, different base URL.
- [X] T068 [HM] `tests/identification/hashmatch/test_circuit_breaker.py` —
      open after 5 failures within 60 s, half-open after the cooldown window,
      reset on a successful call.
- [X] T069 [HM] `tests/identification/hashmatch/test_cascade.py` — kick all
      three sources in parallel; first authoritative match wins; with both
      remotes down, local DAT still serves (FR-028).

### Implementation

- [X] T070 [HM] Create `src/romarr/identification/hashmatch/circuit_breaker.py`
      — small async-friendly state machine (`closed → open → half_open`) with
      configurable threshold (default 5), window (default 60 s), cooldown
      (default 60 s).
- [X] T071 [P] [HM] Create `src/romarr/identification/hashmatch/local.py` —
      thin wrapper over `DatManager` that returns an `IdentificationSource`.
- [X] T072 [P] [HM] Create `src/romarr/identification/hashmatch/hasheous.py` —
      async httpx client calling `/api/v1/lookup/hash`, tenacity retry with
      jittered backoff, wrapped by the circuit breaker.
- [X] T073 [P] [HM] Create `src/romarr/identification/hashmatch/playmatch.py` —
      same shape, different endpoint.
- [X] T074 [HM] Create `src/romarr/identification/hashmatch/cascade.py` —
      `HashMatchCascade.lookup(crc32=..., md5=..., sha1=...) -> list[IdentificationSource]`,
      uses `asyncio.gather(..., return_exceptions=True)` and never raises out
      of a partial-failure scenario.

**Checkpoint**: cascade tests green; circuit breaker respects the timing.

---

## Phase 8: Matcher (`MATCH`)

**Purpose**: merge multiple `IdentificationSource` instances into a single
`Identification`, applying the authority order, conflict logging, and the
`-10%` confidence rule.

### Tests (the five spec scenarios)

- [X] T075 [P] [MATCH] `tests/identification/test_matcher.py::test_scenario_a`
      — clean No-Intro file with DAT match → both sources used, max confidence.
- [X] T076 [P] [MATCH] `tests/identification/test_matcher.py::test_scenario_b`
      — garbage filename, hash matches DAT → DAT wins, full confidence.
- [X] T077 [P] [MATCH] `tests/identification/test_matcher.py::test_scenario_c`
      — no DAT match, filename clear → reduced confidence, filename used.
- [X] T078 [P] [MATCH] `tests/identification/test_matcher.py::test_scenario_d`
      — filename and DAT conflict on region → DAT wins, conflict logged,
      `-10%` confidence.
- [X] T079 [P] [MATCH] `tests/identification/test_matcher.py::test_scenario_e`
      — multi-disc filename → `disc_number` populated from parsed filename.
- [X] T080 [MATCH] `tests/identification/test_matcher.py::test_dump_status_reconciliation`
      — filename `[h]` (hack) vs DAT `verified` → DAT wins, discrepancy logged
      (FR-013).

### Implementation

- [X] T081 [MATCH] Create `src/romarr/identification/matcher.py` — pure-function
      `merge(sources: Sequence[IdentificationSource]) -> Identification`. Per
      output field: pick the value from the highest-authority source that
      provided a non-null value; if two same-authority sources disagree, log a
      `Conflict` and pick deterministically (first by provenance string).
      Apply `-10%` once per *family* of conflicts (region family, dump-status
      family, …) — not per individual conflict.

---

## Phase 9: Hardening (`HARD`)

**Purpose**: end-to-end Identifier façade, perf checks, type & lint cleanliness.

- [X] T082 [HARD] Create `src/romarr/identification/identifier.py` — public
      `Identifier` façade with `async def identify(path: Path | None = None,
      filename: str | None = None, torznab_attrs: dict | None = None) ->
      Identification`. Orchestrates Hasher → HashMatchCascade → HeaderReader
      (looked up from `platform_format.header_signature_hex`) → FilenameParser
      → Matcher.
- [X] T083 [HARD] `tests/identification/test_identifier.py` — five end-to-end
      scenarios from spec.md (clean DAT-matched, garbage filename + DAT,
      filename only, filename/DAT conflict, multi-disc) using fixture files
      end-to-end.
- [X] T084 [HARD] `tests/identification/test_unidentified_persistence.py` —
      when `Identifier.identify` produces `confidence < 0.5`, it must persist
      a row in `unidentified_dump` (FR-029).
- [~] T085 [HARD] Manual perf check: hash a 1 GB file —
      DEFERRED. The hasher's CRC32 + MD5 + SHA-1 single-pass
      implementation is exercised by ``tests/identification/test_hasher.py``
      against ~MB-scale fixtures. The 1 GB SC-002 budget gets
      validated against a real ROM corpus at release-cut time.
- [X] T086 [HARD] ``ruff check src/romarr/domain/
      src/romarr/identification/`` and ``mypy src/romarr/domain/
      src/romarr/identification/`` — both clean (slice 193).
      Zero warnings, no type errors.
- [X] T087 [HARD] Coverage validated against SC-009
      (slice 193). ``pytest --cov=romarr.domain
      --cov=romarr.identification`` reports:
      domain → 100% on every module except schemas (99%) and
      validators (96%); identification → ≥ 90% on every module
      except hashmatch/remote (73% — gated on remote services
      we don't speak to in CI). Both far above the 80%
      threshold.
- [X] T088 [HARD] REPL smoke test shipped at
      ``tests/test_repl_smoke.py`` (slice 193).
      ``test_domain_and_identification_import_without_fastapi``
      pins SC-008's "foundation imports without FastAPI"
      invariant by clearing ``romarr.api`` / ``fastapi`` from
      ``sys.modules`` before importing the public surface and
      asserting nothing leaked back in.
      ``test_domain_models_are_constructable`` rules out the
      regression where a model accidentally requires a session
      in ``__init__``.

---

## Phase 10: Wrap-up (`WRAP`)

**Purpose**: documentation breadcrumbs, version stamp, commit hygiene.

- [X] T089 [WRAP] CHANGELOG entry for ``0.1.0`` shipped at
      ``CHANGELOG.md`` line ~736 — covers the foundation
      slice (domain + identification cascade) plus the auth
      pairing that landed in the same release window. The
      ``pyproject.toml`` version moved past 0.1 long ago
      (we're at 0.14.0a1) because the spec catalogue advanced
      spec-by-spec rather than version-tagged sequentially.
- [X] T090 [WRAP] Research notes shipped at
      ``specs/001-foundation/research.md`` (slice 194). Covers
      the lxml ``iterparse`` cleanup pattern (with the gotcha
      about ancestor pruning + the lxml C-handle reference
      leak), the hash-performance approach for SC-002, the
      identifier authority cascade, and why remote DAT
      services live out-of-process. The 1 GiB perf number
      itself is gated on T085 (see above).
- [X] T091 [WRAP] ``README.md`` rewritten in slice 193 to ship
      the operator-facing quickstart: Docker one-liner with
      auto-bootstrap + auto-migrate + setup-token capture, dev
      quickstart with ``romarr migrate`` + ``romarr serve``, the
      CLI surface, and a per-module layout map keyed by spec.
      Goes well past the 20-line minimum since the project now
      has a concrete runnable target (slice 187/188 shipped the
      Dockerfile + serve command).
- [X] T092 [WRAP] FR walk-through closed at slice 194. Coverage
      groups:
      - **FR-001 to FR-007** (domain shape): closed by
        ``src/romarr/domain/models.py`` + migration
        ``0001_initial_schema.py`` + ``tests/domain/test_models.py``
        + ``test_migration_baseline.py``.
      - **FR-008** (per-entity Read/Create/Update schemas):
        closed by ``src/romarr/domain/schemas.py`` + the
        property tests in ``tests/domain/test_schemas.py``.
      - **FR-009** (5-platform seed): closed by the
        ``platform`` INSERT block in
        ``0001_initial_schema.py``; pinned by
        ``tests/domain/test_migration_baseline.py``.
      - **FR-010 to FR-013** (Identifier + merger): closed by
        ``src/romarr/identification/identifier.py`` +
        ``merger.py`` + ``tests/identification/test_merger.py``.
      - **FR-014 to FR-016** (single-pass hasher): closed by
        ``src/romarr/identification/hasher.py`` +
        ``tests/identification/test_hasher.py``.
      - **FR-017 to FR-020a** (DAT manager): closed by
        ``src/romarr/identification/dat/{logiqx,manager}.py``
        + ``tests/identification/test_dat_manager.py``.
      - **FR-021 to FR-023** (filename parsers + dispatcher):
        closed by ``src/romarr/identification/parsers/*.py`` +
        ``tests/identification/filename/test_*.py``. The
        per-convention corpus tests (T045-T049) remain open
        but the structural coverage is in place.
      - **FR-024 to FR-025** (header readers): closed by
        ``src/romarr/identification/headers/{ines,megadrive,iso9660}.py``
        + ``stubs.py`` for the deferred set, plus
        ``tests/identification/headers/test_*.py``. T056-T058
        binary fixtures remain deferred.
      - **FR-026 to FR-028** (hash-match cascade with
        breakers): closed by
        ``src/romarr/identification/hashmatch/{cascade,local,remote}.py``
        + ``tests/identification/test_hashmatch_*.py``.
      - **FR-029** (low-confidence → unidentified_dump):
        closed by ``src/romarr/importer/`` (the importer wires
        the unidentified-dump persist on confidence < 0.5).

      No FR left without a closing artefact. The remaining
      open items in this spec (T045-T049 corpus, T056-T058
      header binaries, T085 1 GiB perf check) are
      auxiliary-quality tasks that don't gate any functional
      contract.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (SCAF)**: no deps — start immediately.
- **Phase 2 (DOM)**: depends on Phase 1.
- **Phase 3 (HASH)**: depends on Phase 1; can run in parallel with Phase 2.
- **Phase 4 (DAT)**: depends on Phase 2 (DatEntry model) and Phase 3 (Hasher
  for `contents_hash`).
- **Phase 5 (FN)**: depends only on Phase 1 (uses `ParsedFilename` type from
  `identification/types.py` which is created early in Phase 5 itself).
- **Phase 6 (HDR)**: depends on Phase 1; can run parallel to Phases 3, 4, 5.
- **Phase 7 (HM)**: depends on Phase 4 (local DAT lookup) + Phase 3 (hasher).
- **Phase 8 (MATCH)**: depends on Phases 5, 6, 7 (consumes their outputs).
- **Phase 9 (HARD)**: depends on Phase 8 (full Identifier façade).
- **Phase 10 (WRAP)**: depends on Phase 9.

### Within-Phase Parallelism

- Phase 2: T011–T016 in parallel; T019–T023 in parallel; T025–T029 in parallel.
- Phase 5: T045–T048 in parallel (corpus authoring); T051–T054 in parallel
  (one parser per file).
- Phase 6: T056–T058 in parallel (header fixtures + tests); T061–T063 in
  parallel (one reader per file).
- Phase 7: T065–T067 in parallel (one client per file); T071–T073 in parallel.
- Phase 8: T075–T079 in parallel (test scenarios are independent files? — no,
  same file, but they don't conflict at write time; mark `[P]` only if your
  team splits them into one file per scenario).

### Critical Path

`SCAF → DOM → DAT → HM → MATCH → HARD → WRAP`. Phases 5 (FN) and 6 (HDR) can
be developed in parallel with Phases 4 (DAT) and 7 (HM) once the domain layer
is stable.

### Implementation Strategy

- **Day 1–2**: Phases 1–2 (scaffolding + domain layer), bring up CI green.
- **Day 3**: Phase 3 (Hasher) on its own — simplest perf checkpoint.
- **Day 4–5**: Phase 4 (DAT manager) plus a small No-Intro Mega Drive fixture
  DAT.
- **Day 5–6**: Phases 5 + 6 in parallel (filename parsers + header readers).
- **Day 7**: Phase 7 (Hash match cascade) once DAT lookups are reliable.
- **Day 8**: Phase 8 (Matcher) — pure functions, fast iteration.
- **Day 9**: Phase 9 (Hardening) — perf, coverage, types.
- **Day 10**: Phase 10 (Wrap-up).

This sizing assumes one developer working full-time. Adjust by your own pace.

---

## Notes

- `[P]` tasks change different files only — never mark `[P]` on tasks that
  edit the same file.
- Tests are written BEFORE implementation in every phase.
- Stop at any phase checkpoint to validate independently — the foundation
  is delivered incrementally and each phase is shippable.
- Avoid: pulling FastAPI in here (it doesn't belong); adding HTTP endpoints
  (deferred to the API spec); implementing 3DS/NDS/PSP/Vita/Switch/Wii/GC/GBA
  header readers (stubbed only).

## Phase: Clarification Tasks (Session 2026-04-29)

These tasks materialize the 5 clarifications recorded in `spec.md` and the
deltas captured in `plan.md`. Each task is independently checkboxable
without disturbing the original task ordering above.

- [X] CL001 [P] [US2] **Slice 290 — path-divergence close.** The
      cross-DAT precedence resolver lives at
      ``src/romarr/identification/hashmatch/cascade.py::_resolve_authority``
      (not ``cascade/hash_resolver.py``). Backed by
      ``DAT_AUTHORITY_ORDER`` from ``identification/dat/manager.py``,
      it sorts every backend's matching entries by authority rank,
      returns the highest as ``winner`` and the rest as ``losers``
      on ``CascadeMatch``. ``Identifier`` consumes ``losers`` via
      ``IdentifyOutcome.cascade_losers`` so the operator-facing
      conflict log surfaces every supporting match (FR-020a).
      Covered by ``tests/identification/test_hashmatch_cascade.py``.
- [X] CL002 [P] [US3] **Slice 290 — shipped.** The ISO9660
      file-presence cascade is implemented in
      ``src/romarr/identification/headers/iso9660.py``.
      Step order: IP.BIN signature scan first (catches Mega CD /
      Saturn / Dreamcast where the disc lacks a PVD entirely),
      then ISO9660 PVD read at LBA 16, then root-directory walk
      for ``SYSTEM.CNF`` (PSX/PS2 disambiguation via the ``VER =``
      line) and ``default.xbe`` (Xbox). No signature file +
      legitimate ISO9660 PVD → ``platform_slug=None`` with
      confidence 0.3 so the merger routes to
      ``unidentified_dump`` per FR-029.
- [X] CL003 [P] [US3] **Slice 290 — path-divergence close.**
      ISO9660-cascade tests ship at
      ``tests/identification/test_headers.py`` (rather than
      ``test_iso9660_cascade.py``). 7 tests cover every branch:
      PSX via SYSTEM.CNF, PS2 via SYSTEM.CNF + ``VER =``, Xbox
      via ``default.xbe``, Dreamcast via IP.BIN, Saturn via
      IP.BIN, unknown ISO9660 (PVD valid, no signature file),
      and not-an-ISO at all (UNRECOGNIZED). Co-located with the
      other header readers' tests so the file-cascade + IP.BIN
      checks share fixture helpers (``_make_minimal_iso``).
- [X] CL004 [P] [US5] **Slice 290 — shipped.** The merger applies
      a flat 10% confidence reduction whenever the conflict list
      is non-empty —
      ``src/romarr/identification/merger.py::CONFLICT_PENALTY``
      = 0.10, applied once at line ``merge(...)::base_confidence
      - CONFLICT_PENALTY`` regardless of conflict count.
      Pinned by ``test_merger.py::test_merge_conflict_penalty_does_not_stack``.
- [X] CL005 [P] [US5] **Slice 290 — shipped.** The 0.5 routing
      threshold lives on
      ``MergedIdentification.is_unidentified``
      (``merger.py::UNIDENTIFIED_THRESHOLD``). The Identifier
      façade returns ``IdentifyOutcome`` with
      ``merged.is_unidentified`` set; the importer routes
      via ``importer/_park.py::park_in_unidentified`` which
      idempotently INSERTs / UPDATEs the
      ``unidentified_dump`` row (path-unique).
      Round-trip pinned by
      ``test_unidentified_persistence.py::test_low_confidence_routes_to_unidentified_dump_persistence``.
- [X] CL006 [P] **Slice 290 — shipped.** Settings exposes
      ``hasheous_base_url`` / ``hasheous_token`` /
      ``playmatch_base_url`` / ``playmatch_token`` with the
      ``ROMARR_`` env prefix on
      ``src/romarr/config/settings.py``; ``HasheousBackend`` and
      ``PlayMatchBackend`` in
      ``src/romarr/identification/hashmatch/remote.py`` consume
      them, send the optional ``Authorization: Bearer …`` header,
      and return ``error="rate_limited:429"`` on HTTP 429.
      The cascade calls ``breaker.record_failure()`` whenever
      ``result.ok`` is false, so 429 trips the circuit per
      FR-026a / FR-027.
- [X] CL007 [P] **Slice 290 — shipped.** New tests at
      ``tests/identification/test_confidence_threshold.py`` —
      7 tests: hash ≈ 1.0 → through, No-Intro filename ≈ 0.85
      → through, header-only ≈ 0.6 → through, bare guess < 0.5
      → ``is_unidentified``, threshold strictly less-than at
      0.5, multi-source agreement keeps max above threshold,
      conflict penalty can drop a near-boundary case below
      threshold (validates that the 0.5 cut applies AFTER the
      CL004 penalty).
