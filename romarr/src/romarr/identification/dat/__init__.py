"""DAT manager — ingest and look up Logiqx XML DAT entries.

Public surface:

- :class:`DatManager` — async ingestion + per-platform lookups.
- :func:`parse_logiqx` — streaming Logiqx XML parser (used by DatManager).
"""

from romarr.identification.dat.logiqx import LogiqxRom, parse_logiqx
from romarr.identification.dat.manager import DatManager

__all__ = ["DatManager", "LogiqxRom", "parse_logiqx"]
