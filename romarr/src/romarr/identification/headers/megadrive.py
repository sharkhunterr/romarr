"""Mega Drive header reader.

The Mega Drive (Genesis) ROM header sits at offset 0x100 (256 bytes
into the file) and contains a fixed-layout block:

    0x100-0x10F: System name (e.g., "SEGA MEGA DRIVE ", "SEGA GENESIS   ")
    0x110-0x11F: Copyright string (publisher + date)
    0x120-0x14F: Domestic title
    0x150-0x17F: International title
    0x180-0x18D: Serial number (e.g., "GM MK-1051 -01")
    0x18E-0x18F: Checksum
    0x1F0-0x1FE: Region tag bytes (J/U/E in any order)

The reader extracts the in-cart serial, the international title, and
the region byte(s). Spec 001 User Story 3 directly tests this.
"""

from __future__ import annotations

from pathlib import Path

from romarr.identification.headers.base import (
    BaseHeaderReader,
    HeaderReadResult,
    HeaderReadStatus,
)

# Bytes 0-3 of the header at offset 0x100 should match one of these.
_SYSTEM_PREFIXES = (
    b"SEGA MEGA DRIVE",
    b"SEGA GENESIS",
    b"SEGA MEGADRIVE",
    b"SEGA MEGA DRIV",  # truncated
    b"SEGA",
)

# Region byte → ISO codes (Edge Case: a single dump may carry multiple
# region letters; we collect each into a sorted tuple of ISO codes).
_REGION_LETTER_TO_ISO: dict[str, str] = {
    "J": "JP",
    "U": "US",
    "E": "EU",
    "F": "FR",
    "8": "EU",  # 8-bit Europe (rare)
    "4": "US",  # NTSC USA (rare)
    "1": "JP",  # NTSC Japan (rare)
    "5": "JP",  # NTSC Japan (rare)
    "A": "AU",
}


class MegaDriveReader(BaseHeaderReader):
    """Read the Mega Drive 256-byte header at offset 0x100."""

    platform_slug = "megadrive"

    def _read_path(self, path: Path) -> HeaderReadResult:
        with path.open("rb") as fh:
            fh.seek(0x100)
            header = fh.read(0x100)

        if len(header) < 0x100:
            return HeaderReadResult(
                status=HeaderReadStatus.UNRECOGNIZED,
                confidence=0.0,
                error_message="file too short for Mega Drive header (need 512 bytes)",
            )

        # System identifier in the first 16 bytes of the header.
        sys_id = header[0:0x10]
        if not any(sys_id.startswith(p) for p in _SYSTEM_PREFIXES):
            return HeaderReadResult(
                status=HeaderReadStatus.UNRECOGNIZED,
                confidence=0.0,
                error_message=f"system identifier did not match Mega Drive prefixes ({sys_id!r})",
            )

        copyright_str = header[0x10:0x20].decode("ascii", errors="replace").strip()
        domestic_title = header[0x20:0x50].decode("ascii", errors="replace").strip()
        international_title = header[0x50:0x80].decode("ascii", errors="replace").strip()
        serial = header[0x80:0x8E].decode("ascii", errors="replace").strip()

        # Region bytes at 0x1F0-0x1F2 typically; we read the whole tail
        # range and pick out recognised letters.
        region_bytes = header[0xF0:0xFF].decode("ascii", errors="replace")
        regions: list[str] = []
        for letter in region_bytes:
            iso = _REGION_LETTER_TO_ISO.get(letter)
            if iso is not None and iso not in regions:
                regions.append(iso)

        return HeaderReadResult(
            status=HeaderReadStatus.OK,
            platform_slug="megadrive",
            confidence=0.9,
            data={
                "system_identifier": sys_id.decode("ascii", errors="replace").strip(),
                "copyright": copyright_str,
                "domestic_title": domestic_title,
                "international_title": international_title,
                "serial": serial,
                "regions": ",".join(sorted(regions)),
            },
        )
