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


# v0.15.0

## 🌟 Big-picture — the community-first release

Two headline stories : platforms + custom formats no longer ship
as wheel-bundled seeds, they land from operator-registered
community URLs surfaced through a **unified Update Center** in
the header. And a dense stretch of QoL / infrastructure work
consolidates everything shipped since v0.14.11.

---

## 🌐 Update Center — one hub for every community URL

New central manager for URL-driven resources (Custom Formats +
Platform Packs today, extensible per `resource_type`). Lives at
**Paramètres → Mises à jour** and is embedded on both the
Platforms and Custom Formats settings pages — a source added
anywhere shows up everywhere.

- **Aggregated header badge** (green / amber / red) with a
  popover that lists every pending update from Romarr GitHub AND
  every community source in one glance. One-click "Appliquer"
  from the popover.
- **Card layout per source** with an URL shortener
  (`raw.githubusercontent.com/…` → `github.com/owner/repo`),
  4-state version pill (never synced / new / up-to-date /
  update available), and colour-coded action icons (Check /
  Preview / Edit / Trust / Apply / Enable / Delete).
- **Trust flow** — a newly added source starts `pending` : apply
  is blocked until the operator previews the manifest and clicks
  "Faire confiance". No silent side effects, ever.
- **Editable name + URL** — a URL swap resets version tracking
  and flips trust back to pending, because it's semantically a
  new source.
- **Preview modal** — dry-run manifest fetch (name / version /
  item count / item list) that never touches the DB.
- **Local file import** (`.json` with `inline_items` or `.zip`
  with `manifest.json` + item files, 5 MiB cap) for air-gapped
  installs — same ingest pipeline as an online apply.
- **Background sweep every 6 h** via the new `CommunitySync` task
  runner (seeded ON by default). Check-only : lights the badge
  amber when a new version lands upstream, apply stays operator-
  driven.

## 🎮 Platforms — community-first bootstrap

The wheel-bundled builtin platform pack no longer auto-applies
on boot. Migration **0042** preseeds an official community
source pointing at `sharkhunterr/romarr-plateform-pack` and the
lifespan hook auto-fetches + auto-applies it in the background,
so the server starts serving immediately. Offline installs get
a clear empty-state banner pointing at the URL / file paths
above.

**Per-source conflict resolution** (migrations 0043, 0044) —
when multiple sources declare the same slug the operator picks
per (source, slug) between three modes :

- **`use`** (default) : arrays merge across sources; scalars
  decided by global rank.
- **`prefer`** : this source wins scalars for the slug even if
  another source is higher-ranked.
- **`skip`** : this source's contribution is dropped entirely.

Plus a **drag-drop `source_order`** editor to break scalar ties
when no `prefer` fires. The materializer stores per-(source,
slug) JSON snapshots and rewrites the live `platform` row from
the aggregate : scalars from the winner, arrays (aliases,
formats, naming_tokens, newznab_ids) union-merged across every
non-skipped source.

**Redesigned Platforms page** :

- Old "Platform Packs" YAML application history and the built-in
  toggle panel are gone (both obsolete with the community-first
  model).
- Catalogue grid becomes 1 / 2 / 3 columns with proper visual
  hierarchy : name + up-to-3 colour-coded source-initial badges,
  short_name pill · slug · manufacturer · year, aliases summary.
- Detail modal gains a **"Sources qui contribuent"** section
  showing every contributor with a highlighted "Actif" badge on
  the source whose scalars are currently live.

## 🧩 Custom Formats — community packs + per-CF control

- **URL-imported CF packs** via the same Update Center
  infrastructure. Each imported CF surfaces an **origin badge**
  (Built-in / Community · pack name / Manual) on the settings
  row.
- **On/off toggle** per CF — a disabled CF stays in the table
  but the search + importer pipelines skip it when aggregating
  scores. Toggling doesn't flip `is_user_modified`, so community
  sync keeps overwriting the seed body normally after the flip.
- **Compact single-line row layout** with icon-only actions
  (toggle switch + chevron + Pencil + Trash) — was ~180 px tall,
  now ~48 px.
- **Match-guards** to reject cross-franchise false positives out
  of the box :
  - **Subtitle-separator guard** — "The Legend of Zelda" no
    longer fuzzy-matches "The Legend of Zelda - Skyward Sword"
    (Wii U game that isn't the NES original) or "Zelda: Ocarina
    of Time".
  - **File-extension → platform guard** — a `.wbfs` release is
    hard-rejected on a NES-target game (physically impossible)
    via the existing `PlatformFormatBounds` mapping.
- **New CF seeds** — `aftermarket-bootleg-pirate` (-10000) and
  `homebrew-unlicensed` (-1000) so bootleg / pirate reproductions
  are auto-rejected out of the box.
- **Manifest-driven `pack_version`** for platform-pack YAMLs :
  operators can omit the version from the YAML and let
  `manifest.version` carry the single source of truth. The
  adapter injects it at ingest time.

## 🎯 Games — post-add edit modal

New **"Modifier"** button on the game detail header lets the
operator change monitoring + library binding after add (previously
only possible at add time). Backed by a new `useUpdateGame` hook
sending partial PATCH payloads.

## 🔔 Version-check surface

`GET /api/v3/system/version-check` hits GitHub releases with a
1 h in-process cache; the header badge shows the current version
and turns amber when a newer release is available. Mirrored on
Grabarr's admin panel too.

---

## 🐳 Docker & installation — zero-config deployments

Container installs now boot on any NAS / homelab without a
custom compose file :

- **Runtime PUID / PGID** — the entrypoint honours the LSIO-style
  `PUID` / `PGID` env pair and re-owns `/data` before dropping to
  the `romarr` user via `gosu`. Unraid, Synology and QNAP all
  work out of the box.
- **SQLite auto-placement** — no more mandatory
  `ROMARR_DATABASE_URL`. When unset, the settings resolver builds
  an absolute `sqlite+aiosqlite:///` URL under `ROMARR_DATA_DIR`
  and creates the directory if missing.
- **Favicon** — 32 / 64 / 128 PNGs shipped alongside the SVG so
  browsers that ignore SVG favicons don't fall back to a blank
  tab.
- **Dockerfile fixed to bundle `examples/`** — the wheel build
  needs `examples/platform-packs/` for its hatchling
  force-include mapping; the Dockerfile now `COPY`s it.

---

## ⬇️ Deluge — first-class download client

The Deluge stub is gone. `DownloadClient` now supports Deluge
2.0+ end-to-end via its WebUI JSON-RPC :

- Full CRUD from the UI, connectivity probe, category creation
  through the Label plugin (auto-enabled if missing)
- State-machine mapping (`Downloading`, `Seeding`, `Paused`,
  `Error`, `Completed`) → Romarr's canonical `DownloadState`
- Handles all three add-flavours : magnet URI, torrent URL, raw
  bytes (`.torrent` upload)
- Idempotent `add_torrent` — Deluge's "already in session
  (`<hash>`)" reply is parsed as success, not failure
- Client-side filter workaround for Deluge ≤ 2.2's bug where
  `is_finished: True` in `filter_dict` crashes the daemon
- `set_imported_tag()` renames the label to `imported` so the
  importer knows what it's already processed
- Full activity + import wiring : queue reconciler tracks Deluge
  jobs, the webhook importer accepts
  `download_client_kind='deluge'`, folder-mapping-based imports
  work identically to qBittorrent / SABnzbd

---

## 📱 Mobile UX — modals always usable

Every modal footer used to slip below the viewport on portrait
phones as soon as the body grew — 23 modals rewritten to the same
flex pattern :

- Backdrop is scrollable (`overflow-y-auto py-[4vh]
  sm:items-center`)
- Container is bounded (`flex max-h-[92vh] flex-col`)
- Body scrolls internally (`min-h-0 flex-1 overflow-y-auto`)
- Footer buttons stay pinned (`shrink-0`)

Applied uniformly across every operator-facing dialog.

---

## 💾 Backup & Restore — à la carte export / import

New **Settings → Backup & Restore** page + admin-only API
(`/api/v3/backup/{manifest,export,import}`) covering **13
resource types** :

- DAT sources · Quality / Region / Dump / Language / Naming
  profiles · Custom formats
- Indexers (with FK-by-name resolution for portability) ·
  Download clients
- Notifications (Apprise)
- Platform packs (metadata-only — YAML bodies re-fetch on demand)
- Pack sources · Platform-pack config

**Three import modes** : `upsert` (default, add + update by
name), `merge` (add-only, preserves existing), `replace`
(destructive wipe + recreate, guarded by an explicit UI
confirmation and red button).

**Secrets are opt-in** on export — passwords, API keys and
Apprise URLs (Fernet-encrypted in the DB) are excluded by
default. Include-secrets tick is required to bundle them ; the
target install must share the same `ROMARR_AUTH_SECRET_KEY` to
decrypt.

---

## 🌐 Platform packs — GitHub-sourced with preview + auto-sync

The built-in platform pack is no longer the only game in town.
Operators can register any GitHub URL as a trusted pack source
and let Romarr sync from it on demand or on a schedule.

### Pack sources — configurable at will

**Settings → Platforms → Pack sources** panel with :

- Name + URL entry ; kind auto-detected :
  - `raw` — the URL points at a single `*.yaml` file
  - `github_dir` — the URL points at a repo directory
    (`github.com/{owner}/{repo}/tree/{branch}/{path}` or the
    REST contents endpoint), the walker fetches every YAML child
- Enable / disable, sync-now, delete
- Per-source stamp of `last_synced_at`, `last_status`
  (`ok | partial | error`), `last_error`, `last_applied_count`

Only public repos in this release ; auth-token support for
private repos is deferred.

### Preview before apply

**Preview** button on every source opens a modal listing each
YAML with its dry-run outcome (`would_apply`, `would_skip`,
`would_fail`) plus the per-platform diff (insertions, updates,
warnings). Zero DB writes. Includes an **Apply now** shortcut
that chains straight into a real sync without re-fetching.

### Scheduled auto-sync

New `PackSourcesSync` job in the scheduler catalogue
(`Settings → Tasks`) — daily at 05:00, disabled by default.
Operators enable it once they have at least one source
registered. Per-source outcomes are stamped on the row visible in
`Settings → Platforms`.

### Toggle + priority for the built-in pack

New singleton config surface `platform_pack_config`
(migration 0038) with two knobs on **Settings → Platforms →
Pack configuration** (top of the page) :

- **`builtin_enabled`** — gates the boot-time auto-apply of the
  wheel-bundled built-in pack. Off = the install runs on
  community sources only.
- **`priority`** = `"community"` (default) — natural apply order,
  community's later apply wins overlapping slugs — or
  `"builtin"` — after every community sync, re-apply the
  built-in over shared slugs so its values remain
  authoritative.

Endpoints : `GET` / `PATCH /api/v3/rom/platform-pack-config`.

### Built-in pack — clean layout + auto-discovery

The two historical built-in YAMLs
(`builtin-2026.04.001.yaml`, `builtin-2026.05.002.yaml`) moved
out of `src/romarr/builtin_packs/` (bundled resource) into a
browsable `examples/platform-packs/` folder alongside the
community example, `platform-pack-community.yaml`. Hatchling
`force-include` keeps them bundled into the wheel at the same
runtime path — no wheel API change.

Loader dropped its hardcoded `_BUILTIN_PACK_VERSION = "..."`
constant and auto-discovers the newest `builtin-YYYY.MM.NNN.yaml`
by lexical version sort. **Shipping a new built-in is now a
single YAML drop — zero Python change**.

### Platforms page reorganised

Actionable settings (config + sources + packs history) now lead
the page. The catalogue grid moved to the bottom — it's the
read-only tail of the pipeline, not what operators come to
configure.

---

## 📂 Library create modal — filesystem browser

The library-create form used to ask for a bare absolute path.
It now embeds a **Browse…** button that opens an in-place
directory browser :

- Root listing surfaces `/data`, `/downloads`, `/roms`,
  `/media`, `/mnt`, `/config`, `/srv`, `/opt`, `/home`, `/app`,
  `/library`, `/games` — filtered to whatever actually exists in
  the container
- A `mount` badge flags entries that sit on a different
  filesystem from their parent (strong hint of a Docker volume)
- Breadcrumbs, `..` navigation, per-entry Pick + "Pick current
  directory" shortcut
- Manual text entry stays live above the picker — the picker is
  additive, never the only entry channel

Blocked prefixes for defense-in-depth : `/proc`, `/sys`, `/dev`,
`/boot`, `/etc`, `/root`, `/run`, `/tmp`, `/var/log`,
`/var/lib/docker`.

Endpoint : `GET /api/v3/system/filesystem?path=<abs>` (admin).

---

## 👁 Secret fields — pre-fill + eye toggle

Editing an existing API key no longer means retyping it from
scratch. Two configure modals rebuilt around a new reusable
`SecretInput` component :

- **Settings → Metadata Sources → Configure** — pre-fills every
  provider's decrypted config (IGDB client id + secret,
  ScreenScraper ssid + password + optional dev key,
  MobyGames / SteamGridDB / RetroAchievements API keys) so
  tweaking one field is a one-line edit. Auto-expands the
  Advanced disclosure when it contains a stored value.
- **Settings → Indexers → Edit** — same treatment for the
  `api_key` field.

Every secret field now embeds an **eye icon on the right** to
reveal / hide the value in place. Revealed values render in
monospace to make long tokens easier to eyeball. State is
component-local — never persisted, never leaked across mounts.

Endpoints (admin-only, never invoked by list / read paths) :

- `GET /api/v3/metadata/provider/{name}/secrets` → decrypted
  JSON dict, `{}` if unset
- `GET /api/v3/indexer/{id}/secrets` →
  `{"api_key": "..." | null}`

---

## 🔧 Test hygiene + build correctness

- Deluge stub tests rewritten to match the real implementation
  (available = True, constructor requires credentials)
- Provider-schema test flipped the Deluge assertion
- Seeder tests rewired against `len(DEFAULT_CATALOGUE)` so
  future catalogue growth doesn't need a test diff
- Scheduler flaky test (`test_disabled_job_raises_unless_forced`)
  ported to `service.await_run()` — deterministic wait via the
  scheduler's inflight bookkeeping instead of DB polling. The
  `tests/tasks/` bucket now runs 189 / 189 green under
  concurrent load

## 🗂 Migrations

- `0037_pack_sources` — remote pack-source registry table
- `0038_platform_pack_config` — singleton config row (builtin
  toggle + priority)

---

# Draft notes (never tagged) — Native integration surface

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
