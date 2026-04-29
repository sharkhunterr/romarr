"""Load enabled providers from :class:`MetadataProviderConfig`.

Reads each row, skips disabled providers, decrypts the per-provider
config blob, hands it to the matching class's ``configure()``, and
returns instantiated objects ordered by ``priority_global``.

The :func:`load_enabled_providers` API takes a ``scan`` flag that maps
to FR-005: providers whose :attr:`ProviderCapabilities.invoked_in_scan`
is False are excluded when ``scan=True`` (the standard refresh flow).
SteamGridDB sets that flag to False so it is **only** invoked from the
operator-driven manual cover swap.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from sqlalchemy import select

from romarr.metadata.encryption import decrypt
from romarr.metadata.models import MetadataProviderConfig
from romarr.metadata.providers import PROVIDER_REGISTRY, MetadataProvider

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def load_enabled_providers(
    session: AsyncSession, *, scan: bool = True
) -> list[MetadataProvider]:
    """Return every enabled, registered provider, ordered by priority.

    "Enabled" means ``MetadataProviderConfig.enabled = True`` AND the
    name resolves through :data:`PROVIDER_REGISTRY` (a config row for a
    name we don't yet ship is silently skipped — graceful forward
    compatibility for partial deploys).

    When ``scan`` is True, providers whose capabilities mark them as
    not-scan-invokable (e.g. SteamGridDB) are filtered out.
    """
    rows = list(
        (
            await session.execute(
                select(MetadataProviderConfig)
                .where(MetadataProviderConfig.enabled.is_(True))
                .order_by(MetadataProviderConfig.priority_global)
            )
        )
        .scalars()
        .all()
    )

    out: list[MetadataProvider] = []
    for row in rows:
        cls = PROVIDER_REGISTRY.get(row.provider_name)
        if cls is None:
            continue
        provider = cls(
            rate_limit_rps=row.rate_limit_rps,
            rate_limit_burst=row.rate_limit_burst,
        )
        if scan and not provider.capabilities.invoked_in_scan:
            continue
        if row.config_encrypted is not None:
            config = json.loads(decrypt(row.config_encrypted).decode("utf-8"))
        else:
            config = {}
        provider.configure(config)
        out.append(provider)
    return out
