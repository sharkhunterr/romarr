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
    register_gzip,
    register_idempotency,
)
from romarr.api.routers.auth import router as auth_router
from romarr.api.routers.calendar import router as calendar_router
from romarr.api.routers.queue import router as queue_router
from romarr.api.routers.status import router as system_status_router
from romarr.api.routers.tag import router as tag_router
from romarr.api.routers.users import router as users_router
from romarr.api.routers.wanted import router as wanted_router
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
    unidentified_router as importer_unidentified_router,
)
from romarr.importer.webhook import router as importer_webhook_router
from romarr.indexers.api import applications_router, indexers_router
from romarr.libraries.api import libraries_router
from romarr.metadata.api import (
    field_priority_router,
    providers_router,
    refresh_router,
)
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
    Tests that don't want a live scheduler (most of them) opt
    out by setting ``app.state._skip_scheduler = True`` before
    the lifespan starts.
    """
    database_url = getattr(app.state, "_test_database_url", None)
    engine = create_engine(database_url) if database_url else create_engine()
    app.state.db_engine = engine
    app.state.db_sessionmaker = create_sessionmaker(engine)

    # Spec 012 — start the Tasks subsystem when explicitly
    # enabled. Default OFF so the test suite (which builds
    # the app many times per session) doesn't pay the
    # SchedulerService bootstrap cost; production sets
    # ``app.state._enable_scheduler = True`` (or the
    # eventual ``ROMARR_SCHEDULER_ENABLED`` settings flag).
    enable_scheduler = getattr(
        app.state, "_enable_scheduler", False
    )
    scheduler = None
    if enable_scheduler:
        from romarr.tasks.execution.cancellation import CancellationRegistry
        from romarr.tasks.runner_protocol import build_default_registry
        from romarr.tasks.scheduler import SchedulerService

        cancellation_registry = CancellationRegistry()
        scheduler = SchedulerService(
            session_factory=app.state.db_sessionmaker,
            runners=build_default_registry(),
            cancellation_registry=cancellation_registry,
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

    try:
        yield
    finally:
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

    @app.get("/", include_in_schema=False)
    async def _root() -> JSONResponse:
        return JSONResponse({"name": "romarr", "version": __version__})

    # Spec 013 phase MW. Middleware order matters: Starlette runs the
    # last-registered middleware first, so GZip lands on the outermost
    # layer (it must see the final response bytes). CORS goes next,
    # ahead of the routers.
    settings = get_settings()
    register_gzip(app, min_size_bytes=settings.gzip_min_size_bytes)
    register_cors(app, allowed_origins=settings.cors_allowed_origins)
    # Idempotency-Key middleware (FR-020 / FR-025). Registered last
    # in the MW stack so it's nearest the routes — it intercepts
    # mutating methods after CORS has cleared the request, but
    # before the route handler runs the actual mutation.
    register_idempotency(app)

    register_error_handlers(app)
    app.include_router(auth_router)
    app.include_router(users_router)
    # Spec 013 — Sonarr-compat /api/v3/system/status (FR-031, US1).
    app.include_router(system_status_router)
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
    app.include_router(providers_router)
    app.include_router(field_priority_router)
    app.include_router(refresh_router)
    app.include_router(packs_router)
    app.include_router(platform_pack_platforms_router)
    app.include_router(applications_router)
    app.include_router(indexers_router)
    app.include_router(libraries_router)
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
    return app
