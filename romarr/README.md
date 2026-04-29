# Romarr

Self-hosted ROM acquisition manager for the *arr ecosystem. Think
Sonarr / Radarr but for retro video game ROMs — search, grab, identify,
import, organize. Built in the spirit of RomM with the operational
discipline of the *arr family.

## Status

**Pre-alpha.** The catalog of 14 specifications is committed and clarified
under `specs/`; implementation is just starting from `001-foundation`.

## Stack

- Backend: Python 3.12+, FastAPI, SQLAlchemy 2.0 (async), Pydantic v2,
  Alembic, SQLite default + PostgreSQL 15+ optional, Redis 7+ for cache
- Frontend: React 18 + TypeScript strict + Vite + Tailwind +
  shadcn/ui (PWA, mobile-first, FR + EN day one)
- API: REST under `/api/v3/*` (Sonarr v3-shaped) plus a SignalR-compat
  WebSocket at `/signalr/messages`
- Auth: FastAPI-Users + Authlib OIDC, API keys per user
- Notifications: Apprise (single backend)

## Layout

```
specs/                  Complete spec catalog (clarify → plan → tasks)
src/romarr/             Backend Python package
  domain/               Foundation domain model (spec 001)
  identification/       Hasher + parsers + header readers (spec 001)
  ...                   Other layers land as their specs are implemented
tests/                  pytest test suite mirroring src/ layout
.specify/               Spec-Kit configuration and templates
```

## License

GPL-3.0-or-later.
