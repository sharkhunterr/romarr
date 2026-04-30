"""TLS verification helpers.

Resolves the ``ssl_cert_validation`` enum into the right value for
httpx's ``verify=`` kwarg. The tri-state is:

    enabled              -> verify=True   (default; production)
    disabled             -> verify=False  (operator opt-out; lab)
    disabled-for-local   -> verify=True for public hosts,
                            False for RFC1918 / loopback / link-local

The "for-local" mode lets operators run an internal qBit on
``192.168.1.10`` with a self-signed cert without globally weakening
the verifier for public seedboxes.
"""

from __future__ import annotations

import ipaddress
import socket
from typing import Literal

SslCertValidation = Literal["enabled", "disabled", "disabled-for-local"]


def is_local_host(host: str) -> bool:
    """Return True iff ``host`` resolves to an RFC1918, loopback, or
    link-local address (or is the literal ``localhost``).

    Resolution falls back to a simple name lookup when ``host`` is not
    already an IP literal. A failed lookup returns False — we err on
    the side of "treat as public" so the strict validator stays in
    effect when DNS is uncooperative.
    """
    if host == "localhost":
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # Not an IP literal — try a name lookup.
        try:
            resolved = socket.gethostbyname(host)
        except (OSError, socket.gaierror):
            return False
        try:
            ip = ipaddress.ip_address(resolved)
        except ValueError:  # pragma: no cover — gethostbyname returns valid IPs
            return False
    return bool(ip.is_private or ip.is_loopback or ip.is_link_local)


def build_httpx_verify(setting: SslCertValidation, host: str) -> bool:
    """Return the value to pass to httpx's ``verify=`` kwarg.

    Returns ``True`` (use the system trust store) or ``False`` (skip
    verification entirely). The "disabled-for-local" mode resolves
    to one or the other based on :func:`is_local_host`.
    """
    if setting == "enabled":
        return True
    if setting == "disabled":
        return False
    if setting == "disabled-for-local":
        return not is_local_host(host)
    raise ValueError(f"unknown ssl_cert_validation setting: {setting!r}")


__all__ = [
    "SslCertValidation",
    "build_httpx_verify",
    "is_local_host",
]
