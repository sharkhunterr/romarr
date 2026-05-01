"""Pagination helper tests (T011-T014, FR-007/FR-008/FR-009)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy import Column, Integer

from romarr.api.envelopes import PaginationEnvelope
from romarr.api.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PageRequest,
    clamp_page_size,
    page_request,
)

# ---------------------------------------------------------------------------
# T011 — defaults applied when caller omits params
# ---------------------------------------------------------------------------


def test_default_page_request_values() -> None:
    """``PageRequest()`` carries the documented defaults."""
    req = PageRequest()
    assert req.page == 1
    assert req.page_size == DEFAULT_PAGE_SIZE
    assert req.sort_key is None
    assert req.sort_direction == "asc"


def test_default_max_page_size_is_1000() -> None:
    """SC-003 + FR-009: the documented cap."""
    assert MAX_PAGE_SIZE == 1000


# ---------------------------------------------------------------------------
# T012 — pageSize cap (FR-009)
# ---------------------------------------------------------------------------


def test_clamp_page_size_above_max_caps_to_1000() -> None:
    """FR-009: ``pageSize > 1000`` is silently capped at 1000."""
    assert clamp_page_size(2000) == MAX_PAGE_SIZE


def test_clamp_page_size_below_one_floors_at_one() -> None:
    """``pageSize < 1`` is clamped to 1 (smaller values are
    nonsensical; the ge=1 constraint also catches this on the
    Pydantic path)."""
    assert clamp_page_size(0) == 1
    assert clamp_page_size(-5) == 1


def test_clamp_page_size_in_range_passes_through() -> None:
    assert clamp_page_size(50) == 50
    assert clamp_page_size(MAX_PAGE_SIZE) == MAX_PAGE_SIZE


def test_pydantic_constraint_rejects_oversized_page_size() -> None:
    """The :class:`PageRequest` Pydantic validator returns 422
    on ``pageSize > 1000`` — endpoints that prefer the silent-
    cap form should call :func:`clamp_page_size` instead of
    using PageRequest directly."""
    with pytest.raises(ValueError, match="less than or equal to 1000"):
        PageRequest(page=1, pageSize=2000)


# ---------------------------------------------------------------------------
# T013 — invalid sortKey returns 400 with the canonical envelope
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_sort_key_raises_400() -> None:
    """Calling :func:`paginate` with a sortKey not in
    ``sortable_keys`` raises HTTPException(400) carrying the
    canonical error envelope (FR-008)."""
    from romarr.api.pagination import paginate

    # We don't actually need a session — the validation runs
    # before any SQL is issued.
    req = PageRequest(sortKey="NotARealField")
    with pytest.raises(HTTPException) as exc_info:
        await paginate(
            session=None,  # type: ignore[arg-type]
            base_query=None,  # type: ignore[arg-type]
            page_request=req,
            sortable_keys={"id": Column("id", Integer)},
            record_adapter=lambda x: x,
        )
    assert exc_info.value.status_code == 400
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail.get("errorCode") == "invalid_sort_key"
    assert "NotARealField" in detail.get("errorMessage", "")


# ---------------------------------------------------------------------------
# Default sort key falls back to the first ``sortable_keys`` entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_paginate_end_to_end_with_existing_model() -> None:
    """End-to-end exercise of :func:`paginate` against an
    existing project ORM model (the project's ``User`` is the
    smallest one with stable schema). Verifies that the
    helper:

      - applies the default sortKey (first key in
        ``sortable_keys``);
      - returns the documented envelope shape with
        ``totalRecords`` reflecting the unfiltered count;
      - applies ``offset`` + ``limit`` correctly;
      - converts each row through the supplied
        ``record_adapter``.
    """
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    # Importing the rest of the model packages so create_all
    # builds a complete schema (the User table FK-references
    # rows in other tables transitively).
    import romarr.notifications.models
    import romarr.tasks.models  # noqa: F401
    from romarr.api.pagination import paginate
    from romarr.auth.models import User
    from romarr.domain import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    async with sm() as session:
        for i in range(5):
            session.add(
                User(
                    username=f"user-{i}",
                    role="readonly",
                    is_active=True,
                    hashed_password="x",
                )
            )
        await session.commit()

    class _UserOut(BaseModel):
        id: int
        username: str

    def adapt(row: User) -> _UserOut:
        return _UserOut(id=row.id, username=row.username)

    async with sm() as session:
        envelope = await paginate(
            session=session,
            base_query=select(User),
            page_request=PageRequest(),
            sortable_keys={"id": User.id, "username": User.username},
            record_adapter=adapt,
        )

    await engine.dispose()

    assert envelope.page == 1
    assert envelope.page_size == DEFAULT_PAGE_SIZE
    assert envelope.sort_key == "id"  # first in sortable_keys
    assert envelope.sort_direction == "asc"
    assert envelope.total_records == 5
    assert len(envelope.records) == 5
    # Ascending — first record's id is the smallest.
    ids = [record.id for record in envelope.records]
    assert ids == sorted(ids)


# ---------------------------------------------------------------------------
# T014 — uniform shape across endpoints (envelope-level test)
# ---------------------------------------------------------------------------


def test_envelope_round_trip_via_dict() -> None:
    """The envelope round-trips through dict with the documented
    camelCase keys — ``pageSize``, ``sortKey``, ``sortDirection``,
    ``totalRecords``."""
    envelope = PaginationEnvelope[dict](
        page=2,
        pageSize=10,
        sortKey="created_at",
        sortDirection="desc",
        totalRecords=100,
        records=[{"x": 1}],
    )
    payload = envelope.model_dump(by_alias=True)
    assert payload["page"] == 2
    assert payload["pageSize"] == 10
    assert payload["sortKey"] == "created_at"
    assert payload["sortDirection"] == "desc"
    assert payload["totalRecords"] == 100
    assert payload["records"] == [{"x": 1}]


# ---------------------------------------------------------------------------
# FastAPI dependency surface — parses query strings correctly
# ---------------------------------------------------------------------------


def test_page_request_dependency_parses_query() -> None:
    """The :func:`page_request` dependency is FastAPI-callable.
    A small inline app exercises the URL-to-PageRequest path."""
    from fastapi import Depends

    app = FastAPI()

    @app.get("/items")
    async def list_items(
        req: PageRequest = Depends(page_request),  # noqa: B008
    ) -> dict:
        return {
            "page": req.page,
            "pageSize": req.page_size,
            "sortKey": req.sort_key,
            "sortDirection": req.sort_direction,
        }

    with TestClient(app) as client:
        resp = client.get(
            "/items?page=3&pageSize=25&sortKey=name&sortDirection=desc"
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "page": 3,
            "pageSize": 25,
            "sortKey": "name",
            "sortDirection": "desc",
        }


def test_page_request_oversize_page_size_returns_422() -> None:
    """The dependency uses Pydantic's ``le=1000`` constraint —
    ``?pageSize=2000`` is rejected at parse time. Endpoints that
    want the silent-cap behaviour use :func:`clamp_page_size`
    directly."""
    from fastapi import Depends

    app = FastAPI()

    @app.get("/items")
    async def list_items(
        req: PageRequest = Depends(page_request),  # noqa: B008
    ) -> dict:
        return {"ok": True}

    with TestClient(app) as client:
        resp = client.get("/items?pageSize=2000")
        assert resp.status_code == 422


def test_page_request_invalid_direction_rejected() -> None:
    """``?sortDirection=sideways`` is not in the literal — 422."""
    from fastapi import Depends

    app = FastAPI()

    @app.get("/items")
    async def list_items(
        req: PageRequest = Depends(page_request),  # noqa: B008
    ) -> dict:
        return {"ok": True}

    with TestClient(app) as client:
        resp = client.get("/items?sortDirection=sideways")
        assert resp.status_code == 422
