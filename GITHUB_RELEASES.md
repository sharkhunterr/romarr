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
