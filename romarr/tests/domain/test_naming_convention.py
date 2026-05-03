"""Spec 001 T007 — Base.metadata naming convention.

Pins the SQLAlchemy naming convention dict so Alembic autogen
emits stable, predictable constraint names matching the
hand-authored migrations.
"""

from __future__ import annotations

from romarr.domain.base import Base


def test_base_metadata_carries_naming_convention() -> None:
    """The ``Base.metadata`` MetaData must carry the documented
    naming-convention dict; missing it would let Alembic autogen
    emit dialect-specific machine-generated constraint names that
    change across SQLAlchemy versions."""
    convention = Base.metadata.naming_convention
    assert convention is not None
    # Five canonical keys per the SQLAlchemy docs.
    for key in ("ix", "uq", "ck", "fk", "pk"):
        assert key in convention, f"missing convention for {key}"


def test_naming_convention_patterns_match_spec_examples() -> None:
    """The patterns produce the same names as the hand-written
    migrations (e.g., ``uq_library_name``, ``ck_tag_assignment_*``).
    Pinning the patterns means a future Base.metadata bump can't
    silently change generated names."""
    convention = Base.metadata.naming_convention
    assert convention["uq"] == "uq_%(table_name)s_%(column_0_name)s"
    assert convention["ck"] == "ck_%(table_name)s_%(constraint_name)s"
    assert convention["pk"] == "pk_%(table_name)s"
    assert (
        convention["fk"]
        == "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
    )
    assert convention["ix"] == "ix_%(column_0_label)s"
