# Implementation Plan: Foundation — Domain Model and Identification Pipeline

**Branch**: `001-foundation` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification at `specs/001-foundation/spec.md`

## Summary

Romarr's foundation layer delivers two tightly coupled subsystems:

1. The **persistent domain model** — nine tables (`platform`,
   `platform_format`, `platform_naming_token`, `game`, `release`, `dump`,
   `dat_entry`, `unidentified_dump`, `platform_pack`) with their SQLAlchemy
   2.0 async models, Pydantic v2 read/create/update schemas, and an Alembic
   baseline migration that seeds the five MVP platforms.
2. The **multi-source ROM identification pipeline** — a single `Identifier`
   façade plus six sub-modules (Hasher, DAT Manager, Filename Parsers, Header
   Readers, Hash-Match Cascade, Matcher) that produce a confidence-scored
   `Identification` from any combination of hash, Torznab metadata, header
   bytes, and filename.

Technical approach: SQLAlchemy 2.0 async with both SQLite (default) and
PostgreSQL drivers; lxml `iterparse` for streaming Logiqx XML; `httpx` async
with tenacity retries and a per-service circuit breaker for remote hash
backends; pluggable parser/header ABCs registered via the platform-format
table to keep platform-specific logic out of code. The whole layer is
importable from a REPL without booting FastAPI.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: SQLAlchemy 2.0 (async), Pydantic v2, Alembic,
lxml, httpx (async), tenacity, structlog (logging), zlib (CRC32), hashlib
(MD5/SHA-1/SHA-256)
**Storage**: SQLite by default (file-backed), PostgreSQL 15+ optional —
identical SQLAlchemy models, driver-agnostic JSON columns
**Testing**: pytest, pytest-asyncio, pytest-cov, hypothesis (property
tests for parsers), respx (mocking httpx for Hasheous/PlayMatch),
freezegun (deterministic timestamps)
**Target Platform**: Linux server (amd64 + arm64), distributed as a single
multi-arch Docker image; this feature ships as a Python package importable
from a REPL — no HTTP layer required to exercise it
**Project Type**: Backend Python library (the FastAPI app shell will land
in a later API spec; this layer must remain importable standalone)
**Performance Goals**:
- Hash 1 GB ROM in < 10 s on local SSD (single pass for CRC32+MD5+SHA-1)
- Re-ingest an unchanged DAT in < 5 s (zero new rows)
- Hash lookup p95: < 200 ms with local DAT only; < 2 s with both remote
  backends reachable
- Library scan target (10 000 ROMs in < 5 min) is the *consumer*'s budget;
  this feature must not blow the per-file budget of 30 ms identification
  excluding hashing
**Constraints**:
- Streaming I/O only — never load a ROM or DAT entirely into memory
- Hashing MUST run off the asyncio event loop when called from async code
- Idempotent imports / ingestions everywhere (Constitution Article XII)
- Strict typing on `domain/` and `identification/` (mypy --strict, zero
  warnings)
**Scale/Scope**:
- Tens of thousands of `dat_entry` rows per platform (No-Intro full set is
  large but bounded)
- Hundreds of thousands of `dump` rows lifetime
- Single-tenant (multi-user is a later spec)

## Constitution Check

*Gate: must pass before Phase 0 research and again after Phase 1 design.*

| Article | Gate | Status |
|---------|------|--------|
| III — Technology Stack (Locked) | Backend MUST use Python 3.12+, SQLAlchemy 2.0 async, Pydantic v2, Alembic, httpx async; no `requests`/`urllib3` direct. | ✅ Conformant. |
| V — Profile-Driven Decisions | No grab/upgrade/import logic is hardcoded. | ✅ Conformant — this layer exposes building blocks; profiles are consumed in later specs. |
| VI — Identification Cascade | Authority order **hash > Torznab > header > filename**; hash backends queried in parallel; DAT verification on by default; conflicts logged but never block. | ✅ Conformant — encoded in FR-010, FR-011, FR-012, FR-013, FR-026, FR-027, FR-028. |
| XII — Library Discipline | Idempotent imports; idempotent DAT ingestion; multiple Releases per Game first-class; per-Release cutoff. | ✅ Conformant — encoded in FR-003, FR-004, FR-019. |
| XIII — Domain Model | Platform 1—* Game 1—* Release 1—0..1 Dump; Game bound to exactly one Platform; multi-disc via `parent_release_id`. | ✅ Conformant — encoded in FR-002, FR-004, and the data model. |
| XVI — Quality Gates | ≥ 80% coverage on domain/ and identification/, ≥ 70% overall; mypy --strict on those layers; ruff zero warnings. | ✅ Conformant — encoded in SC-009, SC-010 and the Hardening phase of `tasks.md`. |
| XVII — Idempotency & Safety | Idempotent writes; no destructive auto-actions in this layer (it does not move files yet — that's the Importer spec). | ✅ Conformant. |

**Result**: GREEN. No constitutional violations; no entries in Complexity
Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/001-foundation/
├── plan.md              # this file
├── spec.md              # user-value specification
├── data-model.md        # entity-by-entity DDL & invariants
├── tasks.md             # 10-phase granular task list
└── checklists/
    └── requirements.md  # spec-quality checklist
```

### Source Code (repository root)

```text
src/romarr/
├── __init__.py
├── config/
│   ├── __init__.py
│   └── settings.py            # ROMARR_* env vars; Pydantic Settings
├── db/
│   ├── __init__.py
│   ├── base.py                # DeclarativeBase, naming convention
│   ├── session.py             # async engine + session factory
│   └── alembic/
│       ├── env.py
│       ├── script.py.mako
│       └── versions/
│           └── 0001_initial_schema.py  # 9 tables + seed of 5 platforms
├── domain/
│   ├── __init__.py
│   ├── enums.py               # DumpStatus, NamingConvention, ReleaseStatus, GameStatus
│   ├── models/
│   │   ├── __init__.py
│   │   ├── platform.py        # Platform, PlatformFormat, PlatformNamingToken, PlatformPack
│   │   ├── game.py            # Game
│   │   ├── release.py         # Release
│   │   ├── dump.py            # Dump, UnidentifiedDump
│   │   └── dat.py             # DatEntry
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── platform.py        # PlatformRead/Create/Update + Format/Token variants
│   │   ├── game.py
│   │   ├── release.py
│   │   ├── dump.py
│   │   └── dat.py
│   └── validators.py          # cross-field invariants (FR-004, FR-005, FR-006, FR-007)
├── identification/
│   ├── __init__.py            # exposes the public Identifier façade
│   ├── identifier.py          # orchestrator
│   ├── types.py               # ParsedFilename, HeaderInfo, IdentificationSource, Identification, Conflict
│   ├── hasher.py              # streaming CRC32+MD5+SHA-1 (+ optional SHA-256)
│   ├── dat/
│   │   ├── __init__.py
│   │   ├── manager.py         # ingest + lookups
│   │   ├── parsers/
│   │   │   ├── __init__.py
│   │   │   └── logiqx.py      # lxml.iterparse streaming
│   │   └── sources.py         # NoIntro implemented; Redump, TOSEC stubs
│   ├── filename/
│   │   ├── __init__.py
│   │   ├── base.py            # FilenameParser ABC, ParsedFilename
│   │   ├── nointro.py
│   │   ├── goodtools.py
│   │   ├── tosec.py
│   │   ├── scene.py
│   │   └── dispatcher.py      # tries parsers in fixed order, threshold 0.7
│   ├── header/
│   │   ├── __init__.py
│   │   ├── base.py            # HeaderReader ABC
│   │   ├── ines.py
│   │   ├── megadrive.py
│   │   ├── iso9660.py
│   │   └── stubs.py           # 3DS/NDS/PSP/Vita/Switch/Wii/GC/GBA — NotImplementedError
│   ├── hashmatch/
│   │   ├── __init__.py
│   │   ├── cascade.py         # parallel local-DAT + Hasheous + PlayMatch
│   │   ├── local.py
│   │   ├── hasheous.py
│   │   ├── playmatch.py
│   │   └── circuit_breaker.py # 5 failures / 60 s
│   └── matcher.py             # merges sources, logs conflicts, applies confidence rule

tests/
├── conftest.py                # async DB fixture, event_loop policy, in-memory SQLite
├── domain/
│   ├── test_platform_model.py
│   ├── test_game_model.py
│   ├── test_release_model.py
│   ├── test_dump_model.py
│   ├── test_invariants.py
│   └── test_schemas.py
├── identification/
│   ├── test_hasher.py
│   ├── dat/
│   │   ├── test_logiqx_parser.py
│   │   └── test_manager.py
│   ├── filename/
│   │   ├── test_nointro_parser.py
│   │   ├── test_goodtools_parser.py
│   │   ├── test_tosec_parser.py
│   │   ├── test_scene_parser.py
│   │   └── test_dispatcher.py
│   ├── header/
│   │   ├── test_ines.py
│   │   ├── test_megadrive.py
│   │   └── test_iso9660.py
│   ├── hashmatch/
│   │   ├── test_local.py
│   │   ├── test_hasheous.py        # respx-mocked
│   │   ├── test_playmatch.py       # respx-mocked
│   │   ├── test_circuit_breaker.py
│   │   └── test_cascade.py
│   ├── test_matcher.py
│   └── test_identifier.py     # 5 representative end-to-end scenarios
└── fixtures/
    ├── dats/
    │   └── nointro_megadrive_sample.dat
    ├── filenames/
    │   ├── nointro_corpus.txt          # ≈100 lines
    │   ├── goodtools_corpus.txt        # ≈100 lines
    │   ├── tosec_corpus.txt            # ≈100 lines
    │   └── scene_corpus.txt            # ≈100 lines
    ├── headers/
    │   ├── sample.nes                  # iNES magic + minimal body
    │   ├── sample.md                   # SEGA at 0x100 + minimal body
    │   └── sample_psx.iso              # ISO9660 PVD + SYSTEM.CNF
    └── roms/                            # tiny synthetic ROMs with known hashes
        └── known_hash_1mb.bin

pyproject.toml                  # ruff config, mypy config, pytest config, deps
alembic.ini                     # points to src/romarr/db/alembic
README.md                        # follow-up; out of scope unless minimal
```

**Structure Decision**: Single Python package `src/romarr/` with two
top-level domains (`domain/` and `identification/`) plus a thin `db/` for
the async engine + Alembic. No FastAPI / HTTP layer here — that is the API
spec's job. Tests mirror the `src/romarr/` layout one-for-one. Fixtures
live under `tests/fixtures/` and are committed (the synthetic ROMs are
< 1 MB total).

## Phase 0 — Research

Two open technical questions to nail before writing code; both produce a
short note in `research.md` if confirmation is needed at code time.

1. **lxml `iterparse` cleanup pattern** — the canonical pattern is
   `for event, elem in iterparse(...): ... elem.clear()` with `for
   ancestor in elem.xpath('ancestor-or-self::*'): while ancestor.getprevious() is not None: del ancestor.getparent()[0]`
   to avoid memory creep on 200 MB DATs. Confirm against the lxml docs
   and ship the helper in `identification/dat/parsers/logiqx.py`.
2. **SQLAlchemy 2.0 async + `JSON` portability** — use
   `sqlalchemy.JSON` (driver-agnostic) for `regions`, `languages`, `tags`,
   `genres`, `themes`, `franchises`, `companion_extensions`,
   `locked_fields`, `extra_meta`, `custom_metadata`. Avoid `JSONB` to keep
   SQLite parity. PostgreSQL operators that need JSONB will be added in a
   later PostgreSQL-only migration if and only if a query proves slow.

No other research items: every other choice is locked by the constitution.

## Phase 1 — Design Outputs

- `data-model.md` — full table-by-table DDL, indexes, constraints,
  invariants, ENUM values, Pydantic schema notes, ER diagram in mermaid.
- No `contracts/` — this feature ships no HTTP API. The "contract" is the
  Python-level `Identifier` façade plus the SQLAlchemy models, both
  exhaustively tested.
- No `quickstart.md` — this layer is a library; the operator-facing
  quickstart belongs to the API + UI specs. A REPL one-liner is included
  in the wrap-up phase of `tasks.md` instead.

### Re-check: Constitution after design

Same table as above; nothing changed in design that pulls a constraint.
**Result**: GREEN.

## Complexity Tracking

> *Empty.* No constitutional violations. No deviations to justify.

## Clarification Deltas (Session 2026-04-29)

The 5 clarifications recorded in `spec.md` add the following architectural
constraints to this plan:

- **Cross-DAT hash collision precedence** (FR-020a) — the
  `HashMatchCascade` MUST evaluate matches in the fixed authority order
  **No-Intro > Redump > TOSEC**; the first match's metadata wins; the
  others are recorded as supporting matches in the conflict log.
  Implementation lives in `identification/cascade/hash_resolver.py`.
- **ISO9660 platform disambiguation cascade** (FR-024a) — the
  `Iso9660HeaderReader` MUST run a file-presence cascade
  (`SYSTEM.CNF` → PSX/PS2; `IP.BIN` boot sector → Mega CD / Saturn /
  Dreamcast; `default.xbe` → Xbox; otherwise `platform = unknown`).
  Mounting the image read-only via `pycdlib` is the recommended approach;
  no full extraction is required.
- **Hasheous & PlayMatch auth** (FR-026a) — anonymous public endpoints
  by default. Env override knobs: `ROMARR_HASHEOUS_BASE_URL`,
  `ROMARR_HASHEOUS_TOKEN`, `ROMARR_PLAYMATCH_BASE_URL`,
  `ROMARR_PLAYMATCH_TOKEN`. When a token is set, the client sends
  `Authorization: Bearer …`. HTTP 429 counts as a circuit-breaker
  failure.
- **Conflict-confidence penalty cap** (FR-012 rewritten) — flat 10%
  reduction regardless of conflict count; do NOT stack. Pure-function
  signature: `merge(sources: list[ParsedField]) -> (Identification, list[Conflict])`
  with `confidence = max(...) - (0.10 if conflicts else 0.0)`.
- **Merged-Identification confidence threshold** (FR-029 rewritten) —
  ≥ 0.5 to proceed downstream; < 0.5 parks in `unidentified_dump`. A
  hash match yields ≈ 1.0; clean No-Intro filename ≈ 0.85; header-only
  read ≈ 0.6; bare filename guess often < 0.5.

No new tables. No new migration. The existing `0001_foundation.py`
migration documented in `data-model.md` is unchanged structurally — only
constants and helper logic in the identification layer are affected.
