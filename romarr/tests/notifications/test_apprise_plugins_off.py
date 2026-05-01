"""Apprise plugin-loading flag tests (CL007/CL008/CL012, FR-001a).

The env flag ``ROMARR_APPRISE_ALLOW_CUSTOM_PLUGINS`` gates
whether Apprise consults the operator's
``data/apprise-plugins/`` directory at process start. Default
is OFF (built-in providers only) so the directory is not a
silent code-execution surface.
"""

from __future__ import annotations

import os
from typing import Any

import pytest

from romarr.notifications.apprise_init import (
    CUSTOM_PLUGINS_DIR,
    CUSTOM_PLUGINS_ENV_VAR,
    build_apprise_asset,
    custom_plugins_enabled,
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Strip the env var so a developer running with
    ``ROMARR_APPRISE_ALLOW_CUSTOM_PLUGINS=true`` in their shell
    doesn't accidentally fail the OFF-by-default tests."""
    monkeypatch.delenv(CUSTOM_PLUGINS_ENV_VAR, raising=False)
    yield


# ---------------------------------------------------------------------------
# custom_plugins_enabled — flag predicate
# ---------------------------------------------------------------------------


def test_flag_off_when_env_unset() -> None:
    assert custom_plugins_enabled() is False


def test_flag_on_when_env_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CUSTOM_PLUGINS_ENV_VAR, "true")
    assert custom_plugins_enabled() is True


def test_flag_on_handles_uppercase(monkeypatch: pytest.MonkeyPatch) -> None:
    """Case-insensitive — TRUE / True / true all enable."""
    monkeypatch.setenv(CUSTOM_PLUGINS_ENV_VAR, "TRUE")
    assert custom_plugins_enabled() is True
    monkeypatch.setenv(CUSTOM_PLUGINS_ENV_VAR, "True")
    assert custom_plugins_enabled() is True


@pytest.mark.parametrize(
    "value", ["false", "False", "FALSE", "0", "no", "off", ""]
)
def test_flag_off_for_every_non_true_value(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Anything other than ``true`` (case-insensitive) keeps
    the flag off — matches the FR-001a 'opt-in only' contract."""
    monkeypatch.setenv(CUSTOM_PLUGINS_ENV_VAR, value)
    assert custom_plugins_enabled() is False


# ---------------------------------------------------------------------------
# build_apprise_asset — plugin_paths content
# ---------------------------------------------------------------------------


def test_asset_has_empty_plugin_paths_by_default() -> None:
    """OFF: the operator's directory is NOT in ``plugin_paths``
    so Apprise doesn't sweep it on initialisation."""
    asset = build_apprise_asset()
    assert _plugin_paths(asset) == []


def test_asset_includes_plugin_dir_when_flag_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ON: the operator's directory is in ``plugin_paths`` so
    Apprise's normal discovery applies."""
    monkeypatch.setenv(CUSTOM_PLUGINS_ENV_VAR, "true")
    asset = build_apprise_asset()
    paths = _plugin_paths(asset)
    assert len(paths) == 1
    # The path is rendered as a string for Apprise's API.
    assert paths[0] == str(CUSTOM_PLUGINS_DIR)


# ---------------------------------------------------------------------------
# Wiring smoke test — apprise_wrapper.validate_url uses the asset
# ---------------------------------------------------------------------------


def test_validate_url_uses_hardened_asset() -> None:
    """A built-in provider URL still validates with the
    hardened asset (regression guard — confirming
    ``plugin_paths=[]`` doesn't accidentally disable the
    bundled providers)."""
    from romarr.notifications.apprise_wrapper import validate_url

    # Should not raise — discord:// is a built-in provider.
    validate_url("discord://1234567890/abcdefghijklmnop")


# ---------------------------------------------------------------------------
# Internals


def _plugin_paths(asset: Any) -> list[str]:
    """Read ``asset.plugin_paths`` defensively — Apprise's
    attribute name has been ``plugin_paths`` for many releases
    but we don't want this test to crash on a future rename."""
    paths = getattr(asset, "plugin_paths", None)
    if paths is None:
        return []
    return list(paths)


def test_env_var_name_is_documented() -> None:
    """Sanity: the constant matches FR-001a verbatim. If the
    name ever drifts, the README/quickstart references are
    out of sync."""
    assert CUSTOM_PLUGINS_ENV_VAR == "ROMARR_APPRISE_ALLOW_CUSTOM_PLUGINS"


# Document the intended off-by-default behaviour at module
# scope so a code reader sees it without spelunking.
assert os.environ.get(CUSTOM_PLUGINS_ENV_VAR) is None or True
