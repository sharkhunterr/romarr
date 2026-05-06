"""Sonarr-compat ``/api/v3/rootfolder`` shim.

Prowlarr's Sonarr-app client tests the connection by calling this
endpoint to populate its "Sync Profiles → Root Folder" picker.
Without it, Prowlarr's test reports "sentence contains no matching
content" because the populator finds zero rows to display.

Romarr's domain doesn't have a "root folder" concept per se — the
equivalent is :class:`Library`. We project each Library into the
Sonarr root-folder shape so the Prowlarr UI can populate its
picker; the operator picks one Library per Prowlarr→Romarr push
target.
"""

from __future__ import annotations

import os
import shutil
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_readonly
from romarr.auth import Principal
from romarr.libraries.models import Library

router = APIRouter(prefix="/api/v3/rootfolder", tags=["Sonarr-Compat"])


class RootFolderRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: int
    path: str
    accessible: bool
    freeSpace: int = Field(alias="freeSpace")
    unmappedFolders: list[Any] = Field(alias="unmappedFolders", default_factory=list)


def _free_space(path: str) -> int:
    try:
        return shutil.disk_usage(path).free
    except (FileNotFoundError, PermissionError, OSError):
        return 0


@router.get(
    "",
    response_model=list[RootFolderRead],
    response_model_by_alias=True,
    summary=(
        "Sonarr-compat root folder list. Each Romarr Library projects "
        "to one root-folder row so Prowlarr / Notifiarr / etc. can "
        "populate their pickers."
    ),
)
async def list_root_folders(
    _user: Annotated[Principal, Depends(require_readonly)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[RootFolderRead]:
    rows = (
        (await db.execute(select(Library).order_by(Library.id)))
        .scalars()
        .all()
    )
    out: list[RootFolderRead] = []
    for row in rows:
        out.append(
            RootFolderRead(
                id=row.id,
                path=row.path,
                accessible=os.path.isdir(row.path),
                freeSpace=_free_space(row.path),
                unmappedFolders=[],
            )
        )
    return out


__all__ = ["router"]
