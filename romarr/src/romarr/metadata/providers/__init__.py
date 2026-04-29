"""Provider clients for the metadata aggregation layer.

Each provider implements :class:`romarr.metadata.providers.base.MetadataProvider`.
The closed enumeration of nine known names lives in
:data:`romarr.metadata.models.KNOWN_PROVIDERS`; this module supplies
the in-process registry that maps each name to its concrete class.

Until each provider lands in its own slice the registry is empty —
``load_enabled_providers`` will simply return an empty list and the
aggregator will treat that the same as "all providers failed":
``needs_metadata_refresh = True``.
"""

from __future__ import annotations

from romarr.metadata.providers.base import MetadataProvider, ProviderCapabilities

# Concrete providers register themselves here as their slices land.
PROVIDER_REGISTRY: dict[str, type[MetadataProvider]] = {}


def register_provider(name: str, cls: type[MetadataProvider]) -> None:
    """Add a concrete provider class to the registry.

    Called from each provider module's import side. Raises if ``name``
    is already registered to surface accidental shadowing during
    development.
    """
    if name in PROVIDER_REGISTRY:
        raise ValueError(f"provider {name!r} is already registered")
    PROVIDER_REGISTRY[name] = cls


__all__ = [
    "PROVIDER_REGISTRY",
    "MetadataProvider",
    "ProviderCapabilities",
    "register_provider",
]
