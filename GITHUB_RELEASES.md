# GitHub Releases — Romarr

> Release notes for each tagged release. The first ``# vX.Y.Z`` block
> is consumed by the GitLab CI `release:gitlab` / `release:github`
> jobs as the description posted to the GitLab and GitHub release
> pages. CHANGELOG.md is the commit-by-commit machine-generated
> record; this file is the **human-curated highlight reel**.

> **Workflow** : edit this file BEFORE running `npm run release:full`.
> Add a new ``# vX.Y.Z`` block at the top describing the user-visible
> changes. The release script bumps the version, regenerates
> CHANGELOG.md from conventional commits, then tags + pushes; CI picks
> up the tag and posts THIS file's first block as the release body.

---

# v0.15.7

## 📂 Media Management — picker de chemin pour ludothèque

Fini le texte libre pour renseigner un chemin absolu de ludothèque.
Le modal **Create library** (Settings → Media Management) affiche
maintenant un bouton **Browse…** qui ouvre un explorateur de
dossiers embarqué :

- **Racine curated** — au niveau `/`, seuls les dossiers
  probablement montés en `-v` sont surfacés : `/data`, `/downloads`,
  `/roms`, `/media`, `/mnt`, `/config`, `/srv`, `/opt`, `/home`,
  `/app`, `/library`, `/games`. Un badge « mount » signale les
  entrées qui vivent sur un filesystem différent du parent (fort
  indice qu'il s'agit d'un volume Docker).
- **Navigation** — breadcrumbs cliquables, bouton `..` pour
  remonter, listing des sous-dossiers (fichiers et dot-dirs
  cachés).
- **Sélection** — bouton « Pick » par entrée, ou « Pick current »
  pour prendre le dossier en cours de visualisation.
- **Text entry** — l'input texte reste actif au-dessus du picker :
  écriture manuelle toujours possible pour les paths que le
  browser ne surface pas.

Prefixes système bloqués par sécurité : `/proc`, `/sys`, `/dev`,
`/boot`, `/etc`, `/root`, `/run`, `/tmp`, `/var/log`,
`/var/lib/docker`. Endpoint admin-only : la topologie du
container n'est pas exposée aux utilisateurs read-only.

### Endpoint

`GET /api/v3/system/filesystem?path=<absolute-path>` — admin.

---

# v0.15.6

## ⚙️ Platform packs — toggle builtin + priorité configurables

Nouveau panneau **Settings → Platforms → Pack configuration** (en
tête de page, avant la liste des plateformes) avec deux réglages :

### 1. Toggle built-in pack

Case à cocher pour activer/désactiver le pack builtin livré avec
Romarr. Décoché → aucune application au boot, l'install repose
uniquement sur les sources GitHub configurées.

Prend effet au prochain redémarrage.

### 2. Priorité builtin vs community

Radio « qui gagne quand un slug existe dans les deux packs » :

- **Community wins** (défaut) — comportement historique : builtin
  applique au boot, chaque sync community écrase les valeurs
  builtin pour les slugs communs.
- **Built-in wins** — après chaque sync community, Romarr
  ré-applique le builtin par-dessus pour restaurer les valeurs
  builtin sur les slugs partagés. Les slugs que le builtin ne
  touche pas restent tels quels.

### Réorganisation Platforms page

Les paramètres actionnables (config + sources + historique packs)
remontent en tête. Le catalogue des plateformes (grille) passe
en bas — moins prioritaire quand on ouvre la page pour
administrer.

### Backup à la carte

Deux nouvelles ressources dans le système d'export/import :

- `pack_sources` — la liste des URLs GitHub enregistrées
- `platform_pack_config` — les 2 réglages du panneau (singleton)

Le handler `platform_packs` existant (méta-données des packs
appliqués) est inchangé et reste un export métadonnées-only —
les YAML ne sont pas dans le bundle (comportement MVP).

---

# v0.15.5

## 🧹 Platform packs — layout `examples/` + auto-découverte

Refactor interne : les YAMLs builtin quittent leur cachette
sous `src/romarr/builtin_packs/` (bundled à la main dans le wheel)
pour vivre en clair sous **`romarr/examples/platform-packs/`** —
navigable directement dans le repo, aux côtés du pack community
d'exemple.

### Fin du hardcoded `_BUILTIN_PACK_VERSION`

Le loader ne pointe plus vers un nom de fichier précis. Au boot,
il liste `builtin-YYYY.MM.NNN.yaml` dans le dossier et prend le
plus récent par sort lexical. **Livrer un nouveau builtin =
déposer un YAML, rien à toucher côté Python.**

### Bundling wheel préservé

Un `[tool.hatch.build.targets.wheel.force-include]` mappe
`examples/platform-packs/` → `romarr/builtin_packs/` dans la
wheel. Zéro impact runtime : les paths d'import restent
identiques, les tests existants passent tels quels
(`_BUILTIN_PACK_VERSION` reste importable comme constante
calculée, backward-compat garantie).

### Pourquoi c'est mieux

- Une seule source de vérité pour chaque YAML — plus de risque
  de drift entre `src/` et `examples/`.
- Les operators / contributeurs voient tous les YAMLs (builtin +
  community) au même endroit sans ouvrir un wheel.
- Ajouter une nouvelle version builtin devient un simple `git add`
  + bump de `pack_version` dans le nouveau fichier.

---

# v0.15.4

## 🔍 Platform packs — preview + auto-sync programmé

Deux add-ons au workflow « sources GitHub » introduit dans v0.15.3.

### 🔎 Preview avant apply

Un bouton **Preview** sur chaque source ouvre un modal qui liste,
pour chaque YAML trouvé, le résultat qu'aurait un vrai apply :
`would_apply` / `would_skip` / `would_fail`, avec le diff par
plateforme (insertions, updates, champs modifiés, warnings). Zéro
écriture DB — un dry-run pur qui rejoue exactement la validation
utilisée par le `POST /validate` classique.

Depuis le modal, un bouton **Apply now** enchaîne directement la
vraie sync sans re-fetch. Utile pour vérifier une source douteuse
sans risque, ou juste voir ce que va changer un update.

### ⏰ Sync automatique via le scheduler

Nouveau job `PackSourcesSync` dans le catalogue des tâches
(Settings → Tasks) :
- **Cron par défaut** : `0 5 * * *` (tous les jours à 5 h)
- **Désactivé par défaut** — l'operator l'active depuis Tasks
  quand il a au moins une source enregistrée
- **Modifiable** : cron ou intervalle éditables depuis l'UI Tasks
- **Résultat** : le status et le count sont stampés sur la row
  `pack_sources` (visibles dans Settings → Platforms) — success
  global si toutes les sources sont ok, `partial` si au moins une
  YAML a raté, `failed` si zéro pack appliqué et au moins une
  erreur

---

# v0.15.3

## 🌐 Platform packs — sources GitHub configurables

Fini le upload manuel des YAML : chaque installation Romarr peut
désormais enregistrer **une ou plusieurs URLs GitHub** comme
sources de platform packs, puis synchroniser d'un clic.

### Ce que l'user configure

Dans **Settings → Platforms**, un panneau « Pack sources » avec :
- **Nom** + **URL** — la source est ajoutée en un formulaire
- Auto-détection du type :
  - `raw` — URL pointant directement sur un `*.yaml`
    (ex : `raw.githubusercontent.com/…/pack.yaml`)
  - `github_dir` — URL de type
    `https://github.com/{owner}/{repo}/tree/{branch}/{path}` — la
    sync walk le dossier et ingère chaque YAML enfant
- Enable/disable, delete, sync-now, historique du dernier run

### Comportement à la sync

Chaque YAML est passé au même `ingest_pack()` que l'upload manuel :
validation schéma, diff, apply transactionnel, audit trail.
Résultat par fichier : `applied` / `skipped` (déjà connu) / `failed`
(erreur de validation isolée qui ne rollback pas les autres).

### Endpoints admin

`/api/v3/rom/platform-pack-source/*` :
- `GET` — liste
- `POST` — création (auto-détecte `kind`)
- `PATCH /{id}` — toggle enabled / rename
- `DELETE /{id}` — retire la source (les packs déjà appliqués restent)
- `POST /{id}/sync` — fetch + ingest, bilan par YAML

### Limites MVP

- Repos publics seulement (pas d'auth token GitHub — v2)
- Sync manuel uniquement — la scheduler-based auto-sync arrivera
  en même temps que le task runner dédié
- Max 200 YAMLs par listing (garde-fou), 2 MiB par pack

---

# v0.15.2

## 💾 Backup & Restore à la carte — export / import sélectif

Nouvelle page **Settings → Backup & Restore** qui expose un système de
sauvegarde/restauration à la carte : cochez les ressources voulues,
générez un bundle JSON, réimportez-le dans n'importe quelle install
Romarr (même version majeure).

### Ce qui est backupable

11 types de ressources couverts :
- DAT Sources
- Quality / Region / Dump / Language / Naming Profiles
- Custom Formats
- Download Clients (qBittorrent, SABnzbd, Deluge…)
- Indexers (avec résolution FK par nom pour la portabilité)
- Notifications (Apprise)
- Platform Packs (métadonnées — les YAML doivent être re-uploadés)

### Secrets opt-in

Les passwords, API keys et URLs Apprise sont **chiffrés en DB avec
Fernet** et **exclus par défaut** de l'export. Case à cocher
« Include secrets in export » pour les inclure — utile pour cloner
une install complète, à condition que l'instance cible partage le
même `ROMARR_AUTH_SECRET_KEY`.

### 3 modes d'import

- **Upsert** (défaut) : add + update par name — safe, idempotent
- **Merge** : add-only — préserve les configs existantes
- **Replace** : delete-all + recreate — **destructif**, guardé par
  confirmation UI explicite et libellé rouge

### API

3 endpoints admin-only sous `/api/v3/backup/` :
- `GET /manifest` — liste ressources + compteurs
- `POST /export` — génère le bundle JSON
- `POST /import` — applique le bundle, retourne un bilan par ressource

---

# v0.15.1

## 🐳 Docker & installation — zero-config sur Unraid / Synology / NAS

Installation Docker « il suffit de rebuilder » : trois frictions
historiques éliminées d'un coup.

> [!IMPORTANT]
> Aucune migration DB. Pull `sharkhunterr/romarr:latest` et recréer
> le container. Les operators Unraid qui avaient dû ajouter
> `ROMARR_DATABASE_URL` en manuel peuvent maintenant la retirer.

### 🔑 Une seule variable obligatoire — `ROMARR_AUTH_SECRET_KEY`

Fini le `unable to open database file` au premier boot Docker. La
config SQLite se déduit désormais automatiquement de
`ROMARR_DATA_DIR` (`/data` par défaut dans l'image) via un
`model_validator` Pydantic. Un URL explicite (PostgreSQL par
exemple) reste évidemment respecté. Le `data_dir` est aussi créé
automatiquement s'il n'existe pas — plus de crash silencieux sur
un mount vide.

### 👤 PUID / PGID au runtime — pattern LinuxServer.io

Le volume monté sur Unraid appartient typiquement à `nobody:users`
(99:100). Avant, le container démarrait figé en UID 1000 → refus
d'écriture sur `/data`. Nouveau `entrypoint.sh` :

- Lit les env `PUID` et `PGID` (défaut 1000)
- Aligne le user `romarr` sur ces IDs via `usermod`/`groupmod`
- `chown` `/data` (best-effort — n'échoue pas sur bind mounts NFS/CIFS)
- Dégrade vers `romarr` via `gosu` — PID 1 reste `tini` pour la
  propagation des signaux

Résultat : `PUID=99 PGID=100` dans le template Unraid et ça marche
sans manipuler les permissions sur l'hôte.

### 📱 Modals mobile — footer toujours accessible

Bug UX identifié en ajoutant Deluge : quand le body du modal grandit
(erreur de test de connexion, message d'aide long, formulaire riche),
le footer avec « Cancel / Save / Test » était poussé hors du viewport
mobile et devenait inaccessible.

Cause : les modals étaient en `overflow-hidden` avec un simple
`pt-[8vh]` sur le backdrop — pas de max-height, pas de scroll interne.
Sur écrans courts (téléphones, WebUI overlay Chromecast, etc.), tout
ce qui dépassait était perdu.

Fix appliqué à **23 modals** de l'app (DownloadClients, Indexers,
Profiles ×6, RomPacks ×2, MediaManagement, Notifications, Metadata,
Platforms, DatSources, AddGame, BulkTag/Delete ×3, Logs, Unidentified) :

- Backdrop : `overflow-y-auto py-[4vh] sm:items-center` — scroll global
  en fallback si viewport très court, centrage sur desktop
- Container : `flex max-h-[92vh] flex-col rounded-lg` — hauteur bornée
  qui active le flex-col
- Body : `min-h-0 flex-1 overflow-y-auto` — scroll interne du contenu
  long ; le `min-h-0` est CRUCIAL car flex-1 hérite d'un min-height=auto
  qui ignore l'overflow sinon
- Footer : `shrink-0` — garanti toujours visible

### 🌊 Deluge — download client implémenté

Le stub Deluge devient un vrai client fonctionnel. Deluge 2.0+ est
supporté via son WebUI JSON-RPC (endpoint unique `POST /json`) :

- **Auth** : password WebUI (pas d'username natif chez Deluge)
- **Torrents** : magnet / URL / bytes .torrent — tous supportés
- **Categories** : mappées sur le plugin **Label** de Deluge, auto-
  activé au premier `ensure_category` si absent
- **Idempotence** : re-ajouter un torrent déjà présent retourne son
  hash sans crash (parse du message `"already in session (<hash>)"`)
- **`romarr-imported` flag** : implémenté via un **second label**
  distinct (Deluge n'a pas de tags multiples par torrent)
- **Filter Deluge subtilité** : `is_finished: True` crashe le
  filtermanager Deluge ≤2.2 avec « argument of type 'bool' is not
  iterable » — workaround : on filtre côté Python plutôt que côté
  serveur pour ce champ

Testé end-to-end contre Deluge 2.2.0 (image LSIO) : test_connection,
add_torrent (idempotent), get_status, list_managed_downloads,
set_imported_tag, remove — tous passent.

Prérequis : **le WebUI doit être attaché à un daemon** (Connection
Manager côté Deluge, configuration one-shot). `test_connection` le
détecte et remonte un message actionnable si absent.

### 🎨 Favicons PNG en plus du SVG

Certains clients (vieux browsers, panels Unraid, agrégateurs de
services *arr) n'ingèrent pas le SVG et affichaient un placeholder.
Ajout de `favicon.png` (32) + `favicon-32/64/128.png`, référencés
dans `index.html` en fallback après le SVG. Le browser prend le
format qu'il comprend, ordre déterministe.

---

# v0.15.0

## 🔗 Native integration surface for request managers + search pipeline convergence

This release lands the **IGDB-native integration endpoints** that let
external request managers (Allseerr and any other frontend) drive
Romarr as a first-class *arr, plus a round of search-pipeline polish
where every code path now feeds off a single canonical `match_score`.

> [!IMPORTANT]
> No migration required. Pull `sharkhunterr/romarr:latest` and
> recreate the container. Existing games, releases, profiles,
> settings and API keys are preserved.

---

### 🔗 IGDB-native integration API

- New endpoint `GET /api/v1/platforms` — returns the list of Romarr-
  supported platforms with their IGDB IDs, so a request manager can
  disable its "Request" button for platforms Romarr doesn't handle.
- IGDB-native metadata endpoints so allseerr can propagate the exact
  IGDB IDs through the request → grab → import flow instead of doing
  a fuzzy title match a second time on Romarr's side.
- **Concurrent-add tolerant** : two request managers can add the same
  game at the same time without either losing the race — the second
  add returns the existing record instead of crashing.

### 🎯 Search pipeline — one canonical `match_score`

Every candidate now carries a **single canonical match score** that
follows it from search → display → grab → history. Before, three
different scores lived in three different places (RSS eligibility,
UI ranking, grab decision) and could disagree; now they can't.

- `match_score` is recorded on every history row — including RSS
  and cutoff auto-grab decisions — so you can audit *why* a
  specific candidate was chosen.
- `best_score` on a search summary is the same canonical value,
  not a UI-only re-derivation.
- Manual search modal displays the same score used by auto-grab.

### 🕓 Activity / History redesign

- New history row layout with a compact **timeline component** on
  the game detail page: search → grab → import events on a single
  vertical rail, per-game.
- `HistoryTimeline` React component with tests, replacing the
  previous list-of-cards view.
- Search fan-out and event dispatch cleaned up: fewer noisy
  `dispatch` log lines, better correlation between the row you see
  and the underlying request.

### 🔧 Fixes

- **Importer** now coalesces duplicates instead of emitting the
  bogus `match:no_game` marker on the second incoming file. If
  Romarr already has a matching game, subsequent imports attach
  to it cleanly.
- **AutoCheckAdded** now actually **grabs** eligible candidates —
  before it only surfaced them in search results without pulling
  the trigger.
- **Torznab noise** (unidentified torrents that don't fit any
  known scheme) is no longer logged as a *failed grab* — those
  lines were misleading and drowned real errors.

### 🌐 i18n

- English + French translations refreshed for the activity /
  history strings and the manual-search modal.

### 🧪 Tests

- Expanded coverage for the importer orchestrator (321 new lines),
  search rounds (manual + missing), tasks runners (AutoCheckAdded),
  and event dispatch. `HistoryTimeline` shipped with its own suite.

---

**Migration notes** : none. Bump the image tag, restart. History
rows written before this release keep their `match_score = null`;
new rows populate it.

---

# v0.14.6

## 🎮 Romarr — self-hosted ROM acquisition manager for the *arr ecosystem

Romarr does for retro game ROMs what Sonarr does for TV and Radarr
for film: **search, score, grab, identify, import, organise** — a
DAT-verified library driven by the operational discipline of the
*arr family, in one Docker image with a bundled React UI.

> [!IMPORTANT]
> First image published to Docker Hub. Pull `sharkhunterr/romarr:latest`,
> set `ROMARR_AUTH_SECRET_KEY` (32+ chars), mount `/data`, then open
> `/setup` with the token from the container logs. SQLite migrations
> run automatically on first boot via Alembic; on upgrades, games,
> releases, profiles, settings and API keys are preserved.

---

### 🗂️ DAT-Verified Library

- Games, releases and dumps cross-checked against **No-Intro**,
  **Redump**, **TOSEC** and **MAME** authorities.
- Per-game **History** tab — every search, grab and import that
  touched a game.
- Metadata aggregation across IGDB, ScreenScraper, MobyGames,
  LaunchBox and RetroAchievements, with per-field provenance.
- Cover art, bulk monitoring, library-scoped profile cascade.

### 🎚️ Profile Scoring

- Five-axis profile system — **Quality / Region / Dump / Language /
  Naming** — plus custom formats, bound per library.
- `auto_grab_min_score` floor on the quality profile: the RSS /
  on-add / missing / cutoff auto-grab paths only dispatch a
  candidate scoring at or above it; manual grabs ignore it.
- DAT-aware pre-grab cascade tags each candidate `verified` /
  `hack` / `none` from its SHA-1 / CRC32.

### 🔍 Search & Auto-Grab

- One shared 13-step decision pipeline behind **every** round —
  manual search and auto-grab can never diverge.
- Best-eligible-candidate-per-game selection, platform-mismatch
  hard reject, and an already-imported guard so RSS never
  re-grabs a game already on disk.
- Each round dispatches through one helper that also writes the
  `queue_entry` binding the download back to its game — so the
  importer always identifies the completed file.
- Per-(indexer, game) search-history rows carrying the score
  breakdown and a precise non-grab reason.

### 📊 Activity & Import

- Live download + scheduler-task queue with real-time progress.
- Unified Activity → History feed; click any row for a detail
  sheet with the full score breakdown.
- Import pipeline: archive extract → hash → DAT match →
  convention-aware rename into a `<platform>/<game>/<file>` tree.

### 🎨 Interface

- React 18 PWA, mobile-first, dark theme, FR + EN.
- REST `/api/v3/*` (Sonarr v3-shaped) + SignalR-compat WebSocket.
- Forms login · OIDC SSO · per-user API keys · RBAC.

### 🚢 Release pipeline

- Tag-only GitLab → Docker Hub → GitHub pipeline (`npm run
  release:full`): test → build → publish → deploy → release →
  verify, with multi-arch `linux/amd64` + `linux/arm64` images.

---

### 📥 Install

```yaml
services:
  romarr:
    image: sharkhunterr/romarr:latest
    container_name: romarr
    ports:
      - "8585:8585"
    volumes:
      - ./data:/data
    environment:
      - ROMARR_AUTH_SECRET_KEY=change-me-to-a-32+-char-random-string
      - TZ=Europe/Paris
      - PUID=1000
      - PGID=1000
    restart: unless-stopped
```

Full documentation: <https://github.com/sharkhunterr/romarr#readme>
