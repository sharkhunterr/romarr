"""Deluge class-metadata tests.

The previous stub tests (T041) asserted ``available=False`` and that
every method raised ``NotImplementedError('deferred to v1')``. Deluge
was fully implemented against Deluge 2.x's WebUI JSON-RPC in the
0.15.x series; this file keeps a slim metadata smoke test now that
the stub is gone. End-to-end behaviour is covered by the integration
tests hitting a real Deluge container.
"""

from __future__ import annotations

from romarr.downloaders.implementations.deluge import DelugeClient
from romarr.downloaders.types import ClientType


def test_class_metadata() -> None:
    assert DelugeClient.client_type is ClientType.DELUGE
    assert DelugeClient.supports_torrents is True
    assert DelugeClient.supports_usenet is False
    assert DelugeClient.available is True


def test_constructor_requires_credentials() -> None:
    """The real implementation refuses to build without host / port /
    password — no silent stub fallback."""
    import pytest

    with pytest.raises(TypeError):
        DelugeClient(client_id=1, name="broken")  # type: ignore[call-arg]
