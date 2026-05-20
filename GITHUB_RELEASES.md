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
