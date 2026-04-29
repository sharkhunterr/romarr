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
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from romarr import __version__
from romarr.api.error_handlers import register_error_handlers
from romarr.api.routers.auth import router as auth_router
from romarr.api.routers.users import router as users_router
from romarr.db.session import create_engine, create_sessionmaker

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build the engine + sessionmaker on startup; dispose on shutdown.

    Stored on ``app.state`` so the dependency layer can pull them out
    without going through global singletons (which break test
    parallelism).
    """
    database_url = getattr(app.state, "_test_database_url", None)
    engine = create_engine(database_url) if database_url else create_engine()
    app.state.db_engine = engine
    app.state.db_sessionmaker = create_sessionmaker(engine)
    try:
        yield
    finally:
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

    @app.get("/", include_in_schema=False)
    async def _root() -> JSONResponse:
        return JSONResponse({"name": "romarr", "version": __version__})

    register_error_handlers(app)
    app.include_router(auth_router)
    app.include_router(users_router)
    return app
