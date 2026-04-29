"""Romarr application configuration.

All settings come from environment variables prefixed ``ROMARR_``.
The :class:`Settings` class is the single source of truth — every
other module imports it instead of reading the env directly.
"""

from romarr.config.settings import Settings, get_settings

__all__ = ["Settings", "get_settings"]
