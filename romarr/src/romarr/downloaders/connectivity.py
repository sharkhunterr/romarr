"""Connectivity-test orchestrator (T023).

Runs each implementation's ``test_connection`` + ``ensure_category``
through a uniform try/except funnel and returns a flat
:class:`ConnectivityTestResult`. The UI never has to introspect a
typed exception — every failure mode round-trips through the same
``error_code`` literal envelope (FR-008 / SC-006).

Warnings (e.g., the SAB-without-romarr-category case) are
non-blocking — the result is still ``ok=True`` but carries a
:class:`ConnectivityWarning` so the operator knows to act (FR-011).
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from romarr.downloaders.errors import (
    AuthError,
    CategoryWarning,
    DownloaderError,
    TLSError,
    VersionError,
)
from romarr.downloaders.errors import (
    ConnectionError as DownloaderConnError,
)
from romarr.downloaders.types import ConnectivityTestResult, ConnectivityWarning

if TYPE_CHECKING:
    from romarr.downloaders.base import DownloadClient


async def test_connectivity(impl: DownloadClient) -> ConnectivityTestResult:
    """Probe ``impl`` and return a flat result.

    Order matters: TLS / connection errors are checked before auth
    because auth depends on a successful TLS handshake; checking auth
    first would mask the TLS root cause.
    """
    try:
        version = await impl.test_connection()
    except TLSError as exc:
        return ConnectivityTestResult(
            ok=False, error_code="tls", error_message=str(exc)
        )
    except DownloaderConnError as exc:
        return ConnectivityTestResult(
            ok=False, error_code="connection", error_message=str(exc)
        )
    except AuthError as exc:
        return ConnectivityTestResult(
            ok=False, error_code="auth", error_message=str(exc)
        )
    except VersionError as exc:
        return ConnectivityTestResult(
            ok=False, error_code="version", error_message=str(exc)
        )
    except DownloaderError as exc:
        return ConnectivityTestResult(
            ok=False, error_code="internal", error_message=str(exc)
        )

    warnings: list[ConnectivityWarning] = []
    with contextlib.suppress(NotImplementedError):
        try:
            await impl.ensure_category()
        except CategoryWarning as exc:
            warnings.append(
                ConnectivityWarning(
                    code="category_missing", message=str(exc)
                )
            )
        # Connection / auth errors here would already have surfaced
        # in test_connection; if they show up now, propagate them as
        # internal errors so the operator sees something rather than
        # nothing.
        except DownloaderError as exc:  # pragma: no cover — defensive
            return ConnectivityTestResult(
                ok=False,
                error_code="internal",
                error_message=f"category check failed: {exc}",
            )

    return ConnectivityTestResult(
        ok=True, client_version=version, warnings=warnings
    )


__all__ = ["test_connectivity"]
