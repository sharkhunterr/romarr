# 🎮 Romarr — ROM Acquisition Manager

[![GitHub](https://img.shields.io/github/v/tag/sharkhunterr/romarr?label=version&color=9BBC0F)](https://github.com/sharkhunterr/romarr/releases)
[![Docker Pulls](https://img.shields.io/docker/pulls/sharkhunterr/romarr?color=2496ED)](https://hub.docker.com/r/sharkhunterr/romarr)
[![License](https://img.shields.io/badge/license-GPL--3.0--or--later-green.svg)](https://github.com/sharkhunterr/romarr/blob/main/LICENSE)

**Sonarr / Radarr, but for retro game ROMs** — search, score, grab, identify, import and organise a DAT-verified ROM library for the *arr ecosystem.

---

## 🚀 Quick Start

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

```bash
docker compose up -d
docker compose logs romarr | grep setup_token
```

**Access**: http://localhost:8585 — open `/setup`, paste the `token` from the log line, and create the admin account.

---

## ✨ Features

**🗂️ DAT-Verified Library**
- No-Intro / Redump / TOSEC / MAME authorities
- Games, releases and dumps with per-game history
- Metadata aggregation (IGDB, ScreenScraper, MobyGames, LaunchBox, RetroAchievements)
- Cover art + bulk monitoring

**🎚️ Profile Scoring**
- Quality / Region / Dump / Language / Naming profiles, bound per library
- Tunable `auto_grab_min_score` floor
- DAT-aware pre-grab cascade

**🔍 Search & Auto-Grab**
- Manual · RSS · missing · cutoff · on-add — one shared scoring pipeline
- Best eligible candidate per game, platform-mismatch reject, already-imported guard
- Per-(indexer, game) history rows with score breakdown

**📥 Download Clients**
- Torrent: qBittorrent, Deluge, Transmission
- Usenet: SABnzbd, NZBGet

**📦 Import Pipeline**
- Archive extraction → hash → DAT match → convention-aware rename
- Library exporters (RomM, ES-DE…)

**🖥️ Modern Interface**
- React 18 PWA, mobile-first, FR + EN
- Live download + scheduler-task queue, unified Activity history

---

## ⚙️ Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `ROMARR_AUTH_SECRET_KEY` | — (**required**) | Fernet master key, 32+ chars — encrypts stored credentials |
| `ROMARR_DATA_DIR` | `/data` | Database + covers + downloads + library root |
| `ROMARR_BOOTSTRAP_ENABLED` | `true` | Seed default profiles + Platform Pack + setup token |
| `ROMARR_AUTO_MIGRATE` | `true` | Run `alembic upgrade head` before boot |
| `ROMARR_SCHEDULER_ENABLED` | `true` | Run the scheduler job loop |
| `ROMARR_SPA_ENABLED` | `true` | Serve the bundled React UI at `/` |
| `TZ` | `UTC` | Container timezone |
| `PUID` / `PGID` | `1000` | Host-mapped uid/gid |

### Volumes

| Path | Description |
|------|-------------|
| `/data` | SQLite database, covers, downloads, and the imported ROM library |

---

## 🏷️ Available Tags

| Tag | Description |
|-----|-------------|
| `latest` | Latest stable release |
| `vX.Y.Z` | Specific version |

```bash
docker pull sharkhunterr/romarr:latest
```

**Platforms**: `linux/amd64`, `linux/arm64`

---

## 🔄 Update

```bash
docker compose pull
docker compose up -d
docker image prune -f
```

SQLite migrations run automatically on first boot via Alembic — games, releases, profiles, settings and credentials are preserved across upgrades.

---

## 🛠️ Technical Stack

| Layer | Technologies |
|-------|--------------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic |
| Frontend | React 18, TypeScript, Tailwind CSS, Vite |
| Data | SQLite (aiosqlite) default · PostgreSQL 15+ optional · WebSocket real-time |

---

## 🔗 Links

- [📖 Documentation](https://github.com/sharkhunterr/romarr#readme)
- [🐛 Report Issues](https://github.com/sharkhunterr/romarr/issues)
- [⭐ Star on GitHub](https://github.com/sharkhunterr/romarr)

---

## 📄 License

GPL-3.0-or-later — [LICENSE](https://github.com/sharkhunterr/romarr/blob/main/LICENSE)

---

<div align="center">

**Built with Claude Code 🤖 for the homelab community 🏠**

</div>
