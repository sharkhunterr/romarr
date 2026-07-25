"""Schema-discovery endpoint — /api/v3/downloadclient/schema.

Lists every implementation Romarr knows about, with a flag telling
the UI whether it can be configured (qBittorrent + SABnzbd in MVP)
or is greyed out as v1-deferred (Transmission, Deluge, NZBGet).

The ``fields`` shape mirrors Sonarr/Radarr's ``Field`` array so
existing *arr UIs that consume this endpoint render the right form
without per-Romarr knowledge.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends

from romarr.api.dependencies import require_admin
from romarr.auth import Principal
from romarr.downloaders.schemas import DownloadClientSchema
from romarr.downloaders.types import ClientType

router = APIRouter(prefix="/api/v3/downloadclient", tags=["DownloadClients"])


_QBIT_FIELDS: list[dict[str, Any]] = [
    {"name": "host", "label": "Host", "type": "textbox"},
    {"name": "port", "label": "Port", "type": "number"},
    {"name": "username", "label": "Username", "type": "textbox"},
    {"name": "password", "label": "Password", "type": "password", "secret": True},
    {"name": "category_default", "label": "Category", "type": "textbox"},
    {"name": "use_ssl", "label": "Use SSL", "type": "checkbox"},
]


_SAB_FIELDS: list[dict[str, Any]] = [
    {"name": "host", "label": "Host", "type": "textbox"},
    {"name": "port", "label": "Port", "type": "number"},
    {"name": "api_key", "label": "API Key", "type": "textbox", "secret": True},
    {"name": "category_default", "label": "Category", "type": "textbox"},
    {"name": "use_ssl", "label": "Use SSL", "type": "checkbox"},
]


# Deluge WebUI n'a pas de username — le password seul authentifie
# l'opérateur qui accède au WebUI (Deluge distingue une seule identité
# côté web). `category_default` devient le label du plugin Label
# (auto-activé au premier ensure_category).
_DELUGE_FIELDS: list[dict[str, Any]] = [
    {"name": "host", "label": "Host", "type": "textbox"},
    {"name": "port", "label": "Port", "type": "number"},
    {"name": "password", "label": "Password", "type": "password", "secret": True},
    {"name": "category_default", "label": "Category (label)", "type": "textbox"},
    {"name": "use_ssl", "label": "Use SSL", "type": "checkbox"},
]


@router.get(
    "/schema",
    response_model=list[DownloadClientSchema],
    summary="List download-client implementations Romarr knows about.",
)
async def schema_endpoint(
    _admin: Annotated[Principal, Depends(require_admin)],
) -> list[DownloadClientSchema]:
    return [
        DownloadClientSchema(
            implementation=ClientType.QBITTORRENT,
            implementation_name="qBittorrent",
            available=True,
            config_contract="QBittorrentSettings",
            fields=_QBIT_FIELDS,
        ),
        DownloadClientSchema(
            implementation=ClientType.SABNZBD,
            implementation_name="SABnzbd",
            available=True,
            config_contract="SabnzbdSettings",
            fields=_SAB_FIELDS,
        ),
        DownloadClientSchema(
            implementation=ClientType.TRANSMISSION,
            implementation_name="Transmission",
            available=False,
            config_contract="TransmissionSettings",
            fields=[],
        ),
        DownloadClientSchema(
            implementation=ClientType.DELUGE,
            implementation_name="Deluge",
            available=True,
            config_contract="DelugeSettings",
            fields=_DELUGE_FIELDS,
        ),
        DownloadClientSchema(
            implementation=ClientType.NZBGET,
            implementation_name="NZBGet",
            available=False,
            config_contract="NzbgetSettings",
            fields=[],
        ),
    ]
