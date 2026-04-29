"""Hasher tests — FR-014 / FR-015 / FR-016 / SC-002."""

from __future__ import annotations

import hashlib
import zlib
from io import BytesIO
from typing import TYPE_CHECKING

import pytest

from romarr.identification.hasher import Hasher, hash_file

if TYPE_CHECKING:
    from pathlib import Path


def _expected(data: bytes) -> dict[str, str]:
    return {
        "crc32": f"{zlib.crc32(data) & 0xFFFFFFFF:08x}",
        "md5": hashlib.md5(data, usedforsecurity=False).hexdigest(),
        "sha1": hashlib.sha1(data, usedforsecurity=False).hexdigest(),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def test_hasher_empty_stream_produces_known_hashes() -> None:
    """Empty input produces the canonical empty-string digests."""
    expected = _expected(b"")
    result = Hasher().hash_stream(BytesIO(b""))
    assert result.crc32 == expected["crc32"]
    assert result.md5 == expected["md5"]
    assert result.sha1 == expected["sha1"]
    assert result.sha256 is None  # disabled by default
    assert result.size_bytes == 0


def test_hasher_short_stream_matches_python_stdlib() -> None:
    payload = b"Sonic the Hedgehog (USA).md\n"
    expected = _expected(payload)
    result = Hasher().hash_stream(BytesIO(payload))
    assert result.crc32 == expected["crc32"]
    assert result.md5 == expected["md5"]
    assert result.sha1 == expected["sha1"]
    assert result.size_bytes == len(payload)


def test_hasher_chunks_correctly_across_buffer_boundary() -> None:
    """A buffer smaller than the payload exercises the streaming loop."""
    payload = b"x" * (4096 * 3 + 17)  # 3 full buffers + a tail
    expected = _expected(payload)
    result = Hasher(buffer_size=4096).hash_stream(BytesIO(payload))
    assert result.sha1 == expected["sha1"]
    assert result.md5 == expected["md5"]
    assert result.crc32 == expected["crc32"]
    assert result.size_bytes == len(payload)


def test_hasher_optional_sha256_when_enabled() -> None:
    payload = b"abc123"
    result = Hasher(compute_sha256=True).hash_stream(BytesIO(payload))
    assert result.sha256 == _expected(payload)["sha256"]


def test_hasher_single_pass_consumes_stream_fully() -> None:
    """After hashing the stream is at EOF (no further reads possible)."""
    payload = b"hello world"
    stream = BytesIO(payload)
    Hasher().hash_stream(stream)
    assert stream.read() == b""


def test_hasher_invalid_buffer_size_raises() -> None:
    with pytest.raises(ValueError):
        Hasher(buffer_size=0)
    with pytest.raises(ValueError):
        Hasher(buffer_size=-1)


def test_hasher_text_mode_stream_rejected() -> None:
    """The hasher is binary-only; text-mode streams blow up clearly."""
    from io import StringIO

    with pytest.raises(AssertionError, match="binary-mode"):
        Hasher().hash_stream(StringIO("not binary"))


def test_hasher_handles_one_megabyte_payload() -> None:
    """1 MiB completes well under the 10 s ceiling for 1 GiB (SC-002)."""
    import time

    payload = b"R" * (1 << 20)
    start = time.monotonic()
    result = Hasher().hash_stream(BytesIO(payload))
    elapsed = time.monotonic() - start

    assert result.size_bytes == len(payload)
    assert result.sha1 == _expected(payload)["sha1"]
    # 1 MiB should take well under 1 s; this is just a sanity check.
    assert elapsed < 1.0, f"hashing 1 MiB took {elapsed:.3f}s"


def test_hash_path_reads_real_file(tmp_path: Path) -> None:
    payload = b"Final Fantasy IX (USA) (Disc 1).bin sample bytes\n"
    path = tmp_path / "ff9.bin"
    path.write_bytes(payload)

    result = Hasher().hash_path(path)
    expected = _expected(payload)
    assert result.sha1 == expected["sha1"]
    assert result.size_bytes == len(payload)


@pytest.mark.asyncio
async def test_hash_file_runs_off_event_loop(tmp_path: Path) -> None:
    """``hash_file`` is the async-friendly entry point per FR-016."""
    payload = b"Mega Drive header bytes ... " * 32
    path = tmp_path / "rom.md"
    path.write_bytes(payload)

    result = await hash_file(path, compute_sha256=True)
    expected = _expected(payload)
    assert result.sha1 == expected["sha1"]
    assert result.sha256 == expected["sha256"]
    assert result.size_bytes == len(payload)


def test_hash_result_as_dict_round_trips_all_fields() -> None:
    payload = b"abc"
    result = Hasher(compute_sha256=True).hash_stream(BytesIO(payload))
    d = result.as_dict()
    assert set(d) == {"crc32", "md5", "sha1", "sha256", "size_bytes"}
    assert d["size_bytes"] == 3
