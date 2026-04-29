# Implementation Plan: Frontend (React PWA)

**Branch**: `014-frontend-pwa` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification at `specs/014-frontend-pwa/spec.md`
**Depends on**: `013-rest-api-websocket` — the OpenAPI 3.1 spec is the
single source of truth for type generation; the WebSocket is the source
of live events.

## Summary

The Frontend subsystem is a **mobile-first PWA** that consumes the
backend's REST + WebSocket surface and renders eleven pages plus a
common layout. Code is generated from the OpenAPI spec for type safety
across every request/response. Theme is dark by default with light and
auto variants. UI strings live in i18next bundles (FR + EN day one).

The constitutional gates are tight (Article XV):

1. Every view MUST function on a 360 px viewport.
2. Installable PWA with service-worker-cached reads.
3. shadcn/ui + Tailwind on top of Radix primitives.
4. ROM-specific components first-class.
5. FR + EN minimum, drop-in JSON locales for community translations.
6. Dark mode default; light + auto supported.

This feature ships **eleven page implementations** + **ten ROM-specific
components** + the cross-cutting infrastructure (router, auth guard,
WebSocket client, i18n setup, theme provider, OpenAPI codegen,
service worker, Playwright suite).

## Technical Context

**Language/Version**: TypeScript 5.5+ in `strict` mode.
**Primary Dependencies**: React 18, Vite 5+, Tailwind CSS 3.x,
shadcn/ui (Radix primitives + Tailwind), TanStack Query v5, Zustand,
React Router v6 (data router), i18next + react-i18next, date-fns,
recharts, TanStack Virtual, `vite-plugin-pwa` (Workbox under the
hood), `openapi-typescript` + `orval` for codegen, Playwright for E2E,
Vitest + Testing Library for unit/integration, axe-core (CI checks).
**No backend deps in this feature** — pure frontend.
**Storage**: localStorage (theme, language, recent searches);
IndexedDB indirectly via Workbox runtime caching; the backend's
`user.preferences` JSON for cross-device persistence.
**Testing**: Vitest + @testing-library/react for unit/component;
Playwright for E2E (5 critical paths); Lighthouse CI for the PWA gate;
axe-core CI for accessibility.
**Target Platform**: Modern browsers (Chrome 120+, Firefox 120+, Safari
17+, Edge 120+). The PWA install prompt is Chromium-only by default.
**Project Type**: Single-page React application served from the same
FastAPI app at `/` (the backend's `StaticFiles` mount). The Vite build
output goes into `dist/web` which the Docker image ships at
`/opt/romarr/web/`.
**Performance Goals**:
- Initial-route gzip bundle ≤ 500 KB (SC-009; route-based code-
  splitting + tree-shaking + dynamic imports for heavy charts).
- Library page scrolls a 10 000-item fixture at ≥ 60 fps (SC-002;
  TanStack Virtual + windowed lists).
- First Contentful Paint < 1.5 s on a slow-3G profile (Lighthouse).
- Lighthouse PWA score ≥ 90 across Performance, Accessibility, Best
  Practices, PWA (SC-003).
**Constraints**:
- 360 px viewport functional everywhere (Constitution Article XV;
  FR-001).
- 44 × 44 px hit targets on touch (FR-002).
- No hardcoded strings in JSX (FR-011); eslint enforces.
- TypeScript `strict` with zero errors (FR-039).
- WebSocket is enhancement, not requirement (US edge case 5).
**Scale/Scope**:
- 11+ pages, 10 ROM-specific components.
- Approximately 200 i18n keys per language at MVP; expandable.
- Library fixture target 10 000 Games; production may exceed.
- 5 Playwright E2E paths + critical-path coverage ≥ 60%.

## Constitution Check

*Gate: must pass before Phase 0 research and again after Phase 1 design.*

| Article | Gate | Status |
|---------|------|--------|
| III — Technology Stack (Locked) | React 18 + TypeScript strict + Vite + Tailwind 3.x + shadcn/ui + Zustand + TanStack Query v5; FastAPI WebSockets on the consumer side. | ✅ Conformant. |
| IV — API Conventions & Compatibility Surface | Frontend consumes only the documented `/api/v3/*` and `/signalr/messages` from spec 013; no parallel API. | ✅ Conformant. |
| XV — UI Discipline | Mobile-first 360 px (FR-001 + SC-001); installable PWA (FR-004 + SC-003); shadcn/ui + Tailwind primitives; dark default + light + auto (FR-015); FR + EN day one (FR-012); ROM-specific UI components first-class (FR-027). | ✅ Conformant. |
| XVI — Quality Gates | ≥ 60% coverage on critical paths (FR-041 + SC-006); axe-core CI (FR-037 + SC-007); Lighthouse PWA ≥ 90 (SC-003); bundle ≤ 500 KB gzip (SC-009). | ✅ Conformant. |

**Result**: GREEN. No constitutional violations; **Complexity Tracking**
stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/014-frontend-pwa/
├── plan.md              # this file
├── spec.md              # user-value specification
├── tasks.md             # 16-phase task list (one phase per page + reusable components)
└── checklists/
    └── requirements.md  # spec-quality checklist
```

(No `data-model.md` per the user's explicit request — the frontend
introduces no DB tables. All persistence is the backend's.)

### Source Code (additions to the existing repo)

```text
web/                                    # NEW — frontend root, separate from src/romarr/
├── package.json
├── pnpm-lock.yaml                      # or package-lock.json
├── vite.config.ts                      # PWA plugin, alias paths, build target
├── tsconfig.json                       # strict mode
├── tailwind.config.ts                  # shadcn/ui-friendly theme
├── postcss.config.js
├── index.html
├── public/
│   ├── locales/
│   │   ├── en/
│   │   │   ├── common.json
│   │   │   ├── library.json
│   │   │   ├── settings.json
│   │   │   └── ...
│   │   └── fr/
│   │       └── ... (parallel structure)
│   ├── icons/                          # PWA icons (192, 512, maskable)
│   ├── manifest.webmanifest             # generated by vite-plugin-pwa
│   └── platform-icons.svg              # SVG sprite
├── src/
│   ├── main.tsx                        # bootstraps React + i18n + theme + WS + service worker
│   ├── App.tsx                         # root with router + providers
│   ├── components/
│   │   ├── ui/                         # shadcn/ui primitives
│   │   ├── rom/                        # ROM-specific (10 components)
│   │   │   ├── RegionBadge.tsx
│   │   │   ├── ConventionBadge.tsx
│   │   │   ├── DumpStatusIcon.tsx
│   │   │   ├── MultiDiscAccordion.tsx
│   │   │   ├── HashBadge.tsx
│   │   │   ├── ScoreBadge.tsx
│   │   │   ├── LanguagePills.tsx
│   │   │   ├── DatVerifiedBadge.tsx
│   │   │   ├── PlatformIcon.tsx
│   │   │   └── CoverImage.tsx
│   │   └── shared/
│   │       ├── BottomNav.tsx
│   │       ├── Header.tsx
│   │       ├── EmptyState.tsx
│   │       ├── LoadingSkeleton.tsx
│   │       ├── ActionSheet.tsx          # mobile bottom modal
│   │       ├── FloatingActionButton.tsx
│   │       ├── OfflineIndicator.tsx
│   │       ├── ThemeProvider.tsx
│   │       ├── AuthGuard.tsx
│   │       ├── PullToRefresh.tsx
│   │       └── GlobalSearch.tsx         # ⌘+K modal
│   ├── pages/
│   │   ├── Dashboard/
│   │   ├── Library/                    # uses TanStack Virtual
│   │   ├── Add/
│   │   ├── GameDetail/
│   │   │   ├── index.tsx
│   │   │   ├── tabs/
│   │   │   │   ├── Overview.tsx
│   │   │   │   ├── Releases.tsx
│   │   │   │   ├── History.tsx
│   │   │   │   ├── Files.tsx
│   │   │   │   ├── ManualSearch.tsx
│   │   │   │   └── Notes.tsx
│   │   │   └── components/
│   │   ├── Wanted/                     # tabs: Missing | Cutoff
│   │   ├── Activity/                   # tabs: Queue | History
│   │   ├── Calendar/
│   │   ├── Settings/
│   │   │   ├── index.tsx                # sidebar nav
│   │   │   ├── MediaManagement.tsx
│   │   │   ├── Profiles/
│   │   │   │   ├── index.tsx            # 6 sub-tabs
│   │   │   │   ├── Quality.tsx
│   │   │   │   ├── Region.tsx
│   │   │   │   ├── Dump.tsx
│   │   │   │   ├── Language.tsx
│   │   │   │   ├── Naming.tsx           # live preview
│   │   │   │   └── CustomFormats.tsx
│   │   │   ├── QualityDefinitions.tsx
│   │   │   ├── Indexers.tsx
│   │   │   ├── DownloadClients.tsx
│   │   │   ├── Connect.tsx              # notifications
│   │   │   ├── DatSources.tsx
│   │   │   ├── MetadataSources.tsx
│   │   │   ├── Platforms.tsx
│   │   │   ├── General.tsx
│   │   │   ├── Ui.tsx                   # theme + lang
│   │   │   └── Tags.tsx
│   │   ├── System/
│   │   │   ├── index.tsx
│   │   │   ├── Status.tsx
│   │   │   ├── Logs.tsx
│   │   │   ├── Tasks.tsx
│   │   │   ├── Backup.tsx
│   │   │   └── Updates.tsx              # placeholder
│   │   ├── Login/
│   │   ├── Setup/                      # 5-step wizard
│   │   └── NotFound.tsx
│   ├── lib/
│   │   ├── api/                        # hand-written + generated TanStack Query hooks
│   │   │   ├── client.ts               # axios/fetch wrapper around the generated client
│   │   │   ├── games.ts                # invalidation logic on top of generated hooks
│   │   │   ├── releases.ts
│   │   │   ├── profiles.ts
│   │   │   ├── ...
│   │   │   └── generated/              # codegen output
│   │   ├── i18n/
│   │   │   ├── index.ts                # i18next setup + namespaces
│   │   │   └── dates.ts                # date-fns locale wrapper
│   │   ├── ws/
│   │   │   ├── client.ts               # WebSocket connection with backoff
│   │   │   └── invalidations.ts        # event → query-key invalidation map
│   │   ├── store/
│   │   │   ├── ui.ts                   # theme, language, sidebar state
│   │   │   ├── selection.ts            # bulk-select state for Library / Wanted
│   │   │   └── recentSearches.ts
│   │   └── utils/
│   │       ├── format.ts               # bytes, dates, durations
│   │       └── platform-icon.ts
│   ├── types/                          # OpenAPI-generated types
│   │   └── api/                        # codegen output
│   └── styles/
│       └── globals.css                 # Tailwind directives + theme variables
├── tests/
│   ├── unit/                           # Vitest + Testing Library
│   ├── components/
│   │   └── rom/                        # snapshot tests for the 10 ROM components
│   ├── e2e/                            # Playwright
│   │   ├── search-grab-import.spec.ts
│   │   ├── profile-edit.spec.ts
│   │   ├── library-scan.spec.ts
│   │   ├── setup-wizard.spec.ts
│   │   └── bulk-missing-search.spec.ts
│   └── a11y/
│       └── critical-pages.spec.ts      # axe-core
├── eslint.config.js                    # react/jsx-no-literals enforced
└── README.md                            # frontend dev setup
```

**Structure Decision**: keep the frontend as a **separate sibling**
to the Python backend (`web/` next to `src/romarr/`). Vite builds into
`dist/web` which the Docker image copies into `/opt/romarr/web/`; the
backend's `StaticFiles` mount serves it at `/`. This gives the two
codebases independent toolchains while shipping in a single container.

The `pages/` folder follows the documented layout (one folder per
top-level route, with sub-pages and per-page components nested).
Generated TanStack Query hooks live under
`src/lib/api/generated/` and are committed; hand-rolled hooks (with
invalidation logic on top) live alongside under `src/lib/api/`.

The 10 ROM-specific components are exported from
`src/components/rom/`; every page imports them from there. No page
rolls its own region badge or hash badge.

## Phase 0 — Research

Three small research items resolved before code.

1. **OpenAPI codegen tool** — `openapi-typescript` for types,
   `orval` for TanStack Query hooks. Both are well-maintained,
   Apache-licensed, and produce idiomatic TS. `npm run codegen`
   pulls from `http://localhost:8585/api/v3/openapi.json` (or a
   committed copy at `web/openapi.json` for offline builds).
2. **`vite-plugin-pwa` configuration** — Workbox runtime caching
   for the API namespace (`/api/v3/*`) is `NetworkFirst` with a
   cache fallback; for static assets is `CacheFirst` with
   `expiration` rules. Mutation methods (POST/PUT/PATCH/DELETE)
   are excluded from caching via a runtime route filter.
3. **Mobile gestures** — `react-use-gesture` (or its successor
   `@use-gesture/react`) handles long-press, swipe, and
   pull-to-refresh. The bottom-sheet animation uses Framer Motion
   (already a peer dep of shadcn/ui).

No further research items.

## Phase 1 — Design Outputs

- No `data-model.md` per the user's request (the frontend
  introduces no DB tables).
- No `contracts/` — the contract IS the OpenAPI 3.1 spec served by
  the backend; types are auto-generated.
- A small `web/README.md` ships with this feature documenting
  `npm run dev`, `npm run build`, `npm run codegen`,
  `npm run test`, `npm run e2e`.

### Re-check: Constitution after design

Same table as above; nothing in the design pulls a constraint.
**Result**: GREEN.

## Complexity Tracking

> *Empty.* No constitutional violations. No deviations to justify.

## Clarification Deltas (Session 2026-04-29)

This spec's 10 clarifications (5 prior session + 5 in this session) and
2 cross-spec consistency edits add the following architectural
constraints to this plan:

### From this session's 5 questions

- **Service-worker update — Reload toast** (FR-007a) — `vite-plugin-pwa`
  configured with `registerType: 'prompt'`. Custom toast component
  surfaces the "New version available — Reload" CTA. `skipWaiting` +
  `clients.claim` fire ONLY on user click.
- **SteamGridDB cover swap is backend-proxied** (FR-025a) — frontend
  calls `GET /api/v3/cover/{game_id}/sources` and
  `POST /api/v3/cover/{game_id}` ONLY. The SteamGridDB API key is never
  exposed to the browser. CSP MUST NOT need to allowlist
  `steamgriddb.com` for cover swap.
- **Per-page React error boundaries** (FR-038a) — one boundary scoped
  under the router outlet per top-level page. Fallback: localized title,
  Retry, "Back to Dashboard" link, copyable error id. Header + bottom
  nav remain interactive. NO single global boundary.
- **Server-wins-on-read user preferences** (FR-013b) — `localStorage`
  is a cache, never authority. Every app load (post auth resolver)
  overwrites local from `user.preferences`. Every change PATCHes
  immediately with optimistic UI rollback on failure. No conflict UI,
  no version vectors.
- **No remote frontend error reporting** (FR-038b) — unhandled errors
  outside the boundary scope log to `console.error` and surface a
  generic localized toast. NO `/api/v3/log/frontend` endpoint at MVP;
  NO Sentry/Bugsnag SDK.

### Cross-spec consistency

- FR-009a (OIDC credential) updated: explicitly notes spec 010 dropped
  the JWT path; CLIs use API keys per spec 010 FR-005.

### Implementation notes

- The error-boundary component lives at
  `src/components/shared/PageErrorBoundary.tsx` and is mounted around
  `<Outlet/>` in the router config.
- The SW update toast is a Zustand store `swUpdateStore` + a small
  shadcn/ui toast triggered by `registerSW`'s `onNeedRefresh` callback.
- Preferences hydration order on app boot:
  1. Hydrate auth via `GET /api/v3/auth/me`
  2. Overwrite `localStorage` with `user.preferences`
  3. Apply theme + language from preferences before first render
  This ordering avoids the FOUC fixed by FR-016.
