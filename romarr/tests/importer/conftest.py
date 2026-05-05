"""Module-local fixtures for importer tests."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from romarr.importer.types import ImportContext


@pytest.fixture
def correlation_id() -> str:
    return str(uuid4())


@pytest.fixture
def base_context(tmp_path) -> ImportContext:
    """A minimal ``ImportContext`` for tests that just need a
    valid value type to flow through the pipeline.

    Uses a ``.md`` (Mega Drive ROM) suffix rather than an
    archive extension so the orchestrator's audit-only path
    runs to ``match:no_game`` rather than tripping the
    EXTRACT failure branch (slice 302+).
    """
    source = tmp_path / "downloads" / "rom.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_bytes(b"placeholder")
    return ImportContext(
        source_path=source,
        correlation_id=uuid4(),
        imported_via="manual",
        imported_by="test-user",
    )


@pytest.fixture
def now() -> datetime:
    return datetime.now(UTC)
