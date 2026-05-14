"""Domain layer — the foundational data model.

Spec 001-foundation declares nine tables:
- ``platform``, ``platform_format``, ``platform_naming_token``
- ``game``, ``release``, ``dump``
- ``dat_entry``, ``unidentified_dump``, ``platform_pack``

Plus their enums (``DumpStatus``, ``NamingConvention``).

This package provides the SQLAlchemy 2.0 ``DeclarativeBase`` plus all nine
ORM models. Pydantic schemas (Read / Create / Update) live in ``schemas``.
"""

from romarr.domain.base import Base
from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.domain.models import (
    DatEntry,
    DatSource,
    Dump,
    Game,
    Platform,
    PlatformFormat,
    PlatformNamingToken,
    PlatformPack,
    Release,
    RomPack,
    RomPackItem,
    UnidentifiedDump,
)

__all__ = [
    "Base",
    "DatEntry",
    "DatSource",
    "Dump",
    "DumpStatus",
    "Game",
    "NamingConvention",
    "Platform",
    "PlatformFormat",
    "PlatformNamingToken",
    "PlatformPack",
    "Release",
    "RomPack",
    "RomPackItem",
    "UnidentifiedDump",
]
