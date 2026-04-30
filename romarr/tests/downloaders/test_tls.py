"""TLS helper tests (T020)."""

from __future__ import annotations

import pytest

from romarr.downloaders.tls import build_httpx_verify, is_local_host


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "127.0.0.1",
        "127.5.5.5",          # 127.0.0.0/8
        "10.0.0.5",           # RFC1918 /8
        "172.16.0.1",         # RFC1918 lower bound
        "172.31.255.254",     # RFC1918 upper bound
        "192.168.1.10",       # RFC1918 /16
        "::1",                # IPv6 loopback
        "fe80::1",            # IPv6 link-local
    ],
)
def test_local_hosts(host: str) -> None:
    assert is_local_host(host) is True


@pytest.mark.parametrize(
    "host",
    [
        "8.8.8.8",            # public DNS
        "1.1.1.1",
        "172.32.0.1",         # outside RFC1918
        "172.15.0.1",         # outside RFC1918
        "2606:4700:4700::1111",  # Cloudflare IPv6 — globally routable
    ],
)
def test_public_hosts(host: str) -> None:
    assert is_local_host(host) is False


def test_build_httpx_verify_enabled() -> None:
    assert build_httpx_verify("enabled", "127.0.0.1") is True
    assert build_httpx_verify("enabled", "8.8.8.8") is True


def test_build_httpx_verify_disabled() -> None:
    assert build_httpx_verify("disabled", "127.0.0.1") is False
    assert build_httpx_verify("disabled", "8.8.8.8") is False


def test_build_httpx_verify_disabled_for_local() -> None:
    assert build_httpx_verify("disabled-for-local", "127.0.0.1") is False
    assert build_httpx_verify("disabled-for-local", "192.168.1.10") is False
    assert build_httpx_verify("disabled-for-local", "8.8.8.8") is True


def test_build_httpx_verify_unknown_setting() -> None:
    with pytest.raises(ValueError, match="unknown ssl_cert_validation"):
        build_httpx_verify("bogus", "127.0.0.1")  # type: ignore[arg-type]
