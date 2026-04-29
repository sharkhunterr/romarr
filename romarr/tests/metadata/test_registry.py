"""Provider registry + loader tests (T019, T020).

Defines a minimal in-test :class:`MetadataProvider` subclass so the
loader can be exercised without depending on any real provider client.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.metadata import (
    PROVIDER_REGISTRY,
    GameMetadata,
    GameSearchResult,
    MetadataProvider,
    ProviderCapabilities,
    ProviderField,
    encrypt,
    load_enabled_providers,
    register_provider,
)
from romarr.metadata.models import MetadataProviderConfig


def _make_provider_class(
    *,
    name: str,
    invoked_in_scan: bool = True,
    requires_auth: bool = True,
) -> type[MetadataProvider]:
    class _Stub(MetadataProvider):
        capabilities = ProviderCapabilities(
            name=name,
            requires_auth=requires_auth,
            contributable_fields=frozenset({ProviderField.TITLE}),
            invoked_in_scan=invoked_in_scan,
        )

        def __init__(self, **kw: Any) -> None:
            super().__init__(**kw)
            self.received_config: dict[str, Any] | None = None

        def configure(self, config: dict[str, Any]) -> None:
            self.received_config = config

        async def health_check(self) -> bool:
            return True

        async def search_games(
            self, query: str, *, platform_slug: str | None = None
        ) -> list[GameSearchResult]:
            return []

        async def get_game(self, provider_game_id: str) -> GameMetadata:
            raise NotImplementedError

        async def get_cover(self, provider_game_id: str) -> tuple[bytes, str]:
            raise NotImplementedError

        def get_platform_mapping(self, platform_slug: str) -> int | str | None:
            return None

    _Stub.__name__ = f"_Stub_{name}"
    return _Stub


@pytest.fixture
def fresh_registry() -> Any:
    saved = dict(PROVIDER_REGISTRY)
    PROVIDER_REGISTRY.clear()
    try:
        yield PROVIDER_REGISTRY
    finally:
        PROVIDER_REGISTRY.clear()
        PROVIDER_REGISTRY.update(saved)


def test_register_rejects_duplicate(fresh_registry: Any) -> None:
    stub_cls = _make_provider_class(name="igdb")
    register_provider("igdb", stub_cls)
    with pytest.raises(ValueError, match="already registered"):
        register_provider("igdb", stub_cls)


async def test_load_enabled_providers_orders_by_priority(
    async_session: AsyncSession,
    fresh_registry: Any,
    metadata_env: Any,
) -> None:
    """The loader respects priority_global ASC and skips disabled rows."""
    register_provider("igdb", _make_provider_class(name="igdb"))
    register_provider("mobygames", _make_provider_class(name="mobygames"))
    register_provider("screenscraper", _make_provider_class(name="screenscraper"))

    async_session.add_all(
        [
            MetadataProviderConfig(
                provider_name="igdb",
                enabled=True,
                priority_global=10,
                rate_limit_rps=4,
                rate_limit_burst=8,
            ),
            MetadataProviderConfig(
                provider_name="screenscraper",
                enabled=True,
                priority_global=20,
                rate_limit_rps=2,
                rate_limit_burst=4,
            ),
            MetadataProviderConfig(
                provider_name="mobygames",
                enabled=False,  # disabled — must be filtered out
                priority_global=30,
            ),
        ]
    )
    await async_session.commit()

    providers = await load_enabled_providers(async_session)
    names = [p.name for p in providers]
    assert names == ["igdb", "screenscraper"]


async def test_load_enabled_providers_skips_unknown_names(
    async_session: AsyncSession,
    fresh_registry: Any,
    metadata_env: Any,
) -> None:
    """A row referencing a name we don't ship is silently skipped (forward compat)."""
    register_provider("igdb", _make_provider_class(name="igdb"))

    async_session.add_all(
        [
            MetadataProviderConfig(
                provider_name="igdb",
                enabled=True,
                priority_global=10,
            ),
            # Configured but no class registered — must be ignored.
            MetadataProviderConfig(
                provider_name="hasheous",
                enabled=True,
                priority_global=50,
            ),
        ]
    )
    await async_session.commit()

    providers = await load_enabled_providers(async_session)
    assert [p.name for p in providers] == ["igdb"]


async def test_load_enabled_providers_excludes_non_scan_when_scan_true(
    async_session: AsyncSession,
    fresh_registry: Any,
    metadata_env: Any,
) -> None:
    """SteamGridDB-style providers (FR-005) are excluded from the scan flow."""
    register_provider("igdb", _make_provider_class(name="igdb"))
    register_provider(
        "steamgriddb",
        _make_provider_class(name="steamgriddb", invoked_in_scan=False),
    )

    async_session.add_all(
        [
            MetadataProviderConfig(
                provider_name="igdb",
                enabled=True,
                priority_global=10,
            ),
            MetadataProviderConfig(
                provider_name="steamgriddb",
                enabled=True,
                priority_global=90,
            ),
        ]
    )
    await async_session.commit()

    scan_only = await load_enabled_providers(async_session, scan=True)
    assert [p.name for p in scan_only] == ["igdb"]

    everything = await load_enabled_providers(async_session, scan=False)
    assert [p.name for p in everything] == ["igdb", "steamgriddb"]


async def test_load_enabled_providers_decrypts_config(
    async_session: AsyncSession,
    fresh_registry: Any,
    metadata_env: Any,
) -> None:
    """The encrypted config blob is decrypted and handed to ``configure``."""
    register_provider("igdb", _make_provider_class(name="igdb"))

    plaintext = {"client_id": "abc", "client_secret": "shh"}
    blob = encrypt(json.dumps(plaintext).encode("utf-8"))

    async_session.add(
        MetadataProviderConfig(
            provider_name="igdb",
            enabled=True,
            config_encrypted=blob,
            priority_global=10,
        )
    )
    await async_session.commit()

    providers = await load_enabled_providers(async_session)
    assert len(providers) == 1
    assert providers[0].received_config == plaintext  # type: ignore[attr-defined]


async def test_load_enabled_providers_empty_when_none_enabled(
    async_session: AsyncSession,
    fresh_registry: Any,
    metadata_env: Any,
) -> None:
    register_provider("igdb", _make_provider_class(name="igdb"))
    # No enabled rows.
    providers = await load_enabled_providers(async_session)
    assert providers == []
