"""Spec 013 phase FACTORY — canonical application factory module.

The actual implementation lives in :mod:`romarr.api.app` under the
existing :func:`create_app` name. This module re-exports it under
the spec-canonical path so tests, docs, and future imports can
use ``from romarr.api.factory import create_app`` without churn
across the existing call sites.

The factory:

  * builds the FastAPI app with the project title / version /
    description and the canonical /api/v3 docs URLs;
  * registers the global error handlers;
  * mounts every prior spec's routers (auth, metadata, indexers,
    download clients, libraries, profiles, search, importer,
    notifications, tasks);
  * wires the spec 012 Tasks subsystem onto ``app.state`` via
    :class:`SchedulerService` + :class:`CancellationRegistry`
    when ``app.state._enable_scheduler = True`` is set before the
    lifespan starts (default OFF so the test suite doesn't pay
    the bootstrap cost on every app build);
  * runs the four-phase :func:`graceful_shutdown` protocol on
    lifespan exit (FR-021).

Forward-looking phases (MW middleware, ROUTERS bridge endpoints,
WS handler, OPENAPI customiser) extend this factory in place
rather than introducing a parallel module.
"""

from __future__ import annotations

from romarr.api.app import create_app

__all__ = ["create_app"]
