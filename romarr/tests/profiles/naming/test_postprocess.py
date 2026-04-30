"""Post-processing tests (T037-T039)."""

from __future__ import annotations

import pytest

from romarr.profiles.naming.postprocess import (
    collapse_whitespace,
    drop_empty_bracketed_groups,
    postprocess,
    replace_illegal_chars,
)

# ---------------------------------------------------------------------------
# T037 — collapse whitespace
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a  b", "a b"),
        ("a   b", "a b"),
        ("a    b   c", "a b c"),
        ("  Sonic  ", "Sonic"),
        ("Sonic\tthe\nHedgehog", "Sonic the Hedgehog"),
    ],
)
def test_collapse_whitespace(raw: str, expected: str) -> None:
    assert collapse_whitespace(raw) == expected


# ---------------------------------------------------------------------------
# T038 — drop empty bracketed groups
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Sonic ()", "Sonic"),
        ("Sonic ( )", "Sonic"),
        ("Sonic []", "Sonic"),
        ("Sonic [ ]", "Sonic"),
        ("Sonic () (USA)", "Sonic (USA)"),
        ("Sonic () [] (USA)", "Sonic (USA)"),
    ],
)
def test_drop_empty_bracketed_groups(raw: str, expected: str) -> None:
    # collapse_whitespace not applied here — test the dropper alone,
    # then the orchestrator applies whitespace cleanup.
    intermediate = drop_empty_bracketed_groups(raw)
    assert collapse_whitespace(intermediate) == expected


def test_nested_empty_groups_collapse() -> None:
    """``( () )`` collapses through iterative passes."""
    assert collapse_whitespace(drop_empty_bracketed_groups("Sonic ( () )")) == "Sonic"


# ---------------------------------------------------------------------------
# T039 — replace illegal chars
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "illegal",
    [":", "*", "?", '"', "<", ">", "|", "\\"],
)
def test_each_illegal_char_replaced(illegal: str) -> None:
    raw = f"Sonic{illegal}Bad"
    assert replace_illegal_chars(raw) == "Sonic_Bad"


def test_path_separator_preserved() -> None:
    """``/`` is intentionally NOT illegal — it carries semantic meaning
    when a profile produces a subfolder (e.g., ``Platform.Slug/Game.Title``)."""
    assert replace_illegal_chars("megadrive/Sonic") == "megadrive/Sonic"


def test_per_component_illegal_replacement() -> None:
    """Each path component is treated independently."""
    assert (
        replace_illegal_chars("megadrive/Sonic:Bad/Title?")
        == "megadrive/Sonic_Bad/Title_"
    )


# ---------------------------------------------------------------------------
# postprocess(): full pipeline
# ---------------------------------------------------------------------------


def test_postprocess_full_pipeline() -> None:
    raw = "Sonic the Hedgehog (USA) ()  ( )  [ ].md"
    assert postprocess(raw, replace_illegal=True) == "Sonic the Hedgehog (USA).md"


def test_postprocess_no_illegal_replace() -> None:
    """When the operator opts out, illegal chars survive."""
    raw = "Sonic:Bad () ()"
    assert postprocess(raw, replace_illegal=False) == "Sonic:Bad"


def test_postprocess_idempotent() -> None:
    """A pre-cleaned string survives a second pass unchanged."""
    once = postprocess("Sonic ()", replace_illegal=True)
    twice = postprocess(once, replace_illegal=True)
    assert once == twice
