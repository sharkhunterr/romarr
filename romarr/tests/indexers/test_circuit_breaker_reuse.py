"""Confirm we reuse the foundation circuit breaker (T040, T041)."""

from __future__ import annotations

import inspect
import sys

import pytest

from romarr.identification.circuit_breaker import CircuitBreaker
from romarr.indexers import NewznabClient
from romarr.indexers.errors import CircuitOpenError


def test_breaker_class_is_the_foundation_one() -> None:
    """T040: ``CircuitBreaker`` referenced by indexers is the foundation
    one; no second implementation lives under ``romarr.indexers.*``."""
    breaker_modules = [
        m
        for name, m in sys.modules.items()
        if name.startswith("romarr.indexers")
        and m is not None
        and inspect.ismodule(m)
    ]
    for m in breaker_modules:
        # If the module imports CircuitBreaker, it must be the
        # foundation module's class object — never a re-defined one.
        if hasattr(m, "CircuitBreaker"):
            assert m.CircuitBreaker is CircuitBreaker


def test_circuit_open_error_re_exported() -> None:
    """The foundation's ``CircuitOpenError`` IS the one indexers
    callers see — single import surface."""
    from romarr.identification.circuit_breaker import (
        CircuitOpenError as FoundationOpenError,
    )

    assert CircuitOpenError is FoundationOpenError


@pytest.mark.asyncio
async def test_breaker_isolation_between_indexers() -> None:
    """T041: opening the breaker for indexer A does not affect indexer
    B. Two clients with two separate breakers are wholly independent."""
    breaker_a = CircuitBreaker("indexers.A", failure_threshold=1)
    breaker_b = CircuitBreaker("indexers.B", failure_threshold=1)

    # Force breaker A open.
    breaker_a.record_failure()

    # B's breaker remains closed.
    assert breaker_a.state.value == "open"
    assert breaker_b.state.value == "closed"

    # Building two clients with the two separate breakers gives a
    # downstream caller the same isolation guarantee.
    client_a = NewznabClient(
        indexer_id=1,
        name="A",
        base_url="https://a.test",
        api_key=None,
        breaker=breaker_a,
    )
    client_b = NewznabClient(
        indexer_id=2,
        name="B",
        base_url="https://b.test",
        api_key=None,
        breaker=breaker_b,
    )
    assert client_a._breaker is breaker_a  # type: ignore[attr-defined]
    assert client_b._breaker is breaker_b  # type: ignore[attr-defined]
    assert client_a._breaker is not client_b._breaker  # type: ignore[attr-defined]
