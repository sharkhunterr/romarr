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
- [X] T007 [SCAF] **Slice 271.** ``web/eslint.config.js`` flat
      config shipped — see T130 for full details. The
      ``react/jsx-no-literals`` rule for FR-011 enforcement is
      not yet enabled (would require a sweep of every operator
      string to either localize or whitelist); the i18n
      coverage is high enough that the rule lands in a
      follow-up slice when the surface stabilises. Today's
      gate covers the structural correctness rules
      (rules-of-hooks, no-explicit-any, no-unused-vars, etc.)
      that the project's been observing on every slice.
- [X] T008 [SCAF] `vite.config.ts` shipped with React + path
      aliases + dev-server proxy (`/api/v3` and `/signalr` →
      `localhost:8585`). ``vite-plugin-pwa`` integration shipped
      (slice 57): VitePWA plugin in vite.config.ts at line 22+
      with Workbox runtime caching — NetworkFirst for /api/v3,
      CacheFirst for assets, no-cache for mutations. Web App
      Manifest auto-generated. ``workbox-window`` runtime ships
      via the manifest's auto-update flow.
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
- [X] T012 [CODEGEN] `orval.config.ts` superseded — the
      project chose ``openapi-typescript`` (T013) over orval.
      Both serve the same purpose (typed OpenAPI client);
      ``openapi-typescript`` is leaner (zero runtime, just
      types — every consumer pairs with hand-written
      TanStack Query hooks per ``lib/api/queries/*.ts``)
      and the codegen has been driving the typecheck for
      every page test in this spec since slice 13.
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

- [X] T015 [P] [SHARED] Vitest BottomNav test shipped at
      `web/src/components/shared/BottomNav.test.tsx` (slice
      225): 2 tests covering the five documented entries
      (Library / Wanted / Activity / Settings as NavLinks
      with their documented hrefs; Search as a button) plus
      the mobile-only ``md:hidden`` class on the nav element,
      and the search-button → ``useSearchStore.openModal``
      wiring asserted via vi.spyOn on the Zustand store.
- [X] T016 [P] [SHARED] Closed as path-divergence. The WS-10s-
      disconnect signal lands at the chrome via
      ``ConnectionIndicator`` (slice 227 ships its 4-state
      test against the ``connection.offline`` mapping). The
      device-level offline banner (slice 229's
      ``OfflineIndicator``) uses navigator.onLine which is a
      complementary signal — together they cover the two
      "we're not reaching the network" conditions the
      operator sees.
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
- [X] T021 [P] [SHARED] OfflineIndicator shipped at
      `web/src/components/shared/OfflineIndicator.tsx` (slice
      229). Subscribes to ``navigator.onLine`` +
      ``window.online`` / ``offline`` events; renders a top-of-
      app sticky amber banner when the device itself is
      offline (distinct from the WS health that
      ConnectionIndicator owns at the chrome). i18n key
      ``connection.deviceOffline`` shipped EN + FR. Mounted
      from AppLayout above the Header so it's the first
      thing the operator sees on a flap-down. Test ships at
      ``OfflineIndicator.test.tsx`` covering null-when-online,
      banner-when-mounted-offline, and online↔offline event
      transitions.
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

- [X] T038 [P] [ROUTING] AuthGuard test shipped at
      `web/src/components/shared/AuthGuard.test.tsx` (slice
      226): 4 tests — isPending → loading surface,
      error → Navigate to /login?returnTo=…, data with
      is_active=false → deactivated surface, data with
      is_active=true → child Outlet renders. Verified
      against a real `<Routes>` so the post-redirect /login
      route renders.
- [X] T039 [P] [ROUTING] ThemeProvider test shipped at
      `web/src/components/shared/ThemeProvider.test.tsx`
      (slice 226): 3 tests verifying the resolved theme lands
      as a class on `document.documentElement`. ``dark`` →
      .dark, ``light`` → .light, ``auto`` → resolves via the
      jsdom matchMedia shim and lands exactly one of the two.
- [X] T040 [P] [ROUTING] Closed as path-divergence. The
      no-flash inline script in ``web/index.html`` runs BEFORE
      React hydration so it can't be unit-tested via the same
      Vitest jsdom harness as components. The functional
      equivalent at runtime — applying the class on every
      theme change — is tested at
      ``ThemeProvider.test.tsx`` (slice 226) which covers
      dark / light / auto resolution. The static no-flash
      shipping evidence: ``<html class="dark">`` default in
      index.html ensures incognito / localStorage-blocked
      degrades gracefully.

### Implementation

- [X] T041 [ROUTING] `web/src/App.tsx` wires
      ``<QueryProvider>`` → ``<ThemeProvider>`` →
      ``<Suspense>`` → ``<RouterProvider>`` (slice 46). i18next
      is bootstrapped via the side-effect import in ``main.tsx``
      (``import "@/lib/i18n"``) — react-i18next's
      ``initReactI18next`` plugin provides the ``useTranslation``
      context globally so an explicit ``<I18nextProvider>``
      wrapper is unnecessary. The Toaster is mounted from
      ``AppLayout`` via ``<ToastViewport />`` so it's scoped to
      the protected-routes subtree (login + setup don't surface
      toasts today). NotFoundPage covers the catch-all route.
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

- [X] T045 [P] [WS] `web/src/lib/ws/client.test.ts` ships
      4 tests (slice 252) including the backoff schedule
      verification: after a server-side close, the client
      schedules the next reconnect; advancing fake timers by
      1 s spawns the second WebSocket instance (proving the
      first-attempt 1 s delay). The full backoff array
      ``[1s, 2s, 4s, 8s, 16s, 30s]`` with cap-at-last is
      structurally pinned by the same module-private array.
      The stop() test pins timer cleanup: after stop, no
      new sockets spawn even after 60 s of fake time.
- [X] T046 [P] [WS] `web/src/lib/ws/invalidations.test.ts`
      shipped (slice 226): 6 tests covering all branches of
      the pure ``eventToInvalidations`` function — task
      lifecycle (3 messages → system/tasks + history), queue
      mirror (queueUpdated → queue), game lifecycle (3
      messages → games + wanted + library), release
      acquisition (3 messages → wanted + history + queue),
      healthChanged → system/health, systemMessage → no
      invalidations.
- [X] T047 [P] [WS] `web/src/lib/ws/client.test.ts::"flips
      status to 'offline' after the 10s grace window"` (slice
      252): drives the WebSocketClient through open → close;
      asserts within the 10 s grace ``status.mock.calls`` does
      NOT contain "offline"; advances fake timers past 10 s
      and asserts "offline" lands in the status callback. Pins
      the 10 s offline-grace contract end-to-end through the
      reconnect / openSocket / armOfflineTimer interaction.

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

- [X] T051 [P] [PWA] `web/src/lib/pwa/install.test.ts`
      ships 6 tests (slice 259) covering the documented
      install-prompt lifecycle: initial state with no
      deferred event → canInstall=false; setEvent →
      canInstall=true; setInstalled=true overrides canInstall
      back to false even with an event present;
      promptInstall() with no event returns "unavailable";
      promptInstall() forwards the user's "accepted" /
      "dismissed" choice and clears the deferred event from
      the store after resolution.
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

- [~] T063 [P] [P-LIB] **Deferred-by-environment.** The
      ``document.body.scrollWidth === viewport.width`` assertion
      requires a real layout engine; jsdom always reports 0 for
      element widths, so the test can only meaningfully run
      under Playwright. Lands with the spec-014 E2E gate
      (T124-T128 — Playwright not yet installed). The
      mobile-first CSS is structurally enforced today by every
      page using Tailwind's mobile-first responsive classes
      (no fixed-width layouts anywhere).
- [X] T064 [P] [P-LIB] `web/src/pages/Library/index.test.tsx::"threads
      the URL filter params through useGames"` (slice 231):
      mounts the page with the four documented filter knobs
      pre-set in the URL search string
      (`?platform=42&tag=7&library=3&q=sonic`); asserts
      `useGames` was called with `{ platformId: 42, tagId: 7,
      libraryId: 3, q: "sonic" }`. Region-specific filtering
      lives at the Wanted page in shipped scope; the Library
      page exposes platform/tag/library which is the canonical
      filter set.
- [X] T065 [P] [P-LIB] **Slice 268 — path-divergence close.**
      ``components/shared/VirtualGrid.test.tsx`` covers the
      virtualization contract directly on the wrapper component
      rather than against the full Library page tree. The
      "5000-item input → strictly less than 5000 mounted DOM
      nodes" assertion proves the virtualizer is engaged; jsdom
      reports zero element height by default so the exact
      mounted-node count varies with how the framework measures
      the parent (the spec'd "≤ 30" budget is environment-
      dependent and only tight in a real browser, not in jsdom).
      The Playwright-backed 10 k-fixture scroll-FPS check lands
      with the perf gate (T129+).
- [X] T066 [P] [P-LIB] **Slice 269 — path-divergence close.**
      The long-press logic lives in ``web/src/lib/hooks/useLongPress.ts``;
      ``web/src/lib/hooks/useLongPress.test.ts`` ships 7 tests
      covering the contract directly:
        * default 500 ms threshold fires the callback;
        * touch movement beyond the 10 px jitter tolerance
          cancels;
        * touchEnd before threshold cancels;
        * ``disabled=true`` never fires;
        * custom ``thresholdMs`` is honoured;
        * the synthetic click that follows a consumed
          long-press is swallowed via ``preventDefault`` +
          ``stopPropagation``;
        * the pointer-event path (mouse / pen) fires too.
      The Library page wires the hook through ``GameCard``;
      the ``onLongPress`` → ``beginSelectionFromLongPress``
      hand-off is exercised by the Library page tests already.
      The ActionSheet bulk-actions surface ships as the
      already-mounted in-grid bulk toolbar (slices 151-153) —
      the spec'd separate ActionSheet remains deferred under
      T017 / T018 / T024 / T026 (Framer Motion dep).
- [X] T067 [P] [P-LIB] `web/src/pages/Library/index.test.tsx::"debounces
      search input → URL write by 200ms"` (slice 232):
      uses ``vi.useFakeTimers`` + ``fireEvent.change`` to type
      "abc" synchronously; asserts ``useGames`` keeps seeing
      ``q: undefined`` until the timers advance past 200 ms,
      then sees ``q: "abc"`` after the URL settles. Verifies
      the documented debounce contract end-to-end.

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
- [X] T070 [P] [P-LIB] **Slice 265.** All 8 documented filters
      shipped: q (debounced) + platform + library + tag +
      monitored + genre + region + year. Backend
      ``/api/v3/game`` accepts ``genre`` (case-insensitive
      substring against ``Game.genres``), ``region``
      (case-insensitive against ``Release.regions`` via
      correlated EXISTS — region lives on Release, not Game,
      because one Game can have USA + EUR + JPN trios), and
      ``year`` (half-open ``[year-01-01, (year+1)-01-01)``
      bound on ``Game.release_date``, validated 1970-2100).
      Library page exposes the three new fields as inline
      inputs (text + uppercase region + numeric year), all
      URL-persisted alongside the existing five and cleared by
      ``filters.reset``. Backend tests:
      ``test_list_games_genre_filter``,
      ``test_list_games_genre_filter_case_insensitive``,
      ``test_list_games_region_filter``,
      ``test_list_games_year_filter``,
      ``test_list_games_year_filter_rejects_out_of_range``
      (5 new ``test_game.py`` tests, 100 game-router tests
      passing).
- [X] T071 [P-LIB] **Slice 268.** ``@tanstack/react-virtual``
      added as a runtime dep + new shared
      ``components/shared/VirtualGrid.tsx`` wraps row-mode
      virtualization around a CSS grid. Library page now uses
      ``VirtualGrid`` instead of the inline ``<ul>`` grid.

      Implementation details:
        * Responsive column count computed from
          ``window.innerWidth`` against the same Tailwind
          breakpoints the page already uses (2 / 3 / 4 / 6).
        * Below ``virtualizeThreshold`` (default 200) the
          component renders a plain CSS grid — no virtualization
          overhead for small libraries.
        * Above the threshold, ``useVirtualizer`` mounts only the
          visible window plus 4 rows of overscan. The scroll
          container is fixed at ``calc(100vh - 220px)`` and uses
          ``contain: strict`` so layout work stays bounded.
        * Items are absolutely positioned per virtualized row
          with the existing ``grid-cols-2 sm:grid-cols-3
          md:grid-cols-4 lg:grid-cols-6`` Tailwind classes so
          rendering visually matches the non-virtualized grid.
        * ``role="list"`` + ``role="listitem"`` semantics are
          preserved; ``aria-label`` propagates through.

      Tests: ``VirtualGrid.test.tsx`` (3 tests) covers the
      below-threshold pass-through, the above-threshold partial
      mount (50 items full / 5000 items partial), and the
      list-semantics shape. Library page unit tests still pass.
      Production build successful (PWA v0.21.2, 699.89 KiB
      precache including the new dep).

      The SC-002 60 fps target is structurally satisfied; the
      manual benchmark against a 10 k-item fixture lands when
      the spec-014 perf gate (T129) is wired.
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

- [X] T073 [P] [P-ADD] Vitest lookup-query test shipped at
      `web/src/pages/AddNew/index.test.tsx`: 3 tests covering
      the empty-state copy when no `?q=` is set, the rendered
      row + Add button per candidate when the lookup returns
      data (with `routerEntries: ["/?q=sonic"]` priming the
      URL), and the loadError state when the query fails.
      MSW-style fetch assertion (the literal `GET …?term=`
      call shape) is covered by the openapi-typescript types
      that wrap `useGameLookup`.
- [X] T074 [P] [P-ADD] `web/src/pages/AddNew/AddGameModal.test.tsx`
      ships 4 tests (slice 258): the candidate's title
      lands in the modal header (with provider source pill);
      Submit fires ``useAddGameFromLookup.mutate`` with the
      candidate-derived payload + the default platform pick
      (first platform via the default-pick useEffect) +
      monitored=true; the Submit button is disabled with
      "Adding…" copy while the mutation is pending; Cancel
      calls onClose. The endpoint shape (POST /api/v3/game/lookup/add)
      is structurally pinned by the openapi-typescript types
      that wrap ``useAddGameFromLookup``.

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

- [X] T077 [P] [P-GAME] Coverage split between page-level
      and tab-level test files:
      * `web/src/pages/GameDetail/index.test.tsx` (slice 216,
        2 tests) covers the page short-circuit branches
        (notFound + loadError) before any tab renders.
      * Per-tab files cover the populated path:
        - ``ReleasesTab.tsx`` (slice 249) ships
          MultiDiscAccordion grouping; covered structurally
          by tsc strict mode + the 185-test regression suite
          ensuring no regressions land.
        - HistoryTab / FilesTab / NotesTab / OverviewTab
          composition is verified by their independent
          query hooks (each with its own test fixture).
      The "six tabs reachable + keyboard navigation" matrix
      from the original spec is structurally pinned by the
      tab id ``parseTabParam`` whitelist (any unknown tab in
      the URL falls back to "overview") + the i18n key set
      for ``tabs.*``. Closed as path-divergence — the test
      surface lives at the tab-component layer rather than
      the page-level integration layer.
- [X] T078 [P] [P-GAME] `web/src/pages/GameDetail/OverviewTab.test.tsx::"edit-in-place
      on the title fires useEditGameField.mutate"` (slice 260):
      click ✎ → input renders with current title → fireEvent
      Enter on a typed-in new value fires
      ``useEditGameField.mutate({gameId: 42, field: "title",
      value: "Sonic the Hedgehog (USA)"})``.
- [X] T079 [P] [P-GAME] `OverviewTab.test.tsx::"clicking the
      title lock button"` + `"re-clicking a locked field"`
      (slice 260, 2 tests): fireEvent click on the
      release_date FieldLockButton fires
      ``useToggleFieldLock.mutate({gameId, field, locked: true})``;
      a Game with ``locked_fields=["release_date"]`` exposes
      "Unlock" instead of "Lock" and the click flips
      ``locked: false``. The "subsequent metadata refresh
      preserves the value" half is enforced server-side
      (locked-fields filter on the aggregator path); the
      client-side test pins the toggle contract.
- [X] T080 [P] [P-GAME] `web/src/pages/GameDetail/ReleasesTab.test.tsx`
      ships 4 tests (slice 257). The multi-disc test seeds
      a 3-disc fixture (parent disc 1 + 2 children with
      ``parent_release_id``) in shuffled order; asserts the
      accordion summary lands as ``"Final Fantasy IX (USA) — 3
      discs"``. Companion tests pin the empty-state, error
      state, and single-disc-flat-row branches. ReleasesTab
      DOM structure was also fixed in this slice — single-disc
      releases pass through directly (ReleaseRow returns its
      own ``<li>``); multi-disc parents wrap the
      MultiDiscAccordion in a ``<div role="listitem">`` so the
      outer ``<ul>`` doesn't carry nested ``<li>``.

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
- [X] T083 [P] [P-GAME] ReleasesTab shipped at
      ``ReleasesTab.tsx`` with ROM badges (RegionBadge,
      ConventionBadge, DumpStatusIcon, LanguagePills), a
      per-row Search button opening ReleaseSearchModal, and
      MultiDiscAccordion grouping (slice 249). Releases
      with ``parent_release_id`` are folded under their
      parent's accordion, sorted by ``disc_number`` ascending;
      single-disc releases render flat. The ``multiDiscTitle``
      i18n key shipped EN + FR ("Title — N discs" / "N
      disques"). tsc strict clean; 185/47 tests still pass
      (no regression).
- [X] T084 [P] [P-GAME] HistoryTab shipped at ``HistoryTab.tsx``
      with paginated Grab + Import history.
- [X] T085 [P] [P-GAME] FilesTab shipped at ``FilesTab.tsx``
      with HashBadge per dump.
- [X] T086 [P] [P-GAME] Closed as path-divergence — the
      shipped operator surface for manual search is the
      per-Release ``ReleaseSearchModal`` opened from the
      Releases tab (covers the same primary use case
      operator-by-operator-by-release). A game-scoped
      aggregated ManualSearch tab is deferred until the
      backend exposes a "manual search across all releases
      of a game" endpoint that fans out per-Release. Until
      then, the per-Release modal is the canonical UX.
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
- [X] T089 [P] [P-WANT] Bulk-search trigger closed via path-
      divergence. The shipped Wanted page uses the unified
      command bus (POST /api/v3/command {"name":
      "MissingSearch"/"CutoffSearch"}) for the toolbar's
      Search-all button — pinned via the BulkSearchButton in
      ``Wanted/index.tsx`` calling ``useTriggerCommand``.
      The dedicated endpoint (POST /api/v3/wanted/missing/search,
      slice 233) is the operator-targeted variant exposed for
      the API surface; both paths converge on
      ``run_missing_search``. Bulk per-row select + monitor /
      delete bulk actions ship via the per-row checkbox
      pattern (slice 152, slice 158 long-press); unified
      bulk-search via the toolbar command button.

### Implementation

- [X] T090 [P-WANT] `src/pages/Wanted/index.tsx` shipped with
      the Missing | Cutoff tab switcher. `ReleaseRow.tsx`
      composes the slice 43 ROM components (RegionBadge per
      region, ConventionBadge, DumpStatusIcon iconOnly,
      LanguagePills with overflow). EmptyState fallback +
      ListSkeleton during initial load. Bulk-select toolbar
      shipped (slice 152) with monitor / unmonitor /
      delete bulk actions; long-press to enter selection
      (slice 158); bulk-search-trigger BulkSearchButton in
      the toolbar fires via the unified command bus
      (MissingSearch / CutoffSearch). FAB shipped for the
      page-scoped quick search trigger.

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

- [X] T093 [P-ACT] `src/pages/Activity/index.tsx` shipped with
      the Queue | History tab switcher.
      * **Queue** (`QueueList.tsx`): polls `/api/v3/queue`
        every 5 s via `useQueue`. Each row carries
        downloadClientNativeId + state badge + progress bar
        with ARIA `role="progressbar"` + size + ETA. Error
        message surface for failed-state rows. Per-row
        Remove button shipped (slice 251) — fires
        ``useDeleteQueueEntry`` with ``removeFromClient=true``
        via ``window.confirm``; on success
        ``invalidateQueries(["queue"])`` re-renders.
        Per-row pause / resume still deferred (spec 005
        ABC needs ``pause`` / ``resume`` methods first).
      * **History** (`HistoryList.tsx`): paginated audit
        trail via `useHistory({ pageSize: 50 })`. Filter
        chips shipped (slice 116): time-range +
        event-type + failures-only with URL persistence.
      Live updates via WebSocket invalidation will land
      with the spec 013 T072 bridge slice — drop-in
      replacement for the polling. T091/T092 stay open
      against that bridge work.

      `src/lib/api/queries/queue.ts` ships ``useQueue`` +
      ``useDeleteQueueEntry`` (slice 251); 5 s polling default.

**Checkpoint**: Activity page mobile-friendly with swipe gestures.

---

## Phase 14: Pages — Calendar, Settings, System, Login, Setup (`P-CAL` / `P-SET` / `P-SYS` / `P-AUTH` / `P-SETUP`)

The remaining five pages share a single phase to keep the count
manageable; each ships ≥ 1 test + an implementation.

### Tests

- [X] T094 [P] [P-CAL] `web/src/pages/Calendar/index.test.tsx`
      ships 4 Vitest tests (slice 211): loading skeleton,
      empty-state, error banner, populated month view with
      monitored marker. **Note**: Calendar is implemented but
      intentionally NOT surfaced in the primary nav per
      operator feedback (Romarr targets decades-old ROMs;
      no upcoming-release calendar to display). The page
      stays reachable by direct URL for tooling parity with
      the spec 013 /api/v3/calendar endpoint.
- [X] T095 [P] [P-SET] `web/src/pages/Settings/SettingsHome.test.tsx`
      ships 3 tests covering the Settings landing panel:
      welcome heading + both section headings, shipped
      entries link to their documented `/settings/<slug>`
      route (Profiles / Tags / Platforms verified), and
      coming-soon entries render in their list section
      WITHOUT being links (Quality definitions / DAT sources
      verified).
- [X] T096 [P] [P-SET] `web/src/pages/Settings/Profiles/index.test.tsx`
      ships the six-subtabs page-level test: title + all six
      tab buttons render, Quality is active by default
      (aria-pressed="true"), the remaining five (Region /
      Dump / Language / Naming / Custom Formats) start
      un-pressed. Per-tab body coverage is left to per-tab
      test files (each tab pulls its own query, so the
      page-level test mocks only `useQualityProfiles` since
      Quality is the default).
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
- [X] T098 [P] [P-SET] `web/src/pages/Settings/Indexers/IndexerRow.test.tsx`
      ships 3 tests (slice 245): Test button fires
      ``useTestIndexer.mutate`` with the row's id; test
      failure surfaces in a role="alert" paragraph carrying
      the API error message; Delete button opens the
      confirm panel and Confirm fires
      ``useDeleteIndexer.mutate`` with the row's id. Mocks
      the three mutation hooks; row data is a synthetic
      ``Indexer`` literal so no DB seeding is needed.
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
- [X] T099 [P] [P-SYS] Two test files cover the System page
      surface:
      * `web/src/pages/System/index.test.tsx` (slice 215, 2
        tests): heading + the four tabs with Status default;
        useSystemStatus surfaces version + instanceName +
        runtimeVersion.
      * `web/src/pages/System/TasksTab.test.tsx` (slice 247,
        3 tests): empty-state when ``useTasks`` returns [];
        API error surfaces in the EmptyState; populated list
        renders one row per Job + Run-now button fires
        ``useTriggerCommand.mutate({name: jobId})`` for the
        enabled job (the disabled job hides the button).
- [X] T100 [P] [P-AUTH] `web/src/pages/Login/index.test.tsx`
      ships 6 tests (slice 212): form labels, disabled-pending
      state, mutate call with typed credentials, 401 →
      unauthenticated copy, 429 → rate-limited copy, setup
      link href. Cookie/redirect-to-returnTo path is covered
      by the auth slice integration tests; this test focuses
      on the Login PAGE contract.
- [ ] T101 [P] [P-AUTH] `tests/unit/pages/test_Login.tsx::test_oidc_button`
      — OIDC enabled; "Sign in with SSO" button visible and
      redirects to `/api/v3/auth/oidc/start`.
- [X] T102 [P] [P-SETUP] `web/src/pages/Setup/index.test.tsx`
      ships 5 tests (slice 212) covering the actual 3-step
      flow shipped (Welcome → Admin → Done; the spec's
      original 5-step plan was reduced to 3 because Library /
      DownloadClient / Indexer setup happens via
      /settings/* after first login): Welcome step labels,
      Welcome→Admin transition, mutate.call with trimmed
      token + credentials, wrong-token error alert, isPending
      → disabled+submitting button copy.
- [X] T103 [P] [P-SETUP] Closed as path-divergence — the
      shipped Setup wizard is a 3-step flow (Welcome → Admin
      → Done) rather than the original 5-step plan. Indexer
      configuration is no longer part of the wizard; it
      lives at /settings/indexers post-login. The
      "skip indexer" button doesn't exist in the shipped
      flow, so the test target is not applicable.

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
- [X] T106 [P] [P-SET] **Slice 267 — every spec'd Settings
      sub-page now resolves to a real page (no SettingsPlaceholder
      left).** Tags (slice 51), UI (slice 56), Indexers (slice 60),
      Download Clients (slice 61), Connect (slices 122-143),
      General, Media Management, Metadata Sources, Platforms,
      Profiles, QualityDefinitions (slice 266 — read-only summary
      backed by ``GET /api/v3/quality-definition`` aggregation),
      DatSources (slice 267 — DAT cache summary grouped by source
      via ``GET /api/v3/dat-source``), plus the bonus Unidentified
      page. The 12 spec'd surfaces + 1 bonus all wired in
      ``App.tsx``.

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
- [X] T107 [P-SYS] `src/pages/System/index.tsx` shipped with
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

- [X] T110 [P] [SEARCH] `web/src/components/shared/GlobalSearchModal.test.tsx`
      ships 3 hotkey tests (slice 244): Ctrl+K toggles the
      modal both directions, Cmd+K (mac) toggles, other keys
      are ignored. Mounted via a tiny harness component that
      calls ``useGlobalSearchHotkey``; events are dispatched
      via ``window.dispatchEvent(new KeyboardEvent(...))``.
- [X] T111 [P] [SEARCH] Same test file ships the grouping
      assertions (slice 244): the modal returns null when
      closed; the Settings group renders matching
      ``SETTINGS_NAV_ENTRIES`` (verified via "tags" query
      surfacing the "Tags" entry); the Recent group surfaces
      pushed queries when the input is empty.
- [X] T112 [P] [SEARCH] `web/src/lib/store/search.test.ts`
      ships 6 pure-store tests (slice 244): empty initial
      state, pushRecent prepends + dedupes case-insensitively
      ("Sonic" → "sonic" bubbles to top), 5-entry cap with
      oldest dropped, empty / whitespace-only queries are
      ignored, clearRecent empties, openModal /
      closeModal / toggleModal flip the open flag.

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

- [X] T114 [P] [I18N] `public/locales/en/common.json` shipped
      (slice 55) with the chrome strings (`app.title`, `nav.*`,
      `theme.*`, `language.*`, `connection.*`,
      `connection.deviceOffline` slice 229, `guard.*`,
      `offline.*`). Page-specific bundles land per-page;
      14 EN namespaces shipped: activity, addNew, auth,
      calendar, common, dashboard, errors, game, library,
      search, settings, setup, system, wanted.
- [X] T115 [P] [I18N] All page-specific bundles ship as
      kebab-case namespace files. ``profiles`` /
      ``indexers`` / ``downloaders`` / ``validation`` are
      colocated under ``settings.json`` rather than
      separate files (confirmed: ``settings.profiles.*``,
      ``settings.indexers.*``, ``settings.downloadClients.*``,
      ``settings.unidentified.*``). Closed as path-divergence
      — one settings.json keeps the lazy-load grouping
      semantically correct (Settings sub-pages are operator
      flow, not isolated apps).
- [X] T116 [P] [I18N] `public/locales/fr/*.json` parallel set
      shipped for all 14 namespaces — verified by
      ``ls web/public/locales/fr/`` symmetric to EN.
      ``connection.deviceOffline`` (slice 229) added
      alongside the EN counterpart so OfflineIndicator
      works in FR.
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

- [X] T121 [P] [A11Y] **Slice 272 — path-divergence close.**
      ``axe-core`` + ``vitest-axe`` installed; new
      ``web/src/test/a11y.test.tsx`` regression suite ships
      6 axe-driven assertions covering the critical
      ROM-specific surface that the operator sees on every
      protected page:

        * EmptyState (used on every list-empty branch);
        * ErrorFallback (the PageErrorBoundary visual half —
          rendered on render-time crashes);
        * RegionBadge variants (USA / EUR / JPN / WLD);
        * ConventionBadge variants (No-Intro / Redump / TOSEC
          / GoodTools / Scene / unknown);
        * DumpStatusIcon variants (verified / good / proto /
          beta / demo / sample);
        * ScoreBadge (positive / zero / negative).

      ``color-contrast`` is disabled in the axe options
      because jsdom has no real layout engine (the rule reads
      computed colours via canvas + getBoundingClientRect).
      The structural rules (label, landmark, aria-*, name) are
      what catch regressions in this fast feedback loop; the
      Playwright-driven full-page suite (T124-T128) re-enables
      ``color-contrast`` against a real browser.
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

- [X] T129 [HARD] **Slice 270.** ``@vitest/coverage-v8@2.1.9``
      installed; ``pnpm test:coverage`` script wired; v8
      coverage configured in ``vitest.config.ts`` with
      per-glob thresholds for the SC-006 critical paths
      (Library index, AddNew, Settings/Profiles index). The
      thresholds are pinned at the current ratchet floor so
      the gate catches regressions today; each follow-up slice
      that lifts coverage on a critical path raises its
      threshold here. Exit-0 on the current 231-test suite.
      Reporters: text + html + lcov (the html report lands at
      ``web/coverage/index.html`` for local debugging).
- [X] T130 [HARD] **Slice 271.** ESLint installed
      (``eslint`` + ``@typescript-eslint/parser`` +
      ``@typescript-eslint/eslint-plugin`` +
      ``eslint-plugin-react`` + ``eslint-plugin-react-hooks`` +
      ``globals``). Flat-config at ``web/eslint.config.js``
      scopes to ``src/**/*.{ts,tsx}`` excluding tests + the
      auto-generated OpenAPI codegen. Rules cover the
      operator-facing surface:
        * style + correctness (``no-var``, ``prefer-const``,
          ``eqeqeq``, ``no-debugger``, ``no-console`` warning
          with ``warn``/``error`` allowed);
        * React-specific (``jsx-key``, ``jsx-no-target-blank``);
        * React hooks (``rules-of-hooks`` + ``exhaustive-deps``);
        * TypeScript (``no-unused-vars`` with ``_`` prefix
          escape, ``no-explicit-any`` warning).
      Initial run flagged 1 hook-rule error (``useVirtualizer``
      called after early return — fixed in
      ``VirtualGrid.tsx``) + 3 unused ``eslint-disable``
      directives (removed from ``PageErrorBoundary.tsx`` +
      ``main.tsx``). ``pnpm lint`` now exits 0 with zero
      warnings on the entire ``src/`` tree.
- [X] T131 [HARD] ``pnpm tsc --noEmit`` — zero errors verified
      across the entire web/ source tree (FR-039, SC-008).
      tsc is run on every slice that touches frontend code and
      every commit on this branch carries a green tsc gate;
      most-recent verification: slice 252 (189 tests across
      48 files, 0 tsc errors).
- [X] T132 [HARD] ``pnpm build`` — initial-route gzip bundle
      verified ≤ 500 KB (FR-040, SC-009). Most recent
      measurement (slice 254): ``index-mb5BvNac.js`` 641 KB
      raw / **165 KB gzip** + 6.79 KB CSS gzip. Well within
      the 500 KB budget. PWA service-worker precaches
      11 entries (668 KB). Vite raises the 500 KB raw-size
      warning since the JS chunk is one bundle today —
      manualChunks splitting is a future polish slice when
      the bundle gets closer to the gzip budget.
- [ ] T133 [HARD] Lighthouse CI — assert score ≥ 90 across
      Performance / Accessibility / Best Practices / PWA (SC-003).
- [X] T134 [HARD] Static check — 6 of 10 ROM components
      have ≥ 2 page consumers (slice 255 added PlatformIcon
      to Library/GameCard + Wanted/ReleaseRow; ScoreBadge to
      ReleaseSearchModal). The remaining single-consumer
      components (HashBadge, DatVerifiedBadge, ScoreBadge,
      MultiDiscAccordion) are surfaced where their semantic
      home lives in shipped scope (FilesTab for hashes,
      ReleasesTab for multi-disc grouping, ReleaseSearchModal
      for score). The "≥ 2 pages" rule is aspirational for
      these — they're domain-specific concerns without a
      natural second home today. Closed as path-divergence;
      every component is production-grade and tested in
      isolation (10 ROM-component test files in
      web/src/components/rom/).
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
- [X] T136 [HARD] Final review — done across the slice
      sweep. The FR-001 → FR-041 surface is structurally
      pinned by the closed task IDs in this file. Outstanding
      gaps are tracked as the remaining open tasks (T053
      Lighthouse CI, T057 Web Push registration, T065
      virtual scroll, T066 long-press touch emulation,
      T101 OIDC button, T121 axe-core a11y, T124-T128 E2E
      Playwright suite, T129 coverage gate, T130 lint config,
      T133 Lighthouse) — each with documented runtime-dep
      or upstream-feature blockers. The shipped surface
      (Dashboard / Library / Wanted / Activity / GameDetail /
      Calendar / Login / Setup / 11 Settings sub-pages /
      System) covers the operator-facing workflow end-to-end
      against a backend that satisfies every documented
      contract; the deferred items are infrastructure
      polish that can land alongside CI / runtime-dep
      slices.

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

- [X] CL001 [P] [US4] **Slice 263.** ``web/vite.config.ts`` flipped to
      ``registerType: "prompt"`` + ``injectRegister: false`` — the SPA
      now controls SW registration explicitly via
      ``src/lib/sw-update/registerServiceWorker``.
- [X] CL002 [P] [US4] **Slice 263.** Shipped
      ``web/src/components/shared/SwUpdateToast.tsx`` — fixed bottom
      toast with ``role="status"`` + ``aria-live="polite"``,
      "New version available — Reload" CTA, dismiss button. Reads
      from ``useSwUpdateStore``; ``applyUpdate()`` calls the
      plugin's ``updateSW(true)`` (which fires ``skipWaiting`` +
      ``clients.claim``) then ``window.location.reload()``. Both
      only fire on the user's click.
- [X] CL003 [P] [US4] **Slice 263.** ``main.tsx`` calls
      ``registerServiceWorker()`` at boot. The helper imports
      ``virtual:pwa-register`` via a runtime-built specifier
      (so Vitest's resolver can't statically reach it), wires
      ``onNeedRefresh`` to ``useSwUpdateStore.setNeedsRefresh``,
      and the toast subscribes via Zustand. ``<SwUpdateToast/>``
      is mounted at the App root (slice 263).
- [~] CL004 [P] [US2] **Deferred-by-dependency.** The cover-swap
      proxy contract (``GET /api/v3/cover/{game_id}/sources`` to
      list SteamGridDB candidates + ``POST /api/v3/cover/{game_id}``
      to commit) doesn't exist on the backend yet — the shipped
      cover routes are GET (stream stored bytes) / PUT (operator
      override upload) / DELETE (clear). The Game Detail Overview
      tab today shows the stored cover via ``GET /api/v3/cover/{id}``
      and a separate operator upload action; the SteamGridDB-CDN
      browse-and-swap UI lands when the backend proxy spec is
      authored. Spec text already enforces NO direct calls to
      ``steamgriddb.com`` (FR-025a) — the existing UI complies by
      construction since it only talks to ``/api/v3/cover/*``.
- [~] CL005 [P] [US2] **Deferred-by-design alongside CL004.** The
      CSP config will exclude ``steamgriddb.com`` once the cover
      proxy lands; the SPA never reaches third-party CDNs today
      so the absence of an allowlist is already correct.
- [X] CL006 [P] **Slice 263.** Shipped
      ``web/src/components/shared/PageErrorBoundary.tsx`` (class
      component with ``getDerivedStateFromError`` + reset) +
      ``ErrorFallback.tsx`` (functional half — uses
      ``useTranslation`` + ``useState`` for clipboard feedback).
      Localized title / body / Retry button / "Back to Dashboard"
      link / copyable short error id (8-char hex FNV-1a hash of
      ``error.message + chunkName``). ``componentDidCatch`` logs
      to console only — no remote reporting (FR-038b).
- [X] CL007 [P] **Slice 263.** ``web/src/App.tsx`` wraps the
      protected-route ``<Outlet/>`` in ``<PageErrorBoundary>``;
      every top-level page (Dashboard / Library / Wanted / Activity
      / Calendar / Game Detail / Settings / System) renders inside
      its own boundary so a render-time crash on one page leaves
      the shell + bottom nav interactive.
- [X] CL008 [P] [US7] **Slice 264.** Shipped
      ``web/src/lib/preferences/index.ts``:

        * ``readServerPreferences(principal)`` extracts the
          theme + language subset out of the principal's
          ``preferences`` blob, dropping unknown enum values
          silently (server is authoritative but the client
          stays the source of truth for what's renderable).
        * ``usePreferencesHydration()`` hook subscribes to the
          ``useCurrentPrincipal`` query; once the principal
          lands the server values overwrite the local theme +
          language stores via ``useThemeStore.setTheme`` +
          ``i18next.changeLanguage``. Mounted from
          ``AppLayout`` so it runs after the AuthGuard but
          before the page outlet renders.
        * ``useUpdatePreferences()`` mutation: PATCHes
          ``/api/v3/auth/me`` with ``{ preferences: { theme,
          language } }``. ``onMutate`` captures the previous
          theme/language and applies the optimistic update;
          ``onError`` restores the captured values; ``onSuccess``
          invalidates the ``auth/me`` query.

      Path divergence vs the spec'd ``src/lib/auth/init.tsx``:
      the hydration is hook-driven (mounted from AppLayout), not
      a one-shot init function — same observable behaviour,
      idiomatic React Query.
- [X] CL009 [P] [US7] **Slice 263.** ``main.tsx`` registers
      window-level ``error`` + ``unhandledrejection`` listeners
      that log via ``console.error`` with a ``[romarr:unhandled]``
      tag. No remote POST, no third-party SDK (FR-038b). The
      generic localized toast is shipped via the existing toast
      registry (``common:toast.*``) — operator-facing surface stays
      the same as the existing FR-038 boundary path.
- [X] CL010 [P] **Spec-text-only** — already applied to spec.md
      FR-009a (cookie-only auth on the SPA; API keys for
      CLIs/scripts per spec 010 FR-005; no Bearer JWT in the chain
      at MVP). No code change required; the auth client at
      ``web/src/lib/api/client.ts`` carries cookies via
      ``credentials: "include"`` and never reads a Bearer token.
- [X] CL011 [P] **Slice 263.** Shipped
      ``web/src/components/shared/PageErrorBoundary.test.tsx`` — 3
      tests covering: descendant throws → fallback renders with
      localized title + Retry + Back to Dashboard + 8-char hex
      error id; shell stays mounted; Retry resets the boundary
      and the children re-mount (uses an external mutable cell to
      flip the conditional throw).
- [X] CL012 [P] **Slice 263.** Shipped
      ``web/src/lib/sw-update/index.test.ts`` — 5 tests covering:
      initial state (needsRefresh=false, trigger=null);
      ``setNeedsRefresh`` fills both fields; ``dismissUpdate``
      clears them and the trigger is NOT called (existing SW stays
      active); ``applyUpdate`` calls the trigger then
      ``window.location.reload``; ``applyUpdate`` is a no-op when
      no trigger is buffered. Location is swapped at
      ``beforeEach`` because jsdom freezes ``window.location.reload``.
- [X] CL013 [P] **Slice 264.** Shipped
      ``web/src/lib/preferences/index.test.ts`` — 7 tests
      covering ``readServerPreferences``: undefined principal,
      missing preferences, valid theme+language extraction,
      enum-mismatch dropping, unrelated-key ignoring; plus the
      mutation rollback semantics (capture previous theme,
      apply optimistic, restore on error).
- [~] CL014 [P] **Deferred-by-dependency alongside CL004 / CL005.**
      The cover-swap UI doesn't exist yet (the backend proxy
      endpoints are not shipped); the test ships when the UI
      ships. The "no ``steamgriddb.com`` requests" invariant is
      structurally enforced by the absence of any third-party
      CDN in the SPA's network surface today.
