"""iNES header reader.

The iNES format prefixes a 16-byte header to NES ROMs:

    Bytes 0-3: ASCII "NES\\x1A" magic (4E 45 53 1A)
    Byte 4   : PRG-ROM size in 16 KiB units
    Byte 5   : CHR-ROM size in 8 KiB units
    Byte 6   : Mapper low nibble + flags
    Byte 7   : Mapper high nibble + iNES 2.0 marker
    Bytes 8+ : reserved / iNES 2.0 fields

The reader extracts mapper number, PRG / CHR sizes, and reports
``platform_slug = "nes"`` on a magic match. Spec 001 FR-024 / FR-025.
"""

from __future__ import annotations

from pathlib import Path

from romarr.identification.headers.base import (
    BaseHeaderReader,
    HeaderReadResult,
    HeaderReadStatus,
)

INES_MAGIC = b"NES\x1A"


class InesReader(BaseHeaderReader):
    """Read iNES 1.0 / 2.0 headers."""

    platform_slug = "nes"

    def _read_path(self, path: Path) -> HeaderReadResult:
        with path.open("rb") as fh:
            header = fh.read(16)

        if len(header) < 16 or header[:4] != INES_MAGIC:
            return HeaderReadResult(
                status=HeaderReadStatus.UNRECOGNIZED,
                confidence=0.0,
                error_message="iNES magic not found at offset 0",
            )

        prg_units = header[4]
        chr_units = header[5]
        flags6 = header[6]
        flags7 = header[7]
        mapper_low = (flags6 >> 4) & 0x0F
        mapper_high = (flags7 >> 4) & 0x0F
        mapper = (mapper_high << 4) | mapper_low

        # iNES 2.0 marker is bits 2-3 of flags7 == 0b10
        is_ines2 = (flags7 & 0x0C) == 0x08

        return HeaderReadResult(
            status=HeaderReadStatus.OK,
            platform_slug="nes",
            confidence=0.95,
            data={
                "mapper": mapper,
                "prg_size_bytes": prg_units * 16384,
                "chr_size_bytes": chr_units * 8192,
                "ines_version": 2 if is_ines2 else 1,
            },
        )
