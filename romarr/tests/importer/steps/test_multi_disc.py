"""Multi-disc detection tests (T047-T051)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from romarr.importer.steps.multi_disc import (
    detect_multi_disc,
    parse_cue_referenced_files,
)

# ---------------------------------------------------------------------------
# Fixture helper
# ---------------------------------------------------------------------------


@pytest.fixture
def make_cue_pair(tmp_path: Path) -> Callable[[str, str], tuple[Path, Path]]:
    """Materialise a (cue, bin) pair in tmp_path.

    Returns the absolute paths so the detector resolves the
    ``FILE "..." BINARY`` line back to a real Path."""

    def _make(stem: str, bin_filename: str) -> tuple[Path, Path]:
        bin_path = tmp_path / bin_filename
        bin_path.write_bytes(b"\x00" * 32)
        cue_path = tmp_path / f"{stem}.cue"
        cue_path.write_text(
            f'FILE "{bin_filename}" BINARY\n'
            f"  TRACK 01 MODE2/2352\n"
            f"    INDEX 01 00:00:00\n"
        )
        return cue_path, bin_path

    return _make


# ---------------------------------------------------------------------------
# T047 — cue/bin parent + child
# ---------------------------------------------------------------------------


def test_cue_bin_parent_child(
    make_cue_pair: Callable[[str, str], tuple[Path, Path]],
) -> None:
    cue1, bin1 = make_cue_pair(
        "Final Fantasy IX (USA) (Disc 1)",
        "Final Fantasy IX (USA) (Disc 1).bin",
    )
    cue2, bin2 = make_cue_pair(
        "Final Fantasy IX (USA) (Disc 2)",
        "Final Fantasy IX (USA) (Disc 2).bin",
    )

    group = detect_multi_disc([cue1, bin1, cue2, bin2])
    assert group is not None
    assert group.detection_signal == "cue_bin"
    assert len(group.members) == 2
    assert [m.disc_number for m in group.members] == [1, 2]
    # Each member ships both files; primary_file is the .bin.
    for member in group.members:
        assert member.primary_file.suffix == ".bin"
        assert len(member.files) == 2


# ---------------------------------------------------------------------------
# T048 — filename pattern (Disc N) without cue/bin
# ---------------------------------------------------------------------------


def test_filename_pattern_disc_n(tmp_path: Path) -> None:
    paths = [
        tmp_path / "Game (Disc 1).iso",
        tmp_path / "Game (Disc 2).iso",
        tmp_path / "Game (Disc 3).iso",
    ]
    for p in paths:
        p.write_bytes(b"\x00")

    group = detect_multi_disc(paths)
    assert group is not None
    assert group.detection_signal == "filename_pattern"
    assert [m.disc_number for m in group.members] == [1, 2, 3]


def test_filename_pattern_single_disc_returns_none(tmp_path: Path) -> None:
    """A single ``(Disc 1)`` file with no siblings is just a single
    disc — the detector returns None and the orchestrator imports
    it as a regular release."""
    p = tmp_path / "Game (Disc 1).iso"
    p.write_bytes(b"\x00")
    assert detect_multi_disc([p]) is None


# ---------------------------------------------------------------------------
# T049 — Side A/B floppy
# ---------------------------------------------------------------------------


def test_side_a_b_floppy(tmp_path: Path) -> None:
    paths = [
        tmp_path / "Title (Side A).adf",
        tmp_path / "Title (Side B).adf",
    ]
    for p in paths:
        p.write_bytes(b"\x00")

    group = detect_multi_disc(paths)
    assert group is not None
    assert group.detection_signal == "side_a_b"
    assert [m.disc_number for m in group.members] == [1, 2]


# ---------------------------------------------------------------------------
# T050 — hash the .bin not the .cue
# ---------------------------------------------------------------------------


def test_hash_the_bin_not_the_cue(
    make_cue_pair: Callable[[str, str], tuple[Path, Path]],
) -> None:
    cue1, bin1 = make_cue_pair(
        "Game (Disc 1)", "Game (Disc 1).bin"
    )
    cue2, bin2 = make_cue_pair(
        "Game (Disc 2)", "Game (Disc 2).bin"
    )
    group = detect_multi_disc([cue1, bin1, cue2, bin2])
    assert group is not None
    for member in group.members:
        assert member.primary_file == (
            bin1 if member.disc_number == 1 else bin2
        )


# ---------------------------------------------------------------------------
# Cue parser
# ---------------------------------------------------------------------------


def test_parse_cue_extracts_referenced_files(
    make_cue_pair: Callable[[str, str], tuple[Path, Path]],
) -> None:
    cue, _bin = make_cue_pair("Game", "Game.bin")
    files = parse_cue_referenced_files(cue)
    assert files == ["Game.bin"]


def test_parse_cue_handles_missing_file_gracefully(tmp_path: Path) -> None:
    missing = tmp_path / "missing.cue"
    assert parse_cue_referenced_files(missing) == []


def test_parse_cue_with_multiple_tracks(tmp_path: Path) -> None:
    cue = tmp_path / "Game.cue"
    cue.write_text(
        'FILE "Game (Track 01).bin" BINARY\n'
        "  TRACK 01 MODE2/2352\n"
        "    INDEX 01 00:00:00\n"
        'FILE "Game (Track 02).bin" BINARY\n'
        "  TRACK 02 AUDIO\n"
        "    INDEX 01 00:00:00\n"
    )
    files = parse_cue_referenced_files(cue)
    assert files == ["Game (Track 01).bin", "Game (Track 02).bin"]


# ---------------------------------------------------------------------------
# Edge: mixed signals, irrelevant files
# ---------------------------------------------------------------------------


def test_irrelevant_files_dont_trigger_detection(tmp_path: Path) -> None:
    """A folder of unrelated ROMs returns None."""
    paths = [tmp_path / f"rom-{i}.md" for i in range(5)]
    for p in paths:
        p.write_bytes(b"\x00")
    assert detect_multi_disc(paths) is None


# ---------------------------------------------------------------------------
# T051 — property test: random disc layouts never produce invalid trees
# ---------------------------------------------------------------------------


_disc_filename = st.builds(
    lambda title, n, ext: f"{title} (Disc {n}).{ext}",
    title=st.sampled_from(["GameA", "GameB", "GameC", "Quest", "Saga"]),
    n=st.integers(min_value=1, max_value=4),
    ext=st.sampled_from(["iso", "bin", "img"]),
)
_random_filename = st.builds(
    lambda stem, ext: f"{stem}.{ext}",
    stem=st.text(
        alphabet=st.characters(
            min_codepoint=0x41,
            max_codepoint=0x7A,
            blacklist_categories=("Cs",),
        ),
        min_size=1,
        max_size=12,
    ).filter(lambda s: "Disc" not in s and "Side" not in s),
    ext=st.sampled_from(["zip", "7z", "txt"]),
)


@given(
    filenames=st.lists(
        st.one_of(_disc_filename, _random_filename),
        min_size=0,
        max_size=10,
    ),
)
@settings(
    max_examples=200,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=None,
)
def test_property_random_disc_layouts_never_produce_invalid_trees(
    tmp_path: Path,
    filenames: list[str],
) -> None:
    """Hypothesis: random combinations of disc-style and unrelated
    filenames never produce a tree that violates the invariants:
    members are sorted by disc_number and disc numbers are unique
    (no duplicate disc 1)."""
    paths: list[Path] = []
    for name in filenames:
        path = tmp_path / name
        if path.exists():
            continue
        path.write_bytes(b"\x00")
        paths.append(path)

    group = detect_multi_disc(paths)
    if group is None:
        return

    disc_numbers = [m.disc_number for m in group.members]
    assert disc_numbers == sorted(disc_numbers)
    assert len(set(disc_numbers)) == len(disc_numbers)
    assert len(group.members) >= 2
