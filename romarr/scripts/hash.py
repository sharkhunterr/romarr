#!/usr/bin/env python3
"""Hash one or more files with Romarr's streaming hasher.

Used for ad-hoc DAT-match queries from the command line. Output is
one line per file: ``<sha1>  <crc32>  <md5>  <size>  <path>``.

Usage:
    python scripts/hash.py rom1.md rom2.iso
"""

from __future__ import annotations

import sys
from pathlib import Path

from romarr.identification.hasher import Hasher


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python scripts/hash.py <file> [<file> ...]", file=sys.stderr)
        return 2

    hasher = Hasher()
    rc = 0
    for arg in argv:
        path = Path(arg)
        if not path.is_file():
            print(f"not a file: {arg}", file=sys.stderr)
            rc = 1
            continue
        try:
            result = hasher.hash_path(path)
        except OSError as exc:
            print(f"failed to hash {arg}: {exc}", file=sys.stderr)
            rc = 1
            continue
        print(f"{result.sha1}  {result.crc32}  {result.md5}  {result.size_bytes}  {arg}")
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
