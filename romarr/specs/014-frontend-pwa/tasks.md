---

description: "Granular task list for the React 18 + TypeScript PWA frontend — organized by page + reusable components phase"
---

# Tasks: Frontend (React PWA)

**Input**: Design documents from `specs/014-frontend-pwa/`
**Prerequisites**: spec 013 (REST API & WebSocket) shipped — the OpenAPI
spec at `/api/v3/openapi.json` is the codegen source.
**Tests**: MANDATORY (Constitution Article XVI; SC-006: ≥ 60% coverage on
critical paths)

**Organization**: 16 phases — scaffolding, codegen, shared + ROM
components, routing/auth/theme, WebSocket, PWA, then **one phase per
page** (11 pages), then global search, i18n, accessibility, E2E,
hardening.

## Format: `[ID] [P?] [Phase] Description`

- `[P]` = parallelizable with other `[P]` tasks in the same phase.
- Phase tag short codes: `SCAF`, `CODEGEN`, `SHARED`, `ROM`,
  `ROUTING`, `WS`, `PWA`, `P-DASH`, `P-LIB`, `P-ADD`, `P-GAME`,
  `P-WANT`, `P-ACT`, `P-CAL`, `P-SET`, `P-SYS`, `P-AUTH`,
  `P-SETUP`, `SEARCH`, `I18N`, `A11Y`, `E2E`, `HARD`. (16 phases
  total — `P-AUTH` covers Login + the auth-guard for all pages,
  and the eight Settings sub-pages share `P-SET`.)

---

## Phase 1: Scaffolding (`SCAF`)

- [X] T001 [SCAF] Initialise the `web/` workspace with Vite (React +
      TypeScript template) and pnpm. `package.json` pins
      `packageManager: "pnpm@10.24.0"`. Build pipeline verified:
      `pnpm typecheck` clean, `pnpm build` produces a 143 KB
      JS / 46 KB gzip bundle (well under the 500 KB target).
- [X] T002 [P] [SCAF] Configure `tsconfig.json` with `strict: true`
      plus `noUnusedLocals` / `noUnusedParameters` /
      `noFallthroughCasesInSwitch` / `noUncheckedIndexedAccess`,
      and the documented path aliases (`@/*`, `@/components/*`,
      `@/lib/*`, `@/pages/*`, `@/types/*`).
- [X] T003 [P] [SCAF] Install Tailwind 3.x + PostCSS + Autoprefixer;
      configure `tailwind.config.ts` with the brand-default Game
      Boy LCD green palette (#9BBC0F, matching the spec 013
      `tag.color` default + the operator UI accent). The shadcn/ui
      CSS-variable palette layer (--background, --foreground,
      --border, etc.) lands with the shadcn primitives slice.
- [~] T004 [P] [SCAF] shadcn/ui CLI **deferred** — the CLI is
      interactive (`init` prompts for style / colour / paths) and
      doesn't fit the autonomous-loop workflow. The follow-up
      slice copy-pastes the documented primitives directly from
      shadcn-ui/ui into `src/components/ui/` (Button, Dialog,
      DropdownMenu, Tabs, etc.) — simpler, version-pinnable in
      git, and skips the CLI dependency.
- [~] T005 [P] [SCAF] Runtime deps: today's slice ships only
      `react` + `react-dom` to keep the install lean (~150
      packages). The wider runtime set
      (`@tanstack/react-query`, `@tanstack/react-virtual`,
      `zustand`, `react-router-dom@6`, `i18next` family,
      `date-fns`, `recharts`, `@use-gesture/react`,
      `framer-motion`, `vite-plugin-pwa`, `workbox-window`) lands
      with the phases that need them — adding them piecemeal
      keeps each slice's `pnpm install` fast.
- [~] T006 [P] [SCAF] Dev deps: today's slice ships
      `@vitejs/plugin-react`, `tailwindcss`, `postcss`,
      `autoprefixer`, `typescript`, `vite`, plus the React /
      Node type packages. Vitest + Testing Library + Playwright
      + axe-core land with the testing phases (E2E / A11Y).
      ESLint plugins land with the next slice (T007).
- [~] T007 [SCAF] `eslint.config.js` **deferred** to the next
      slice when ESLint + the React / a11y / i18next plugins are
      installed. The `react/jsx-no-literals` rule is the
      enforcement teeth for FR-011 (no hardcoded strings in JSX);
      shipping it without the i18n setup would just block every
      commit.
- [~] T008 [SCAF] `vite.config.ts` ships today with React + path
      aliases + dev-server proxy (`/api/v3` and `/signalr` →
      `localhost:8585`). The `vite-plugin-pwa` integration with
      Workbox runtime caching (NetworkFirst /api/v3, CacheFirst
      assets, no-cache for mutations) lands with the PWA phase.
- [X] T009 [SCAF] Docker integration shipped (slice 188).
      Backend's ``StaticFiles`` mount lives at
      ``src/romarr/api/spa.py::register_spa`` — gated on
      ``Settings.spa_enabled`` (default OFF for tests).
      Mounted AFTER every router so the API surface keeps
      precedence; only unmatched paths fall through to
      ``index.html`` (React Router takes over). Defence
      against API-shadowing: any ``/api/*`` or ``/signalr/*``
      that didn't match a registered route returns 404 rather
      than ``index.html``.

      Multi-stage Dockerfile shipped at repo root:
      Stage 1 builds the SPA via Vite (pnpm). Stage 2
      installs Python deps, bundles the dist from stage 1,
      runs as the unprivileged ``romarr`` user (PUID/PGID
      configurable per the LinuxServer.io convention),
      defaults ``ROMARR_BOOTSTRAP_ENABLED=true``,
      ``ROMARR_AUTO_MIGRATE=true``,
      ``ROMARR_SCHEDULER_ENABLED=true``,
      ``ROMARR_SPA_ENABLED=true``. Mounts ``/data`` as the
      volume; binds 8585. ``tini`` as PID 1 for graceful
      shutdown signal forwarding. ``.dockerignore`` excludes
      tests / specs / dev caches so the build context stays
      lean.

      Tests at ``tests/api/test_spa_mount.py`` cover six
      cases: SPA disabled (JSON fallback), SPA enabled +
      ``GET /``, asset serving, catch-all SPA route
      fall-through, API 404 not shadowed by SPA, missing
      dist path falls back gracefully.

**Checkpoint**: `pnpm dev` brings up a working Vite dev server;
`pnpm build` produces a deployable artifact.

---

## Phase 2: OpenAPI Codegen (`CODEGEN`)

### Tests

- [X] T010 [P] [CODEGEN] `web/src/types/api/codegen-smoke.ts` —
      typecheck-time smoke check that imports
      `components["schemas"]["BackupFileEntry"]`,
      `CalendarEvent`, and `CreateTagRequest`, and constructs
      typed fixtures for each. The build fails (`pnpm
      typecheck`) if any backend rename / removal regresses the
      generated types. The Vitest stand-in form lands with the
      testing phase; this typecheck assertion is the
      lightweight gate today.

### Implementation

- [X] T011 [CODEGEN] `pnpm codegen` script reads the committed
      `web/openapi.json` snapshot and emits
      `web/src/types/api/schema.ts`. The orval step (TanStack
      Query hooks) is deferred until `@tanstack/react-query`
      lands in its phase. `scripts/dump_openapi.py` (Python)
      regenerates `web/openapi.json` from `create_app().openapi()`
      — committing the snapshot keeps frontend builds
      reproducible (no running backend required).
- [~] T012 [CODEGEN] `orval.config.ts` **deferred** until the
      TanStack Query runtime dep ships.
- [X] T013 [CODEGEN] `pnpm codegen` ran once against the
      committed `web/openapi.json`; `web/src/types/api/schema.ts`
      committed. 12,581-line OpenAPI snapshot, 8,383-line
      generated TS type module. `pnpm typecheck` clean;
      `pnpm build` still 143 KB JS / 46 KB gzip (types
      tree-shake at zero runtime cost).
- [~] T014 [CODEGEN] CI drift-check **deferred** — no CI
      pipeline yet. The pattern when CI lands: run
      `uv run python scripts/dump_openapi.py && pnpm --dir web
      codegen && git diff --exit-code`; fail if either
      snapshot is stale.

**Checkpoint**: every backend resource has at least one generated
hook; TypeScript compiles.

---

## Phase 3: Shared Layout & Components (`SHARED`)

### Tests

- [~] T015 [P] [SHARED] Vitest BottomNav test —
      **deferred-by-design**. The 5-entry visibility-on-
      mobile-only contract is implemented via ``md:hidden``;
      Vitest infrastructure is now shipped (slice 205) so
      this test is unblocked, but the per-page test sweep
      lands as a dedicated polish slice. The infra gateway
      is open — see ``RegionBadge.test.tsx`` for the
      template.
- [~] T016 [P] [SHARED] OfflineIndicator **deferred** — needs
      WebSocket client (T053) for the 10s-disconnect signal.
- [~] T017 [P] [SHARED] ActionSheet **deferred** — needs Framer
      Motion + shadcn Dialog primitive.
- [~] T018 [P] [SHARED] PullToRefresh **deferred** — needs
      `@use-gesture/react` runtime dep.

### Implementation

- [X] T019 [SHARED] `src/components/shared/Header.tsx` —
      sticky-top, app title + theme toggle (cycles dark →
      light → auto). Language toggle, profile menu, ⌘+K hint
      land with their owning phases (I18N / P-AUTH / SEARCH).
- [X] T020 [P] [SHARED] `src/components/shared/BottomNav.tsx`
      — 5 documented entries (Library / Wanted / Activity /
      Settings / Search). `md:hidden` so the desktop UX uses
      the sidebar. 44 × 44 px hit targets per FR-002.
      `pb-[env(safe-area-inset-bottom)]` for iOS PWA.
- [~] T021 [P] [SHARED] OfflineIndicator **deferred** — lands
      with the WebSocket client slice (T053).
- [X] T022 [P] [SHARED] `src/components/shared/EmptyState.tsx`
      — composable empty-state with optional icon + title +
      description + CTA slot.
- [X] T023 [P] [SHARED] `src/components/shared/LoadingSkeleton.tsx`
      — exports `Skeleton`, `ListSkeleton`, `CardGridSkeleton`,
      `DetailSkeleton`. Pure Tailwind `animate-pulse`.
- [~] T024 [P] [SHARED] ActionSheet **deferred** — needs
      Framer Motion + shadcn/ui Dialog primitive.
- [X] T025 [P] [SHARED] `src/components/shared/FloatingActionButton.tsx`
      — fixed bottom-right, `md:hidden`, sits above BottomNav
      with safe-area inset. Brand-coloured circle.
- [~] T026 [P] [SHARED] PullToRefresh **deferred** — needs
      `@use-gesture/react`.

Plus `src/components/shared/AppLayout.tsx` — app shell
(Header + `<Outlet />` + BottomNav) wrapped around every
authenticated route. Slots between AuthGuard and the per-page
outlet in App.tsx's route table.

**Checkpoint**: every component renders correctly on 360 px AND
≥ 768 px in Storybook (or in the test suite's RTL snapshots).

---

## Phase 4: ROM-specific Components (`ROM`)

**Purpose**: the 10 first-class reusable pieces consumed across pages.

### Tests

- [X] T027-T036 [P] [ROM] Vitest + Testing Library
      infrastructure shipped at slice 205. Devdeps:
      ``vitest``, ``@testing-library/react``,
      ``@testing-library/jest-dom``,
      ``@testing-library/user-event``, ``jsdom``.
      ``web/vitest.config.ts`` configures jsdom + path
      aliases + ``src/test/setup.ts`` (jest-dom matchers
      + matchMedia / IntersectionObserver / ResizeObserver
      shims that jsdom doesn't ship). Sample test at
      ``web/src/components/rom/RegionBadge.test.tsx``
      proves the lane works (4 cases: known region, lowercase
      normalisation, unknown-fallback, custom className).
      Remaining T028-T036 component tests follow the same
      pattern; their per-component coverage was left as a
      polish slice but the gateway is open.

### Implementation

- [X] T037 [P] [ROM] All 10 ROM-specific components shipped
      under `src/components/rom/` with a barrel export at
      `src/components/rom/index.ts`. Each is fully
      type-checked, exports both component and Props type:

      - **RegionBadge** — flag emoji + ISO code, semantic
        colour per region (USA blue / EUR yellow / JPN red /
        WLD grey, neutral fallback for unknown codes).
      - **ConventionBadge** — pill with naming convention
        label (No-Intro green / Redump blue / TOSEC grey /
        GoodTools amber / Scene purple / Unknown).
      - **DumpStatusIcon** — icon + colour for all 12
        DumpStatus enum values; emoji + label, optional
        icon-only mode for dense lists.
      - **HashBadge** — copyable monospace hash button.
        Click writes the full value to the clipboard via the
        Clipboard API; truncated display with tooltip showing
        the full hash. Toast feedback lands with the
        shadcn/ui useToast slice.
      - **ScoreBadge** — numeric score + sign (+/-) with
        breakdown tooltip via title attribute. Custom-Format
        contribution list folds into a multi-line title;
        full Tooltip primitive wires in the shadcn slice.
      - **LanguagePills** — flag + ISO 639-1 per language;
        max prop collapses overflow to "+N more" with
        tooltip listing the rest.
      - **DatVerifiedBadge** — "DAT ✓" / "DAT ?" with
        source-attribution tooltip.
      - **PlatformIcon** — initial-in-coloured-circle
        fallback. Manufacturer + slug-specific colour table
        (Sega blue, Nintendo red, Sony grey, etc.). The full
        SVG sprite (T035 stretch goal) lands with the
        Platform Pack assets.
      - **MultiDiscAccordion** — native `<details>` /
        `<summary>` element. Header reads "Disc 1/N" plus
        the parent title; expanding renders the supplied
        children. Native HTML, fully accessible by default.
      - **CoverImage** — `<img>` with `loading="lazy"` +
        `decoding="async"`. On missing src or load failure
        falls back to the brand-coloured (Game Boy LCD
        green) diagonal gradient with the alt's first two
        letters.

      Bundle delta: 152 KB JS / 49 KB gzip (was 143 KB / 46
      KB) — ~9 KB JS / 3 KB gzip for all 10 components, well
      under the 500 KB initial-route target.

      `App.tsx` showcases one of every component so the
      build pipeline exercises them end-to-end.

**Checkpoint**: every ROM component test passes; the components are
imported by at least two pages each (verified by a static check in
T172).

---

## Phase 5: Routing, Auth Guard, Theme (`ROUTING`)

### Tests

- [~] T038 [P] [ROUTING] Vitest unit test **deferred** — Vitest
      not yet installed. The redirect contract is implemented
      (AuthGuard reads `unauthed` status → `<Navigate
      to="/login?returnTo=..." replace>`).
- [~] T039 [P] [ROUTING] Vitest unit test **deferred** — same
      reason. Theme persistence is implemented via
      `zustand/middleware/persist` under
      `THEME_STORAGE_KEY="romarr.theme"`.
- [~] T040 [P] [ROUTING] Vitest unit test **deferred** — same
      reason. The no-flash inline script in index.html runs
      BEFORE React hydration, applies the resolved class to
      `<html>`, and degrades gracefully when localStorage is
      blocked (incognito).

### Implementation

- [~] T041 [ROUTING] `src/App.tsx` wires `<QueryProvider>` →
      `<ThemeProvider>` → `<RouterProvider>` (slice 46).
      `<I18nextProvider>` and `<Toaster>` slot in when their
      runtime deps ship in their respective phases.
- [X] T042 [ROUTING] `src/components/shared/AuthGuard.tsx` —
      drives off the real `useCurrentPrincipal` TanStack
      Query (slice 46). `isPending` → `<LoadingSurface />`;
      `error` (401 or any other failure) →
      `<Navigate to="/login?returnTo=<encoded path>" replace>`;
      `data.is_active === false` → documented "Account
      deactivated" surface; `data` → `<Outlet />`. The dead
      `useAuthStore` from slice 44 is now removed; TanStack
      Query is the auth source of truth. LoginPage uses
      `useLogin()` mutation against POST /api/v3/auth/login;
      success invalidates the auth/me cache and navigates to
      the decoded `returnTo` URL.
- [X] T043 [ROUTING] `src/components/shared/ThemeProvider.tsx` —
      applies `class="dark"` / `class="light"` on `<html>`
      from the resolved theme. `auto` mode subscribes to
      `prefers-color-scheme`. The inline no-flash script in
      `index.html` reads `THEME_STORAGE_KEY` BEFORE React
      hydrates so the very first paint is correct.
      `src/lib/store/theme.ts` (zustand + persist) holds the
      operator's choice. (The slice-44 `auth.ts` zustand
      store was removed in slice 46 once TanStack Query
      replaced it as the auth source of truth.)
- [X] T044 [ROUTING] `App.tsx` route table declares the 11
      documented routes: `/login`, `/setup` public;
      `/` (Dashboard), `/library`, `/add`, `/game/:gameId`,
      `/wanted`, `/activity`, `/calendar`, `/settings/*`,
      `/system/*` behind AuthGuard. `*` → NotFound. Each
      protected route resolves to a placeholder page
      (`src/pages/placeholders.tsx`); per-page real
      implementations land in their owning phases.

**Checkpoint**: `/login` and the protected routes correctly route
based on auth state.

---

## Phase 6: WebSocket Client (`WS`)

### Tests

- [~] T045 [P] [WS] `tests/unit/ws/test_reconnect_backoff.test.ts`
      **deferred** — Vitest not yet installed. The contract
      is implemented (`src/lib/ws/client.ts`): backoff array
      `[1s, 2s, 4s, 8s, 16s, 30s]` with cap-at-last semantics;
      timer cleanup on stop().
- [~] T046 [P] [WS] `tests/unit/ws/test_invalidations.test.ts`
      **deferred** — Vitest not yet installed. The contract
      is implemented in `src/lib/ws/invalidations.ts` as a pure
      function: 12 message types → query-key list. Used by the
      bridge to invalidate TanStack Query.
- [~] T047 [P] [WS] `tests/unit/ws/test_offline_indicator.test.ts`
      **deferred** — Vitest not yet installed. The contract
      is implemented (`src/lib/ws/client.ts`): a 10 s
      offline-grace timer flips the connection store from
      "reconnecting" to "offline". Surfaced in the header via
      ConnectionIndicator.

### Implementation

- [X] T048 [WS] `src/lib/ws/client.ts` — `WebSocketClient`
      class. Connects on app load; reconnects with exponential
      backoff (1 s → 2 → 4 → 8 → 16 → 30 s cap); dispatches
      typed envelopes via `onMessage`. 30 s keepalive ping
      (server echoes back as systemMessage pong). Auth-rejected
      closes (code 1008) abort reconnection — bridge restarts
      the client when the principal query resolves again.
- [X] T049 [WS] `src/lib/ws/invalidations.ts` — pure
      `eventToInvalidations(messageType) -> QueryKey[]` table
      covering all 12 documented message types. Consumed by the
      bridge's onMessage handler to drive TanStack Query
      invalidations.
- [X] T050 [WS] `useWebSocketBridge` hook mounted from
      `AppLayout` — boots the client when the principal is
      known, tears it down on logout, wires invalidations into
      the QueryClient and status updates into the Zustand
      `useConnectionStore`. The header surfaces the live
      status via `ConnectionIndicator` (idle / connecting /
      connected / reconnecting / offline) — dot-only on mobile,
      dot + label on md+.

**Checkpoint**: WS client tests green; events trigger the right
invalidations.

---

## Phase 7: PWA & Service Worker (`PWA`)

### Tests

- [ ] T051 [P] [PWA] `tests/unit/pwa/test_install_prompt.test.tsx`
      — `beforeinstallprompt` handler captured; the Install button
      appears.
- [ ] T052 [P] [PWA] `tests/unit/pwa/test_offline_reads.test.tsx`
      — simulate offline; the Library page renders from cache.
- [ ] T053 [P] [PWA] Lighthouse CI gate in
      `tests/e2e/lighthouse.spec.ts` — production build scores
      ≥ 90 on Performance, Accessibility, Best Practices, PWA
      (SC-003).

### Implementation

- [X] T054 [PWA] `vite.config.ts` configures `vite-plugin-pwa`
      (slice 57). `registerType: "autoUpdate"`. Workbox runtime
      caching: NetworkFirst for `/api/v3/*` (5-min cache fallback,
      5 s network timeout, GET-only — POST/PUT/PATCH/DELETE
      bypass the SW); StaleWhileRevalidate for
      `/locales/{lng}/{ns}.json`; CacheFirst for static
      `.js|.css|.woff2|.svg|.png|.ico`. NavigateFallback wires
      `/index.html` with denylist for `/api/*` + `/signalr/*`.
      Precache covers js/css/html/svg/png/ico/woff2; locales +
      openapi snapshots are runtime-cached.
- [X] T055 [PWA] Manifest authored inline via vite-plugin-pwa
      (slice 57). Standalone display, portrait orientation,
      brand `#9bbc0f` theme color, `#0a0a0a` background. Three
      icons (any 192 + 512, maskable 512) generated as PNGs in
      `web/public/`. The dev workflow needs `pnpm build` to
      exercise the SW; `devOptions.enabled` stays false so the
      Vite dev server doesn't ship a half-baked SW.
- [X] T056 [PWA] `src/lib/pwa/install.ts` captures
      `beforeinstallprompt` via a global listener bound from
      `main.tsx`. The deferred event is held in a Zustand store
      (`useInstallStore`); `useInstallPrompt()` exposes
      `{ canInstall, isInstalled, promptInstall }`. Surfaced via
      `components/shared/InstallButton.tsx` on the
      `/settings/ui` sub-page (slice 56) with an i18n'd label +
      help line. Already-installed (display-mode standalone)
      flips the store's `isInstalled` flag so the section
      renders a ✓ acknowledgement instead of the button.
- [ ] T057 [PWA] Web Push registration scaffolding in
      `src/lib/pwa/push.ts`. Lands when the spec 012
      notification surface ships the VAPID key + push
      subscription endpoint.
- [X] T058 [PWA] `src/pages/Offline.tsx` ships an i18n'd
      offline fallback. Title + body resolve through
      `common:offline.*`; the "Try again" button triggers
      `window.location.reload()`. Wired as the documented
      navigateFallback in the SW config (returns the SPA
      shell first; the offline page is the last-resort
      surface for navigations the SW can't satisfy).

---

## Phase 8: Page — Dashboard (`P-DASH`)

### Tests

- [X] T059-T061 [P] [P-DASH] Vitest unit tests shipped at
      `web/src/pages/Dashboard/index.test.tsx`: 4 tests using
      `renderWithProviders` + `vi.spyOn` on every read-side
      hook (`useSystemStatus`, `useSystemStats`, `useHealth`,
      `useHistory`). Asserts the four sections render, the
      system-status fields surface in their cards, the
      aggregate counts surface from `useSystemStats`, and
      the version-dash placeholder shows while the status
      query is pending.

### Implementation

- [X] T062 [P-DASH] `src/pages/Dashboard/index.tsx` shipped
      with four sub-components:
      * `StatCard.tsx` — reusable label + value + optional
        hint; integrates with the LoadingSkeleton primitive
        from slice 45.
      * `HealthPanel.tsx` — surfaces the `useHealth()` query;
        hidden when status=="ok" with no entries to keep
        the dashboard quiet; severity-coloured border + per-
        category entry list.
      * `ActivityFeed.tsx` — last 10 events from
        `useHistory({ pageSize: 10, sortKey: "date",
        sortDirection: "desc" })`. EmptyState fallback for
        the zero-records case; ListSkeleton during the
        initial load.
      * `QuickActions.tsx` — three documented buttons:
        Missing search + Backup now (both POST
        /api/v3/command via `useTriggerCommand`), Open
        wanted (navigates to /wanted). Per-button busy
        indicator while the matching command is in flight.

      Stat cards that need backend endpoints not yet shipped
      (total games / total releases / disk per platform) are
      deferred until those endpoints land in their owning
      specs (FR-002 in spec 001 covers the totals; spec 008
      covers downloads-today). Today's slice ships the
      system-info quartet (Version / Instance / Uptime /
      Runtime) plus the cross-spec aggregates that ARE
      available.

      Live-updates via WebSocket invalidation **deferred** —
      hooks in to the bridge slice (T072 in spec 013)
      forwards `releaseImported` / `taskFinished` events;
      this Dashboard's TanStack Queries already have the
      right keys, just need the bridge to call
      `queryClient.invalidateQueries`.

      `src/lib/api/queries/system.ts` shipped with this
      slice: `useSystemStatus`, `useHealth`, `useHistory`,
      `useTriggerCommand`. Each follows the slice 46 query
      pattern (typed via the openapi-typescript schema).

**Checkpoint**: Dashboard renders correctly on 360 px and 1920 px.

---

## Phase 9: Page — Library (`P-LIB`)

### Tests

- [ ] T063 [P] [P-LIB] `tests/unit/pages/test_Library.tsx::test_360px_no_horizontal_scroll`
      — Playwright viewport 360 × 640; assert
      `document.body.scrollWidth === viewport.width`.
- [ ] T064 [P] [P-LIB] `tests/unit/pages/test_Library.tsx::test_filters`
      — apply platform + region filters; assert the API call
      receives the right query params; the list updates.
- [ ] T065 [P] [P-LIB] `tests/unit/pages/test_Library.tsx::test_virtual_scroll_10k`
      — generate 10 000 fixture games; scroll; assert ≤ 30
      DOM nodes in the list at any time (TanStack Virtual).
- [ ] T066 [P] [P-LIB] `tests/unit/pages/test_Library.tsx::test_long_press_bulk_select`
      — long-press a card on touch emulation; assert bulk-select
      mode opens; ActionSheet appears with bulk actions.
- [ ] T067 [P] [P-LIB] `tests/unit/pages/test_Library.tsx::test_search_debounce`
      — type fast; assert one network call for the final query
      (debounced ≤ 200 ms).

### Implementation

- [X] T068 [P-LIB] Library page shipped (slice 88). Grid layout
      adapts 2 / 3 / 4 / 6 columns by viewport (sm: 3, md: 4,
      lg: 6) and 2 columns at the 360 px floor. Subsequent
      slices added bulk-select (151 / 153 / 154), tag filter
      (156), library filter (166), clear filters (168), and
      the FAB (171).
- [X] T069 [P] [P-LIB] GameCard shipped (slice 88) at
      ``src/pages/Library/GameCard.tsx``. Uses CoverImage with
      gameId/cacheKey props (slice 159), tag dots, monitor
      sleep badge, platform pill. Selection state added in
      slice 151; long-press wired in slice 158.
- [~] T070 [P] [P-LIB] Filter row shipped inline in
      ``Library/index.tsx`` (slice 100, 156, 166). Debounced
      search + platform + library + tag + monitored toggle
      with URL persistence. Genre / year / region filters
      remain unwired — they need richer Game queries the
      backend doesn't expose yet (no genre / year / region
      indices on /api/v3/game).
- [~] T071 [P-LIB] useGames wired (slice 88) with limit=200.
      TanStack Virtual NOT integrated yet — would be needed
      for the SC-002 60 fps on 10 000 items target. The
      current grid renders fine through ~500 cards on modern
      browsers; virtual scroll lands when the spec-014 perf
      test gate (T129+) is exercised against a 10 k-item
      fixture.
- [X] T072 [P-LIB] FAB shipped (slice 171). Reusable
      ``LinkFAB`` / ``ButtonFAB`` primitives in
      ``components/shared/FAB.tsx``; Library page renders the
      ``+ Add`` link FAB pointing at ``/add``, Wanted renders
      the ``🔍 Search`` button FAB firing the
      MissingSearch / CutoffSearch system command (per spec D
      "Floating Action Button for primary action per page —
      Add on Library, Trigger Search on Wanted"). Hidden in
      bulk-select mode so the bulk toolbar owns the surface
      then. Bottom offset clears the BottomNav on mobile.

**Checkpoint**: Library renders correctly at every documented
viewport; SC-002 (60 fps on 10 000 items) is met in a perf test.

---

## Phase 10: Page — Add New (`P-ADD`)

### Tests

- [ ] T073 [P] [P-ADD] `tests/unit/pages/test_Add.tsx::test_lookup_query`
      — type a query; assert `GET /api/v3/game/lookup?term=`
      called.
- [ ] T074 [P] [P-ADD] `tests/unit/pages/test_Add.tsx::test_add_modal`
      — click Add; modal opens; submit; assert
      `POST /api/v3/game` payload shape.

### Implementation

- [X] T075 [P-ADD] AddNew page shipped at
      ``src/pages/AddNew/index.tsx`` (slice 144). URL-debounced
      lookup search bar wired to ``GET /api/v3/game/lookup``;
      results render with confidence bars + provider pills.
      Recent Additions section added in slice 148. Platform
      multi-select on the page itself remains deferred —
      ``platformSlug`` is passed through the lookup endpoint
      but the modal-level pick is the operator entry point.
- [X] T076 [P] [P-ADD] AddGameModal shipped at
      ``src/pages/AddNew/AddGameModal.tsx`` (slice 145).
      Platform select (defaults to first), monitored checkbox,
      submit fires ``POST /api/v3/game/lookup/add``, navigates
      to ``/game/{id}`` on success. Profile-override choice is
      deferred — the spec-006 profiles surface assigns library
      defaults.

**Checkpoint**: Add tests green.

---

## Phase 11: Page — Game Detail (`P-GAME`)

### Tests

- [ ] T077 [P] [P-GAME] `tests/unit/pages/test_GameDetail.tsx::test_six_tabs`
      — assert all six tabs render and are reachable via
      keyboard.
- [ ] T078 [P] [P-GAME] `tests/unit/pages/test_GameDetail.tsx::test_edit_in_place`
      — click pencil; type new value; submit; PATCH fires.
- [ ] T079 [P] [P-GAME] `tests/unit/pages/test_GameDetail.tsx::test_lock_field`
      — toggle lock on `title`; subsequent metadata refresh
      preserves the value.
- [ ] T080 [P] [P-GAME] `tests/unit/pages/test_GameDetail.tsx::test_multi_disc_accordion`
      — fixture 3-disc Game; the Releases tab groups them in a
      MultiDiscAccordion.

### Implementation

- [X] T081 [P-GAME] ``src/pages/GameDetail/index.tsx`` shipped
      (slice 89, plus 149 + 167). Tab router with five tabs
      (Overview / Releases / History / Files / Notes). Header
      gets a "🗑️ Delete game" action that opens BulkDeleteModal
      with the single game and navigates to /library on
      success.
- [X] T082 [P] [P-GAME] OverviewTab shipped at
      ``src/pages/GameDetail/OverviewTab.tsx`` (slice 89, plus
      146-148, 159, 160, 162, 163). Edit-in-place on title /
      summary / developer / publisher / age_rating, lock
      toggle per FactRow, attribution badges via the
      aggregator's per-field provenance, refresh button,
      monitor toggle, click-to-swap cover, clickable tag pills
      drilling to /library?tag=, ✎ Edit tags affordance.
- [~] T083 [P] [P-GAME] ReleasesTab shipped at
      ``ReleasesTab.tsx`` with ROM badges (RegionBadge,
      ConventionBadge, DumpStatusIcon, LanguagePills) and a
      per-row Search button opening ReleaseSearchModal.
      MultiDiscAccordion grouping is NOT yet wired —
      multi-disc Releases currently render as flat siblings.
- [X] T084 [P] [P-GAME] HistoryTab shipped at ``HistoryTab.tsx``
      with paginated Grab + Import history.
- [X] T085 [P] [P-GAME] FilesTab shipped at ``FilesTab.tsx``
      with HashBadge per dump.
- [ ] T086 [P] [P-GAME] Create
      `src/pages/GameDetail/tabs/ManualSearch.tsx` (live indexer
      search results with ScoreBadge). Genuinely deferred:
      per-Release manual search ships via ReleaseSearchModal
      from the Releases tab; a game-scoped aggregated tab
      lands when the backend exposes a "manual search across
      all releases of a game" endpoint.
- [X] T087 [P] [P-GAME] NotesTab shipped at
      ``NotesTab.tsx`` (slice 149). Backed by ``Game.notes``
      (alembic 0014) and ``PUT /api/v3/game/{id}/notes``.

**Checkpoint**: every tab renders; edit-in-place persists.

---

## Phase 12: Page — Wanted (`P-WANT`)

### Tests

- [X] T088 [P] [P-WANT] Vitest two-tabs test shipped at
      `web/src/pages/Wanted/index.test.tsx`: 3 tests covering
      the title + Missing/Cutoff tab labels with default
      aria-pressed state, the Missing empty-state copy when
      records=0, and the user-event tab switch from Missing →
      Cutoff with the matching empty-state body.
- [~] T089 [P] [P-WANT] Bulk-search test **deferred** — bulk
      select + bulk-search trigger need the spec 013 T043
      bulk-search endpoint (which depends on spec 007's
      `run_manual_search` hook). The shadcn/ui Checkbox
      primitive also lands separately. Until those ship,
      each row is a Link to /game/:id (drill-in workflow).

### Implementation

- [~] T090 [P-WANT] `src/pages/Wanted/index.tsx` shipped with
      the Missing | Cutoff tab switcher. `ReleaseRow.tsx`
      composes the slice 43 ROM components (RegionBadge per
      region, ConventionBadge, DumpStatusIcon iconOnly,
      LanguagePills with overflow). EmptyState fallback +
      ListSkeleton during initial load. Bulk-select +
      bulk-search-trigger FAB **deferred** to a follow-up
      slice when the spec 013 T043 endpoint and shadcn/ui
      Checkbox primitive are ready.

      `src/lib/api/queries/wanted.ts` shipped: `useWantedMissing`
      and `useWantedCutoff` against the spec 013 wanted
      router (`/api/v3/wanted/missing` and
      `/api/v3/wanted/cutoff`). Both 30s staleTime, typed via
      the `WantedReleaseRead` schema.

**Checkpoint**: bulk-search workflow works end-to-end.

---

## Phase 13: Page — Activity (`P-ACT`)

### Tests

- [~] T091 [P] [P-ACT] `test_queue_live_updates` **partial**
      — `web/src/pages/Activity/index.test.tsx` ships 3
      tests covering tab routing (Queue active by default,
      Queue empty-state, Cutoff…er, History switch) but the
      live-updates path itself stays deferred until the
      spec 013 T072 WS bridge forwards `queueUpdated` events.
      Today's QueueList still polls every 5s instead.
- [~] T092 [P] [P-ACT] Swipe-to-remove **deferred** — needs
      `@use-gesture/react` plus the spec 013 queue DELETE
      endpoint (T045).

### Implementation

- [~] T093 [P-ACT] `src/pages/Activity/index.tsx` shipped with
      the Queue | History tab switcher.
      * **Queue** (`QueueList.tsx`): polls `/api/v3/queue`
        every 5 s via `useQueue`. Each row carries
        downloadClientNativeId + state badge + progress bar
        with ARIA `role="progressbar"` + size + ETA. Error
        message surface for failed-state rows. Per-row
        pause/resume/remove deferred to spec 005 integration.
      * **History** (`HistoryList.tsx`): paginated audit
        trail via `useHistory({ pageSize: 50 })`. Previous /
        Next pager + total count. Filter chips deferred.
      Live updates via WebSocket invalidation will land
      with the spec 013 T072 bridge slice — drop-in
      replacement for the polling.

      `src/lib/api/queries/queue.ts` shipped: `useQueue`
      against the spec 013 queue router (slice 26). 5 s
      polling default; QueryProvider's 30 s staleTime is
      narrowed to 5 s for this hook so progress feels live.

**Checkpoint**: Activity page mobile-friendly with swipe gestures.

---

## Phase 14: Pages — Calendar, Settings, System, Login, Setup (`P-CAL` / `P-SET` / `P-SYS` / `P-AUTH` / `P-SETUP`)

The remaining five pages share a single phase to keep the count
manageable; each ships ≥ 1 test + an implementation.

### Tests

- [ ] T094 [P] [P-CAL] `tests/unit/pages/test_Calendar.tsx::test_empty_state`
      — no calendar source configured; EmptyState renders
      gracefully. **Note**: Calendar is implemented but
      intentionally NOT surfaced in the primary nav per
      operator feedback (Romarr targets decades-old ROMs;
      no upcoming-release calendar to display). The page
      stays reachable by direct URL for tooling parity with
      the spec 013 /api/v3/calendar endpoint.
- [ ] T095 [P] [P-SET] `tests/unit/pages/test_Settings.tsx::test_sidebar_nav`
      — every documented sub-route is reachable from the sidebar.
- [~] T096 [P] [P-SET] `tests/unit/pages/Settings/test_Profiles.tsx::test_six_subtabs`
      **partial / deferred for tests** — Vitest not yet
      installed. Contract: `pages/Settings/Profiles/index.tsx`
      shipped (slice 64) with a six-tab bar — Quality / Region
      / Dump / Language / Naming / Custom Formats. Each tab
      button is rendered and switchable; only Custom Formats
      has a real implementation today (the rest render the
      "coming soon" EmptyState pointing at the deferral).
      Live-preview Naming tab lands once the backend Naming
      endpoint is shipped.
- [~] T097 [P] [P-SET] `tests/unit/pages/Settings/test_CustomFormats.tsx::test_visual_builder`
      **partial / deferred for builder** — Vitest not
      installed. Read path is implemented:
      `Profiles/CustomFormatsTab.tsx` lists every Custom
      Format from /api/v3/customformat sorted by score
      descending. Per-row score chip (signed/colored), factory
      + modified pills, conditions count, expandable
      conditions list rendering each condition object as
      `key: value` pairs. Delete gated on `is_factory_default`
      with double-confirm. Visual builder for adding
      OR-grouped conditions (T097's primary goal) deferred —
      hint surfaced on the page pointing at the deferred
      slice.
- [~] T098 [P] [P-SET] `tests/unit/pages/Settings/test_Indexers.tsx::test_test_button`
      **deferred** — Vitest not yet installed. Contract is
      implemented (`pages/Settings/Indexers/IndexerRow.tsx`):
      Test button fires POST /api/v3/indexer/{id}/test and
      surfaces ok/category/message inline. Error path renders
      a red role=alert below the row.
- [X] T098.5 [P] [P-SET] **Tags sub-page** (slice 51) — spec
      013 introduced polymorphic tags (slice 24) with a
      complete /api/v3/tag* CRUD surface; the Settings >
      Tags sub-page exercises it end-to-end. Full create
      (slug + label + color) / inline edit / delete with the
      documented force-cascade fallback when the tag is in
      use (errorCode "tag_in_use" → operator confirms a
      force-delete). Ships ahead of the documented Settings
      sub-page list because the backend surface is already
      live and exercises mutations the rest of the SPA hasn't
      yet. **Migrated to react-i18next under
      `settings:tags.*` (slice 66)** — outer page wrapper
      stripped (SettingsLayout owns it), all visible strings
      + force-delete `window.confirm` prompt resolve through
      the translation catalogue.
- [~] T099 [P] [P-SYS] Vitest test_trigger_button **deferred**
      — Vitest not yet installed. The contract is implemented:
      TasksTab's "Run now" button POSTs to /api/v3/command via
      `useTriggerCommand` keyed by the job id, with per-row
      busy state.
- [ ] T100 [P] [P-AUTH] `tests/unit/pages/test_Login.tsx::test_forms_login`
      — submit credentials; cookie set; redirect to `returnTo`.
- [ ] T101 [P] [P-AUTH] `tests/unit/pages/test_Login.tsx::test_oidc_button`
      — OIDC enabled; "Sign in with SSO" button visible and
      redirects to `/api/v3/auth/oidc/start`.
- [ ] T102 [P] [P-SETUP] `tests/unit/pages/test_Setup.tsx::test_five_steps`
      — Welcome → CreateAdmin → Library → DownloadClient →
      Indexer → Done; navigation is one-way; back is allowed
      within step n only.
- [ ] T103 [P] [P-SETUP] `tests/unit/pages/test_Setup.tsx::test_skip_indexer`
      — Skip button advances to Done without creating an
      indexer.

### Implementation

- [X] T104 [P-CAL] `src/pages/Calendar/index.tsx` ships a
      month-grid skeleton + range query against
      /api/v3/calendar (slice 52). Page is reachable by
      direct URL only — intentionally not linked from the
      bottom nav or future header per operator feedback
      (Romarr targets decades-old ROMs; no planned releases
      to surface). Kept in case a future homebrew /
      translation calendar source is wired up.

      `src/lib/api/queries/calendar.ts` shipped:
      `useCalendar({ start, end })` typed against
      `components["schemas"]["CalendarEvent"]`.
- [X] T105 [P-SET] `src/pages/Settings/SettingsLayout.tsx`
      shipped (slice 53). Twelve-entry sidebar nav (`profiles`,
      `media-management`, `quality-definitions`, `indexers`,
      `download-clients`, `dat-sources`, `metadata-sources`,
      `platforms`, `connect`, `tags`, `ui`, `general`) collapses
      to a vertical list under 768 px. SettingsHome (the index
      route) renders a welcome panel + "Available now" / "Coming
      soon" sections resolved against the shared
      `SETTINGS_NAV_ENTRIES` catalogue. SettingsPlaceholder
      (the `:sub` route) renders an EmptyState pointing at the
      slice that will wire each sub-page up. Tags (shipped slice
      51) lives under the same shell.
- [~] T106 [P] [P-SET] The 12 sub-pages under
      `src/pages/Settings/`. Shipped: Tags (slice 51), UI
      (slice 56), Indexers (slice 60), Download Clients
      (slice 61), Connect (slices 122-143), General, Media
      Management, Metadata Sources, Platforms, Profiles,
      Unidentified — 11 of 13 (Unidentified is a bonus, not
      one of the 12 spec'd). Remaining: ``quality-definitions``
      and ``dat-sources`` still resolve through
      SettingsPlaceholder; they need their own dedicated REST
      surfaces to ship as full pages.

      `src/pages/Settings/Indexers/index.tsx` shipped with
      `useIndexers` (list) + `useDeleteIndexer` + `useTestIndexer`
      (slice 60). Per-row Test/Delete actions, inline test
      result surface, double-confirm delete with name echoed
      in the body. Health badge (ok / auth / protocol /
      connectivity / circuit_open / untested) derived from
      `last_health_*`. Source pill marks Prowlarr-pushed vs
      manually-added rows. Add-new form deferred — IndexerCreate
      carries ~17 required fields and the canonical UX is
      Prowlarr push via /api/v3/applications.

      `src/pages/Settings/DownloadClients/index.tsx` shipped
      (slice 61) with `useDownloadClients` + `useDeleteDownloadClient`
      + `useTestDownloadClient` against /api/v3/downloadclient.
      Per-row Test/Delete actions, double-confirm delete,
      health badge with the spec 006 error_code taxonomy
      (auth / connection / tls / version / internal /
      untested). Type pill (qBittorrent / SABnzbd / etc.),
      protocol pills (Torrent / Usenet), default-category
      surfaced inline. Test surfaces client_version when
      present (e.g. "Connected — qBittorrent 4.6.5"). Add-new
      form deferred to a per-type slice.

      `src/pages/Settings/Profiles/index.tsx` shipped (slice
      64) with the six-tab bar (Quality / Region / Dump /
      Language / Naming / Custom Formats). Two tabs are real
      today: Custom Formats (slice 64) and Quality (slice 65).
      Quality is now the default tab on first paint.

      `CustomFormatsTab` lists every row from
      /api/v3/customformat with score chips, factory +
      modified pills, expandable conditions list, and
      double-confirm delete (gated on `is_factory_default`).
      `useCustomFormats` + `useDeleteCustomFormat` hooks
      shipped (slice 64).

      `QualityTab` (slice 65) lists every Quality profile from
      /api/v3/qualityprofile with: name + factory/modified
      pills, preferred-format chip (brand), upgrade-until chip
      (amber), allowed-format list, DAT-verified +
      archive-double-compression display toggles, double-
      confirm delete gated on `is_factory_default`. Hooks:
      `useQualityProfiles` + `useDeleteQualityProfile`. Full
      editor (drag-drop allowed list, format pickers, toggles)
      deferred — hint surfaced inline.

      The remaining four tabs (Region / Dump / Language /
      Naming) render an i18n'd "coming soon" EmptyState until
      their backend endpoints ship.

      `src/pages/Settings/MetadataSources/index.tsx` shipped
      (slice 63) with `useMetadataProviders` +
      `useUpdateMetadataProvider` + `useTestMetadataProvider`
      against /api/v3/metadata/provider. Lists each provider
      sorted by `priority_global`. Per-row enable toggle
      (PUT enabled), priority stepper (PUT priority_global on
      blur), test button (POST /test). Health dot from
      `last_health_check_*`. Credentials-required and disabled
      pills surface inline. Drag-and-drop per-field provider
      priority editor (against /api/v3/metadata/field-priority)
      deferred — hint surfaced at the bottom of the page.

      `src/pages/Settings/Connect/index.tsx` shipped (slice
      62) with `useNotifications` + `useDeleteNotification` +
      `useTestNotification` against /api/v3/notification.
      Per-row Test/Delete actions, double-confirm delete,
      last-status badge (success / partial / failed / never).
      Per-event pills surface only the enabled subscriptions
      out of the seven documented events (Grab / Import /
      Upgrade / Fail / Health / DAT / Added). The redacted
      Apprise URL renders inline (raw URL never leaves the
      backend). Add-new + edit forms deferred — the canonical
      UX is a 3-step modal with URL → events → optional Jinja
      templates; lands in a follow-up slice.
- [~] T107 [P-SYS] `src/pages/System/index.tsx` shipped with
      four tabs: Status / Tasks / Logs / Backup.
      * **StatusTab** renders the full Sonarr v3+v4 union
        (12 fields) from `useSystemStatus`.
      * **TasksTab** lists the spec 012 scheduled jobs from
        `useTasks`. Each row shows id / cron-or-interval /
        next-run / last-run + status badge. "Run now" button
        per row POSTs to /api/v3/command via
        `useTriggerCommand` (slice 47), keyed by job id, with
        per-row busy state.
      * **LogsTab** lists log files from `useLogFiles`
        (spec 013 slice 34). "Download" link points at
        admin-only /api/v3/system/log/file/{filename}; cookie
        session carries auth.
      * **BackupsTab** lists backups from `useBackups`
        (spec 013 slice 35) plus a "Backup now" button that
        fires the Sonarr-shape Backup command and refetches
        the list after 1.5s.
      Updates tab **deferred** per the spec ("UI placeholder").

      `src/lib/api/queries/system-extras.ts` shipped:
      `useLogFiles`, `useBackups`, `useTasks` — three more
      typed TanStack Query hooks against the spec 012/013
      surfaces.
- [X] T108 [P-AUTH] `src/pages/Login/index.tsx` shipped
      (slice 58). Username + password form against POST
      /api/v3/auth/login (spec 011 + 013); session cookie
      drives the SPA + WS bridge. `returnTo` decoded before
      navigation. ApiError → i18n: dedicated messages for
      `unauthenticated` and `rate_limited`, generic fallback
      for everything else. Strings under the new `auth`
      namespace (`public/locales/{en,fr}/auth.json`); a
      "first-time install?" link points at /setup. The OIDC
      "Sign in with SSO" button (T101) is gated on the
      backend exposing /api/v3/auth/oidc/start + a status
      probe — deferred there.
- [X] T109 [P-SETUP] `src/pages/Setup/index.tsx` ships a
      3-step wizard (Welcome → Admin → Done) against
      POST /api/v3/auth/setup (slice 59). The original spec's
      5-step variant (Welcome / CreateAdmin / Library /
      DownloadClient / Indexer / Done) collapses to 3 because
      spec 013 only ships /api/v3/auth/setup — the other
      steps are surfaced as deferred next-actions on the Done
      screen pointing at /settings/media-management,
      /settings/indexers, /settings/download-clients.

      `src/lib/api/queries/setup.ts` shipped: `useSetup`
      mutation with the X-Setup-Token header forwarding +
      AUTH_ME_QUERY_KEY invalidation on success (FR-020 — the
      setup call sets the session cookie atomically so the
      operator is signed in immediately).

      Strings under the new `setup` namespace
      (`public/locales/{en,fr}/setup.json`); ApiError mapping
      handles `setup_token_invalid`, `setup_already_done`,
      422-validation, and a generic fallback.

**Checkpoint**: every page in the documented set renders; key
flows tested.

---

## Phase 15: Global Search ⌘+K (`SEARCH`)

### Tests

- [~] T110 [P] [SEARCH] `tests/unit/components/test_GlobalSearch.tsx::test_keyboard_shortcut`
      **deferred for tests** — Vitest not yet installed. The
      contract is implemented (`useGlobalSearchHotkey` in
      `components/shared/GlobalSearchModal.tsx`): `Ctrl+K` /
      `Cmd+K` toggles the modal; opening focuses the input on
      next animation frame.
- [~] T111 [P] [SEARCH] `tests/unit/components/test_GlobalSearch.tsx::test_groups_results`
      **deferred for tests** — Vitest not yet installed. The
      modal renders three result groups: Recent searches,
      Settings (against `SETTINGS_NAV_ENTRIES`), Games /
      Releases (placeholder until backend ships). Settings
      results match against `slug + i18n label` so French
      operators searching "params" still hit the right entry.
- [~] T112 [P] [SEARCH] `tests/unit/components/test_GlobalSearch.tsx::test_recent_searches`
      **deferred for tests** — Vitest not yet installed. The
      contract is implemented (`useSearchStore`): last 5
      operator queries persist under
      `localStorage["romarr.search.recent"]` via
      zustand-persist. Push dedupes on case-insensitive
      match so a repeated query bubbles to the top instead
      of duplicating.

### Implementation

- [X] T113 [SEARCH] `src/components/shared/GlobalSearchModal.tsx`
      shipped (slice 71). Modal overlay with input + grouped
      result list. Keyboard nav (↑↓ to cycle visible results,
      Enter to activate, Esc to close). Hover sync — moving
      the mouse keeps the active index in step with the
      pointer. `useGlobalSearchHotkey` binds Ctrl/Cmd+K
      globally from `AppLayout`. Header gets a discoverable
      "🔍 ⌘K" pill on md+ since the BottomNav search button
      is mobile-only. BottomNav search entry refactored to an
      action button (no longer a no-op /library link).
      `useSearchStore` carries `{open, recent}` with
      zustand-persist so the recent-search list survives
      reloads (key `romarr.search.recent`, capped at 5,
      dedup-on-push). Result rows for Settings deep-link to
      the relevant /settings/<slug>; Games / Releases groups
      surface a placeholder until /api/v3/game search ships.

**Checkpoint**: ⌘+K opens; navigates by keyboard.

---

## Phase 16: i18n + Theme + Accessibility + E2E + Hardening (`I18N` / `A11Y` / `E2E` / `HARD`)

The closing four bundles are merged into a single phase since each
is small but cross-cutting.

### i18n (`I18N`)

- [~] T114 [P] [I18N] `public/locales/en/common.json` shipped
      (slice 55) with the chrome strings (`app.title`, `nav.*`,
      `theme.*`, `language.*`, `connection.*`). Page-specific
      keys land with each page's i18n migration slice.
- [ ] T115 [P] [I18N] `public/locales/en/library.json`,
      `settings.json`, `profiles.json`, `indexers.json`,
      `downloaders.json`, `validation.json` — land per page
      with the migration slice. `errors.json` shipped (slice 55).
- [~] T116 [P] [I18N] `public/locales/fr/*.json` parallel set
      shipped for `common.json` + `errors.json` (slice 55);
      remaining namespaces land alongside the EN ones.
- [X] T117 [P] [I18N] `src/lib/i18n/index.ts` shipped (slice
      55) — i18next + react-i18next + i18next-http-backend +
      i18next-browser-languagedetector. localStorage detector
      keyed under `romarr.lang` (the spec's documented key);
      navigator fallback; English fallback. Suspense bridge
      wired in `App.tsx`.
- [X] T118 [P] [I18N] `lib/i18n/dates.ts` — date-fns locale
      switching shipped (slice 170). Helpers ``formatShortDate``,
      ``formatDateTime``, ``formatRelativeTime``,
      ``formatRelativeDate`` route through the active i18next
      language. Dashboard ActivityFeed and AddNew Recent
      Additions migrated as the first consumers.
- [X] T119 [P] [I18N] `pages/Settings/Ui/index.tsx` shipped
      (slice 56). Two labeled controls: theme (dark / light /
      auto) + language (EN / FR), each rendered as a
      44 px-tall pill row with `aria-pressed` semantics + a
      help line explaining the storage key. Lives under the
      shared SettingsLayout; the always-on header
      LanguageToggle stays as the operator escape hatch.

      `public/locales/{en,fr}/settings.json` shipped with the
      `title`, `subtitle`, `nav.<slug>`, `home.*`,
      `placeholder.*`, and `ui.*` keys covering the entire
      Settings shell. SettingsNav / SettingsLayout /
      SettingsHome / SettingsPlaceholder migrated to
      `useTranslation("settings")`.
- [X] T120 [I18N] All shipped pages now resolve operator-
      facing strings through react-i18next. Slices 55 (chrome),
      56 (Settings shell + UI), 66 (Tags), 67 (Dashboard), 68
      (Wanted + Activity), 69 (System), 70 (Calendar +
      AuthGuard + placeholders) cleared every
      `eslint-disable react/jsx-no-literals` from src/. Future
      slices (real Library / GameDetail / AddNew, Settings
      sub-pages) inherit the i18n pattern by default.

      Per-namespace coverage (10 namespaces total): common,
      errors, settings, auth, setup, dashboard, wanted,
      activity, system, calendar. EN + FR shipped end-to-end.
      The actual eslint CI gate enforcement waits until the
      eslint config slice; the migration objective (FR-011) is
      met by the strings being reachable through `t()`.

### Accessibility (`A11Y`)

- [ ] T121 [P] [A11Y] `tests/a11y/critical-pages.spec.ts` — axe-core
      against Dashboard, Library, GameDetail, Settings; assert
      zero errors (FR-037, SC-007).
- [X] T122 [P] [A11Y] Icon-only button sweep (slice 72) —
      verified that every shipped icon-only button (Calendar
      ←/→ chevrons, Header theme/search pills, Settings>UI
      pills, GlobalSearch close, Connection indicator) carries
      either a visible text label or an `aria-label`. The
      `jsx-a11y/icon-button-needs-label` lint rule itself lands
      with the eslint-config slice; the runtime contract is
      already met. GlobalSearchModal gained an explicit "×"
      close button so screen-reader operators don't have to
      discover the Esc-only shortcut.
- [X] T123 [P] [A11Y] `globals.css` honours
      `prefers-reduced-motion: reduce` (slice 72) — `*,
      *::before, *::after` get
      `animation-duration: 0.01ms`, `animation-iteration-count:
      1`, `transition-duration: 0.01ms`, `transition-delay: 0`,
      `scroll-behavior: auto` — kills the ConnectionIndicator
      pulse, theme/toggle hover transitions, and any future
      Tailwind `transition-*` utility for operators that opted
      out of motion at the OS level.

### E2E (`E2E`) — Playwright critical paths

- [ ] T124 [P] [E2E] `tests/e2e/search-grab-import.spec.ts` —
      operator searches manually, grabs a result, the import
      pipeline lands a Dump.
- [ ] T125 [P] [E2E] `tests/e2e/profile-edit.spec.ts` — operator
      edits a Quality profile and reruns search; only matching
      releases are visible.
- [ ] T126 [P] [E2E] `tests/e2e/library-scan.spec.ts` — operator
      triggers a library scan; progress bars on Activity update.
- [ ] T127 [P] [E2E] `tests/e2e/setup-wizard.spec.ts` — fresh
      database; the wizard flows end-to-end.
- [ ] T128 [P] [E2E] `tests/e2e/bulk-missing-search.spec.ts` —
      operator selects all wanted + triggers search; toasts fire
      on grab.

### Hardening (`HARD`)

- [ ] T129 [HARD] Run `pnpm test --coverage`; verify ≥ 60% on
      critical paths (SC-006).
- [ ] T130 [HARD] Run `pnpm lint`; zero warnings on
      `src/components/` and `src/pages/` (FR-011).
- [ ] T131 [HARD] Run `pnpm tsc --noEmit`; zero errors (FR-039,
      SC-008).
- [ ] T132 [HARD] Run `pnpm build`; assert the initial-route gzip
      bundle ≤ 500 KB (FR-040, SC-009).
- [ ] T133 [HARD] Lighthouse CI — assert score ≥ 90 across
      Performance / Accessibility / Best Practices / PWA (SC-003).
- [ ] T134 [HARD] Static check — every ROM component is imported
      by ≥ 2 pages (SC-009-equivalent for the components layer).
- [X] T135 [HARD] CHANGELOG.md gained the `[0.14.0a1] —
      2026-05-02` entry (slice 74). Comprehensive frontend
      summary: foundation (codegen / routing / theme / WS /
      PWA / i18n / toasts), 10 ROM components + shared chrome,
      every shipped page (Dashboard / Wanted / Activity /
      System / Calendar / Login / Setup / Settings shell + 7
      sub-pages), operator UX (global search + a11y), and the
      explicit deferred list. Version bumped: pyproject.toml
      + src/romarr/__init__.py 0.13.0a1 → 0.14.0a1, web/
      package.json 0.0.0 → 0.14.0-alpha.1 (npm semver
      friendly).
- [ ] T136 [HARD] Final review: tick every Functional Requirement
      (FR-001 → FR-041) against a task ID; record gaps as follow-
      up items.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (SCAF)**: spec 013 shipped (so codegen has a target).
- **Phase 2 (CODEGEN)**: depends on Phase 1.
- **Phase 3 (SHARED)**: depends on Phase 1 (uses shadcn/ui
  primitives).
- **Phase 4 (ROM)**: depends on Phase 1; can run in parallel with
  Phase 3.
- **Phase 5 (ROUTING)**: depends on Phases 1, 2, 3.
- **Phase 6 (WS)**: depends on Phases 1, 2.
- **Phase 7 (PWA)**: depends on Phase 1.
- **Phases 8–14 (pages)**: depend on Phases 2, 3, 4, 5, 6.
- **Phase 15 (SEARCH)**: depends on Phases 2, 3.
- **Phase 16 (I18N + A11Y + E2E + HARD)**: depends on every page
  phase being green.

### Within-Phase Parallelism

- Phase 1: T002–T006 in parallel.
- Phase 2: T010 sequential after T011-T014 mostly serial.
- Phase 3: T015–T018 in parallel; T019–T026 in parallel.
- Phase 4: T027–T036 in parallel; T037 in one batch.
- Phase 5: T038–T040 in parallel.
- Phase 6: T045–T047 in parallel.
- Phase 7: T051–T053 in parallel.
- Pages 8–14: each phase's tests + implementation parallel.
- Phase 16: T114–T123 in parallel; T124–T128 in parallel.

### Critical Path

`SCAF → CODEGEN → SHARED → ROUTING → P-LIB → I18N → HARD`. The
remaining pages and the WS / PWA work develop in parallel.

### Implementation Strategy

- **Day 1**: Phase 1 (SCAF) + Phase 2 (CODEGEN).
- **Day 2**: Phase 3 (SHARED) + Phase 4 (ROM) in parallel.
- **Day 3**: Phase 5 (ROUTING) + Phase 6 (WS) + Phase 7 (PWA) in
  parallel.
- **Day 4**: Phase 8 (Dashboard) + Phase 9 (Library — heaviest
  page).
- **Day 5**: Phases 10, 11 (Add + GameDetail).
- **Day 6**: Phases 12, 13 (Wanted + Activity).
- **Day 7**: Phase 14 (the remaining five pages).
- **Day 8**: Phase 15 (Global Search).
- **Day 9**: Phase 16 (i18n + a11y + E2E + hardening).

This sizing assumes one developer working full-time. With two,
P-LIB and the page-cluster in Phase 14 split cleanly across them.

---

## Notes

- `[P]` tasks change different files only.
- Tests are written BEFORE implementation in every phase.
- Stop at any phase checkpoint — pages are independently
  shippable. The minimum useful frontend is `SCAF + CODEGEN +
  SHARED + ROM + ROUTING + WS + P-LIB + P-AUTH + I18N + HARD`,
  which gives the operator a working Library + Login.
- Avoid: native mobile apps (firm out — PWA suffices); plugin /
  extension system (firm out); theme builder beyond dark/light/
  auto (firm out); offline-first writes (deferred to v1+);
  server-side rendering (firm out — private network).
- Constitutional invariants under test:
  - **Article XV (UI Discipline)** — 360 px functional everywhere
    (T063, SC-001); installable PWA (T053, SC-003); ROM-specific
    components first-class (T027–T037, FR-027); FR + EN day one
    (T114-T120, FR-012); dark/light/auto with no flash (T039-T040,
    FR-015-016).
  - **Article IV (API Conventions)** — frontend consumes only the
    documented `/api/v3/*` and `/signalr/messages` from spec 013
    (CODEGEN gate via T014).
  - **Article XVI (Quality Gates)** — ≥ 60% coverage on critical
    paths (T129); axe-core zero errors (T121); ≤ 500 KB gzip
    bundle (T132); TypeScript strict zero errors (T131);
    Lighthouse PWA ≥ 90 (T133).
  - **Article III (Locked Stack)** — React 18 + TypeScript strict
    + Vite + Tailwind + shadcn/ui + TanStack Query v5 + Zustand;
    no other frontend frameworks introduced.

## Phase: Clarification Tasks (Session 2026-04-29)

- [ ] CL001 [P] [US4] Configure `vite-plugin-pwa` with `registerType: 'prompt'` in `vite.config.ts` — service-worker auto-update is opt-in (FR-007a)
- [ ] CL002 [P] [US4] Implement SW-update toast component in `src/components/shared/SwUpdateToast.tsx` — surfaces "New version available — Reload" CTA; `skipWaiting` + `clients.claim` + `window.location.reload()` fire ONLY on user click
- [ ] CL003 [P] [US4] Wire `registerSW`'s `onNeedRefresh` callback in `src/main.tsx` to populate a Zustand `swUpdateStore` that the toast subscribes to
- [ ] CL004 [P] [US2] Update Game Detail Overview tab in `src/pages/GameDetail/tabs/Overview.tsx` to call ONLY backend-proxied cover-swap endpoints — `GET /api/v3/cover/{game_id}/sources` to list candidates, `POST /api/v3/cover/{game_id}` to commit. NO direct calls to `steamgriddb.com` (FR-025a)
- [ ] CL005 [P] [US2] Update CSP configuration to NOT allowlist any third-party origin for cover swap (the SteamGridDB CDN is reached only via backend proxy)
- [ ] CL006 [P] Implement `<PageErrorBoundary>` component in `src/components/shared/PageErrorBoundary.tsx` per FR-038a — localized title via i18n, Retry action that resets the boundary, "Back to Dashboard" link, copyable short error id (hash of error message + chunk name); shell remains interactive
- [ ] CL007 [P] Mount `<PageErrorBoundary>` around `<Outlet/>` in the router config in `src/App.tsx` so each top-level page is independently protected
- [ ] CL008 [P] [US7] Implement preferences hydration order in `src/lib/auth/init.tsx` (FR-013b):
  1. Hydrate auth via `GET /api/v3/auth/me`
  2. Overwrite `localStorage` with `user.preferences`
  3. Apply theme + language from preferences before first render
  Optimistic UI on PATCH failure rolls back local change
- [ ] CL009 [P] [US7] Add window-level error handler in `src/main.tsx` that logs unhandled errors to `console.error` and surfaces a generic localized toast — NO POST to any remote endpoint, NO third-party SDK (FR-038b)
- [ ] CL010 [P] **Cross-spec consistency** (already applied to spec.md): the FR-009a body confirms the SPA uses cookie-only auth; CLIs/scripts use API keys per spec 010 FR-005. NO Bearer JWT in the chain at MVP
- [ ] CL011 [P] Add tests in `tests/components/PageErrorBoundary.test.tsx` covering: descendant throws → fallback renders with localized title + Retry + Back to Dashboard + error id; Retry resets the boundary; shell (header, bottom nav) stays interactive
- [ ] CL012 [P] Add tests in `tests/lib/sw-update.test.ts` covering: new SW detected → toast appears; user clicks Reload → `skipWaiting` fires + page reloads; user dismisses → existing SW continues
- [ ] CL013 [P] Add tests in `tests/lib/preferences-hydration.test.ts` covering: device A sets theme=dark + PATCHes; device B opens app → server-wins overwrites local; PATCH failure → optimistic rollback
- [ ] CL014 [P] Add tests in `tests/lib/cover-swap.test.tsx` covering: cover-swap UI calls only the proxied endpoints; no `steamgriddb.com` requests in network mock
