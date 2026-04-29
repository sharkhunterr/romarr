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
- [ ] T007 [SCAF] Create `src/romarr/db/base.py` — `DeclarativeBase` subclass with the
      SQLAlchemy naming convention dict (`ix`, `uq`, `ck`, `fk`, `pk` patterns) so
      Alembic generates portable, predictable constraint names.
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
- [ ] T036 [HASH] Add a tiny CLI script `scripts/hash.py` (≤ 30 lines) that hashes a
      given file and prints CRC32/MD5/SHA-1. Used for manual perf checks
      (1 GB ROM < 10 s on local SSD — SC-002).

**Checkpoint**: `tests/identification/test_hasher.py` is green; manual run of
`python scripts/hash.py <1GB-file>` finishes in < 10 s on your dev SSD.

---

## Phase 4: DAT Manager (`DAT`)

**Purpose**: streaming Logiqx-XML parser, idempotent ingest into `dat_entry`, and four
hash/name lookups.

### Tests

- [ ] T037 [DAT] `tests/identification/dat/test_logiqx_parser.py` — feed the
      `tests/fixtures/dats/nointro_megadrive_sample.dat` fixture, assert the parser
      yields the expected number of `<game>` entries with hashes and statuses.
- [ ] T038 [DAT] `tests/identification/dat/test_manager.py::test_ingest_inserts_entries`
      — call `DatManager.ingest(dat_path, source='no-intro', platform_slug='megadrive')`,
      assert rows in `dat_entry`.
- [ ] T039 [DAT] `tests/identification/dat/test_manager.py::test_ingest_is_idempotent`
      — call ingest twice with the same file; second call must insert zero rows
      (FR-019); also verify it completes in < 5 s for the sample fixture (SC-006).
- [ ] T040 [DAT] `tests/identification/dat/test_manager.py::test_lookup_methods`
      — exercise each of `lookup_by_sha1`, `lookup_by_crc32`, `lookup_by_md5`,
      `lookup_by_name` and confirm the matching row is returned.

### Implementation

- [ ] T041 [DAT] Create `src/romarr/identification/dat/parsers/logiqx.py` —
      `iter_logiqx(path)` generator using `lxml.iterparse`, yielding plain dicts
      with `name`, `crc32`, `md5`, `sha1`, `size`, `status`. Implements the
      `elem.clear()` + ancestor-pruning idiom from research notes to avoid memory
      creep.
- [ ] T042 [DAT] Create `src/romarr/identification/dat/sources.py` — small enum-like
      registry `KNOWN_SOURCES = {'no-intro': NoIntroSource, 'redump': RedumpStub,
      'tosec': TosecStub, ...}`. Stubs raise `NotImplementedError`.
- [ ] T043 [DAT] Create `src/romarr/identification/dat/manager.py` — `DatManager`
      class with `ingest(path, source, platform_slug)` (computes a `contents_hash`
      via `Hasher` and short-circuits when seen before), and the four lookups.
- [ ] T044 [DAT] Wire DAT-related commits into bulk insert via SQLAlchemy
      `session.execute(insert(DatEntry), rows)` in batches of 1 000 to keep memory
      flat for full No-Intro DATs.

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

- [ ] T056 [P] [HDR] Generate `tests/fixtures/headers/sample.nes` (16-byte iNES
      header + minimal body) and `test_ines.py` asserting magic match + mapper
      number + PRG/CHR sizes.
- [ ] T057 [P] [HDR] Generate `tests/fixtures/headers/sample.md` ("SEGA" string
      at offset 0x100 + region byte) and `test_megadrive.py` asserting region
      decode + serial extraction.
- [ ] T058 [P] [HDR] Generate `tests/fixtures/headers/sample_psx.iso` (minimal
      ISO9660 PVD at sector 16 + a `SYSTEM.CNF` containing `BOOT = cdrom:\SLUS_001.23;1`)
      and `test_iso9660.py` asserting system/volume identifier + PSX serial.
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

- [ ] T065 [P] [HM] `tests/identification/hashmatch/test_local.py` — wrap the
      DAT manager's `lookup_by_sha1`, assert it returns a hit for a known SHA-1.
- [ ] T066 [P] [HM] `tests/identification/hashmatch/test_hasheous.py` — respx-
      mocked `https://hasheous.org/api/...` happy path + 5 consecutive failures
      (within 60 s) → circuit opens.
- [ ] T067 [P] [HM] `tests/identification/hashmatch/test_playmatch.py` — same
      shape as Hasheous, different base URL.
- [ ] T068 [HM] `tests/identification/hashmatch/test_circuit_breaker.py` —
      open after 5 failures within 60 s, half-open after the cooldown window,
      reset on a successful call.
- [ ] T069 [HM] `tests/identification/hashmatch/test_cascade.py` — kick all
      three sources in parallel; first authoritative match wins; with both
      remotes down, local DAT still serves (FR-028).

### Implementation

- [ ] T070 [HM] Create `src/romarr/identification/hashmatch/circuit_breaker.py`
      — small async-friendly state machine (`closed → open → half_open`) with
      configurable threshold (default 5), window (default 60 s), cooldown
      (default 60 s).
- [ ] T071 [P] [HM] Create `src/romarr/identification/hashmatch/local.py` —
      thin wrapper over `DatManager` that returns an `IdentificationSource`.
- [ ] T072 [P] [HM] Create `src/romarr/identification/hashmatch/hasheous.py` —
      async httpx client calling `/api/v1/lookup/hash`, tenacity retry with
      jittered backoff, wrapped by the circuit breaker.
- [ ] T073 [P] [HM] Create `src/romarr/identification/hashmatch/playmatch.py` —
      same shape, different endpoint.
- [ ] T074 [HM] Create `src/romarr/identification/hashmatch/cascade.py` —
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

- [ ] T082 [HARD] Create `src/romarr/identification/identifier.py` — public
      `Identifier` façade with `async def identify(path: Path | None = None,
      filename: str | None = None, torznab_attrs: dict | None = None) ->
      Identification`. Orchestrates Hasher → HashMatchCascade → HeaderReader
      (looked up from `platform_format.header_signature_hex`) → FilenameParser
      → Matcher.
- [ ] T083 [HARD] `tests/identification/test_identifier.py` — five end-to-end
      scenarios from spec.md (clean DAT-matched, garbage filename + DAT,
      filename only, filename/DAT conflict, multi-disc) using fixture files
      end-to-end.
- [ ] T084 [HARD] `tests/identification/test_unidentified_persistence.py` —
      when `Identifier.identify` produces `confidence < 0.5`, it must persist
      a row in `unidentified_dump` (FR-029).
- [ ] T085 [HARD] Manual perf check: hash a 1 GB file via the CLI from T036,
      record the time in `specs/001-foundation/research.md` (create file if
      missing) — gate SC-002.
- [ ] T086 [HARD] Run `ruff check . --fix-only=false` and `mypy` — both must
      finish with **zero** warnings on `src/romarr/domain/` and
      `src/romarr/identification/`.
- [ ] T087 [HARD] Run `pytest --cov` — verify domain/ ≥ 80%, identification/
      ≥ 80%, overall ≥ 70% (SC-009). Add targeted tests for any uncovered
      branch.
- [ ] T088 [HARD] Add a single root-level `tests/test_repl_smoke.py`:
      `from romarr.identification import Identifier; from romarr.domain.models import Game, Release, Dump`
      — assert these imports succeed without booting FastAPI (SC-008).

---

## Phase 10: Wrap-up (`WRAP`)

**Purpose**: documentation breadcrumbs, version stamp, commit hygiene.

- [ ] T089 [WRAP] Update `pyproject.toml` `version = "0.1.0a1"`; add a
      one-line release note to `CHANGELOG.md` (create file if missing):
      "0.1.0a1 — Foundation: domain model + identification pipeline."
- [ ] T090 [WRAP] Add `specs/001-foundation/research.md` capturing the lxml
      iterparse cleanup pattern decided in Phase 0 + the perf number from
      T085.
- [ ] T091 [WRAP] Add a 20-line `README.md` snippet (or create the file)
      documenting how to run the test suite, how to apply Alembic migrations
      against a fresh SQLite, and one REPL one-liner showing
      `Identifier.identify(...)`.
- [ ] T092 [WRAP] Final review: open `specs/001-foundation/spec.md` and tick
      every Functional Requirement (FR-001 → FR-029) against a corresponding
      task ID; record any gaps as follow-up items.

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

- [ ] CL001 [P] [US2] Implement cross-DAT hash precedence resolver in `src/romarr/identification/cascade/hash_resolver.py` — fixed authority order **No-Intro > Redump > TOSEC**; first match's metadata wins; others recorded as supporting matches in the conflict log (FR-020a)
- [ ] CL002 [P] [US3] Implement ISO9660 platform-disambiguation file-presence cascade in `src/romarr/identification/headers/iso9660.py` — `SYSTEM.CNF` → PSX/PS2 (with `BOOT2 =` / `VER =` disambiguation); `IP.BIN` boot sector → Mega CD / Saturn / Dreamcast; `default.xbe` → Xbox; otherwise `platform = unknown` (FR-024a)
- [ ] CL003 [P] [US3] Add fixture-based tests for the ISO9660 cascade in `tests/identification/test_iso9660_cascade.py` covering each branch including the unknown-platform path
- [ ] CL004 [P] [US5] Update `merge(...)` in `src/romarr/identification/cascade/merger.py` to apply a flat 10% confidence reduction when one or more conflicts fire (no stacking) (FR-012)
- [ ] CL005 [P] [US5] Update Identifier façade in `src/romarr/identification/identifier.py` so files with merged confidence < 0.5 are routed to `unidentified_dump` (FR-029)
- [ ] CL006 [P] Wire env-var overrides for Hasheous and PlayMatch base URLs and optional bearer tokens in `src/romarr/identification/cascade/clients.py`: `ROMARR_HASHEOUS_BASE_URL`, `ROMARR_HASHEOUS_TOKEN`, `ROMARR_PLAYMATCH_BASE_URL`, `ROMARR_PLAYMATCH_TOKEN`. HTTP 429 counts as a circuit-breaker failure (FR-026a, FR-027)
- [ ] CL007 [P] Add tests in `tests/identification/test_confidence_threshold.py` covering the 0.5 boundary: hash match (≈1.0 → through), No-Intro filename (≈0.85 → through), header-only (≈0.6 → through), bare guess (<0.5 → unidentified_dump)
