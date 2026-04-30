"""Connectivity tester (Phase 6).

``test_connectivity(client) -> ConnectivityTestResult`` runs the
two-step probe documented in spec 004 FR-006 / FR-006a:

  1. ``t=caps`` — must succeed; failure → result.ok = False with the
     auth/protocol/connectivity category that fired.
  2. If caps advertises a search type as ``available=yes``, also run
     a minimal ``t=search&q=test`` to confirm the search path works
     end-to-end.

The function never raises — it always returns a structured result so
the API layer can render it directly without a try/except.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

from romarr.indexers.errors import (
    CircuitOpenError,
    IndexerAuthError,
    IndexerProtocolError,
)

if TYPE_CHECKING:
    from romarr.indexers.client import NewznabClient


class ConnectivityTestResult(BaseModel):
    """Outcome of a single connectivity probe."""

    model_config = ConfigDict(extra="forbid")

    ok: bool
    caps_ok: bool
    search_ok: bool | None  # None when caps doesn't advertise search
    server: str | None = None
    category: (
        Literal["auth", "protocol", "connectivity", "circuit_open", "ok"]
        | None
    ) = None
    message: str | None = None


async def test_connectivity(
    client: NewznabClient,
) -> ConnectivityTestResult:
    """Probe ``client`` for caps + (conditionally) search."""
    caps = None
    try:
        caps = await client.caps()
    except IndexerAuthError as exc:
        return ConnectivityTestResult(
            ok=False,
            caps_ok=False,
            search_ok=None,
            category="auth",
            message=str(exc),
        )
    except CircuitOpenError as exc:
        return ConnectivityTestResult(
            ok=False,
            caps_ok=False,
            search_ok=None,
            category="circuit_open",
            message=str(exc),
        )
    except IndexerProtocolError as exc:
        return ConnectivityTestResult(
            ok=False,
            caps_ok=False,
            search_ok=None,
            category="protocol",
            message=str(exc),
        )

    advertises_search = bool(
        caps.searching.get("search", {}).get("available")
    )
    if not advertises_search:
        # Caps OK but the indexer doesn't advertise search; the
        # connectivity tester reports partial success so the operator
        # UI can ask them to enable search manually (FR-006).
        return ConnectivityTestResult(
            ok=True,
            caps_ok=True,
            search_ok=None,
            server=caps.server,
            category="ok",
            message=(
                "caps reachable but search is not advertised; "
                "operator-side configuration may be needed"
            ),
        )

    try:
        await client.search("test", categories=None)
    except IndexerAuthError as exc:
        return ConnectivityTestResult(
            ok=False,
            caps_ok=True,
            search_ok=False,
            server=caps.server,
            category="auth",
            message=str(exc),
        )
    except CircuitOpenError as exc:
        return ConnectivityTestResult(
            ok=False,
            caps_ok=True,
            search_ok=False,
            server=caps.server,
            category="circuit_open",
            message=str(exc),
        )
    except IndexerProtocolError as exc:
        return ConnectivityTestResult(
            ok=False,
            caps_ok=True,
            search_ok=False,
            server=caps.server,
            category="protocol",
            message=str(exc),
        )

    return ConnectivityTestResult(
        ok=True,
        caps_ok=True,
        search_ok=True,
        server=caps.server,
        category="ok",
    )


__all__ = ["ConnectivityTestResult", "test_connectivity"]
