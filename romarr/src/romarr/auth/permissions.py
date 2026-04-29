"""Permission guards — role + scope enforcement.

Two principal kinds reach the guards:

  1. A **session-authenticated user** — their ``role`` is checked
     against ``required_role`` via :func:`role_implies`.
  2. An **API-key-authenticated principal** — the key's ``scopes``
     are checked against the scope mapped from ``required_role``
     via :func:`role_to_required_scope` + :func:`scope_implies`.

Trusted-proxy auth is treated as a session (the proxy supplies the
username; the row's ``role`` controls access).

The guards return ``True`` / ``False`` rather than raising — the
upstream API layer lifts that to a 403 ``permission_denied`` per
FR-024.
"""

from __future__ import annotations

from dataclasses import dataclass

from romarr.auth.constants import (
    role_implies,
    role_to_required_scope,
    scope_implies,
)


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated caller's identity.

    ``user_id`` is the row id (or 0 for the system sentinel — never
    arrives via the auth chain in practice).

    ``role`` is the user's role text. ``api_key_scopes`` is the
    API-key scope list when authentication came via an API key;
    ``None`` for cookie/proxy authentication.
    """

    user_id: int
    username: str
    role: str
    api_key_scopes: list[str] | None = None

    @property
    def via_api_key(self) -> bool:
        return self.api_key_scopes is not None

    def has_role(self, required_role: str) -> bool:
        """Authorise based on the role hierarchy.

        For API-key principals, also check that the key's scopes
        include the scope mapped from ``required_role``. For session
        / proxy principals, the scope check is a no-op.
        """
        if not role_implies(self.role, required_role):
            return False

        if self.api_key_scopes is None:
            return True

        required_scope = role_to_required_scope(required_role)
        if required_scope is None:
            return False
        return scope_implies(self.api_key_scopes, required_scope)


def require_role(principal: Principal | None, required_role: str) -> bool:
    """Return ``True`` when the principal satisfies ``required_role``.

    Unauthenticated callers (``principal=None``) always fail closed.
    """
    if principal is None:
        return False
    return principal.has_role(required_role)
