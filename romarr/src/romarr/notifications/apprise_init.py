"""Apprise initialisation hardening (FR-001a, CL007/CL008).

Apprise ships ~80 built-in providers (Discord, Slack, Telegram,
Matrix, ntfy, Gotify, Pushover, email, generic webhook, etc.)
that cover every realistic MVP target. It can ALSO load
arbitrary Python modules from a configured plugin directory —
useful for site-specific extensions but a code-execution surface
the operator doesn't expect by default.

Per FR-001a, custom plugin loading is **disabled by default**
and gated behind an explicit env flag:

    ROMARR_APPRISE_ALLOW_CUSTOM_PLUGINS = true

When unset (or set to anything other than "true"), this module
configures every Apprise instance the wrapper builds with
``plugin_paths=[]`` so the ``data/apprise-plugins/`` directory
is not consulted. When the flag is on, ``plugin_paths`` is set
to the documented operator-controlled directory; the operator
explicitly acknowledges that the directory is now a code-
execution surface.

Helpers exported here:

  * :data:`CUSTOM_PLUGINS_ENV_VAR` — canonical env-var name.
  * :func:`custom_plugins_enabled` — bool read of the flag.
  * :func:`build_apprise_asset` — :class:`apprise.AppriseAsset`
    pre-configured with the right ``plugin_paths`` for the
    current flag state. The wrapper's
    :class:`apprise.Apprise()` calls thread it through.
"""

from __future__ import annotations

import os
from pathlib import Path

import apprise

CUSTOM_PLUGINS_ENV_VAR: str = "ROMARR_APPRISE_ALLOW_CUSTOM_PLUGINS"
"""Env var that controls whether the operator's plugin directory
is consulted on Apprise initialisation."""

CUSTOM_PLUGINS_DIR: Path = Path("data/apprise-plugins")
"""Documented plugin directory consulted when the flag is on.
Resolved at process startup; if the directory doesn't exist
the operator gets a quiet no-op rather than a hard failure
(they may have set the flag in advance of dropping plugins
in)."""


def custom_plugins_enabled() -> bool:
    """Return True iff the env flag is explicitly set to ``true``
    (case-insensitive). Anything else — unset, ``false``,
    ``no``, etc. — returns False."""
    raw = os.environ.get(CUSTOM_PLUGINS_ENV_VAR, "")
    return raw.strip().lower() == "true"


def build_apprise_asset() -> apprise.AppriseAsset:
    """Return an :class:`apprise.AppriseAsset` pre-configured
    for the current env-flag state.

    * Flag OFF (default): ``plugin_paths=[]`` — the bundled
      Apprise providers stay available (they're loaded from
      Apprise's own package directory, not from
      ``plugin_paths``); the operator's plugin directory is
      not consulted.
    * Flag ON: ``plugin_paths=[CUSTOM_PLUGINS_DIR]`` — the
      operator's directory is included in plugin discovery.
    """
    if custom_plugins_enabled():
        return apprise.AppriseAsset(
            plugin_paths=[str(CUSTOM_PLUGINS_DIR)]
        )
    return apprise.AppriseAsset(plugin_paths=[])


__all__ = [
    "CUSTOM_PLUGINS_DIR",
    "CUSTOM_PLUGINS_ENV_VAR",
    "build_apprise_asset",
    "custom_plugins_enabled",
]
