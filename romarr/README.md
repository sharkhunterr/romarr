# Romarr

Self-hosted ROM acquisition manager for the *arr ecosystem. Think
Sonarr / Radarr but for retro video game ROMs — search, grab, identify,
import, organize. Built in the spirit of RomM with the operational
discipline of the *arr family.

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

## License

GPL-3.0-or-later.
