# Changelog

All notable changes to Romarr land here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) with semver.

## [0.5.0a1] — 2026-04-30

### Added

- **Spec 005 — Download Clients** (full feature: qBittorrent + SABnzbd
  MVP + three v1-deferred stubs + connectivity orchestrator + routing +
  retry state machine + per-client circuit breaker + admin API)
  - ``DownloadClient`` ABC with ``test_connection``, ``add_torrent`` /
    ``add_nzb``, ``get_status``, ``remove``, ``set_imported_tag``,
    ``ensure_category``. Five concrete impls: ``QBittorrentClient`` +
    ``SabnzbdClient`` (configurable, available=true) and the
    ``Transmission`` / ``Deluge`` / ``NZBGet`` stubs that raise
    ``NotImplementedError("deferred to v1")`` from every method
    (available=false; greyed out by the schema endpoint).
  - SABnzbd via direct httpx against the documented query-string API
    (``/api?mode=...``); auth flavour: ``{"status": false, "error":
    "API Key Incorrect"}`` translates to :class:`AuthError`. SAB
    cannot create categories — ``ensure_category`` raises
    :class:`CategoryWarning` when ``romarr`` is missing (FR-011).
  - qBittorrent via direct httpx against Web API v2 (deviation from
    FR-004's qbittorrent-api mandate — see module docstring for
    rationale). Idempotent on existing magnet info-hash: returns
    existing hash + additively merges tags via ``/torrents/addTags``,
    leaves the existing category alone (FR-004a / CL001).
    Min-version gate: rejects qBit < 4.4.0 (webapi < 2.8.3) with
    :class:`VersionError` (FR-005a / CL003).
  - Pure-function ``route_release`` — indexer override > priority,
    ties broken by id; ``select_torrent_form`` / ``select_nzb_form``
    pick the highest-preference variant (.torrent URL > bytes >
    magnet; .nzb URL > bytes) per FR-003a / CL002. 30-row JSONL
    corpus parametrises the routing test.
  - Pure-function retry state machine: 5-min retry cadence,
    1-hour failure ceiling (FR-022 / SC-007). Auth + Version errors
    skip the retry rotation entirely (non-transient).
  - Per-client circuit breaker registry on top of the foundation
    breaker (Article III) — 5 failures within 60s opens, 60s
    cooldown to half-open (FR-022a / CL004).
  - One new table (``download_client``) via Alembic ``0005`` which
    also installs the deferred FK on ``indexer.download_client_id``
    (ON DELETE SET NULL) that was created columnless in spec 004.
    Credentials Fernet-encrypted via the metadata encryption helper.
  - Admin API at ``/api/v3/downloadclient/*`` (CRUD + ``?test=true``
    + ``/test`` + ``/schema``); CL005 admin gate via spec 010's
    ``require_admin``. Encrypted blobs NEVER appear in any response.

## [0.4.0a1] — 2026-04-30

### Added

- **Spec 004 — Indexers (Prowlarr-First)** (full feature: parser + client +
  rate limiter + registry + connectivity + RSS sync + health + admin API)
  - Generic Newznab/Torznab HTTP client with extended-attribute parsing
    under both ``torznab:`` and ``grabarr:`` namespaces; per-field
    :class:`FieldProvenance` tracks which source supplied each value.
  - Foundation filename-parser fallback fills any field whose
    ``*_provenance is None`` after parsing (FR-004).
  - Per-indexer monotonic-clock rate limiter + reuse of the foundation
    ``CircuitBreaker`` (Article III pinned by a static-import test).
  - Two new tables (``indexer`` + ``application``) via Alembic ``0004``;
    32-byte URL-safe app-token gen + bcrypt hash for inbound Prowlarr
    callbacks; FR-022 encryption-at-rest for indexer + Prowlarr API
    keys via the metadata Fernet helper.
  - Connectivity tester runs caps then optional minimal search; results
    are flat (``ok / caps_ok / search_ok / category``) so the UI doesn't
    need a try/except path.
  - ``IndexerRssSync.sync_all_enabled_indexers`` parallel-isolated via
    ``asyncio.gather(return_exceptions=True)`` (FR-019a); per-task
    health writes use ``commit=False`` and the orchestrator commits
    once after gather.
  - Admin API at ``/api/v3/applications/*`` (register/list/read/delete)
    and ``/api/v3/indexer*`` (CRUD + ``?test=true`` + ``/test`` + ``/schema``);
    all admin-gated via spec 010. Application registration returns
    the plaintext app token exactly once; subsequent reads omit it.
  - Best-effort ``notify_prowlarr_change`` callback for indexer
    deletions on Prowlarr-pushed indexers (FR-016 — never blocks).

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
