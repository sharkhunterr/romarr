"""Cross-endpoint canonical-envelope conformance (spec 013 T014, SC-003).

Every paginated read endpoint in the API surface MUST accept the
canonical query params (``page``, ``pageSize``, ``sortKey``,
``sortDirection``) and return the canonical
:class:`PaginationEnvelope` shape:

  ``{page, pageSize, sortKey, sortDirection, totalRecords, records}``

This table-driven test hits five endpoints through the real
FastAPI app (auth-cookie authenticated) and checks the response
shape. A regression where any endpoint accidentally returns a
bare list / a different envelope shape / a snake_case alias
fails the assertion immediately — catches the kind of
client-breaking refactor that would otherwise leak into a
release.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from romarr.auth import ROLE_ADMIN, User, hash_password


# Each entry: (label, method, path, extra_params).
# All paths return PaginationEnvelope[T]. We don't seed rows —
# even an empty result must carry the canonical keys.
_PAGINATED_ENDPOINTS: tuple[tuple[str, str, str, dict[str, str]], ...] = (
    ("history", "GET", "/api/v3/history", {}),
    (
        "history-since",
        "GET",
        "/api/v3/history/since",
        {"date": "2026-01-01T00:00:00Z"},
    ),
    ("queue", "GET", "/api/v3/queue", {}),
    ("wanted-missing", "GET", "/api/v3/wanted/missing", {}),
    ("wanted-cutoff", "GET", "/api/v3/wanted/cutoff", {}),
)

_REQUIRED_KEYS: frozenset[str] = frozenset(
    {"page", "pageSize", "sortKey", "sortDirection", "totalRecords", "records"}
)


async def _seed_admin_and_login(
    api_engine: AsyncEngine, api_client: httpx.AsyncClient
) -> None:
    """Inline auth helper — most spec-local conftests have one
    of these but the test root doesn't."""
    sm = async_sessionmaker(api_engine, expire_on_commit=False)
    async with sm() as session:
        session.add(
            User(
                username="admin",
                role=ROLE_ADMIN,
                is_active=True,
                hashed_password=hash_password("hunter2-correct-horse-battery-staple"),
            )
        )
        await session.commit()
    resp = await api_client.post(
        "/api/v3/auth/login",
        json={
            "username": "admin",
            "password": "hunter2-correct-horse-battery-staple",
        },
    )
    assert resp.status_code == 204, resp.text


@pytest.mark.parametrize(
    ("label", "method", "path", "extra_params"), _PAGINATED_ENDPOINTS
)
@pytest.mark.asyncio
async def test_paginated_endpoint_returns_canonical_envelope(
    api_client: httpx.AsyncClient,
    api_engine: AsyncEngine,
    label: str,
    method: str,
    path: str,
    extra_params: dict[str, str],
) -> None:
    """Every paginated read endpoint MUST honour the canonical
    pagination contract — same keys, same camelCase aliases,
    same shape regardless of whether the underlying table is
    empty."""
    await _seed_admin_and_login(api_engine, api_client)

    params: dict[str, str | int] = {"page": 1, "pageSize": 10}
    params.update(extra_params)
    response = await api_client.request(method, path, params=params)
    assert response.status_code == 200, (
        f"{label} returned {response.status_code}: {response.text}"
    )
    body = response.json()
    actual_keys = set(body.keys())
    missing = _REQUIRED_KEYS - actual_keys
    assert not missing, (
        f"{label} envelope is missing keys {sorted(missing)}; "
        f"got {sorted(actual_keys)}"
    )
    assert isinstance(body["records"], list)
    assert body["page"] == 1
    assert body["pageSize"] == 10
    assert isinstance(body["totalRecords"], int)
    assert body["totalRecords"] >= 0
