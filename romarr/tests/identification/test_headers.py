"""Header reader tests — iNES, Mega Drive, ISO9660 cascade, stubs."""

from __future__ import annotations

from pathlib import Path

import pytest

from romarr.identification.headers import (
    HeaderReadStatus,
    InesReader,
    Iso9660Reader,
    MegaDriveReader,
    UnsupportedPlatformError,
)
from romarr.identification.headers.ines import INES_MAGIC
from romarr.identification.headers.iso9660 import ISO_SECTOR_SIZE
from romarr.identification.headers.stubs import StubReader

# ---------------------------------------------------------------------------
# iNES
# ---------------------------------------------------------------------------


def test_ines_reads_magic_and_mapper(tmp_path: Path) -> None:
    """A synthetic 16-byte iNES header with mapper 0x12 round-trips."""
    # Mapper 0x12 → flags6 = 0x20 (high nibble), flags7 = 0x10
    header = INES_MAGIC + bytes([2, 1, 0x20, 0x10]) + b"\x00" * 8
    payload = header + b"\xff" * 32
    rom = tmp_path / "fixture.nes"
    rom.write_bytes(payload)

    result = InesReader().read(rom)
    assert result.status == HeaderReadStatus.OK
    assert result.platform_slug == "nes"
    assert result.data["mapper"] == 0x12
    assert result.data["prg_size_bytes"] == 2 * 16384
    assert result.data["chr_size_bytes"] == 1 * 8192
    assert result.confidence > 0.9


def test_ines_rejects_non_nes(tmp_path: Path) -> None:
    rom = tmp_path / "garbage.nes"
    rom.write_bytes(b"NOPE" + b"\x00" * 12)
    result = InesReader().read(rom)
    assert result.status == HeaderReadStatus.UNRECOGNIZED


def test_ines_short_file(tmp_path: Path) -> None:
    rom = tmp_path / "short.nes"
    rom.write_bytes(b"NES")  # truncated
    result = InesReader().read(rom)
    assert result.status == HeaderReadStatus.UNRECOGNIZED


# ---------------------------------------------------------------------------
# Mega Drive
# ---------------------------------------------------------------------------


def _mega_drive_rom(
    *,
    sys_id: bytes = b"SEGA MEGA DRIVE ",
    serial: bytes = b"GM MK-1051 -01",
    region_block: bytes = b"JUE          ",
) -> bytes:
    """Build a synthetic 512-byte Mega Drive header."""
    rom = bytearray(512)
    # 0x00..0xFF — vector table (left as zeros for the test).
    # 0x100..0x10F — system identifier
    rom[0x100 : 0x100 + 16] = sys_id.ljust(16)[:16]
    # 0x110..0x11F — copyright string
    rom[0x110 : 0x110 + 16] = b"(C)SEGA 1991.JUL".ljust(16)[:16]
    # 0x120..0x14F — domestic title
    rom[0x120 : 0x120 + 48] = b"SONIC THE HEDGEHOG".ljust(48)[:48]
    # 0x150..0x17F — international title
    rom[0x150 : 0x150 + 48] = b"SONIC THE HEDGEHOG".ljust(48)[:48]
    # 0x180..0x18D — serial
    rom[0x180 : 0x180 + len(serial)] = serial
    # 0x1F0..0x1FE — region block (relative offset 0xF0..0xFF inside header)
    rom[0x1F0 : 0x1F0 + len(region_block)] = region_block
    return bytes(rom)


def test_mega_drive_reads_jue_regions(tmp_path: Path) -> None:
    rom = tmp_path / "sonic.md"
    rom.write_bytes(_mega_drive_rom())
    result = MegaDriveReader().read(rom)
    assert result.status == HeaderReadStatus.OK
    assert result.platform_slug == "megadrive"
    assert "JP" in result.data["regions"]
    assert "US" in result.data["regions"]
    assert "EU" in result.data["regions"]
    assert "MK-1051" in str(result.data.get("serial", ""))


def test_mega_drive_rejects_non_sega(tmp_path: Path) -> None:
    rom = tmp_path / "garbage.md"
    rom.write_bytes(_mega_drive_rom(sys_id=b"NINTENDO ROM!"))
    result = MegaDriveReader().read(rom)
    assert result.status == HeaderReadStatus.UNRECOGNIZED


def test_mega_drive_short_file(tmp_path: Path) -> None:
    rom = tmp_path / "short.md"
    rom.write_bytes(b"\x00" * 100)
    result = MegaDriveReader().read(rom)
    assert result.status == HeaderReadStatus.UNRECOGNIZED


# ---------------------------------------------------------------------------
# ISO9660 cascade
# ---------------------------------------------------------------------------


def _iso_with_signature_file(
    tmp_path: Path,
    *,
    filename: str,
    file_body: bytes = b"",
    ip_bin_signature: bytes = b"",
) -> Path:
    """Build a minimal valid ISO9660 image with one file at the root.

    Layout:
      LBA 0  : (optional) IP.BIN sector — bytes 0..15 carry the signature
      LBA 16 : Primary Volume Descriptor
      LBA 17 : Root directory (one record for ``filename``)
      LBA 18+: file body
    """
    n_sectors = 32
    image = bytearray(n_sectors * ISO_SECTOR_SIZE)

    # IP.BIN at LBA 0 (when caller provides a signature)
    if ip_bin_signature:
        image[0 : len(ip_bin_signature)] = ip_bin_signature

    # PVD at LBA 16
    pvd = bytearray(ISO_SECTOR_SIZE)
    pvd[0] = 0x01  # type: PVD
    pvd[1:6] = b"CD001"
    pvd[6] = 0x01  # version
    # Volume identifier (offset 40, 32 bytes, padded with spaces)
    vol_id = b"TEST_VOLUME".ljust(32)[:32]
    pvd[40 : 40 + 32] = vol_id
    # Root directory record (offset 156, 34 bytes)
    root_record = bytearray(34)
    root_record[0] = 34  # length of record
    # Root extent location at offset 2 (8 bytes both-endian) — LBA 17
    root_record[2:6] = (17).to_bytes(4, "little")
    root_record[6:10] = (17).to_bytes(4, "big")
    # Root data length at offset 10 — one sector
    root_record[10:14] = ISO_SECTOR_SIZE.to_bytes(4, "little")
    root_record[14:18] = ISO_SECTOR_SIZE.to_bytes(4, "big")
    # File flags at offset 25 = 2 (directory)
    root_record[25] = 2
    # Name length + name (single-byte ``\x00``)
    root_record[32] = 1
    root_record[33] = 0
    pvd[156 : 156 + 34] = root_record
    image[16 * ISO_SECTOR_SIZE : 17 * ISO_SECTOR_SIZE] = pvd

    # Root directory at LBA 17 — one entry pointing at the file at LBA 18
    root_dir = bytearray()
    name_bytes = (filename + ";1").encode("ascii")
    record_len = 33 + len(name_bytes)
    if record_len % 2 == 1:
        record_len += 1  # ISO9660 requires even-length records
    rec = bytearray(record_len)
    rec[0] = record_len
    rec[2:6] = (18).to_bytes(4, "little")
    rec[6:10] = (18).to_bytes(4, "big")
    rec[10:14] = max(len(file_body), 1).to_bytes(4, "little")
    rec[14:18] = max(len(file_body), 1).to_bytes(4, "big")
    rec[32] = len(name_bytes)
    rec[33 : 33 + len(name_bytes)] = name_bytes
    root_dir.extend(rec)
    image[17 * ISO_SECTOR_SIZE : 17 * ISO_SECTOR_SIZE + len(root_dir)] = root_dir

    # File body at LBA 18
    if file_body:
        image[18 * ISO_SECTOR_SIZE : 18 * ISO_SECTOR_SIZE + len(file_body)] = file_body

    iso_path = tmp_path / "test.iso"
    iso_path.write_bytes(bytes(image))
    return iso_path


def test_iso9660_psx_via_system_cnf(tmp_path: Path) -> None:
    body = b"BOOT2 = cdrom0:\\SLPS_001.41;1\nVMODE = NTSC\n"
    iso = _iso_with_signature_file(tmp_path, filename="SYSTEM.CNF", file_body=body)
    result = Iso9660Reader().read(iso)
    assert result.status == HeaderReadStatus.OK
    assert result.platform_slug == "psx"
    assert result.data["serial"] == "SLPS_001.41"
    assert result.data["detection_path"] == "system_cnf"


def test_iso9660_ps2_via_system_cnf_with_ver(tmp_path: Path) -> None:
    body = b"BOOT2 = cdrom0:\\SLES_500.00;1\nVER = 1.20\nVMODE = PAL\n"
    iso = _iso_with_signature_file(tmp_path, filename="SYSTEM.CNF", file_body=body)
    result = Iso9660Reader().read(iso)
    assert result.status == HeaderReadStatus.OK
    assert result.platform_slug == "ps2"
    assert result.data["serial"] == "SLES_500.00"


def test_iso9660_xbox_via_default_xbe(tmp_path: Path) -> None:
    iso = _iso_with_signature_file(
        tmp_path, filename="default.xbe", file_body=b"XBE\x00binarycontent"
    )
    result = Iso9660Reader().read(iso)
    assert result.status == HeaderReadStatus.OK
    assert result.platform_slug == "xbox"


def test_iso9660_dreamcast_via_ip_bin(tmp_path: Path) -> None:
    """IP.BIN signature wins even when the disc lacks a normal ISO9660 PVD."""
    iso = _iso_with_signature_file(
        tmp_path,
        filename="GAMEFILE.BIN",
        ip_bin_signature=b"SEGA SEGAKATANA ",
    )
    result = Iso9660Reader().read(iso)
    assert result.status == HeaderReadStatus.OK
    assert result.platform_slug == "dreamcast"
    assert result.data["detection_path"] == "ip_bin"


def test_iso9660_saturn_via_ip_bin(tmp_path: Path) -> None:
    iso = _iso_with_signature_file(
        tmp_path,
        filename="GAMEFILE.BIN",
        ip_bin_signature=b"SEGA SEGASATURN ",
    )
    result = Iso9660Reader().read(iso)
    assert result.platform_slug == "saturn"


def test_iso9660_unknown_iso_returns_low_confidence(tmp_path: Path) -> None:
    """A valid ISO9660 with no signature file → unknown platform."""
    iso = _iso_with_signature_file(tmp_path, filename="GAMEFILE.BIN")
    result = Iso9660Reader().read(iso)
    assert result.status == HeaderReadStatus.OK
    assert result.platform_slug is None
    assert result.confidence < 0.5
    assert result.data["detection_path"] == "iso9660_only"


def test_iso9660_not_an_iso_at_all(tmp_path: Path) -> None:
    not_iso = tmp_path / "garbage.iso"
    not_iso.write_bytes(b"\x00" * (32 * ISO_SECTOR_SIZE))
    result = Iso9660Reader().read(not_iso)
    assert result.status == HeaderReadStatus.UNRECOGNIZED


# ---------------------------------------------------------------------------
# Stub readers (FR-025)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "slug",
    ["3ds", "nds", "psp", "vita", "switch", "wii", "gamecube", "gba"],
)
def test_stub_reader_raises_unsupported(tmp_path: Path, slug: str) -> None:
    reader = StubReader(slug)
    fake_rom = tmp_path / f"{slug}.bin"
    fake_rom.write_bytes(b"\x00" * 16)
    with pytest.raises(UnsupportedPlatformError):
        reader.read(fake_rom)


def test_stub_reader_rejects_unknown_slug() -> None:
    with pytest.raises(ValueError):
        StubReader("not-a-real-platform")
