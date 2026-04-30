"""Library Management & Exporters subsystem (spec 009).

A *library* is the operator-facing concept of "where my ROMs live
and how they're organised". Multi-library is supported from MVP:
each library carries its own root path, its own five profiles
(Quality / Region / Dump / Language / Naming), its own optional
platform allowlist, and its own downstream exporter set
(RomM / ES-DE / Pegasus / LaunchBox).

Slice 1 ships SCAF + PERS — module skeleton, errors, value types,
SQLAlchemy 2.0 models for the ``library`` table and the
``library_platform`` m2m, Pydantic ``Read/Create/Update`` schemas
with cross-field validators, and Alembic migration ``0009`` that
also closes the forward-reference FKs deferred by specs 005 / 006
/ 008.

The router, heartbeat loop, full + incremental scanners, four
exporters, manual-import flow, and admin API land in subsequent
slices.
"""

from romarr.libraries.disk_space import check_min_disk_free
from romarr.libraries.errors import (
    DiskFullError,
    ExporterError,
    LibraryError,
    LibraryUnavailable,
    NoEligibleLibrary,
    PathUnwritable,
)
from romarr.libraries.routing import route_to_library
from romarr.libraries.types import (
    ExporterOutcome,
    LibrarySnapshot,
    LibraryStatus,
    LifecyclePolicy,
    RoutingChoice,
    ScanProgress,
)

__all__ = [
    "DiskFullError",
    "ExporterError",
    "ExporterOutcome",
    "LibraryError",
    "LibrarySnapshot",
    "LibraryStatus",
    "LibraryUnavailable",
    "LifecyclePolicy",
    "NoEligibleLibrary",
    "PathUnwritable",
    "RoutingChoice",
    "ScanProgress",
    "check_min_disk_free",
    "route_to_library",
]
