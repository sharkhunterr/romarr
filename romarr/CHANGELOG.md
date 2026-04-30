# Changelog

All notable changes to Romarr land here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) with semver.

## [0.3.0a1] — 2026-04-30

### Added

- **Spec 003 — Platform Packs** (full feature: validator + ingestor + built-in
  pack + overrides + admin API + hardening)
  - YAML pack format validated against a Draft 2020-12 JSON Schema.
  - Pure-function validator: schema check + duplicate-slug / duplicate-extension
    / dangling-parent / parent-graph cycle detection (iterative DFS) + ReDoS
    static heuristic for nested-quantifier shapes.
  - Transactional ingestor with FR-009 idempotency / FR-010 same-version-conflict
    / FR-013a downgrade rejection / FR-011-13 per-platform rules / FR-014
    parsing-strategies upsert / FR-024 failed-row persistence in a fresh session.
  - Two new tables: ``parsing_strategies`` and
    ``platform_pack_application_log`` (Alembic migration ``0003``).
  - 20-platform built-in YAML pack auto-applied on first boot via
    ``romarr.platform_packs.apply_builtin_pack``; resolves through
    ``ROMARR_BUILTIN_PACK_PATH`` → wheel resource → operator drop-dir.
  - User-override flow: ``mark_overridden`` cascades the user flag to
    formats + tokens; ``release_override`` reads the matching
    ``platform_pack`` row to drive the revert; format-CRUD helpers
    enforce the FR-026 user-override precondition.
  - Admin API at ``/api/v3/rom/platform-pack/*`` (upload + list + detail +
    re-apply + validate-only) and ``/api/v3/rom/platform/{id}/*`` (override +
    format-CRUD), all gated by ``require_admin`` from spec 010.
  - Hypothesis property test for the cycle detector against a
    ``graphlib.TopologicalSorter`` reference oracle.

## [0.2.0a1] — 2026-04-29

### Added

- **Spec 002 — Metadata Aggregation** (provider phase + admin API + hardening)
  - 9 metadata providers behind a single ``MetadataProvider`` ABC: IGDB,
    ScreenScraper, MobyGames, LaunchBox, SteamGridDB, RetroAchievements,
    HowLongToBeat, Hasheous, PlayMatch.
  - Pure lock-aware additive aggregator (FR-009 anti-RomM-#1770 invariant
    with hypothesis property-based test).
  - Per-Game refresh orchestrator with in-process per-Game asyncio lock
    coalescing (FR-013a).
  - Three new tables (``metadata_provider_config``, ``metadata_cache``,
    ``field_priority``) wired up via Alembic migration ``0002`` with
    full nine-provider seed and the canonical RomM-aligned default
    field-priority list.
  - Encryption-at-rest for provider credentials via Fernet keyed off
    ``ROMARR_AUTH_SECRET_KEY`` + scrypt KDF.
  - Admin endpoints under ``/api/v3/metadata/*`` and
    ``/api/v3/game/{id}/refresh-metadata``, all gated by
    ``require_admin`` from spec 010.
  - ``romarr metadata reencrypt`` CLI sub-command (interface stub —
    rotation flow lands once auth-spec key-management surface stabilises).

## [0.1.0] — 2026-04-29

### Added

- **Spec 001 — Foundation** (domain + identification cascade)
- **Spec 010 — Auth & Multi-User**
  - Forms + API-key + trusted-proxy authentication chain
  - Admin user-CRUD + lone-admin protection
  - Setup-token bootstrap; per-IP rate limiter
