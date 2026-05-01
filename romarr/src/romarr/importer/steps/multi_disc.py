"""Multi-disc / multi-side set detection (FR-017, FR-018, FR-019).

Pure-function detector. Given a list of file paths the orchestrator
discovered together (one extracted folder, one Sonarr-style import
batch), return a :class:`MultiDiscGroup` if the set forms a
multi-disc CD/DVD release or a multi-side floppy/cartridge release,
or ``None`` if it's a single-member collection.

Detection signals (in priority order):

  1. ``cue_bin`` — every ``.cue`` file is matched to its referenced
     ``.bin`` via the cue parser. A set of ≥2 cue/bin pairs is a
     multi-disc release. The orchestrator hashes the ``.bin``
     file (FR-019).
  2. ``filename_pattern`` — files whose stems share a common prefix
     and end with ``(Disc N)`` / ``(CD N)`` / ``(Disk N)``.
  3. ``side_a_b`` — floppy / Atari-style multi-side releases
     ending with ``(Side A)`` / ``(Side B)``.

The detector is **pure**: no I/O beyond reading ``.cue`` text. The
orchestrator dispatches it inside the EXTRACT slice's working
directory.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


_DETECTION = Literal["cue_bin", "filename_pattern", "side_a_b"]


@dataclass(frozen=True)
class DiscMember:
    """One disc / side within a multi-disc set.

    ``files`` carries every file that constitutes the member (the
    ``.cue`` + ``.bin`` for CD images; the single ROM file for
    cartridges and floppies). ``primary_file`` is the canonical
    bytestream the orchestrator hashes — the ``.bin`` for cue/bin
    pairs, the only file otherwise.
    """

    disc_number: int
    files: tuple[Path, ...]
    primary_file: Path


@dataclass(frozen=True)
class MultiDiscGroup:
    """Detected multi-disc release. Discs are sorted by
    ``disc_number`` ascending; the parent disc is index 0
    (``disc_number=1``)."""

    members: tuple[DiscMember, ...]
    detection_signal: _DETECTION


# ---------------------------------------------------------------------------
# Cue parser


_CUE_FILE_LINE = re.compile(
    r'^\s*FILE\s+"(?P<name>[^"]+)"\s+(?P<format>BINARY|MOTOROLA|AIFF|WAVE|MP3)',
    re.IGNORECASE | re.MULTILINE,
)


def parse_cue_referenced_files(cue_path: Path) -> list[str]:
    """Return the bare filenames listed in ``FILE "..." BINARY``
    directives inside ``cue_path``. Returns an empty list when the
    file isn't a cue or carries no FILE entries.

    Pure: reads one file off disk, never writes."""
    try:
        text = cue_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return [m.group("name") for m in _CUE_FILE_LINE.finditer(text)]


# ---------------------------------------------------------------------------
# Pattern parsers


_DISC_PATTERNS = [
    re.compile(r"\((?:Disc|CD|Disk)\s+(?P<n>\d+)(?:\s+of\s+\d+)?\)", re.IGNORECASE),
    re.compile(r"\bDisc[\s_-]+(?P<n>\d+)\b", re.IGNORECASE),
]
_SIDE_PATTERN = re.compile(r"\(Side\s+(?P<letter>[A-Z])\)", re.IGNORECASE)


def _match_disc_number(name: str) -> int | None:
    """Return the disc number embedded in a filename stem, if any."""
    for pattern in _DISC_PATTERNS:
        match = pattern.search(name)
        if match:
            return int(match.group("n"))
    return None


def _match_side_letter(name: str) -> int | None:
    """Map ``(Side A)``/``(Side B)`` to a 1-based disc number."""
    match = _SIDE_PATTERN.search(name)
    if match is None:
        return None
    letter = match.group("letter").upper()
    if not ("A" <= letter <= "Z"):
        return None
    return ord(letter) - ord("A") + 1


def _strip_disc_suffix(name: str) -> str:
    """Remove ``(Disc N)`` / ``(Side A)`` etc. so two members of the
    same release share the same prefix when grouped."""
    out = name
    for pattern in _DISC_PATTERNS:
        out = pattern.sub("", out)
    out = _SIDE_PATTERN.sub("", out)
    return re.sub(r"\s+", " ", out).strip()


# ---------------------------------------------------------------------------
# Detector


def detect_multi_disc(files: Sequence[Path]) -> MultiDiscGroup | None:
    """Return a :class:`MultiDiscGroup` if ``files`` forms a
    multi-disc / multi-side set; ``None`` otherwise.

    Detection priority: cue/bin > filename pattern > side A/B.
    Detection requires ≥ 2 distinct disc/side numbers — a single
    file ending with ``(Disc 1)`` returns ``None``; the
    orchestrator imports it as a single-disc release.
    """
    paths = list(files)
    if len(paths) < 2:
        return None

    # 1. cue/bin
    cue_group = _detect_cue_bin(paths)
    if cue_group is not None:
        return cue_group

    # 2. filename pattern (Disc N / CD N / Disk N)
    disc_group = _detect_filename_pattern(paths)
    if disc_group is not None:
        return disc_group

    # 3. side A/B floppy
    side_group = _detect_side_letters(paths)
    if side_group is not None:
        return side_group

    return None


def _detect_cue_bin(paths: list[Path]) -> MultiDiscGroup | None:
    cues = [p for p in paths if p.suffix.lower() == ".cue"]
    if len(cues) < 2:
        return None

    members: list[DiscMember] = []
    by_name = {p.name.lower(): p for p in paths}

    for cue in cues:
        disc_num = _match_disc_number(cue.stem)
        if disc_num is None:
            return None  # cue without a recognisable number — bail

        referenced = parse_cue_referenced_files(cue)
        if not referenced:
            return None

        # Resolve the .bin path relative to the cue, prefer the
        # caller's input list so we keep its canonical Path
        # representation.
        bin_path: Path | None = None
        for ref in referenced:
            candidate_lower = ref.lower()
            if candidate_lower in by_name:
                bin_path = by_name[candidate_lower]
                break
            sibling = cue.parent / ref
            if sibling in paths:
                bin_path = sibling
                break
        if bin_path is None:
            return None

        members.append(
            DiscMember(
                disc_number=disc_num,
                files=tuple(sorted({cue, bin_path})),
                primary_file=bin_path,
            )
        )

    if len({m.disc_number for m in members}) < 2:
        return None

    members.sort(key=lambda m: m.disc_number)
    return MultiDiscGroup(members=tuple(members), detection_signal="cue_bin")


def _detect_filename_pattern(paths: list[Path]) -> MultiDiscGroup | None:
    candidates: dict[str, list[tuple[int, Path]]] = {}
    for p in paths:
        n = _match_disc_number(p.stem)
        if n is None:
            continue
        prefix = _strip_disc_suffix(p.stem)
        candidates.setdefault(prefix, []).append((n, p))

    # Take the largest grouping with ≥ 2 distinct disc numbers.
    best: tuple[str, list[tuple[int, Path]]] | None = None
    for prefix, items in candidates.items():
        unique = {n for n, _ in items}
        if len(unique) < 2:
            continue
        if best is None or len(items) > len(best[1]):
            best = (prefix, items)
    if best is None:
        return None

    items = sorted(best[1], key=lambda pair: pair[0])
    members = tuple(
        DiscMember(disc_number=n, files=(p,), primary_file=p) for n, p in items
    )
    return MultiDiscGroup(members=members, detection_signal="filename_pattern")


def _detect_side_letters(paths: list[Path]) -> MultiDiscGroup | None:
    candidates: list[tuple[int, Path]] = []
    for p in paths:
        n = _match_side_letter(p.stem)
        if n is not None:
            candidates.append((n, p))
    if len({n for n, _ in candidates}) < 2:
        return None
    candidates.sort(key=lambda pair: pair[0])
    members = tuple(
        DiscMember(disc_number=n, files=(p,), primary_file=p)
        for n, p in candidates
    )
    return MultiDiscGroup(members=members, detection_signal="side_a_b")


__all__ = [
    "DiscMember",
    "MultiDiscGroup",
    "detect_multi_disc",
    "parse_cue_referenced_files",
]
