"""Envelope shape tests (T015, FR-010)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from romarr.api.envelopes import ErrorEnvelope, PaginationEnvelope

# ---------------------------------------------------------------------------
# Pagination envelope shape
# ---------------------------------------------------------------------------


def test_pagination_envelope_aliases_camel_case() -> None:
    """Spec FR-007: the JSON keys are camelCase
    (``pageSize``, ``sortKey``, ``sortDirection``,
    ``totalRecords``) regardless of the Python field names."""
    envelope = PaginationEnvelope[dict](
        page=1,
        pageSize=50,
        sortKey="id",
        sortDirection="asc",
        totalRecords=10,
        records=[{"id": 1}],
    )
    serialised = envelope.model_dump(by_alias=True)
    expected_keys = {
        "page",
        "pageSize",
        "sortKey",
        "sortDirection",
        "totalRecords",
        "records",
    }
    assert set(serialised.keys()) == expected_keys


def test_pagination_envelope_is_frozen() -> None:
    """Defensive: the envelope is immutable so consumers can't
    mutate the response shape after construction."""
    envelope = PaginationEnvelope[dict](
        page=1,
        pageSize=50,
        sortKey="id",
        sortDirection="asc",
        totalRecords=0,
        records=[],
    )
    with pytest.raises(ValueError, match="Instance is frozen"):
        envelope.page = 2  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Error envelope shape
# ---------------------------------------------------------------------------


def test_error_envelope_minimum_fields() -> None:
    """``errorMessage`` is required; ``errorCode`` and
    ``details`` are optional."""
    envelope = ErrorEnvelope(errorMessage="something went wrong")
    payload = envelope.model_dump(by_alias=True, exclude_none=True)
    assert payload == {"errorMessage": "something went wrong"}


def test_error_envelope_with_code_and_details() -> None:
    envelope = ErrorEnvelope(
        errorMessage="bad input",
        errorCode="invalid_sort_key",
        details={"sortKey": "FooBar"},
    )
    payload = envelope.model_dump(by_alias=True, exclude_none=True)
    assert payload == {
        "errorMessage": "bad input",
        "errorCode": "invalid_sort_key",
        "details": {"sortKey": "FooBar"},
    }


# ---------------------------------------------------------------------------
# T015 — global error handler produces the canonical envelope
# ---------------------------------------------------------------------------


def test_existing_error_handler_envelope() -> None:
    """The project's existing error_handlers register an
    HTTPException handler that wraps string-detail responses
    into ``{errorMessage, errorCode}``. This test pins that
    contract — adjusting the handler that any other test
    relies on would break the envelope shape across the API."""
    from romarr.api.error_handlers import register_error_handlers

    app = FastAPI()
    register_error_handlers(app)

    @app.get("/raises-400")
    async def raises_400() -> dict:
        raise HTTPException(status_code=400, detail="bad request")

    @app.get("/raises-404-with-dict")
    async def raises_404() -> dict:
        raise HTTPException(
            status_code=404,
            detail={
                "errorMessage": "thing missing",
                "errorCode": "not_found",
            },
        )

    with TestClient(app) as client:
        resp_400 = client.get("/raises-400")
        assert resp_400.status_code == 400
        body = resp_400.json()
        assert body["errorMessage"] == "bad request"
        assert body["errorCode"] == "http_error"

        resp_404 = client.get("/raises-404-with-dict")
        assert resp_404.status_code == 404
        body = resp_404.json()
        assert body["errorMessage"] == "thing missing"
        assert body["errorCode"] == "not_found"


def test_envelope_used_by_existing_endpoints_in_suite() -> None:
    """Sanity coverage: the project's existing error envelope
    shape (used by spec 010-012's API tests) is consistent with
    :class:`ErrorEnvelope`. If a future error handler change
    breaks this round-trip, tests across the suite will fail."""
    sample = {
        "errorMessage": "validation failed",
        "errorCode": "validation_error",
        "details": {"fields": ["name", "email"]},
    }
    envelope = ErrorEnvelope.model_validate(sample)
    assert envelope.error_message == "validation failed"
    assert envelope.error_code == "validation_error"
    assert envelope.details == {"fields": ["name", "email"]}
