"""Dispatcher corpus-recall test (spec 001 T049 / SC-003).

Loads the four convention-specific corpora at
``tests/fixtures/filenames/`` and asserts the dispatcher picks the
correct convention for ≥ 95% of entries (SC-003 success criterion).

Each corpus file is JSONL — one JSON record per line, ``#``-prefixed
comments and blank lines ignored. Each record carries the
canonical-form fields:

    filename     : str
    regions      : list[str]    (ISO codes, sorted alphabetically)
    languages    : list[str]    (ISO-639-1 codes, sorted alphabetically)
    revision     : str | None
    dump_status  : str          (DumpStatus enum value)
    tags         : list[str]

The recall test checks the dispatched convention only — the per-field
extraction is exercised by the parser-specific tests
(``test_no_intro_parser.py``, ``test_parsers.py``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from romarr.domain.enums import NamingConvention
from romarr.identification.parsers import default_dispatcher

_FIXTURES_ROOT = Path(__file__).resolve().parents[2] / "fixtures" / "filenames"

_RECALL_THRESHOLD = 0.95
"""SC-003 minimum recall across the combined corpus."""


def _load_corpus(name: str) -> list[dict[str, Any]]:
    """Load a JSONL corpus file. Lines starting with ``#`` are ignored."""
    path = _FIXTURES_ROOT / name
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, raw in enumerate(fh, start=1):
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                msg = f"{name}:{line_no}: invalid JSON: {exc}"
                raise AssertionError(msg) from exc
    return records


_CORPUS_FILES: dict[NamingConvention, str] = {
    NamingConvention.NO_INTRO: "nointro_corpus.txt",
    NamingConvention.GOODTOOLS: "goodtools_corpus.txt",
    NamingConvention.TOSEC: "tosec_corpus.txt",
    NamingConvention.SCENE: "scene_corpus.txt",
}


def test_corpus_recall() -> None:
    """SC-003: dispatcher picks the right convention ≥ 95% of the time.

    The corpora are intentionally small (≈ 30-50 entries each, ≈ 150
    total) but cover the canonical patterns plus the prevalent
    edge cases. The success bar is on the *combined* corpus —
    individual conventions are reported alongside for diagnostics.
    """
    dispatcher = default_dispatcher()
    total = 0
    correct = 0
    per_convention: dict[NamingConvention, tuple[int, int]] = {}

    for convention, corpus_name in _CORPUS_FILES.items():
        records = _load_corpus(corpus_name)
        c_total = len(records)
        c_correct = 0

        for rec in records:
            filename = rec["filename"]
            parsed = dispatcher.parse(filename)
            if parsed.convention is convention:
                c_correct += 1

        per_convention[convention] = (c_correct, c_total)
        total += c_total
        correct += c_correct

    assert total > 0, "no corpus entries were loaded — fixtures missing?"
    recall = correct / total

    diagnostics = "\n".join(
        f"  {conv.name}: {c}/{t} ({(c / t) if t else 0:.1%})"
        for conv, (c, t) in sorted(per_convention.items())
    )
    assert recall >= _RECALL_THRESHOLD, (
        f"corpus recall {recall:.2%} < {_RECALL_THRESHOLD:.0%} "
        f"(SC-003)\n{diagnostics}"
    )


@pytest.mark.parametrize(
    "convention,corpus_name",
    list(_CORPUS_FILES.items()),
    ids=lambda v: v.name if hasattr(v, "name") else str(v),
)
def test_each_corpus_loads_and_parses(
    convention: NamingConvention, corpus_name: str
) -> None:
    """Every corpus entry is well-formed JSONL and produces a non-empty title."""
    dispatcher = default_dispatcher()
    records = _load_corpus(corpus_name)
    assert records, f"{corpus_name} is empty"

    for rec in records:
        filename = rec["filename"]
        parsed = dispatcher.parse(filename)
        # Every entry parses to *some* title (even when convention
        # detection misses, the dispatcher still surfaces a fallback
        # ParsedFilename with title set to the stem).
        assert parsed.title, f"{corpus_name}: {filename!r} produced empty title"
