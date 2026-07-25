r"""Deluge WebUI JSON-RPC implementation of :class:`DownloadClient`.

Deluge expose une seule surface HTTP : ``POST /json`` avec un body
``{"id": <n>, "method": "<name>", "params": [...]}``. L'authentification
se fait par ``auth.login(password)`` qui pose un cookie ``_session_id``
que httpx propage sur les appels suivants.

Points d'attention :

* Le WebUI Deluge est une couche par-dessus le daemon libtorrent.
  Après ``auth.login`` on doit vérifier via ``web.connected`` qu'un
  daemon est bien attaché — sinon les appels ``core.*`` planteront
  avec ``No such method``. Sur une install standalone (le cas normal),
  le WebUI est déjà connecté au daemon local, mais un opérateur avec
  un WebUI thin-client doit avoir fait ``web.connect(host_id)`` au
  premier boot du WebUI (une seule fois, persisté côté Deluge).

* Deluge n'a pas de « catégorie » native — on utilise **le plugin
  Label** (livré out-of-the-box mais désactivé par défaut). Romarr
  active le plugin au ``ensure_category`` et pose le label sur chaque
  torrent ajouté. Sans Label, on peut quand même add/remove les
  torrents ; on perd juste le filtre pour ``list_managed_downloads``
  qui doit alors scanner tous les torrents du daemon (comportement
  dégradé mais fonctionnel).

* Les « tags » n'existent pas dans Deluge. On simule ``TAG_IMPORTED``
  en **renommant le label** ``romarr`` → ``romarr-imported`` sur les
  torrents finis (pratique existante côté \*arr). Alternative :
  utiliser le champ ``label`` avec suffixe. On préfère un **second
  label distinct** pour rester compat avec le pattern des autres
  clients.

* ``select_only_matching_file`` : Deluge supporte les priorités de
  fichiers via ``core.set_torrent_options({file_priorities: [...]})``.
  Implémentation dans une slice ultérieure — non-op ici (comportement
  du parent = accepter tout le torrent). Grabarr Direct est notre
  raccourci pour les torrents multi-fichiers.
"""

from __future__ import annotations

import base64
import logging
from datetime import datetime, timezone
from typing import Any, ClassVar

import httpx

from romarr.downloaders.base import DownloadClient
from romarr.downloaders.errors import (
    AuthError,
    CategoryWarning,
    ConnectionError as DownloaderConnError,
    TLSError,
    VersionError,
)
from romarr.downloaders.tags import TAG_IMPORTED, TAG_ROMARR
from romarr.downloaders.tls import SslCertValidation, build_httpx_verify
from romarr.downloaders.types import (
    ClientType,
    DownloadState,
    DownloadStatus,
    ManagedDownload,
    NzbSource,
    TorrentBytes,
    TorrentMagnet,
    TorrentSource,
    TorrentUrl,
)

logger = logging.getLogger(__name__)

# Deluge < 2.0 n'a pas le plugin Label dans le core (fourni en séparé).
# Deluge 2.0 (2019) marque le premier release avec Label intégré + WebUI
# JSON-RPC stabilisé. On refuse plus vieux pour éviter les 40 workarounds.
_MIN_DELUGE_VERSION = "2.0.0"


def _map_state(status: dict[str, Any]) -> DownloadState:
    """Traduit les états Deluge en :class:`DownloadState` canonique.

    États natifs Deluge (champ ``state``) : ``Downloading``, ``Seeding``,
    ``Paused``, ``Error``, ``Queued``, ``Checking``, ``Moving``, ``Allocating``.
    Le champ ``is_finished`` distingue ``COMPLETED`` de ``SEEDING`` :
    un torrent fini + seeding actif → SEEDING ; fini + pause → COMPLETED.
    """
    native = str(status.get("state") or "").lower()
    is_finished = bool(status.get("is_finished"))
    if native == "error":
        return DownloadState.FAILED
    if native == "paused":
        return DownloadState.COMPLETED if is_finished else DownloadState.PAUSED
    if native in ("queued", "checking", "allocating", "moving"):
        return DownloadState.QUEUED
    if native == "seeding":
        return DownloadState.SEEDING
    if native == "downloading":
        # Un torrent qui download mais reçoit 0 bytes depuis un moment
        # (`download_payload_rate == 0` + progrès < 100%) → STALLED.
        # Deluge n'a pas de flag dédié, on approxime.
        rate = int(status.get("download_payload_rate") or 0)
        if rate == 0 and float(status.get("progress") or 0.0) < 100.0:
            return DownloadState.STALLED
        return DownloadState.DOWNLOADING
    # Deluge peut retourner "Completed" via certaines versions (rare)
    if is_finished:
        return DownloadState.COMPLETED
    return DownloadState.DOWNLOADING


class DelugeClient(DownloadClient):
    """Deluge implementation of the download-client ABC.

    Ne supporte que les torrents (Deluge n'a jamais fait Usenet).
    Compat Deluge 2.0+ (WebUI JSON-RPC stable + plugin Label intégré).
    """

    client_type: ClassVar[ClientType] = ClientType.DELUGE
    supports_torrents: ClassVar[bool] = True
    supports_usenet: ClassVar[bool] = False
    available: ClassVar[bool] = True

    def __init__(
        self,
        *,
        client_id: int,
        name: str,
        host: str,
        port: int,
        password: str,
        use_ssl: bool = False,
        url_base: str | None = None,
        ssl_cert_validation: SslCertValidation = "enabled",
        category_default: str = TAG_ROMARR,
        timeout_seconds: float = 15.0,
    ) -> None:
        super().__init__(client_id=client_id, name=name)
        self._host = host
        self._port = port
        # Deluge WebUI ne connaît qu'un password (pas de username) —
        # l'identité de l'opérateur vient du fait qu'il a le password.
        self._password = password
        self._scheme = "https" if use_ssl else "http"
        self._url_base = (url_base or "").rstrip("/")
        self._verify = build_httpx_verify(ssl_cert_validation, host)
        self._label = category_default
        self._timeout = timeout_seconds
        # Compteur monotone pour le champ `id` du JSON-RPC — la spec
        # Deluge veut un id unique par request pour matcher réponses ↔
        # requêtes. On pourrait mettre 0 partout (Deluge tolère), mais
        # un compteur aide au debug (logs, éventuels multiplex).
        self._rpc_id = 0

    @property
    def base_url(self) -> str:
        """URL du endpoint JSON-RPC unique."""
        return f"{self._scheme}://{self._host}:{self._port}{self._url_base}/json"

    # ---- HTTP + JSON-RPC plumbing --------------------------------------------

    def _new_client(self) -> httpx.AsyncClient:
        # cookie jar activé automatiquement via `httpx.AsyncClient` —
        # `_session_id` posé par `auth.login` propagé aux appels suivants.
        return httpx.AsyncClient(
            verify=self._verify,
            timeout=self._timeout,
        )

    def _next_rpc_id(self) -> int:
        self._rpc_id += 1
        return self._rpc_id

    async def _rpc(
        self,
        client: httpx.AsyncClient,
        method: str,
        params: list[Any] | None = None,
    ) -> Any:
        """Exécute un JSON-RPC Deluge, retourne le champ `result`.

        Deluge renvoie toujours HTTP 200 avec un body
        ``{"id": <n>, "result": <val>|null, "error": <obj>|null}``.
        Un ``error`` non-null signale l'échec applicatif — traité en
        :class:`DownloaderConnError` avec le message Deluge inclus.
        """
        payload = {
            "id": self._next_rpc_id(),
            "method": method,
            "params": params or [],
        }
        try:
            resp = await client.post(self.base_url, json=payload)
        except httpx.ConnectError as e:
            raise DownloaderConnError(
                f"Deluge unreachable at {self.base_url}: {e}"
            ) from e
        except httpx.TimeoutException as e:
            raise DownloaderConnError(
                f"Deluge timeout at {self.base_url}: {e}"
            ) from e
        except httpx.HTTPError as e:
            # Erreurs TLS s'exposent souvent via ssl.SSLError wrapée
            # dans httpx.HTTPError — on distingue par le message pour
            # remonter un signal actionnable côté UI.
            msg = str(e)
            if "SSL" in msg or "certificate" in msg.lower():
                raise TLSError(f"Deluge TLS handshake failed: {e}") from e
            raise DownloaderConnError(f"Deluge HTTP error: {e}") from e

        if resp.status_code != 200:
            raise DownloaderConnError(
                f"Deluge HTTP {resp.status_code} on {method}: {resp.text[:200]}"
            )
        try:
            data = resp.json()
        except Exception as e:
            raise DownloaderConnError(
                f"Deluge non-JSON response on {method}: {resp.text[:200]}"
            ) from e

        err = data.get("error")
        if err:
            # Structure Deluge : {code, message} — le code numérique
            # varie selon la version, on relaie le message brut.
            msg = err.get("message") if isinstance(err, dict) else str(err)
            msg_s = str(msg)
            # AuthError uniquement sur les messages sans ambiguïté —
            # « session » seul est trop générique (Deluge dit
            # « Torrent already in session » = duplicate, pas auth).
            if "Not authenticated" in msg_s or "Not Authorized" in msg_s:
                raise AuthError(f"Deluge auth failed on {method}: {msg}")
            raise DownloaderConnError(f"Deluge rpc {method}: {msg}")
        return data.get("result")

    async def _login(self, client: httpx.AsyncClient) -> None:
        """Pose le cookie de session via ``auth.login(password)``.

        Deluge répond ``true`` en cas de succès, ``false`` sinon (pas
        d'error object) — d'où le check du result.
        """
        ok = await self._rpc(client, "auth.login", [self._password])
        if ok is not True:
            raise AuthError("Deluge password rejected (auth.login returned false)")

    async def _ensure_connected_to_daemon(self, client: httpx.AsyncClient) -> None:
        """Vérifie que le WebUI est bien attaché au daemon libtorrent.

        Sur une install standalone (99% des cas) c'est automatique — le
        WebUI et le daemon partagent le même process/config. Sur un
        WebUI thin-client, il faut avoir fait ``web.connect(host_id)``
        au setup initial (persisté côté Deluge). Cette méthode vérifie
        seulement — pas d'auto-connect (l'opérateur doit le faire une
        fois côté Deluge).
        """
        connected = await self._rpc(client, "web.connected")
        if not connected:
            hosts = await self._rpc(client, "web.get_hosts")
            hosts_desc = ", ".join(f"{h[0][:8]}" for h in (hosts or []))
            raise DownloaderConnError(
                f"Deluge WebUI not attached to any daemon. "
                f"Available hosts: [{hosts_desc}]. "
                f"Attach one from Deluge's WebUI ('Connection Manager')."
            )

    # ---- contract ------------------------------------------------------------

    async def test_connection(self) -> str:
        """Login + version check.

        Retourne la version Deluge (ex. ``"2.1.1"``). Raises :
        :class:`AuthError` si le password est rejeté,
        :class:`DownloaderConnError` si l'hôte est injoignable ou si le
        WebUI n'est pas attaché à un daemon,
        :class:`VersionError` si Deluge < 2.0.
        """
        async with self._new_client() as client:
            await self._login(client)
            await self._ensure_connected_to_daemon(client)
            # `daemon.get_version` renvoie la version du daemon
            # (ex. "2.1.1"). `daemon.info` n'existe pas dans l'API
            # publique — piège documenté dans les issues Deluge #3421.
            version = await self._rpc(client, "daemon.get_version")
            v = str(version or "").strip()
            if not v:
                raise DownloaderConnError("Deluge daemon.info returned empty")
            # Compare comme tuple d'ints pour éviter les faux positifs
            # lex ("10.0" > "2.0" en string mais l'inverse en semver).
            try:
                cur = tuple(int(x) for x in v.split(".")[:3])
                minv = tuple(int(x) for x in _MIN_DELUGE_VERSION.split("."))
            except ValueError:
                # Version format inattendu → on log mais on laisse passer
                # (mieux vaut une compat approximative qu'un faux refus).
                logger.warning(f"[deluge] version parse failed for {v!r}")
                return v
            if cur < minv:
                raise VersionError(
                    f"Deluge {v} is too old (minimum {_MIN_DELUGE_VERSION})"
                )
            return v

    async def add_torrent(
        self,
        source: TorrentSource,
        *,
        category: str,
        tags: list[str],
        save_path: str | None = None,
    ) -> str:
        """Ajoute un torrent, retourne son info-hash.

        Deluge accepte 3 formats :
          - ``core.add_torrent_url(url, options)``      → pour .torrent HTTP
          - ``core.add_torrent_magnet(magnet, options)`` → pour magnet:
          - ``core.add_torrent_file(name, b64_dump, options)`` → pour bytes

        Idempotence FR-004a : si le hash existe déjà, Deluge renvoie
        ``None`` (au lieu du hash) et log un warning côté daemon. On
        récupère le hash via ``core.get_torrent_status`` sur le hash
        pré-calculé du magnet, ou via un scan si download_url.
        """
        options: dict[str, Any] = {}
        if save_path:
            options["download_location"] = save_path

        async with self._new_client() as client:
            await self._login(client)

            try:
                if isinstance(source, TorrentMagnet):
                    result = await self._rpc(
                        client, "core.add_torrent_magnet", [source.magnet_uri, options]
                    )
                elif isinstance(source, TorrentUrl):
                    result = await self._rpc(
                        client, "core.add_torrent_url", [str(source.url), options]
                    )
                elif isinstance(source, TorrentBytes):
                    b64 = base64.b64encode(source.data).decode("ascii")
                    # `filename` sert seulement au log Deluge, n'importe
                    # quel nom passe (Deluge extrait le vrai contenu).
                    result = await self._rpc(
                        client,
                        "core.add_torrent_file",
                        [f"romarr-{category}.torrent", b64, options],
                    )
                else:
                    raise TypeError(f"Unsupported TorrentSource: {type(source)!r}")
            except DownloaderConnError as e:
                # Idempotence FR-004a : Deluge lève AddTorrentError
                # « Torrent already in session (<hash>) » quand on
                # essaie de ré-ajouter un torrent déjà présent. On
                # récupère le hash depuis le message et on retourne
                # l'existant plutôt que de crasher — même contract que
                # qBit qui merge additivement les tags.
                msg = str(e)
                if "already in session" in msg:
                    import re
                    m = re.search(r"\(([0-9a-fA-F]{40})\)", msg)
                    if m:
                        info_hash = m.group(1).lower()
                        logger.info(
                            f"[deluge] add_torrent idempotent: {info_hash[:8]} already present"
                        )
                        await self._apply_label(client, info_hash, self._label)
                        return info_hash
                raise

            # Deluge retourne l'info-hash sur succès, None si l'URL/
            # magnet ne se résout pas encore (rare). On relève dans ce
            # cas — le caller peut retry.
            if not result:
                raise DownloaderConnError(
                    "Deluge add_torrent returned no hash "
                    "(metadata not resolved yet — retry later)"
                )
            info_hash = str(result)

            # Applique le label (catégorie Romarr) — best-effort, sans
            # le plugin Label ça raise, on log mais on ne fail pas l'add.
            await self._apply_label(client, info_hash, self._label)

            # Deluge n'a pas de "tags" au sens qBit. Les tags passés par
            # Romarr (`romarr`, `romarr-imported`, `platform:gb`) sont
            # loggés pour debug mais ignorés — la catégorie unique
            # tient lieu de tag principal.
            if tags:
                logger.debug(
                    f"[deluge] {info_hash[:8]}: tags ignored "
                    f"(Deluge has no tag concept): {tags}"
                )
            return info_hash

    async def add_nzb(self, source: NzbSource, *, category: str) -> str:
        # Explicite plutôt que d'hériter d'une NotImplementedError obscure
        raise TypeError("Deluge does not support Usenet (NZB) sources")

    async def get_status(self, client_native_id: str) -> DownloadStatus:
        async with self._new_client() as client:
            await self._login(client)
            keys = [
                "name", "state", "is_finished", "progress",
                "download_payload_rate", "upload_payload_rate",
                "eta", "num_seeds", "num_peers",
                "total_size", "total_done",
                "save_path", "download_location",
            ]
            raw = await self._rpc(
                client, "core.get_torrent_status", [client_native_id, keys]
            )
            if not raw:
                raise DownloaderConnError(
                    f"Deluge get_torrent_status({client_native_id[:8]}) empty "
                    f"— torrent may have been removed"
                )
            return DownloadStatus(
                client_id=self.client_id,
                client_native_id=client_native_id,
                name=str(raw.get("name") or client_native_id),
                state=_map_state(raw),
                # Deluge renvoie progress en [0..100], canonicalise [0..1]
                progress=max(0.0, min(1.0, float(raw.get("progress") or 0.0) / 100.0)),
                eta_seconds=int(raw.get("eta") or 0) or None,
                seeders=int(raw.get("num_seeds") or 0),
                peers=int(raw.get("num_peers") or 0),
                download_rate_bps=int(raw.get("download_payload_rate") or 0),
                upload_rate_bps=int(raw.get("upload_payload_rate") or 0),
                total_bytes=int(raw.get("total_size") or 0) or None,
                save_path=str(
                    raw.get("download_location") or raw.get("save_path") or ""
                ) or None,
                fetched_at=datetime.now(timezone.utc),
            )

    async def remove(self, client_native_id: str, *, delete_files: bool) -> None:
        async with self._new_client() as client:
            await self._login(client)
            # `remove_data=True` supprime aussi les fichiers du disque
            await self._rpc(
                client, "core.remove_torrent", [client_native_id, delete_files]
            )

    async def set_imported_tag(self, client_native_id: str) -> None:
        """Deluge n'ayant pas de tags, on renomme le label du torrent
        vers ``romarr-imported`` pour marquer l'import complet.

        Best-effort : si le plugin Label n'est pas actif, on log et
        on continue (le pipeline ne doit pas planter pour un flag).
        """
        async with self._new_client() as client:
            await self._login(client)
            await self._apply_label(client, client_native_id, TAG_IMPORTED)

    async def list_managed_downloads(self) -> list[ManagedDownload]:
        """Liste tous les torrents finis dont le label = catégorie Romarr
        ET qui ne portent pas encore le label ``romarr-imported``.

        Si le plugin Label est indisponible, dégrade en scan complet
        (tous les torrents finis remontés). Bruit acceptable pour un
        setup edge — le pattern standard est d'avoir Label activé.
        """
        managed: list[ManagedDownload] = []
        async with self._new_client() as client:
            await self._login(client)

            # Filter Deluge subtilité : le filtermanager de Deluge
            # <= 2.2 traite chaque valeur du filter_dict comme si
            # `status[field] in values` — donc `is_finished: True`
            # crash avec « argument of type 'bool' is not iterable ».
            # Workaround : on ne filtre PAS côté serveur sur
            # `is_finished`, on récupère tout et on filtre en Python.
            # `label` par contre est bien géré (liste de strings) donc
            # on le garde côté serveur quand le plugin est up.
            label_available = await self._label_plugin_available(client)
            filter_dict: dict[str, Any] = {}
            if label_available:
                filter_dict["label"] = [self._label, TAG_IMPORTED]

            keys = ["name", "save_path", "download_location", "label", "is_finished"]
            raw = await self._rpc(
                client, "core.get_torrents_status", [filter_dict, keys]
            )
            if not isinstance(raw, dict):
                return managed

            for info_hash, item in raw.items():
                if not item.get("is_finished"):
                    continue
                item_label = str(item.get("label") or "")
                # Si on n'a pas pu filtrer côté serveur, filtre côté client
                if not label_available and item_label not in (
                    self._label, TAG_IMPORTED, ""
                ):
                    continue
                managed.append(ManagedDownload(
                    client_id=self.client_id,
                    client_native_id=str(info_hash),
                    name=str(item.get("name") or info_hash),
                    save_path=str(
                        item.get("download_location") or item.get("save_path") or ""
                    ),
                    imported=(item_label == TAG_IMPORTED),
                ))
        return managed

    async def ensure_category(self) -> None:
        """Active le plugin Label + crée le label ``romarr`` s'il manque.

        Contrairement à qBit qui auto-crée les catégories, Deluge exige
        que le plugin Label soit chargé côté daemon. On tente l'enable
        automatique via ``core.enable_plugin`` — si le plugin est
        physiquement absent (Deluge minimal build), on remonte un
        :class:`CategoryWarning` qui devient un warning non-bloquant
        côté connectivity orchestrator (FR-011).
        """
        async with self._new_client() as client:
            await self._login(client)

            enabled_plugins = await self._rpc(client, "core.get_enabled_plugins")
            if "Label" not in (enabled_plugins or []):
                try:
                    await self._rpc(client, "core.enable_plugin", ["Label"])
                except Exception as e:
                    raise CategoryWarning(
                        f"Deluge Label plugin unavailable ({e}). "
                        f"Install/enable it via Deluge's Preferences → "
                        f"Plugins → Label."
                    ) from e

            labels = await self._rpc(client, "label.get_labels")
            if self._label not in (labels or []):
                await self._rpc(client, "label.add", [self._label])
            if TAG_IMPORTED not in (labels or []):
                await self._rpc(client, "label.add", [TAG_IMPORTED])

    # ---- helpers -------------------------------------------------------------

    async def _label_plugin_available(self, client: httpx.AsyncClient) -> bool:
        try:
            enabled = await self._rpc(client, "core.get_enabled_plugins")
            return "Label" in (enabled or [])
        except Exception:
            return False

    async def _apply_label(
        self,
        client: httpx.AsyncClient,
        info_hash: str,
        label: str,
    ) -> None:
        """Pose ``label`` sur ``info_hash``, sans crasher si le plugin
        Label n'est pas dispo.
        """
        if not await self._label_plugin_available(client):
            logger.debug(
                f"[deluge] Label plugin not enabled — skip set_torrent for {info_hash[:8]}"
            )
            return
        try:
            # `label.set_torrent` crée le label si manquant sur Deluge 2.x
            await self._rpc(client, "label.set_torrent", [info_hash, label])
        except Exception as e:
            logger.warning(
                f"[deluge] label.set_torrent({info_hash[:8]}, {label!r}) failed: {e}"
            )


__all__ = ["DelugeClient"]
