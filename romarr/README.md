# Romarr

Self-hosted ROM acquisition manager for the *arr ecosystem. Think
Sonarr / Radarr but for retro video game ROMs — search, grab, identify,
import, organize. Built in the spirit of RomM with the operational
discipline of the *arr family.

> [!WARNING]
> **Vibe-coded project** — this application was built through
> AI-assisted development using [Claude Code](https://claude.ai/code).
> All architectural decisions, product direction, feature scope, UX
> choices, DB schema, API contracts, and design tradeoffs were made by
> the project maintainer; the AI acted as an implementation partner
> turning those decisions into code. Every review, refactor, and
> release call comes from a human.

## Quickstart (Docker)

```bash
docker build -t romarr .
docker run -d \
  --name romarr \
  -p 8585:8585 \
  -v /srv/romarr/data:/data \
  -e ROMARR_AUTH_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  romarr
docker logs romarr | grep setup_token
```

Capture the `token` value from the WARNING line, then complete setup
with `POST /api/v3/auth/setup` (or visit `http://localhost:8585/setup`
once the SPA boots) and provide an admin username + password. The
session cookie auto-logs you in.

The image defaults `ROMARR_BOOTSTRAP_ENABLED=true`,
`ROMARR_AUTO_MIGRATE=true`, `ROMARR_SCHEDULER_ENABLED=true`, and
`ROMARR_SPA_ENABLED=true` so a fresh container produces a working
install. Override any of these via environment variables.

## Quickstart (development)

```bash
# Backend
uv sync
ROMARR_AUTH_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(32))') \
  uv run romarr migrate
ROMARR_AUTH_SECRET_KEY=… ROMARR_BOOTSTRAP_ENABLED=true \
  uv run romarr serve --port 8585

# Frontend (separate terminal)
cd web && pnpm install && pnpm dev
```

The Vite dev server proxies `/api/v3/*` to the backend on port 8585.

## CLI

- `romarr serve` — boot uvicorn + the FastAPI app. Honours the
  `ROMARR_*_ENABLED` env flags.
- `romarr migrate` — run `alembic upgrade head` against the configured
  database. Useful when `ROMARR_AUTO_MIGRATE` is off and migrations
  belong to a separate CI step.
- `romarr metadata reencrypt` — rotate the master encryption key for
  stored provider credentials (rotation flow lands in 0.2).

## Companion: Grabarr

Romarr pairs perfectly with
[Grabarr](https://github.com/sharkhunterr/grabarr) — a companion
project that exposes ROM repositories and shadow libraries
(Vimm's Lair, Edge Emulation, RomsFun, CDRomance, MyAbandonware,
Internet Archive, and more) as standard **Torznab indexers**.

Traditional torrent trackers cover a fraction of the retro-gaming
catalogue; the rest lives on HTTP-only sites that Prowlarr can't
reach natively. Grabarr bridges that gap : it scrapes those sources
and generates seedable `.torrent` files on the fly, so from Romarr's
perspective they behave like any other indexer returning candidates.

**Recommended setup**

1. Deploy Grabarr next to Romarr (same Docker network is easiest).
2. Register Grabarr's Torznab URL in Prowlarr (one indexer slot,
   covers every upstream Grabarr aggregates).
3. Register Prowlarr in Romarr's **Settings → Indexers**.
4. Add a monitored game — Romarr's cutoff-search + auto-grab
   pipeline now reaches every source Grabarr indexes without
   further configuration.

The full flow (Romarr → Prowlarr → Grabarr → shadow source →
BitTorrent client → Romarr importer) is documented on Grabarr's
repository.

## Stack

- **Backend**: Python 3.12+, FastAPI, SQLAlchemy 2.0 (async), Pydantic
  v2, Alembic, SQLite default + PostgreSQL 15+ optional, Redis 7+ for
  cache (optional, in-memory fallback present)
- **Frontend**: React 18 + TypeScript strict + Vite + Tailwind +
  shadcn/ui (PWA, mobile-first, FR + EN day one)
- **API**: REST under `/api/v3/*` (Sonarr v3-shaped) plus a SignalR-
  compat WebSocket at `/signalr/messages`
- **Auth**: forms login + OIDC SSO + per-user API keys + trusted-proxy
  headers, role-based access (admin / user / readonly), sliding 30-day
  sessions, login rate-limit
- **Notifications**: Apprise (single backend, Sonarr/Radarr-shaped
  webhook payloads)

## Layout

```
specs/                  Complete spec catalogue (14 specs, clarify → plan → tasks)
src/romarr/             Backend Python package
  domain/               Foundation domain model (spec 001)
  identification/       Hasher + parsers + header readers (spec 001)
  metadata/             Multi-source metadata aggregation (spec 002)
  platform_packs/       YAML-bundled platform definitions (spec 003)
  indexers/             Newznab + Torznab + Prowlarr (spec 004)
  downloaders/          qBittorrent + SABnzbd (spec 005)
  profiles/             Quality / Region / Dump / Language / Naming /
                        Custom Format (spec 006)
  search/               13-step decision pipeline + cache + blocklist (spec 007)
  importer/             Webhook + extract + DAT match + move (spec 008)
  libraries/            CRUD + scanner + exporters (spec 009)
  auth/                 Forms / OIDC / API keys / proxy / RBAC (spec 010)
  notifications/        Apprise dispatcher + health engine (spec 011)
  tasks/                APScheduler + per-job runners (spec 012)
  api/                  FastAPI factory + middleware + routers (spec 013)
  cli/                  `romarr serve` / `migrate`
  db/                   Alembic migration env + helpers
web/                    React SPA (spec 014)
tests/                  pytest test suite mirroring src/ layout
.specify/               Spec-Kit configuration and templates
Dockerfile              Multi-stage build (Node 20 SPA → Python 3.12 runtime)
```

## Legal & responsibility

Romarr is a **search, decision, and organization tool**. It does not
host, seed, distribute, or provide ROM images, DAT files, cover art,
or any other copyrighted material. Every byte transits between the
operator's indexers, download clients, and storage without ever
touching Romarr's own infrastructure.

Users are solely responsible for ensuring they have the legal right
to acquire, store, and use any content that flows through Romarr's
indexer / downloader / importer pipelines, in accordance with the
copyright, dumping, and preservation laws of their jurisdiction. The
Romarr project and its maintainers assume no liability for how the
software is used and make no representation about the legality of
any content the operator chooses to route through it.

## Acknowledgments

**The Need**: the *arr ecosystem is brilliant for movies, TV, music,
and books, but retro-game ROMs are a category of their own — with
DAT verification, region priorities, revision tracking, and a
sprawling ecosystem of shadow archives that traditional torrent
indexers don't cover. Managing a serious collection by hand doesn't
scale.

**The Solution**: Romarr brings the *arr playbook to retro gaming —
monitored games, quality profiles, custom formats, cutoff-based
upgrades, DAT-verified imports, per-region priorities, and a
webhook-driven importer that plays nicely with the same download
clients the rest of the *arr family talks to.

**The Approach**: as a young parent with limited time and no
fullstack development background, traditional coding wasn't an
option. Romarr was built with [Claude Code](https://claude.ai/code)
as an implementation partner — every architectural decision, spec,
DB schema, API surface, UX pattern, and review call was made by the
project maintainer; the AI translated those calls into code, ran the
tests, and shipped the diffs the human approved.

Inspired by the *arr family (Sonarr, Radarr, Readarr, Lidarr,
Prowlarr) and by [RomM](https://github.com/rommapp/romm) for the
retro-gaming domain model.

## License

GPL-3.0-or-later.
