"""ISO9660 header reader with platform-disambiguation cascade.

ISO9660 is the file-system used by **many** disc-based platforms —
Mega CD, Saturn, Dreamcast, PSX, PS2, original Xbox, GameCube
(sometimes), 3DO, Jaguar CD. When the operator drops an unknown
``.iso`` or ``.cue/.bin`` into a watch folder with no platform hint
in the path, the reader runs a cascade per spec 001 FR-024a (CL002):

  1. ``SYSTEM.CNF`` at the volume root → PSX or PS2.
     - The ``BOOT2 =`` line in ``SYSTEM.CNF`` distinguishes the two:
       a ``VER =`` line indicates PS2; ``cdrom0:\\SLPS_…`` /
       ``cdrom0:\\SLES_…`` shapes are PSX-typical.
  2. ``IP.BIN`` boot sector at LBA 0 with a recognisable system
     identifier string (``SEGA SEGASATURN``, ``SEGA MEGADRIVE``,
     ``SegaDiscSystem``, ``SEGA SEGAKATANA`` for Dreamcast) → Mega CD
     / Saturn / Dreamcast respectively.
  3. ``default.xbe`` at the volume root → original Xbox.
  4. None of the above → ``platform = unknown``; the dump is queued
     in ``unidentified_dump`` (FR-029) with the volume identifier and
     any extracted serial preserved.

The reader does NOT use the Primary Volume Descriptor's volume
identifier string for disambiguation (homebrew / unofficial discs
frequently lie there).

Implementation note: we use a **lightweight** ISO9660 reader that
parses the Primary Volume Descriptor at LBA 16 and walks the root
directory looking for the signature files. We avoid pulling in
``pycdlib`` for this MVP scope — the cascade only needs to find a
handful of known filenames and read a few bytes from LBA 0.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import BinaryIO

from romarr.identification.headers.base import (
    BaseHeaderReader,
    HeaderReadResult,
    HeaderReadStatus,
)

ISO_SECTOR_SIZE = 2048
"""ISO9660 logical sector size."""

# IP.BIN system-identifier signatures (first 16 bytes of the boot sector).
_IP_BIN_SIGNATURES: dict[bytes, str] = {
    b"SEGA SEGAKATANA": "dreamcast",
    b"SEGA SEGASATURN": "saturn",
    b"SEGA MEGADRIVE": "megacd",
    b"SegaDiscSystem": "megacd",
    b"SEGA TERA68K": "megacd",
}

# ISO9660 Primary Volume Descriptor offsets (relative to start of LBA 16).
_PVD_VOLUME_IDENTIFIER_OFFSET = 40
_PVD_VOLUME_IDENTIFIER_LEN = 32
_PVD_ROOT_DIR_RECORD_OFFSET = 156
_PVD_ROOT_DIR_RECORD_LEN = 34


class Iso9660Reader(BaseHeaderReader):
    """ISO9660 reader + platform disambiguation cascade."""

    # No fixed platform_slug — we disambiguate at read time per FR-024a.
    platform_slug = None

    def _read_path(self, path: Path) -> HeaderReadResult:
        with path.open("rb") as fh:
            # Step 1: peek IP.BIN at LBA 0 — Sega CD-based platforms put
            # the system identifier here, BEFORE the ISO9660 PVD which
            # they typically lack entirely. So check IP.BIN first.
            ip_platform = self._check_ip_bin(fh)
            if ip_platform is not None:
                fh.seek(0)
                ip_header = fh.read(64)
                return HeaderReadResult(
                    status=HeaderReadStatus.OK,
                    platform_slug=ip_platform,
                    confidence=0.85,
                    data={
                        "system_identifier": ip_header[:16]
                        .decode("ascii", errors="replace")
                        .strip(),
                        "detection_path": "ip_bin",
                    },
                )

            # Step 2: try to read the ISO9660 Primary Volume Descriptor.
            # If the file isn't ISO9660 at all we'll get UNRECOGNIZED.
            pvd_data = self._read_pvd(fh)
            if pvd_data is None:
                return HeaderReadResult(
                    status=HeaderReadStatus.UNRECOGNIZED,
                    confidence=0.0,
                    error_message=(
                        "no IP.BIN signature and no ISO9660 PVD found"
                    ),
                )

            volume_identifier, root_record = pvd_data

            # Step 3: walk the root directory for signature files.
            file_listing = self._list_root_files(fh, root_record)

            # SYSTEM.CNF → PSX or PS2 (further disambiguated)
            system_cnf_lba = file_listing.get("SYSTEM.CNF")
            if system_cnf_lba is not None:
                platform_slug, serial = self._classify_psx_ps2(fh, system_cnf_lba)
                return HeaderReadResult(
                    status=HeaderReadStatus.OK,
                    platform_slug=platform_slug,
                    confidence=0.9,
                    data={
                        "volume_identifier": volume_identifier,
                        "serial": serial or "",
                        "detection_path": "system_cnf",
                    },
                )

            # default.xbe → original Xbox
            if "default.xbe".upper() in {k.upper() for k in file_listing}:
                return HeaderReadResult(
                    status=HeaderReadStatus.OK,
                    platform_slug="xbox",
                    confidence=0.9,
                    data={
                        "volume_identifier": volume_identifier,
                        "detection_path": "default_xbe",
                    },
                )

            # No signature file → unknown platform but the disc is
            # legitimately ISO9660. Surface the volume identifier so
            # the operator has something to triage with.
            return HeaderReadResult(
                status=HeaderReadStatus.OK,
                platform_slug=None,
                confidence=0.3,
                data={
                    "volume_identifier": volume_identifier,
                    "detection_path": "iso9660_only",
                },
                error_message="no platform-signature file found at volume root",
            )

    # ------------------------------------------------------------------
    # IP.BIN check
    # ------------------------------------------------------------------

    @staticmethod
    def _check_ip_bin(fh: BinaryIO) -> str | None:
        """Read the first 64 bytes and look for an IP.BIN signature."""
        fh.seek(0)
        head = fh.read(64)
        if len(head) < 16:
            return None
        for sig, slug in _IP_BIN_SIGNATURES.items():
            if head[: len(sig)] == sig:
                return slug
        return None

    # ------------------------------------------------------------------
    # ISO9660 PVD
    # ------------------------------------------------------------------

    @staticmethod
    def _read_pvd(fh: BinaryIO) -> tuple[str, bytes] | None:
        """Read the Primary Volume Descriptor at LBA 16.

        Returns ``(volume_identifier, root_directory_record_bytes)`` or
        ``None`` if the file isn't valid ISO9660.
        """
        fh.seek(16 * ISO_SECTOR_SIZE)
        pvd = fh.read(ISO_SECTOR_SIZE)
        if len(pvd) < ISO_SECTOR_SIZE:
            return None
        # Type byte 0x01 + identifier b"CD001" + version byte 0x01.
        if not (pvd[0] == 0x01 and pvd[1:6] == b"CD001"):
            return None
        volume_identifier = (
            pvd[
                _PVD_VOLUME_IDENTIFIER_OFFSET : _PVD_VOLUME_IDENTIFIER_OFFSET
                + _PVD_VOLUME_IDENTIFIER_LEN
            ]
            .decode("ascii", errors="replace")
            .strip()
        )
        root_record = pvd[
            _PVD_ROOT_DIR_RECORD_OFFSET : _PVD_ROOT_DIR_RECORD_OFFSET
            + _PVD_ROOT_DIR_RECORD_LEN
        ]
        return volume_identifier, root_record

    @staticmethod
    def _list_root_files(
        fh: BinaryIO, root_record: bytes
    ) -> dict[str, int]:
        """Walk the root directory and return ``{filename: extent_lba}``."""
        # Root record fields: extent location at offset 2 (8 bytes
        # both-endian; we read the little-endian 32-bit value).
        if len(root_record) < 14:
            return {}
        root_lba = int.from_bytes(root_record[2:6], "little")
        # Root data length at offset 10 (8 bytes both-endian).
        root_len = int.from_bytes(root_record[10:14], "little")

        if root_lba == 0 or root_len == 0:
            return {}

        fh.seek(root_lba * ISO_SECTOR_SIZE)
        root_data = fh.read(root_len)

        files: dict[str, int] = {}
        offset = 0
        while offset < len(root_data):
            record_len = root_data[offset]
            if record_len == 0:
                # Padding to next sector — advance to next sector.
                offset = ((offset // ISO_SECTOR_SIZE) + 1) * ISO_SECTOR_SIZE
                continue
            extent_lba = int.from_bytes(root_data[offset + 2 : offset + 6], "little")
            name_len = root_data[offset + 32]
            name_bytes = root_data[offset + 33 : offset + 33 + name_len]
            name = name_bytes.decode("ascii", errors="replace")
            # Strip the trailing ";1" version suffix ISO9660 appends.
            if ";" in name:
                name = name.split(";", 1)[0]
            # Skip the . and .. directory entries (single-byte names).
            if name not in ("\x00", "\x01"):
                files[name] = extent_lba
            offset += record_len
        return files

    # ------------------------------------------------------------------
    # PSX / PS2 disambiguation
    # ------------------------------------------------------------------

    @staticmethod
    def _classify_psx_ps2(
        fh: BinaryIO, system_cnf_lba: int
    ) -> tuple[str, str | None]:
        """Read SYSTEM.CNF and pick PSX vs PS2.

        Returns ``(platform_slug, serial)``. The serial is extracted
        from the BOOT/BOOT2 line for both platforms.
        """
        fh.seek(system_cnf_lba * ISO_SECTOR_SIZE)
        # SYSTEM.CNF is short (a few hundred bytes); one sector is more
        # than enough.
        body = fh.read(ISO_SECTOR_SIZE).decode("ascii", errors="replace")

        # PS2 always carries a VER = line (e.g., "VER = 1.20"); PSX
        # never does. That's the cleanest signal.
        is_ps2 = "VER" in {
            line.split("=", 1)[0].strip().upper()
            for line in body.splitlines()
            if "=" in line
        }

        # Extract the serial from BOOT or BOOT2.
        serial: str | None = None
        boot_re = re.compile(
            r"BOOT2?\s*=\s*cdrom0:\\?([A-Z]+_\d{3}\.\d{2});?",
            re.IGNORECASE,
        )
        match = boot_re.search(body)
        if match is not None:
            serial = match.group(1).upper()

        return ("ps2" if is_ps2 else "psx"), serial
