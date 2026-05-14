"""Streaming parser for clrmamepro / ROMVault DAT files.

``clrmamepro`` is the second-most-common DAT serialisation after
Logiqx XML — the libretro / ``libretro-database`` mirror publishes
every No-Intro set in this dialect. Format::

    clrmamepro (
        name "Nintendo - Nintendo Entertainment System"
        description "..."
        version 20250101-123456
    )
    game (
        name "Super Mario Bros."
        description "Super Mario Bros."
        rom ( name "Super Mario Bros..nes" size 40976 crc abcd1234
              md5 ... sha1 ... )
    )

The grammar is paren-balanced atoms — strings are either bare
words or double-quoted. The parser yields the same
:class:`LogiqxRom` records the Logiqx parser emits so
:class:`DatManager` can dispatch on format without caring about
the source dialect downstream.
"""

from __future__ import annotations

from collections.abc import Iterator

from romarr.identification.dat.logiqx import LogiqxRom, _lower_hex


def _tokenise(text: str) -> Iterator[str]:
    """Yield ``(``, ``)``, or atom strings from a clrmamepro body."""
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if ch.isspace():
            i += 1
            continue
        if ch == "(":
            yield "("
            i += 1
            continue
        if ch == ")":
            yield ")"
            i += 1
            continue
        if ch == '"':
            # quoted string — ends at the next unescaped "
            start = i + 1
            i = start
            while i < n and text[i] != '"':
                if text[i] == "\\" and i + 1 < n:
                    i += 2
                    continue
                i += 1
            yield text[start:i]
            i += 1  # skip closing quote
            continue
        # bare atom — read up to whitespace / paren
        start = i
        while i < n and not text[i].isspace() and text[i] not in "()":
            i += 1
        yield text[start:i]


def _parse_kv_block(tokens: list[str]) -> dict[str, object]:
    """Consume ``( key value key value ... )`` and return a dict.

    Atoms appear as alternating key/value pairs. A nested block
    (``( ... )``) is stored under the preceding key — repeated
    keys (multiple ``rom`` entries inside one ``game``) are
    accumulated as a list. Unrecognised flag-style atoms (no
    following value) are silently skipped — clrmamepro emits
    ``flags baddump`` and similar markers we don't model.
    """
    assert tokens.pop(0) == "("
    out: dict[str, object] = {}
    while tokens:
        tok = tokens.pop(0)
        if tok == ")":
            return out
        if not tokens:
            break
        nxt = tokens[0]
        if nxt == "(":
            value: object = _parse_kv_block(tokens)
        elif nxt == ")":
            continue
        else:
            tokens.pop(0)
            value = nxt
        existing = out.get(tok)
        if existing is None:
            out[tok] = value
        elif isinstance(existing, list):
            existing.append(value)
        else:
            out[tok] = [existing, value]
    return out


def parse_clrmamepro(source: bytes) -> Iterator[LogiqxRom]:
    """Stream ``rom`` rows out of a clrmamepro DAT body.

    Only ``game (...)`` and ``machine (...)`` blocks are emitted; the
    leading ``clrmamepro (...)`` header and any other top-level
    blocks are skipped. Yields one :class:`LogiqxRom` per ``rom``
    element so the caller can stream them into a bulk insert
    without buffering the whole DAT.
    """
    text = source.decode("utf-8", errors="replace")
    tokens: list[str] = list(_tokenise(text))

    while tokens:
        block_kind = tokens.pop(0)
        if not tokens or tokens[0] != "(":
            # malformed — bail rather than hard-fail; surfaces as
            # a no-op rather than a crash for callers.
            return
        block = _parse_kv_block(tokens)
        if block_kind not in ("game", "machine"):
            continue

        game_name = str(block.get("name", "")).strip()
        description = block.get("description")
        description_str: str | None = (
            str(description).strip() if isinstance(description, str) else None
        )

        rom_field = block.get("rom")
        roms: list[dict[str, object]]
        if isinstance(rom_field, dict):
            roms = [rom_field]
        elif isinstance(rom_field, list):
            roms = [r for r in rom_field if isinstance(r, dict)]
        else:
            continue

        for rom in roms:
            size_val = rom.get("size")
            try:
                size_bytes = int(size_val) if size_val is not None else None
            except (TypeError, ValueError):
                size_bytes = None
            crc = rom.get("crc")
            md5 = rom.get("md5")
            sha1 = rom.get("sha1")
            yield LogiqxRom(
                parent_game_name=game_name,
                rom_name=str(rom.get("name", "")).strip(),
                size_bytes=size_bytes,
                crc32=_lower_hex(crc) if isinstance(crc, str) else None,
                md5=_lower_hex(md5) if isinstance(md5, str) else None,
                sha1=_lower_hex(sha1) if isinstance(sha1, str) else None,
                description=description_str,
            )
