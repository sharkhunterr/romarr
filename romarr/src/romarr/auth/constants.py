"""Role + scope vocabulary for spec 010.

Per the clarified FR-001 / FR-002 / FR-003 (CL — drop is_superuser):
the only role-storage column is ``user.role``, taking one of three
values; ``admin > user > readonly`` defines implication.

Per the clarified FR-009a (Q2 — coarse 3-tier scopes): API keys
carry a JSON array whose values are a subset of
``{"read", "write", "admin"}``. Endpoint guards map
``@require_role(...)`` onto the matching scope:

  - ``readonly`` → ``read``
  - ``user``     → ``write``
  - ``admin``    → ``admin``

Higher scopes imply lower (an admin-scoped key passes a read guard).
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"
    READONLY = "readonly"


# Plain string aliases for use cases where StrEnum's repr noise would
# clutter logs / API responses (the JSON shape uses raw strings).
ROLE_ADMIN: str = Role.ADMIN.value
ROLE_USER: str = Role.USER.value
ROLE_READONLY: str = Role.READONLY.value


class Scope(StrEnum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


SCOPE_READ: str = Scope.READ.value
SCOPE_WRITE: str = Scope.WRITE.value
SCOPE_ADMIN: str = Scope.ADMIN.value


# Implication ranks — lower number = higher privilege.
_ROLE_RANK: dict[str, int] = {
    ROLE_ADMIN: 0,
    ROLE_USER: 1,
    ROLE_READONLY: 2,
}

_SCOPE_RANK: dict[str, int] = {
    SCOPE_ADMIN: 0,
    SCOPE_WRITE: 1,
    SCOPE_READ: 2,
}


def role_implies(holder_role: str, required_role: str) -> bool:
    """Return ``True`` when ``holder_role`` satisfies ``required_role``.

    ``admin`` implies ``user`` implies ``readonly``. Unknown roles
    always fail closed (no implication).
    """
    held = _ROLE_RANK.get(holder_role)
    needed = _ROLE_RANK.get(required_role)
    if held is None or needed is None:
        return False
    return held <= needed


def scope_implies(holder_scopes: list[str], required_scope: str) -> bool:
    """Return ``True`` when any of ``holder_scopes`` satisfies the requirement.

    A holder with ``admin`` scope passes ``write`` and ``read`` guards.
    A holder with ``write`` passes ``read``. Unknown scopes are
    ignored.
    """
    needed = _SCOPE_RANK.get(required_scope)
    if needed is None:
        return False
    return any(
        _SCOPE_RANK.get(s, 999) <= needed for s in holder_scopes
    )


def role_to_required_scope(required_role: str) -> str | None:
    """Map an endpoint's required role onto the scope an API key must hold.

    Per spec 010 FR-009a:
      - ``readonly`` → ``read``
      - ``user``     → ``write``
      - ``admin``    → ``admin``

    Returns ``None`` for unknown roles (fail-closed at the guard layer).
    """
    return {
        ROLE_READONLY: SCOPE_READ,
        ROLE_USER: SCOPE_WRITE,
        ROLE_ADMIN: SCOPE_ADMIN,
    }.get(required_role)
