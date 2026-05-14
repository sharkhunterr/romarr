"""Pydantic schema-level tests for the Grabarr-direct widening.

Slice 422 widened the DB CHECK constraint; slice 423 widens the
pydantic Literal so the (future) "Add Grabarr" wizard can POST
through the existing ``/api/v3/indexer`` endpoint. The Add Indexer
modal's ``_IMPLEMENTATIONS`` array stays at newznab/torznab — the
wizard is a separate flow.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from romarr.indexers.schemas import IndexerCreate, IndexerUpdate


def test_indexer_create_accepts_grabarr_implementation() -> None:
    obj = IndexerCreate(
        name="Grabarr direct",
        implementation="grabarr",
        url="https://grabarr.test/torznab/default",
    )
    assert obj.implementation == "grabarr"


def test_indexer_create_rejects_unknown_implementation() -> None:
    # The widening only adds 'grabarr' — arbitrary literals still
    # bounce at the pydantic layer before they ever reach the DB
    # CHECK constraint.
    with pytest.raises(ValidationError):
        IndexerCreate(
            name="Nope",
            implementation="not-a-real-impl",  # type: ignore[arg-type]
            url="https://example.test/api",
        )


def test_indexer_update_accepts_grabarr_implementation() -> None:
    obj = IndexerUpdate(implementation="grabarr")
    assert obj.implementation == "grabarr"


def test_indexer_update_keeps_implementation_optional() -> None:
    obj = IndexerUpdate()
    assert obj.implementation is None
