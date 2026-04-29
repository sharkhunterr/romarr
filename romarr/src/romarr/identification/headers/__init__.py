"""Header readers — the safety net when filenames are useless (FR-024).

Three concrete readers ship with the foundation:
- :class:`InesReader` — NES (.nes / .unif) iNES 16-byte header
- :class:`MegaDriveReader` — Mega Drive system identifier at $0100
- :class:`Iso9660Reader` — generic disc image with platform cascade
  (FR-024a / spec 001 Q2): SYSTEM.CNF → PSX/PS2; IP.BIN → Sega CD systems;
  default.xbe → Xbox

Stub readers exist for FR-025 platforms (3DS, NDS, PSP, Vita, Switch,
Wii, GameCube, GBA) — they accept the format but raise a clear "not yet
supported" error so the upstream identifier can route around them.
"""

from romarr.identification.headers.base import (
    BaseHeaderReader,
    HeaderReadResult,
    HeaderReadStatus,
    UnsupportedPlatformError,
)
from romarr.identification.headers.ines import InesReader
from romarr.identification.headers.iso9660 import Iso9660Reader
from romarr.identification.headers.megadrive import MegaDriveReader

__all__ = [
    "BaseHeaderReader",
    "HeaderReadResult",
    "HeaderReadStatus",
    "InesReader",
    "Iso9660Reader",
    "MegaDriveReader",
    "UnsupportedPlatformError",
]
