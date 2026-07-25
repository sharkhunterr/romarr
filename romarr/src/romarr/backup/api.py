"""Endpoints `/api/v3/backup/` — manifest + export + import à la carte.

Admin-only : les 3 endpoints touchent à des ressources critiques
(imports peuvent overwrite ou delete-all en mode replace) donc ils
sont gardés derrière `require_admin`.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.backup.schemas import (
    Bundle,
    ExportRequest,
    ImportRequest,
    ImportResult,
    Manifest,
)
from romarr.backup.service import export_bundle, import_bundle, list_manifest

router = APIRouter(prefix="/api/v3/backup", tags=["Backup"])


@router.get(
    "/manifest",
    response_model=Manifest,
    summary="Liste des ressources backupables + leur nombre d'items actuels.",
)
async def get_manifest(
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Manifest:
    return await list_manifest(db)


@router.post(
    "/export",
    response_model=Bundle,
    summary="Génère un bundle JSON des ressources sélectionnées.",
)
async def post_export(
    payload: ExportRequest,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Bundle:
    """Le bundle est retourné en JSON natif. L'UI le télécharge côté
    client (`URL.createObjectURL` + `<a download>`) — pas de fichier
    stocké côté serveur.
    """
    return await export_bundle(
        db,
        resources=payload.resources,
        include_secrets=payload.include_secrets,
    )


@router.post(
    "/import",
    response_model=ImportResult,
    summary="Applique un bundle. Retourne un bilan par ressource.",
)
async def post_import(
    payload: ImportRequest,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ImportResult:
    """Un bundle peut contenir plus de ressources que ce qui est
    demandé — le service ne traite que l'intersection (bundle × wanted).
    """
    return await import_bundle(
        db,
        payload.bundle,
        resources=payload.resources,
        mode=payload.mode,
    )
