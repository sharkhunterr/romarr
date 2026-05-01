# Changelog

All notable changes to Romarr land here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) with semver.

## [0.9.0a1] — 2026-05-01

### Added

- **Spec 008 — Import Pipeline** (partial: 12 of 13 pipeline
  steps + webhook + read-side API. Orchestrator end-to-end +
  manual / retry / match POST endpoints land with the
  follow-up integration slice; polling watcher waits on
  ``DownloadClient.list_managed_downloads`` being added to spec
  005's ABC).
  - One new table (``import_history``) + three column
    extensions on ``unidentified_dump``
    (``rejection_reason``, ``library_id``, ``suggested_game_id``).
    Alembic ``0008`` chains after ``0009_libraries`` and
    finalises the gated ``unidentified_dump.library_id`` FK
    when the library table exists.
  - ``ImportLockManager`` — per-(release_id, sha1)
    :class:`asyncio.Lock` registry with a 60-s timeout
    (FR-033 / FR-034). Test seam supports timeout-on-contention
    via real ``asyncio.wait_for``.
  - ``ImportContext`` / ``ImportOutcome`` /
    ``LifecycleAction`` / ``MultiDiscGroup`` /
    ``RejectionReason`` frozen Pydantic value types — Article
    XVII purity-by-construction so the orchestrator threads
    them between steps without mutation.
  - Twelve pipeline steps under ``romarr.importer.steps``:
      * ``EXTRACT`` — zip/7z/rar with depth-3 limit, bomb
        defense (``max(4 × compressed, 5 GiB)`` cap with
        incremental enforcement on zip/rar), idempotent skip
        via sentinel file, path-traversal rejection.
      * ``HASH`` — directory walker filtered by extension +
        per-platform-format ``min_size_bytes`` floor; hashes
        via spec 001's ``Hasher`` in
        ``asyncio.to_thread``.
      * ``DATMATCH`` — wraps spec 001's
        ``HashMatchCascade``; non-VERIFIED winners propagate
        ``dump_status`` while flipping ``dat_verified`` to
        False (US5.3).
      * ``IDENTIFY`` — wraps spec 001's ``Identifier`` with
        precomputed-hashes pass-through (hash-once invariant).
      * ``GAMEMATCH`` — case-insensitive exact + RapidFuzz
        threshold-90 against monitored Games + threshold-95
        unmonitored fallback for the FR-016
        ``suggested_game_id`` hint.
      * ``MULTIDISC`` — cue/bin > filename-pattern > side-A/B
        detection; primary_file is the .bin for cue/bin pairs
        (FR-019). Hypothesis property test asserts the
        detector never produces an invalid tree across 200
        random layouts.
      * ``PROFILEGATE`` — composes spec 006's
        ``ProfileEvaluator`` with fixed Q→R→D→L ordering;
        ``force=True`` flips rejection into a
        ``force_overrode:<reason>`` warning (US4.2).
      * ``RENDER`` — composes spec 006's
        ``NamingTemplateEngine`` and resolves the full
        destination including platform / multi-disc subfolders.
      * ``MOVE`` — atomic mover. Hardlink-first, EXDEV
        fallback to ``shutil.copy2`` + SHA-1 verify. Idempotent
        on matching dest, collision-protected on mismatching
        dest, fault-injection clean (no partial dest, no
        leftover .tmp). Maps ``OSError`` to structured
        ``RejectionReason`` codes.
      * ``DBUPDATE`` — inserts the fresh Dump, optionally
        retires prior Dumps when ``keep_dump_history=False``
        (FR-028), transitions Release.status →
        ``imported``.
      * ``LIFECYCLE`` — async dispatch by
        ``LifecycleAction.kind``. ``schedule_remove`` spawns a
        fire-and-forget task that sleeps the grace window then
        removes (FR-029); ``ImportOutcome`` publishes BEFORE
        the grace window completes (FR-030).
      * ``NOTIFY`` — ``ImporterEventBus`` in-process pub/sub +
        ``OnImport`` (FR-031) + ``OnUpgrade`` (FR-032)
        emitter. Spec 011's notification subsystem will
        subscribe Apprise / WebSocket / library exporters on
        top.
  - Webhook entry point: POST
    ``/api/v3/webhook/download-complete`` with constant-time
    ``secrets.compare_digest`` token check, sliding-window
    10-req/60s/IP rate limit, schema validation. Returns 202
    ACCEPTED in ~0.34 ms p50 / 0.66 ms p95 (~1500x under the
    1 s SC-008 budget); recorded in
    ``specs/008-import-pipeline/research.md``.
  - Read-side API: ``GET /api/v3/rom/import/history`` (paginated,
    filterable) and ``GET /api/v3/rom/unidentified`` +
    ``DELETE /api/v3/rom/unidentified/{id}`` (admin-only;
    FR-038 — does NOT delete the source file).
  - Coverage: 93.13 % on ``romarr.importer`` (target ≥ 75 %);
    full importer suite 91 passing.

## [0.8.0a1] — 2026-05-01

### Added

- **Spec 009 — Library Management & Exporters** (partial: model +
  routing + 4 exporter primitives + heartbeat + full scan + library
  CRUD API. Incremental scan + manual import + scan/exporter API
  endpoints land in follow-up slices that depend on spec 008's
  importer and the watchdog package.)
  - One new table (``library``), one m2m
    (``library_platform``), one column addition
    (``release.library_id``), and the integrating Alembic
    migration ``0009`` that finalises the forward-reference FKs
    deferred by spec 006 (``library_custom_format.library_id``)
    and spec 008 (``unidentified_dump.library_id``, gated on
    spec 008 having shipped its column).
  - Pure-function multi-library router
    (``romarr.libraries.routing``) implementing FR-006:
    ``routing_score = region_score + quality_bonus`` via spec
    006's ``ProfileEvaluator``; tie-break on lower
    ``library.id``. Custom Format scores deliberately excluded —
    those belong to the search engine, not the importer. AST
    smoke test asserts the router source imports nothing from
    sqlalchemy / httpx / aiohttp / requests / redis / logging.
  - Pre-import disk-space gate
    (``romarr.libraries.disk_space.check_min_disk_free``)
    raising ``DiskFullError`` (subclass of ``LibraryUnavailable``)
    with operator-facing free-GB message (FR-030).
  - Library CRUD endpoints under ``/api/v3/rom/library*`` —
    POST/GET/PUT/DELETE with the m2m platform allowlist, Fernet
    encryption of the RomM API key on save, and the
    FR-025/026/027 force-delete cascade gate (409
    ``library_in_use`` without force; 409
    ``historical_dumps_present`` even with force when
    ``keep_dump_history=true`` and historical Dumps exist; 204 +
    ``library_id=NULL`` on attached Releases when force succeeds
    with no history).
  - Four exporter primitives sharing one atomic+lock writer:
      * ES-DE / Batocera / Recalbox ``gamelist.xml`` via
        ``lxml.etree`` (FR-016, FR-017, FR-017a, FR-018, FR-018a).
        Cover materialisation hardlinks from
        ``data/covers/`` with EXDEV fallback to ``shutil.copy2``,
        idempotent on unchanged source mtime.
      * Pegasus ``metadata.txt`` colon-separated key/value
        document.
      * LaunchBox per-platform-or-global ``launchbox-export.xml``;
        rating maps from Romarr's 0..1 to LaunchBox's 0..5
        ``<CommunityStarRating>``.
      * RomM remote-push ``push_to_romm`` — best-effort POST to
        ``/api/platforms/<id>/scan`` with tenacity 3-attempt
        exponential-jitter retry on connect / timeout / 5xx.
        Fernet-decrypts the API key per call so plaintext never
        lives in memory between requests. Never raises (FR-015 /
        US9: a RomM hiccup must not block an otherwise-successful
        import).
  - Per-library heartbeat with 5-min debounce
    (``romarr.libraries.heartbeat`` + ``_debounce.WindowedDebouncer``)
    implementing FR-028 / FR-029. ``HeartbeatProbe`` is a
    single-library state machine; ``run_heartbeat_pass`` is a
    pure loop driver with per-library cadence. The shared
    ``WindowedDebouncer[K]`` (PEP 695 syntax) is reusable by spec
    011's notification consumer.
  - Async full filesystem scanner
    (``romarr.libraries.scanner.full_scan``) implementing FR-009
    + FR-010 + FR-011 + FR-012: walks ``library.path`` with
    ``Path.rglob`` (sorted for determinism), hashes off the
    event loop via ``asyncio.to_thread``, applies the
    idempotent skip on ``(path, size)`` match, link-by-``sha1``
    rebind for renamed/relocated files, and the orphan sweep
    that transitions Releases back to ``'wanted'``.
    ``ScanProgressEmitter`` ticks every 100 files seen with a
    forced emit on orphans and a terminal emit on ``finish()``.
  - Performance: 100-file full scan runs in ~0.12 s; projected
    10 000-file scan in ~12 s, well under the 5-min SC-003
    second-leg budget. Recorded in
    ``specs/009-library-exporters/research.md``.
  - Coverage: 92.24 % on ``romarr.libraries`` (target ≥ 75 %);
    full library suite 96 passing.

## [0.7.0a1] — 2026-04-30

### Added

- **Spec 007 — Search & Decision Engine** (full feature: 5 entry
  modes, 13-step pure pipeline, frozen ``LibraryState``, query
  cache, blocklist, history, dispatch bridge, 5 admin-gated
  endpoints).
  - Five round entry points — `manual`, `rss`, `on_add`, `missing`,
    `cutoff` — all running through the same pure-function
    pipeline. `manual` and `rss` ship in MVP; `on_add` /
    `missing` / `cutoff` deferred to follow-ups that consume
    spec 008's importer query helpers and spec 009's library
    bindings.
  - 13-step decision pipeline: identify → blocklist gate → DAT
    lookup → quality / region / dump / language gates → custom
    format scoring → DAT-verified bonus → indexer priority →
    seeders → final score. 350+ hypothesis examples confirm
    determinism (same input ↔ same output).
  - Async query cache (`romarr.search.cache`) with LRU eviction
    above 10 000 entries; deduplicates concurrent (game, indexer)
    fan-outs across rounds.
  - Append-only `Blocklist` + `SearchHistory` tables (Alembic
    `0007`); blocklist enforces FR-021 at-least-one-match
    invariant via Pydantic cross-field validator.
  - `dispatch_winner` bridges a winning `Candidate` to spec 005's
    `route_release(...)` and translates downloader errors into
    `GRABBED` / `NO_ELIGIBLE_CLIENT` / `PENDING_RETRY` / `FAILED`
    outcomes (FR-016 / SC-005).
  - Admin-gated REST surface: `POST /api/v3/rom/search/manual`,
    `POST /api/v3/rom/release/grab` (with `?force=true` blocklist
    override per FR-022 / SC-006), `POST /api/v3/command`
    (Sonarr-compat dispatcher), `GET /api/v3/rom/search/history`,
    and `GET/POST/DELETE /api/v3/blocklist*`.
  - Performance: 100-result pipeline scoring runs in ~1.7 ms
    median (118× under the 200 ms SC-003 budget), recorded in
    `specs/007-search-decision-engine/research.md`.
  - Coverage: 90.93 % on `romarr.search` (target ≥ 75 %); 109
    spec-007 tests, full suite 1 252 passing.

## [0.6.0a1] — 2026-04-30

### Added

- **Spec 006 — Profiles** (full feature: six profile types + pure-function
  evaluator + Custom Format scorer + sandboxed Jinja naming engine +
  idempotent first-boot seeders + admin API)
  - Six SQLAlchemy 2.0 models — ``QualityProfile``, ``RegionProfile``,
    ``DumpProfile``, ``LanguageProfile``, ``NamingProfile``,
    ``CustomFormat`` — plus the ``library_custom_format`` m2m. Each
    profile carries the FR-003a seeder sentinels (``seed_key`` +
    ``is_user_modified``) and ``is_factory_default``. Alembic
    migration ``0006`` ships the six tables, the m2m, and the
    partial unique index on ``seed_key WHERE seed_key IS NOT NULL``.
    Library FK columns + the m2m's ``library_id`` FK are deferred
    to spec 009 (forward-reference pattern matching spec 005's
    ``indexer.download_client_id``).
  - Pure-function ``ProfileEvaluator`` — four evaluators
    (Quality / Region / Dump / Language) returning a flat
    ``EvaluationResult`` envelope. 1 250 hypothesis property
    examples confirm purity (SC-002, exceeds the 1 000 floor).
  - Pure-function ``compute_custom_format_score`` — closed
    seven-operator dispatch with OR-grouping per condition
    (FR-021); list-valued fields (tags / regions / languages)
    match if ANY element satisfies. Region scoring formula
    explicit at ``len(priorities) − index`` (FR-013).
  - Sandboxed Jinja2 ``NamingTemplateEngine`` —
    ``ImmutableSandboxedEnvironment`` + per-namespace
    ``is_safe_attribute`` + AST walk at SAVE time rejects unknown
    top-level names, unknown attributes on ``Game`` / ``Release`` /
    ``Dump`` / ``Platform``, non-allowlist filters, and
    function/method invocations. Filter set restricted to four:
    ``lower`` / ``upper`` / ``replace`` / ``truncate``. Five
    canonical convention corpora (no-intro / redump / tosec /
    es-de / romm) at 11-12 golden fixtures each + 13 bad-template
    rejections cover SC-004 + SC-005.
  - Idempotent first-boot seeder — 26 default profiles (3 / 3 / 3 /
    3 / 3 / 11) shipped as JSON files. Looks up by ``seed_key``,
    upserts only when ``is_user_modified = false`` AND values
    differ; operator edits are sacred (FR-003a). Default-catalogue
    drift cleanly refreshes non-edited rows on next boot.
  - Admin API at ``/api/v3/qualityprofile*`` + the five other
    profile paths plus ``/preview`` for naming templates. Reads
    accessible to any authenticated user; mutations + preview
    require admin (FR-032a). PUT flips ``is_user_modified=true`` in
    the same transaction. ``?force=true`` accepted on every DELETE
    (cascade unbinding lights up in spec 009).
  - JSON Schema endpoint at ``{base}/schema`` per profile type —
    auto-generated from the Pydantic ``*Read`` schema via
    ``TypeAdapter(...).json_schema()``, always in sync with the
    model (FR-030).

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
