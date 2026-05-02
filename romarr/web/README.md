# Romarr Web (`web/`)

Romarr's React 18 + TypeScript PWA frontend. Sibling workspace to
the Python backend at `src/romarr/` — independent toolchain,
ships in the same Docker image (the backend's `StaticFiles` mount
serves `dist/` at `/`).

## Stack

- **React 18** + **TypeScript 5** (`strict` mode, zero errors)
- **Vite 5** for build / dev server
- **Tailwind 3** (shadcn/ui CSS variables land in a follow-up
  slice)
- **pnpm 10** — the workspace's package manager (matches the
  pinned `packageManager` field in `package.json`)

## Getting started

```sh
cd web
pnpm install
pnpm dev          # http://localhost:5173 — proxies /api/v3 + /signalr to localhost:8585
pnpm build        # tsc -b && vite build → dist/
pnpm typecheck    # tsc --noEmit, strict
```

## Spec 014 progress

This workspace is the SCAF-phase scaffold. Subsequent slices
land:

- **CODEGEN** — `openapi-typescript` + `orval` against the
  backend's `/api/v3/openapi.json`.
- **SHARED + ROM** — common layout (header, bottom nav, etc.)
  and the 10 ROM-specific components (RegionBadge,
  DumpStatusIcon, MultiDiscAccordion, …).
- **ROUTING** — React Router v6 data router + auth guard +
  theme provider.
- **WS** — WebSocket client with auto-reconnect.
- **PWA** — `vite-plugin-pwa` + Workbox runtime caching.
- 11 page implementations (Dashboard, Library, Add New, Game
  Detail, Wanted, Activity, Calendar, Settings, System, Login,
  Setup).

See `specs/014-frontend-pwa/` for the full task list.
