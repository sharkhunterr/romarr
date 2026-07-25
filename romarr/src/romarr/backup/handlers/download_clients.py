"""Handler backup — DownloadClient.

Deux secrets possibles selon le type :
  * qbittorrent      : `password_encrypted`
  * sabnzbd, grabarr : `api_key_encrypted`
  * deluge           : `password_encrypted`

Sans `include_secrets`, les rows importées auront ces champs à `None`
et Romarr signalera « client non configuré » — l'opérateur re-saisit
le password/api_key dans l'UI. C'est le comportement le plus safe :
les credentials ne quittent jamais l'install source sans opt-in
explicite.

FK `download_client_id` porté PAR les indexers (pas ici) — donc ce
handler n'a rien à faire des cycles inter-ressources.
"""
from __future__ import annotations

from romarr.backup.handlers._shared import SimpleModelHandler
from romarr.backup.registry import register
from romarr.backup.schemas import ResourceKey
from romarr.downloaders.models import DownloadClient


class DownloadClientHandler(SimpleModelHandler):
    key = ResourceKey.DOWNLOAD_CLIENTS
    label = "Download Clients"
    has_secrets = True

    model_class = DownloadClient
    FIELDS = [
        "name",
        "type",
        "host",
        "port",
        "use_ssl",
        "url_base",
        "username",
        "category_default",
        "tags",
        "priority",
        "enable_for_torrents",
        "enable_for_usenet",
        "enabled",
        "remove_completed_downloads",
        "remove_failed_downloads",
        "ssl_cert_validation",
        "timeout_seconds",
        "download_root",
    ]
    SECRET_FIELDS = ["password_encrypted", "api_key_encrypted"]


register(DownloadClientHandler())
