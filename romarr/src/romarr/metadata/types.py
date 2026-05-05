"""Value types shared by every metadata-layer module.

These are non-persisted Pydantic models + a ``StrEnum`` of canonical
field names. Persistence-layer SQLAlchemy models live in
:mod:`romarr.metadata.models` (spec 002 PERS phase).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProviderField(StrEnum):
    """Canonical field-name vocabulary used by every provider.

    The aggregator's per-field priority logic is keyed on these names.
    Adding a field is a configuration change (insert ``field_priority``
    rows), NEVER a schema migration — see ``data-model.md``.
    """

    TITLE = "title"
    SUMMARY = "summary"
    COVER = "cover"
    GENRES = "genres"
    RELEASE_DATE = "release_date"
    DEVELOPER = "developer"
    PUBLISHER = "publisher"
    RATING = "rating"
    AGE_RATING = "age_rating"
    THEMES = "themes"
    FRANCHISES = "franchises"
    PLAYERS_MIN = "players_min"
    PLAYERS_MAX = "players_max"
    HLTB_MAIN = "hltb_main"
    ACHIEVEMENTS_COUNT = "achievements_count"


class GameSearchResult(BaseModel):
    """One row of a provider's "search games by title" response.

    Romarr's domain binds a Game to exactly one Platform, so providers
    that know the platform of a candidate emit one row per (game,
    platform) pair. Providers without that knowledge leave both
    ``platform_slug`` and ``platform_name`` ``None`` and the operator
    picks the platform manually in the AddGame modal.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    provider_name: str
    provider_game_id: str
    title: str
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Match strength in [0, 1]; provider-supplied or fuzz-derived.",
    )
    platform_slug: str | None = Field(
        default=None,
        description=(
            "Romarr platform slug the candidate maps to, when the "
            "provider knows. Resolved server-side via the per-provider "
            "platform_mapping config."
        ),
    )
    platform_name: str | None = Field(
        default=None,
        description="Human-readable platform name (e.g. 'Mega Drive').",
    )
    platform_manufacturer: str | None = Field(
        default=None,
        description=(
            "Platform manufacturer name (e.g. 'Nintendo'). The "
            "frontend uses it to colour the platform pill so the "
            "operator can spot families at a glance."
        ),
    )
    release_year: int | None = Field(
        default=None,
        description="First-release year for the candidate (provider-supplied).",
    )
    cover_url: str | None = Field(
        default=None,
        description=(
            "Absolute URL to a small cover thumbnail; the AddNew page "
            "renders it as a hero image so the operator can disambiguate "
            "candidates visually."
        ),
    )


class GameMetadata(BaseModel):
    """A single provider's contribution for a single Game.

    ``fields`` only contains fields the provider could fill — the
    aggregator skips missing keys instead of overwriting non-locked
    values with NULL (FR-009 additive-merge invariant).
    """

    model_config = ConfigDict(extra="forbid")

    provider_name: str
    provider_game_id: str
    fields: dict[ProviderField, Any] = Field(default_factory=dict)
    cover_url: str | None = None
    fetched_at: datetime


class AggregationResult(BaseModel):
    """Output of :func:`romarr.metadata.aggregator.aggregate`."""

    model_config = ConfigDict(extra="forbid")

    game_id: int
    fields: dict[ProviderField, tuple[Any, str]] = Field(default_factory=dict)
    skipped_locked: list[ProviderField] = Field(default_factory=list)
    cover_path: str | None = None
    needs_metadata_refresh: bool = False
