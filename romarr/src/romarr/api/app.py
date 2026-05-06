"""FastAPI application factory.

Per spec 013 the production app exposes a /api/v3/* surface; this
slice ships the bootstrap + auth router only. Later slices register
the rest of the routers (game, indexer, library, search, …) via
their own ``register_router(app)`` helpers.

The factory is pure-function on purpose so tests can spin up a fresh
app per test with overridden settings / dependencies.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from romarr import __version__
from romarr.api.error_handlers import register_error_handlers
from romarr.api.middleware import (
    register_cors,
    register_csrf,
    register_gzip,
    register_idempotency,
    register_rate_limit,
)
from romarr.api.openapi import customize_openapi
from romarr.api.spa import register_spa
from romarr.api.routers.auth import router as auth_router
from romarr.api.routers.backup import router as backup_router
from romarr.api.routers.calendar import router as calendar_router
from romarr.api.routers.cover import router as cover_router
from romarr.api.routers.game import router as game_router
from romarr.api.routers.history import router as history_router
from romarr.api.routers.language import router as language_router
from romarr.api.routers.log import router as log_router
from romarr.api.routers.dat_sources import router as dat_sources_router
from romarr.api.routers.rootfolder import router as rootfolder_router
from romarr.api.routers.quality_definitions import (
    router as quality_definitions_router,
)
from romarr.api.routers.queue import router as queue_router
from romarr.api.routers.release import router as release_router
from romarr.api.routers.status import router as system_status_router
from romarr.api.routers.tag import router as tag_router
from romarr.api.routers.users import router as users_router
from romarr.api.routers.wanted import router as wanted_router
from romarr.api.ws import SubscriptionRegistry, ws_router
from romarr.config import get_settings
from romarr.db.session import create_engine, create_sessionmaker
from romarr.downloaders.api import (
    clients_router as download_clients_router,
)
from romarr.downloaders.api import (
    schema_router as download_clients_schema_router,
)
from romarr.importer.api import (
    history_router as importer_history_router,
)
from romarr.importer.api import (
    manual_router as importer_manual_router,
)
from romarr.importer.api import (
    unidentified_router as importer_unidentified_router,
)
from romarr.importer.webhook import router as importer_webhook_router
from romarr.indexers.api import applications_router, indexers_router
from romarr.libraries.api import (
    exporters_router,
    libraries_router,
    manual_import_router,
    scan_router,
)
from romarr.metadata.api import (
    field_priority_router,
    providers_router,
    refresh_router,
)
from romarr.metadata.api.lookup import router as metadata_lookup_router
from romarr.notifications.api import (
    health_router as notifications_health_router,
)
from romarr.notifications.api import (
    notifications_router,
    webhook_payloads_md_router,
)
from romarr.platform_packs.api import (
    packs_router,
)
from romarr.platform_packs.api import (
    platforms_router as platform_pack_platforms_router,
)
from romarr.profiles.api import (
    custom_format_router,
    dump_profile_router,
    language_profile_router,
    naming_profile_router,
    quality_profile_router,
    region_profile_router,
)
from romarr.search.api import (
    blocklist_router as search_blocklist_router,
)
from romarr.search.api import (
    grab_router as search_grab_router,
)
from romarr.search.api import (
    history_router as search_history_router,
)
from romarr.search.api import (
    search_router,
)
from romarr.tasks.api import (
    command_router as tasks_command_router,
)
from romarr.tasks.api import (
    runs_router as tasks_runs_router,
)
from romarr.tasks.api import (
    tasks_router,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the engine + sessionmaker on startup; dispose on shutdown.

    Stored on ``app.state`` so the dependency layer can pull them out
    without going through global singletons (which break test
    parallelism).

    Also wires the spec 012 Tasks subsystem onto ``app.state``:
    a :class:`SchedulerService` with the production runner
    registry plus a :class:`CancellationRegistry`. On shutdown
    the graceful-shutdown protocol runs (FR-021, US6).

    Slice 173 wires the spec-006 ``seed_defaults`` (default
    profiles catalogue) and the spec-003 ``apply_builtin_pack``
    (Platform Pack ingestion) — both called once on startup so
    a fresh database boots into a usable state. Both are
    idempotent so re-runs are no-ops, and both are guarded by
    ``app.state._enable_bootstrap`` (default OFF) so the test
    suite that builds the app many times per session doesn't
    pay the seeding cost.

    Tests that don't want a live scheduler (most of them) opt
    out by setting ``app.state._skip_scheduler = True`` before
    the lifespan starts.
    """
    database_url = getattr(app.state, "_test_database_url", None)

    # Slice 187 — settings-driven lifespan toggles. Tests can
    # still override via ``app.state._enable_bootstrap`` /
    # ``_enable_scheduler`` / ``_auto_migrate``; production
    # operators flip ``ROMARR_*_ENABLED`` env vars.
    from logging import getLogger

    from romarr.config.settings import get_settings

    settings = get_settings()
    bootstrap_log = getLogger(__name__)

    # Auto-migration happens BEFORE uvicorn boots — see
    # ``romarr.cli.main._serve``. Alembic's env.py drives its
    # own asyncio.run loop, which clashes with the lifespan's
    # already-running loop. The CLI step keeps the migration
    # idempotent + bounded by the same Settings.auto_migrate
    # flag the lifespan would have honoured.

    engine = create_engine(database_url) if database_url else create_engine()
    app.state.db_engine = engine
    app.state.db_sessionmaker = create_sessionmaker(engine)

    # Slice 173 / 187 — bootstrap seeders + setup-token mint.
    # Defaults OFF for tests; production sets
    # ``ROMARR_BOOTSTRAP_ENABLED=true``. Tests can still
    # override per-instance via ``app.state._enable_bootstrap``.
    enable_bootstrap = getattr(
        app.state, "_enable_bootstrap", settings.bootstrap_enabled
    )
    if enable_bootstrap:
        from romarr.auth.setup import maybe_bootstrap_setup_token
        from romarr.platform_packs.builtin import apply_builtin_pack
        from romarr.profiles.seeders.runner import seed_defaults

        sm = app.state.db_sessionmaker
        # Default profiles first (T055): the platform pack uses
        # them by reference, so they must exist before the pack
        # ingestion runs.
        try:
            async with sm() as session:
                changed = await seed_defaults(session)
                await session.commit()
            bootstrap_log.info(
                "lifespan.seed_defaults", extra={"counts": changed}
            )
        except Exception as exc:
            # Don't paralyse the API if the seed catalogue is
            # malformed; the operator can re-run via the
            # eventual /api/v3/system/seed-defaults endpoint.
            bootstrap_log.warning(
                "lifespan.seed_defaults_failed",
                exc_info=True,
                extra={"error": str(exc)},
            )
        # Built-in Platform Pack (T038).
        try:
            async with sm() as session:
                result = await apply_builtin_pack(session, sessionmaker=sm)
            bootstrap_log.info(
                "lifespan.apply_builtin_pack",
                extra={"applied": result is not None},
            )
        except Exception as exc:
            bootstrap_log.warning(
                "lifespan.apply_builtin_pack_failed",
                extra={"error": str(exc)},
            )
        # Spec 010 T085 — setup-token bootstrap. Skips when an
        # active human user already exists, otherwise mints a
        # one-shot token and prints the plaintext to logs so the
        # operator can complete /auth/setup.
        try:
            async with sm() as session:
                token_result = await maybe_bootstrap_setup_token(session)
                await session.commit()
            if token_result.plaintext is not None:
                bootstrap_log.warning(
                    "lifespan.setup_token_minted",
                    extra={
                        "expires_at": token_result.expires_at.isoformat()
                        if token_result.expires_at
                        else None,
                        "token": token_result.plaintext,
                    },
                )
            else:
                bootstrap_log.info(
                    "lifespan.setup_token_skipped",
                    extra={"reason": token_result.reason},
                )
        except Exception as exc:
            bootstrap_log.warning(
                "lifespan.setup_token_failed",
                exc_info=True,
                extra={"error": str(exc)},
            )

    # Spec 011 + spec 013 T068 / T072 (slice 274) — construct the
    # in-process EventChannel + WS bridge BEFORE the scheduler so
    # the scheduler can wire ``taskStarted`` / ``taskFinished``
    # emission through the bridge (slice 276 / T064).
    from romarr.api.ws.bridge import WsBridge
    from romarr.notifications.channel import EventChannel

    event_channel = EventChannel()
    await event_channel.start()
    app.state.event_channel = event_channel
    ws_bridge = WsBridge(registry=app.state.ws_subscriptions)
    ws_bridge.attach(event_channel)
    app.state.ws_bridge = ws_bridge

    # Spec 009 CL003 — orphan-releases health check. Runs once
    # per startup; if any Release has no library_id (the spec 009
    # backfill couldn't bind it via path-prefix), emit a single
    # OnHealthIssue so the operator sees it on the Dashboard.
    if enable_bootstrap:
        try:
            from romarr.libraries._orphan_health import (
                check_orphan_releases_on_startup,
            )

            await check_orphan_releases_on_startup(
                sessionmaker=app.state.db_sessionmaker,
                event_channel=event_channel,
            )
        except Exception:
            bootstrap_log.warning(
                "lifespan.orphan_releases_check_failed", exc_info=True
            )

    # Spec 012 — start the Tasks subsystem when explicitly
    # enabled. Default OFF so the test suite (which builds
    # the app many times per session) doesn't pay the
    # SchedulerService bootstrap cost; production sets
    # ``app.state._enable_scheduler = True`` (or the
    # eventual ``ROMARR_SCHEDULER_ENABLED`` settings flag).
    enable_scheduler = getattr(
        app.state, "_enable_scheduler", settings.scheduler_enabled
    )
    scheduler = None
    if enable_scheduler:
        from romarr.tasks.execution.cancellation import CancellationRegistry
        from romarr.tasks.runner_protocol import build_default_registry
        from romarr.tasks.scheduler import SchedulerService

        # Slice 190 / spec 011 T057 — build the HealthEngine
        # so the scheduler's HealthCheck cron probes the live
        # configuration (libraries, indexers, download
        # clients, metadata providers) rather than a stub.
        # Engine construction itself is best-effort so a
        # malformed row can't take down the scheduler.
        health_engine = None
        if enable_bootstrap:
            try:
                from romarr.notifications.health.builder import (
                    build_health_engine,
                )

                health_engine = await build_health_engine(
                    app.state.db_sessionmaker
                )
                app.state.health_engine = health_engine
                bootstrap_log.info("lifespan.health_engine_built")
            except Exception as exc:
                bootstrap_log.warning(
                    "lifespan.health_engine_build_failed",
                    exc_info=True,
                    extra={"error": str(exc)},
                )
                health_engine = None

        cancellation_registry = CancellationRegistry()
        scheduler = SchedulerService(
            session_factory=app.state.db_sessionmaker,
            runners=build_default_registry(health_engine=health_engine),
            cancellation_registry=cancellation_registry,
            ws_bridge=ws_bridge,
            event_channel=event_channel,
        )
        try:
            await scheduler.start()
        except Exception:
            # Failure to bootstrap (DB not seeded, etc.) shouldn't
            # paralyse the API surface — endpoints surface 503 if
            # the scheduler isn't on app.state.
            scheduler = None
        else:
            app.state.scheduler = scheduler
            app.state.cancellation_registry = cancellation_registry
            # Slice 278 — wire OnGameAdded → AutoCheckAdded.
            # The dispatcher subscribes globally to the channel and
            # fires the matching job when the event lands. Best
            # effort: trigger failures log but never block the
            # channel.
            from romarr.tasks.event_dispatch import attach_event_dispatch

            event_dispatcher = attach_event_dispatch(event_channel, scheduler)
            app.state.event_dispatcher = event_dispatcher

    # Spec 009 T030 — heartbeat loop. Independent of the
    # scheduler: it has its own per-library cadence and
    # publishes events directly on the EventChannel rather
    # than through the audit ledger. Default OFF for the test
    # suite; production sets ROMARR_HEARTBEAT_ENABLED=true.
    heartbeat_loop = None
    enable_heartbeat = getattr(
        app.state, "_enable_heartbeat", settings.heartbeat_enabled
    )
    if enable_heartbeat:
        from romarr.libraries.heartbeat_loop import HeartbeatLoop

        heartbeat_loop = HeartbeatLoop(
            sessionmaker=app.state.db_sessionmaker,
            event_channel=event_channel,
        )
        try:
            await heartbeat_loop.start()
        except Exception:
            bootstrap_log.warning(
                "lifespan.heartbeat_start_failed", exc_info=True
            )
            heartbeat_loop = None
        else:
            app.state.heartbeat_loop = heartbeat_loop
            bootstrap_log.info("lifespan.heartbeat_started")

    # Spec 008 T022 — importer polling watcher. Same opt-in
    # pattern as the heartbeat: default OFF for tests, production
    # sets ROMARR_IMPORTER_WATCHER_ENABLED=true. The watcher is
    # the FR-001 fallback to the webhook surface — clients that
    # don't speak webhooks (or webhook drops) get picked up on
    # the 30 s tick.
    watcher = None
    enable_watcher = getattr(
        app.state, "_enable_watcher", settings.importer_watcher_enabled
    )
    if enable_watcher:
        from romarr.importer._dispatch import (
            build_get_enabled_clients,
            build_managed_download_dispatcher,
        )
        from romarr.importer.orchestrator import start_watcher

        try:
            watcher = await start_watcher(
                get_clients=build_get_enabled_clients(
                    app.state.db_sessionmaker
                ),
                dispatcher=build_managed_download_dispatcher(
                    app.state.db_sessionmaker,
                    event_channel=event_channel,
                ),
            )
        except Exception:
            bootstrap_log.warning(
                "lifespan.watcher_start_failed", exc_info=True
            )
            watcher = None
        else:
            app.state.watcher = watcher
            bootstrap_log.info("lifespan.watcher_started")

    try:
        yield
    finally:
        if watcher is not None:
            from romarr.importer.orchestrator import stop_watcher

            await stop_watcher()
        if heartbeat_loop is not None:
            await heartbeat_loop.stop()
        # Slice 278 — detach the event-dispatcher (if attached)
        # before tearing down the channel so we don't fire
        # spurious triggers during shutdown.
        event_dispatcher = getattr(app.state, "event_dispatcher", None)
        if event_dispatcher is not None:
            event_channel.unsubscribe_global(event_dispatcher)
        ws_bridge.detach(event_channel)
        await event_channel.stop()
        if scheduler is not None:
            from romarr.tasks.shutdown import graceful_shutdown

            cr = getattr(app.state, "cancellation_registry", None)
            await graceful_shutdown(
                scheduler=scheduler,
                cancellation_registry=cr,
            )
        await engine.dispose()


def create_app(*, database_url: str | None = None) -> FastAPI:
    """Build the FastAPI app.

    ``database_url`` lets tests pass an in-memory SQLite URL without
    polluting the global cache used by :func:`romarr.db.session.get_engine`.
    """
    app = FastAPI(
        title="Romarr",
        version=__version__,
        description="Self-hosted ROM acquisition manager",
        lifespan=_lifespan,
        # Spec 013 will fully wire these; we ship reasonable defaults
        # so /docs and /openapi.json work from day one.
        docs_url="/api/v3/docs",
        redoc_url="/api/v3/redoc",
        openapi_url="/api/v3/openapi.json",
    )

    if database_url is not None:
        # ``_lifespan`` reads this off ``app.state`` to override the
        # cached default. Test code uses ``with create_app(database_url=…)``.
        app.state._test_database_url = database_url

    # Spec 013 — Sonarr-shape /api/v3/system/status reports startTime
    # as the moment the app was built. create_app() runs once per
    # process, so this is functionally the process boot time.
    app.state._start_time = datetime.now(UTC)

    # Spec 013 phase WS — process-local subscription registry.
    # The bridge consumer (lands in a follow-up slice) reads
    # this off app.state to broadcast events to subscribers.
    app.state.ws_subscriptions = SubscriptionRegistry()

    # Spec 013 phase MW. Middleware order matters: Starlette runs the
    # last-registered middleware first, so GZip lands on the outermost
    # layer (it must see the final response bytes). CORS goes next,
    # ahead of the routers.
    settings = get_settings()
    register_gzip(app, min_size_bytes=settings.gzip_min_size_bytes)
    register_cors(app, allowed_origins=settings.cors_allowed_origins)
    # CSRF middleware (FR-027). Registered after CORS so
    # cross-origin preflights succeed before CSRF kicks in.
    # Defaults to disabled — flipped on once the spec 014
    # frontend wires cookie-reading + header-echoing.
    register_csrf(app, enabled=settings.csrf_protect)
    # Rate-limit middleware (FR-022 / FR-023 / FR-024).
    # Defaults to disabled so the test suite (which fires
    # repeated POSTs at /login / /setup) doesn't 429 on the
    # 6th call. Production sets ROMARR_RATE_LIMIT_ENABLED=true.
    register_rate_limit(
        app,
        enabled=settings.rate_limit_enabled,
        login_limit=settings.rate_limit_login_per_minute,
        setup_limit=settings.rate_limit_setup_per_minute,
        default_limit=settings.rate_limit_default_per_minute,
    )
    # Idempotency-Key middleware (FR-020 / FR-025). Registered last
    # in the MW stack so it's nearest the routes — it intercepts
    # mutating methods after CORS / CSRF have cleared the request,
    # but before the route handler runs the actual mutation.
    register_idempotency(app)

    register_error_handlers(app)
    app.include_router(auth_router)
    app.include_router(users_router)
    # Spec 013 — Sonarr-compat /api/v3/system/status (FR-031, US1).
    app.include_router(system_status_router)
    # Sonarr-compat shims so Prowlarr's "Test" against an
    # Apps → Sonarr registration populates without errors.
    app.include_router(rootfolder_router)
    app.include_router(language_router)
    # Spec 013 — Tag CRUD (T060). The /detail/{id} sub-route is
    # registered before the {tag_id} catch-all in the router so
    # FastAPI's path matcher hits the literal first.
    app.include_router(tag_router)
    # Spec 013 — Queue mirror (T057). List endpoint only in this
    # slice; DELETE / retry land with the spec 005 client wiring.
    app.include_router(queue_router)
    # Spec 013 — Wanted lists (T056): /missing + /cutoff
    # paginated reads. Bulk-search trigger lands with the spec 007
    # run_manual_search hook.
    app.include_router(wanted_router)
    # Spec 013 — Calendar (T059): MVP empty list. The schema is
    # pinned so the frontend can wire the month view now.
    app.include_router(calendar_router)
    # Spec 014 T106 (slice 266) — Settings > Quality Definitions
    # read-only summary. Aggregates Platform → PlatformFormat
    # rows server-side so the UI doesn't fan out N+1 fetches.
    app.include_router(quality_definitions_router)
    # Spec 014 T106 (slice 267) — Settings > DAT Sources read-only
    # summary. Groups DatEntry rows by source so the operator can
    # see which authoritative DAT databases are loaded.
    app.include_router(dat_sources_router)
    # Spec 008 + 014 (slice 86) — Game/Release reads. Drives
    # the Frontend's manual-match Game picker (slice 84's
    # POST /unidentified/{id}/match needs a way to pick the
    # target Game + Release).
    # IMPORTANT: lookup must register BEFORE game_router so that
    # `GET /api/v3/game/lookup` doesn't get swallowed by the
    # ``{game_id}`` catch-all on game_router.
    app.include_router(metadata_lookup_router)
    app.include_router(game_router)
    # Spec 014 slice 159 — cover-art bytes endpoint, lives on
    # its own /api/v3/cover prefix so the FileResponse pipeline
    # stays out of the JSON-only game router.
    app.include_router(cover_router)
    # Spec 014 (slice 98) — Release operator-toggle surface
    # (PATCH /api/v3/rom/release/{id} for the monitor flag).
    # Manual grab lives at the same prefix in spec 007's
    # search router; both routers share the prefix.
    app.include_router(release_router)
    # Spec 013 — Unified history (T058): UNION across
    # import_history / search_history / job_run, paginated.
    # /since variant filters by minimum date for cheap polling.
    app.include_router(history_router)
    # Spec 013 — Logs (T054): paginated entries (MVP empty), file
    # listing, file download.
    app.include_router(log_router)
    # Spec 013 — Backup management (T055): list + delete. The
    # "trigger backup" flow is served by the command bus
    # (POST /api/v3/command {"name": "Backup"}).
    app.include_router(backup_router)
    app.include_router(providers_router)
    app.include_router(field_priority_router)
    app.include_router(refresh_router)
    app.include_router(packs_router)
    app.include_router(platform_pack_platforms_router)
    app.include_router(applications_router)
    app.include_router(indexers_router)
    app.include_router(libraries_router)
    # Spec 009 T076 + T081 — manual scan triggers.
    app.include_router(scan_router)
    # Spec 009 T082 (slice 279) — read-only exporter catalog.
    app.include_router(exporters_router)
    # Spec 009 T079 + T083 — manual-import surface.
    app.include_router(manual_import_router)
    # Schema router goes before the {client_id} catch-all so /schema
    # doesn't get pattern-matched as an integer id.
    app.include_router(download_clients_schema_router)
    app.include_router(download_clients_router)
    app.include_router(quality_profile_router)
    app.include_router(region_profile_router)
    app.include_router(dump_profile_router)
    app.include_router(language_profile_router)
    app.include_router(naming_profile_router)
    app.include_router(custom_format_router)
    # Search subsystem (spec 007)
    app.include_router(search_router)
    app.include_router(search_grab_router)
    app.include_router(search_history_router)
    app.include_router(search_blocklist_router)
    # Importer subsystem (spec 008).
    app.include_router(importer_webhook_router)
    app.include_router(importer_history_router)
    app.include_router(importer_unidentified_router)
    # Spec 008 T088 — manual import + retry endpoints.
    app.include_router(importer_manual_router)
    # Notifications + health subsystem (spec 011). The webhook-
    # payloads doc router shares the /api/v3/notification prefix
    # with the CRUD router, so it goes before the catch-all
    # ``{notification_id}`` patterns to avoid pattern collision.
    app.include_router(webhook_payloads_md_router)
    app.include_router(notifications_router)
    app.include_router(notifications_health_router)
    # Tasks & Scheduler subsystem (spec 012). The runs router
    # shares the /api/v3/system/tasks prefix with the CRUD
    # router; mounting order doesn't matter for collision
    # because the run paths are deeper (``/{job_id}/runs*``).
    app.include_router(tasks_router)
    app.include_router(tasks_runs_router)
    app.include_router(tasks_command_router)

    # Spec 013 phase WS — /signalr/messages WebSocket route.
    # Registered after the REST routers so the OpenAPI
    # customisation that follows sees the full HTTP surface;
    # WebSocket routes don't appear in the OpenAPI doc.
    app.include_router(ws_router)

    # Spec 014 T009 — SPA static-file mount. Registered after
    # every router so router routes still take precedence;
    # only unmatched paths fall through to the SPA's catch-all
    # which returns ``index.html`` (React Router takes over
    # client-side). When ``spa_enabled`` is False (test
    # default) we keep the legacy JSON ``GET /`` smoke
    # response so the existing root-route assertions hold.
    spa_mounted = register_spa(
        app,
        enabled=settings.spa_enabled,
        dist_path=settings.spa_dist_path,
    )
    if not spa_mounted:

        @app.get("/", include_in_schema=False)
        async def _root() -> JSONResponse:
            return JSONResponse({"name": "romarr", "version": __version__})

    # Spec 013 phase OPENAPI — runs after every router has been
    # registered so the customizer sees the full route set.
    customize_openapi(app)

    return app
