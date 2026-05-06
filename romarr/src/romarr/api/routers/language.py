"""Sonarr-compat ``/api/v3/language`` shim.

Prowlarr's Sonarr-app client expects a static list of languages
to populate "Language Profile" pickers. Romarr handles language
preference per :class:`LanguageProfile` and stores release-level
language codes as ISO 639-1 strings, so we project a fixed list
of common languages here for compatibility.

Operators don't actually use this on the Romarr side — it exists
so Prowlarr's connection test populates without errors.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from romarr.api.dependencies import require_readonly
from romarr.auth import Principal

router = APIRouter(prefix="/api/v3/language", tags=["Sonarr-Compat"])


class LanguageRead(BaseModel):
    id: int
    name: str
    nameLower: str


# Sonarr's documented language ids — kept stable so Prowlarr's
# preference rules survive a Romarr restart.
_LANGUAGES: list[LanguageRead] = [
    LanguageRead(id=0, name="Unknown", nameLower="unknown"),
    LanguageRead(id=1, name="English", nameLower="english"),
    LanguageRead(id=2, name="French", nameLower="french"),
    LanguageRead(id=3, name="Spanish", nameLower="spanish"),
    LanguageRead(id=4, name="German", nameLower="german"),
    LanguageRead(id=5, name="Italian", nameLower="italian"),
    LanguageRead(id=6, name="Danish", nameLower="danish"),
    LanguageRead(id=7, name="Dutch", nameLower="dutch"),
    LanguageRead(id=8, name="Japanese", nameLower="japanese"),
    LanguageRead(id=9, name="Cantonese", nameLower="cantonese"),
    LanguageRead(id=10, name="Mandarin", nameLower="mandarin"),
    LanguageRead(id=11, name="Russian", nameLower="russian"),
    LanguageRead(id=12, name="Polish", nameLower="polish"),
    LanguageRead(id=13, name="Vietnamese", nameLower="vietnamese"),
    LanguageRead(id=14, name="Swedish", nameLower="swedish"),
    LanguageRead(id=15, name="Norwegian", nameLower="norwegian"),
    LanguageRead(id=16, name="Finnish", nameLower="finnish"),
    LanguageRead(id=17, name="Turkish", nameLower="turkish"),
    LanguageRead(id=18, name="Portuguese", nameLower="portuguese"),
    LanguageRead(id=19, name="Flemish", nameLower="flemish"),
    LanguageRead(id=20, name="Greek", nameLower="greek"),
    LanguageRead(id=21, name="Korean", nameLower="korean"),
    LanguageRead(id=22, name="Hungarian", nameLower="hungarian"),
    LanguageRead(id=23, name="Hebrew", nameLower="hebrew"),
    LanguageRead(id=24, name="Lithuanian", nameLower="lithuanian"),
    LanguageRead(id=25, name="Czech", nameLower="czech"),
    LanguageRead(id=26, name="Hindi", nameLower="hindi"),
    LanguageRead(id=27, name="Romanian", nameLower="romanian"),
    LanguageRead(id=28, name="Thai", nameLower="thai"),
    LanguageRead(id=29, name="Bulgarian", nameLower="bulgarian"),
    LanguageRead(id=30, name="Arabic", nameLower="arabic"),
    LanguageRead(id=31, name="Ukrainian", nameLower="ukrainian"),
    LanguageRead(id=32, name="Persian", nameLower="persian"),
    LanguageRead(id=33, name="Bengali", nameLower="bengali"),
]


@router.get(
    "",
    response_model=list[LanguageRead],
    summary="Sonarr-compat language list (static). Used by Prowlarr's connection test.",
)
async def list_languages(
    _user: Annotated[Principal, Depends(require_readonly)],
) -> list[LanguageRead]:
    return list(_LANGUAGES)


__all__ = ["router"]
