"""Role + scope vocabulary tests."""

from __future__ import annotations

import pytest

from romarr.auth import (
    ROLE_ADMIN,
    ROLE_READONLY,
    ROLE_USER,
    SCOPE_ADMIN,
    SCOPE_READ,
    SCOPE_WRITE,
    role_implies,
    scope_implies,
)
from romarr.auth.constants import role_to_required_scope


@pytest.mark.parametrize(
    ("holder", "required", "expected"),
    [
        (ROLE_ADMIN, ROLE_READONLY, True),
        (ROLE_ADMIN, ROLE_USER, True),
        (ROLE_ADMIN, ROLE_ADMIN, True),
        (ROLE_USER, ROLE_READONLY, True),
        (ROLE_USER, ROLE_USER, True),
        (ROLE_USER, ROLE_ADMIN, False),
        (ROLE_READONLY, ROLE_READONLY, True),
        (ROLE_READONLY, ROLE_USER, False),
        (ROLE_READONLY, ROLE_ADMIN, False),
        ("garbage", ROLE_READONLY, False),
        (ROLE_ADMIN, "garbage", False),
    ],
)
def test_role_implies(holder: str, required: str, expected: bool) -> None:
    assert role_implies(holder, required) is expected


@pytest.mark.parametrize(
    ("holder_scopes", "required", "expected"),
    [
        ([SCOPE_ADMIN], SCOPE_READ, True),
        ([SCOPE_ADMIN], SCOPE_WRITE, True),
        ([SCOPE_ADMIN], SCOPE_ADMIN, True),
        ([SCOPE_WRITE], SCOPE_READ, True),
        ([SCOPE_WRITE], SCOPE_WRITE, True),
        ([SCOPE_WRITE], SCOPE_ADMIN, False),
        ([SCOPE_READ], SCOPE_READ, True),
        ([SCOPE_READ], SCOPE_WRITE, False),
        ([SCOPE_READ], SCOPE_ADMIN, False),
        ([SCOPE_READ, SCOPE_WRITE], SCOPE_WRITE, True),
        (["nonsense"], SCOPE_READ, False),
        ([], SCOPE_READ, False),
    ],
)
def test_scope_implies(
    holder_scopes: list[str], required: str, expected: bool
) -> None:
    assert scope_implies(holder_scopes, required) is expected


def test_role_to_required_scope_mapping() -> None:
    assert role_to_required_scope(ROLE_READONLY) == SCOPE_READ
    assert role_to_required_scope(ROLE_USER) == SCOPE_WRITE
    assert role_to_required_scope(ROLE_ADMIN) == SCOPE_ADMIN
    assert role_to_required_scope("garbage") is None
