# Changelog

All notable changes to Romarr land here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) with semver.

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
