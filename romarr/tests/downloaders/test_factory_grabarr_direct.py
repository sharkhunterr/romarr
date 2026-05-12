"""Factory branch for ``ClientType.GRABARR_DIRECT`` — slice 424.

Unit-level: builds a fake :class:`DownloadClient` row in memory and
asserts ``build_client_from_row`` produces a fully-configured
:class:`GrabarrDirectClient`. The Fernet encryption layer is
exercised by the api_key round-trip — we encrypt the test key with
the production helper so this also covers the decryption path
inside the factory.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from romarr.downloaders.factory import build_client_from_row
from romarr.downloaders.implementations.grabarr_direct import (
    GrabarrDirectClient,
)
from romarr.downloaders.types import ClientType
from romarr.metadata.encryption import encrypt


def _row(**over: Any) -> Any:
    base: dict[str, Any] = {
        "id": 7,
        "name": "Local Grabarr",
        "type": ClientType.GRABARR_DIRECT.value,
        "host": "grabarr.lan",
        "port": 8081,
        "use_ssl": False,
        "url_base": None,
        "username": None,
        "password_encrypted": None,
        "api_key_encrypted": encrypt(b"rmk_test_secret"),
        "category_default": "romarr",
        "ssl_cert_validation": "enabled",
        "timeout_seconds": 90,
    }
    base.update(over)
    return SimpleNamespace(**base)


def test_factory_builds_grabarr_direct_with_decrypted_apikey() -> None:
    client = build_client_from_row(_row())
    assert isinstance(client, GrabarrDirectClient)
    assert client.client_id == 7
    assert client.name == "Local Grabarr"
    # The Fernet ciphertext was round-tripped through decrypt() —
    # the constructor sees the plaintext.
    assert client._api_key == "rmk_test_secret"  # noqa: SLF001
    assert client._timeout == 90  # noqa: SLF001
    assert client.base_url == "http://grabarr.lan:8081"


def test_factory_tolerates_absent_apikey_until_wizard_lands() -> None:
    """The DB schema permits ``api_key_encrypted`` to be NULL today
    (the wizard will make it required). The factory must not crash
    on absence — ``test_connection`` surfaces the 401 instead."""
    client = build_client_from_row(_row(api_key_encrypted=None))
    assert isinstance(client, GrabarrDirectClient)
    assert client._api_key == ""  # noqa: SLF001


def test_factory_honours_use_ssl_and_url_base() -> None:
    client = build_client_from_row(
        _row(use_ssl=True, port=443, url_base="/grabarr")
    )
    assert isinstance(client, GrabarrDirectClient)
    assert client.base_url == "https://grabarr.lan:443/grabarr"


def test_factory_routes_unknown_type_to_value_error() -> None:
    with pytest.raises(ValueError, match="unknown download client type"):
        build_client_from_row(_row(type="not-a-real-type"))


def test_factory_honours_download_root_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Slice 425 — the http_direct streamer needs a base path under
    which to write files. Until the R3 wizard adds it as a column
    on the download_client row, operators pin it via the
    ``ROMARR_GRABARR_DIRECT_DOWNLOAD_ROOT`` env var."""
    monkeypatch.setenv(
        "ROMARR_GRABARR_DIRECT_DOWNLOAD_ROOT", "/data/grabarr-dl"
    )
    client = build_client_from_row(_row())
    assert isinstance(client, GrabarrDirectClient)
    assert str(client._download_root) == "/data/grabarr-dl"  # noqa: SLF001


def test_factory_falls_back_to_downloads_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(
        "ROMARR_GRABARR_DIRECT_DOWNLOAD_ROOT", raising=False
    )
    client = build_client_from_row(_row())
    assert isinstance(client, GrabarrDirectClient)
    assert str(client._download_root) == "/downloads"  # noqa: SLF001
