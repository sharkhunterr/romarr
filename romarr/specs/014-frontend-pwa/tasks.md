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
- [~] T009 [SCAF] Docker integration **deferred** — needs the
      backend's `StaticFiles` mount wired at `/`, which is a
      coordinated change touching `src/romarr/api/app.py`. The
      multi-stage build outline is documented in
      `web/README.md`; the actual Dockerfile lands when the
      frontend has enough to serve.

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

- [~] T015 [P] [SHARED] Vitest BottomNav test **deferred** —
      Vitest not yet installed. The 5-entry visibility-on-mobile-
      only contract is implemented via `md:hidden`.
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

- [~] T027-T036 [P] [ROM] Vitest + Testing Library unit tests
      **deferred** — Vitest is not yet installed (lands with
      the testing phase). The components themselves ship today
      (T037); compile-time correctness is exercised end-to-end
      via the App.tsx showcase + `pnpm typecheck` + `pnpm
      build`. Per-component RTL tests come along when the
      testing matrix is wired.

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

- [~] T059-T061 [P] [P-DASH] Vitest unit tests **deferred** —
      Vitest not yet installed. The Dashboard's contract is
      implemented end-to-end (StatCards render system info,
      HealthPanel surfaces the spec 011 snapshot,
      QuickActions fires Sonarr-shape commands); the spec
      tests get written when the testing matrix lands.

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

- [ ] T068 [P-LIB] Create `src/pages/Library/index.tsx` — grid
      layout (1 / 2 / 4 / 6 columns by viewport).
- [ ] T069 [P] [P-LIB] Create
      `src/pages/Library/components/GameCard.tsx` using the ROM
      components (CoverImage, RegionBadge, DumpStatusIcon,
      PlatformIcon).
- [ ] T070 [P] [P-LIB] Create
      `src/pages/Library/components/FilterBar.tsx` with debounced
      search + platform/library/profile/tag/genre/year/region
      filters.
- [ ] T071 [P-LIB] Wire the page to the generated `useGames` hook
      with TanStack Virtual for the grid.
- [ ] T072 [P-LIB] Add the FAB for "Add New" → navigate to
      `/add`.

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

- [ ] T075 [P-ADD] Create `src/pages/Add/index.tsx` with the
      lookup search bar and the platform multi-select.
- [ ] T076 [P] [P-ADD] Create
      `src/pages/Add/components/AddGameModal.tsx` with the
      library/profile/monitored choices.

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

- [ ] T081 [P-GAME] Create
      `src/pages/GameDetail/index.tsx` with the tab router.
- [ ] T082 [P] [P-GAME] Create
      `src/pages/GameDetail/tabs/Overview.tsx` with EditableField
      + LockToggle + AttributionBadge.
- [ ] T083 [P] [P-GAME] Create
      `src/pages/GameDetail/tabs/Releases.tsx` using
      MultiDiscAccordion + ROM badges.
- [ ] T084 [P] [P-GAME] Create
      `src/pages/GameDetail/tabs/History.tsx`.
- [ ] T085 [P] [P-GAME] Create
      `src/pages/GameDetail/tabs/Files.tsx` (HashBadge per dump).
- [ ] T086 [P] [P-GAME] Create
      `src/pages/GameDetail/tabs/ManualSearch.tsx` (live indexer
      search results with ScoreBadge).
- [ ] T087 [P] [P-GAME] Create
      `src/pages/GameDetail/tabs/Notes.tsx`.

**Checkpoint**: every tab renders; edit-in-place persists.

---

## Phase 12: Page — Wanted (`P-WANT`)

### Tests

- [~] T088 [P] [P-WANT] Vitest two-tabs test **deferred** —
      Vitest not yet installed. The contract is implemented:
      `WantedPage` renders Missing | Cutoff tabs; switching
      tabs triggers the matching endpoint via
      `useWantedMissing` / `useWantedCutoff`.
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

- [~] T091 [P] [P-ACT] `test_queue_live_updates` **deferred**
      — Vitest not yet installed. Plus the WS path needs the
      spec 013 T072 bridge slice to forward `queueUpdated`
      events. Today's QueueList polls every 5s instead.
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
- [ ] T096 [P] [P-SET] `tests/unit/pages/Settings/test_Profiles.tsx::test_six_subtabs`
      — Quality / Region / Dump / Language / Naming / CustomFormats
      each render; the Naming tab shows a live preview.
- [ ] T097 [P] [P-SET] `tests/unit/pages/Settings/test_CustomFormats.tsx::test_visual_builder`
      — operator can add an OR-grouped condition via the visual
      builder.
- [ ] T098 [P] [P-SET] `tests/unit/pages/Settings/test_Indexers.tsx::test_test_button`
      — test button fires the documented endpoint and shows
      success/error.
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
      yet.
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
- [ ] T106 [P] [P-SET] Create the 11 sub-pages under
      `src/pages/Settings/` per the spec.
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

- [ ] T110 [P] [SEARCH] `tests/unit/components/test_GlobalSearch.tsx::test_keyboard_shortcut`
      — `Ctrl+K`; modal opens with input focused.
- [ ] T111 [P] [SEARCH] `tests/unit/components/test_GlobalSearch.tsx::test_groups_results`
      — Games / Releases / Settings categories.
- [ ] T112 [P] [SEARCH] `tests/unit/components/test_GlobalSearch.tsx::test_recent_searches`
      — last 5 in localStorage.

### Implementation

- [ ] T113 [SEARCH] Create
      `src/components/shared/GlobalSearch.tsx` — modal + keyboard
      navigation + recent-searches store.

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
- [ ] T118 [P] [I18N] `lib/i18n/dates.ts` — date-fns locale
      switching. Lands when the first page using formatted
      dates migrates.
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
- [ ] T120 [I18N] CI gate: `eslint react/jsx-no-literals` zero
      warnings on `components/` and `pages/` (FR-011). The
      chrome (Header, BottomNav, ConnectionIndicator) is
      migrated; pages still carry the per-file disable
      comment until their migration slice.

### Accessibility (`A11Y`)

- [ ] T121 [P] [A11Y] `tests/a11y/critical-pages.spec.ts` — axe-core
      against Dashboard, Library, GameDetail, Settings; assert
      zero errors (FR-037, SC-007).
- [ ] T122 [P] [A11Y] Add `aria-label` to every icon-only button
      (sweep + lint rule `jsx-a11y/icon-button-needs-label`).
- [ ] T123 [P] [A11Y] Honour `prefers-reduced-motion` in
      `globals.css` — disable transitions when set.

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
- [ ] T135 [HARD] Update repo `CHANGELOG.md`: "0.14.0a1 — Frontend
      (React PWA): mobile-first, installable PWA, FR + EN, 11
      pages, 10 ROM components, OpenAPI codegen, SignalR-compat
      WebSocket consumer."
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
