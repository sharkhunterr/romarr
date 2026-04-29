# Feature Specification: Frontend (React PWA)

**Feature Branch**: `014-frontend-pwa` (branch creation skipped: git repo lives in parent dir)
**Created**: 2026-04-29
**Status**: Draft
**Depends on**: `013-rest-api-websocket` — the OpenAPI 3.1 spec served at
`/api/v3/openapi.json` is the single source of truth for type generation;
the `/signalr/messages` WebSocket is the source of live events.
**Input**: User description: "Build the React 18 + TypeScript frontend for Romarr — mobile-first PWA, dark by default, fully internationalized FR + EN. Constitution compliance on the 360-pixel viewport, PWA install, shadcn/ui + Tailwind, ROM-specific components first-class."

## Clarifications

### Session 2026-04-29

- Q: Brand accent color identifying Romarr across the UI? → A: Game Boy LCD green `#9BBC0F`
- Q: How does the UI render a translation key with no value in any bundle? → A: Render the raw key with an `[i18n]` prefix in production (e.g., `[i18n] library.empty_state_title`); render the bare key in development
- Q: After an OIDC round-trip, what credential does the browser SPA hold? → A: Cookie session only (`HttpOnly + SameSite=Lax`); no JWT exposed to JavaScript. Non-browser clients (CLIs, scripts) use API keys per spec 010 FR-005 (no Bearer JWT in the chain at MVP per spec 010 clarification)
- Q: What happens when the operator visits `/setup` on an already-set-up instance? → A: Silent redirect to `/` (Dashboard) — the setup wizard is a one-shot first-boot affordance, mirroring Sonarr / Radarr behaviour
- Q: When does the Web Push permission prompt fire? → A: Only on explicit operator click in `/settings/ui` or `/settings/connect`. A one-time Dashboard banner after first login informs that the option exists; the prompt itself never auto-fires
- Q: How does the installed PWA apply a new service-worker build? → A: Non-blocking toast ("New version available — Reload"); `skipWaiting` + `clients.claim` fire only on user click. No silent auto-reload
- Q: What network path swaps the Game Detail cover from SteamGridDB? → A: Backend proxies SteamGridDB. The frontend calls `/api/v3/cover/{game_id}/sources` and `POST /api/v3/cover/{game_id}` to pick one. The SteamGridDB API key never reaches the browser
- Q: What does the operator see when a page-level component throws during render? → A: A per-page error boundary scoped under the router outlet catches the throw and renders a localized fallback (Retry + "Back to Dashboard" + copyable error id); header + bottom nav remain interactive
- Q: How are user preferences reconciled across two devices? → A: Server wins on read, last-write-wins on write. `localStorage` is a cache, never the authority. Every app load overwrites local from `user.preferences`; every change PATCHes immediately
- Q: How are unhandled JavaScript errors surfaced and recorded? → A: Console only plus a generic localized toast. No remote reporting endpoint, no third-party SDK. Operators copy the console output and the per-page boundary's error id into a GitHub issue. A backend log-ingest endpoint is deferred to v1+

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Operator browses the Library on their phone (Priority: P1)

A Romarr operator opens Romarr in mobile Safari (iPhone, 390 px) or
Chrome on Android (360 px). They land on the Library page, see a
single-column grid of game cards with cover, title, platform
badge, region badges, and dump-status icon. They filter by
"Mega Drive" + "USA" with two taps; the list refreshes
instantly. They long-press a card to enter bulk-select mode and
toggle monitor on three games via a bottom action sheet.

**Why this priority**: Mobile-first is the constitutional core
(Article XV). Without a working Library on 360 px, the whole
mobile-first promise collapses.

**Independent Test**: Open the page in Chrome DevTools'
360 px-wide mobile preset; assert the layout has zero
horizontal scrollbars, every interactive element is reachable
via touch, the bottom navigation bar is visible. Filter and
bulk-select via Playwright touch emulation.

**Acceptance Scenarios**:

1. **Given** a viewport of 360 px width, **When** the operator
   loads `/library`, **Then** the page renders without
   horizontal scroll and every visible interactive control has
   ≥ 44 × 44 px hit target.
2. **Given** the same page, **When** the operator types in the
   search bar, **Then** the list filters with ≤ 200 ms
   debounce; intermediate keystrokes do NOT trigger network
   requests.
3. **Given** 10 000 Games in the library, **When** the operator
   scrolls, **Then** the list maintains ≥ 60 fps via virtual
   scrolling; only the visible rows are mounted.
4. **Given** the operator long-presses a card, **When** the
   gesture is detected, **Then** the page enters bulk-select
   mode; subsequent taps on cards toggle their selected state;
   a bottom action sheet appears with bulk-action buttons.

---

### User Story 2 — Operator edits a Game's metadata in place (Priority: P1)

A Romarr operator opens *Sonic the Hedgehog* on Mega Drive at
`/game/123`. They see five tabs: Overview, Releases, History,
Files, Manual Search. The Overview tab shows the cover, title,
summary, and a row of metadata fields each with a "lock" toggle
and a small attribution badge (`igdb` / `mobygames` /
`screenscraper`). They click the title's edit pencil, change it,
toggle the field's lock; the field is now protected from
metadata refresh.

**Why this priority**: Edit-in-place + per-field locks are the
constitutional anti-RomM-#1770 mechanism (Article IX). Without a
clear, intuitive UI for it, operators cannot trust the
metadata-aggregation feature.

**Independent Test**: Open `/game/{id}`; click a field's edit
pencil; modify the value; click the lock toggle; assert the
PATCH includes the new value AND the locked-fields update;
trigger a metadata refresh from the page; assert the locked
field is unchanged.

**Acceptance Scenarios**:

1. **Given** a Game detail page, **When** the operator clicks a
   field's edit pencil, **Then** an inline input appears,
   focused; submitting saves via PATCH with optimistic UI
   update.
2. **Given** a field with a lock toggle, **When** the operator
   locks it and triggers a metadata refresh from the same page,
   **Then** the locked field's value is preserved.
3. **Given** the Releases tab, **When** the operator views a
   multi-disc Game, **Then** the discs render as a collapsible
   accordion grouped by `parent_release_id` with the parent disc
   first.

---

### User Story 3 — Operator triggers Missing Search in bulk (Priority: P1)

A Romarr operator opens `/wanted`, sees the Missing tab with 47
wanted Releases. They tap "Select All", then "Search Selected".
The bulk-search command is fired; the Activity page lights up
with progress events; toasts notify of grabs as they happen.

**Why this priority**: This is the most-used grow-the-collection
workflow.

**Independent Test**: With 47 fixture wanted Releases, navigate to
`/wanted/missing`; click "Select All"; click "Search Selected";
assert a `MissingSearch` command is dispatched with the right
release ids; navigate to `/activity`; assert progress events
arrive over WebSocket; assert toasts fire on grab.

**Acceptance Scenarios**:

1. **Given** the Missing tab with N wanted Releases, **When**
   the operator clicks "Select All" then "Search Selected",
   **Then** a single command POST fires; the response carries
   the command id; the Activity page shows progress.
2. **Given** the search produces a grab, **When** the
   `releaseGrabbed` event arrives over the WebSocket,
   **Then** a toast appears within 1 second of the event with
   the Game's title.
3. **Given** the WebSocket disconnects mid-search, **When** the
   operator switches to the Activity page, **Then** the page
   falls back to TanStack Query polling (the search results
   are still visible).

---

### User Story 4 — PWA installs and reads work offline (Priority: P1)

A Romarr operator on Chrome desktop sees the install prompt;
they install Romarr to their dock. The app opens in its own
window with the theme-color status bar. They go offline; they
can still browse the Library (cached reads work) but mutation
buttons are visibly disabled with an "offline" indicator.

**Why this priority**: PWA installability is the constitutional
requirement (Article XV). Offline reads are what makes a
homelab dashboard usable across spotty Wi-Fi.

**Independent Test**: Open Romarr in Chrome; assert the install
prompt appears via `beforeinstallprompt`; install the PWA;
disconnect the network; assert the Library page still renders
with the last-cached data; assert mutation UI is disabled.

**Acceptance Scenarios**:

1. **Given** a Chromium browser, **When** the operator visits
   the app for the second time, **Then** the install prompt
   fires and the manifest passes Lighthouse PWA checks
   (installable, service worker, manifest, score ≥ 90).
2. **Given** the installed PWA, **When** the network is offline,
   **Then** previously-loaded pages render from the cache
   (network-first with cache fallback for API calls).
3. **Given** the offline state, **When** the operator clicks a
   mutating button, **Then** the button is disabled with an
   "offline" tooltip; the disabled state is announced via
   `aria-disabled`.

---

### User Story 5 — Operator manages settings on the desktop (Priority: P2)

A Romarr operator opens `/settings` on a 1920 × 1080 monitor.
They see a left sidebar with the documented sub-pages. They
configure their first indexer at `/settings/indexers`; click
"Test"; see the green "Connected" badge; save. They configure
a Discord notification; click "Test"; assert their channel
gets a synthetic message.

**Why this priority**: Settings is where operators spend their
day-1 time. A coherent settings UX gates onboarding.

**Independent Test**: Walk through each documented Settings
sub-page in Playwright; assert it renders, the form fields
match the OpenAPI schema, the test buttons fire, and submit
persists via the documented endpoints.

**Acceptance Scenarios**:

1. **Given** the Settings page, **When** the operator navigates
   between sub-pages via the sidebar, **Then** the right pane
   updates without a full page reload (client-side routing).
2. **Given** an Indexer create form, **When** the operator
   submits without filling required fields, **Then** the form
   surfaces field-level validation errors aligned with the
   server's response shape.
3. **Given** a notification "Test" button, **When** the
   operator clicks it, **Then** the button shows a loading
   state; on response, a toast confirms success or surfaces the
   structured error.

---

### User Story 6 — Dashboard pulses with live state (Priority: P2)

A Romarr operator parks Romarr in their browser. The Dashboard
shows current stats (games, releases, queued downloads) and a
recent-activity feed. As scheduled jobs fire, the feed updates
in real time; as health changes, the health panel transitions
in/out without flicker.

**Why this priority**: A static dashboard is dead weight. Live
updates are how operators trust the system is alive.

**Independent Test**: Open `/`; trigger a `MissingSearch`
command from the API; assert the activity feed receives a new
row within 1 s; degrade an indexer's health; assert the
health panel transitions to "warning" with the right message.

**Acceptance Scenarios**:

1. **Given** the Dashboard, **When** an `OnImport` event fires
   over the WebSocket, **Then** the recent-activity feed
   prepends the new row within 1 s.
2. **Given** the same page, **When** a `healthChanged` event
   arrives, **Then** the health panel updates with the new
   status, optionally adding/removing rows.
3. **Given** the WebSocket disconnects, **When** the connection
   is broken for ≥ 10 s, **Then** an offline indicator appears
   in the header; reconnection clears it.

---

### User Story 7 — Operator switches the UI to French (Priority: P2)

A Francophone operator opens `/settings/ui`, picks "Français"
in the language selector, and watches every visible string
translate without a page reload.

**Why this priority**: French + English is the constitutional
day-one bundle (Article XV). Language-switching feels broken if
it requires a reload.

**Independent Test**: Render the app in `en`; trigger the
language switch to `fr`; assert no `window.location.reload()`
fires; assert all visible strings are now French (snapshot
test with a hand-picked corpus of 20 strings across pages).

**Acceptance Scenarios**:

1. **Given** the app rendered in English, **When** the
   operator switches to French via the dropdown, **Then** every
   visible string updates without a reload; the choice
   persists in localStorage and is PATCHed onto the user's
   `preferences` JSON.
2. **Given** dates in the UI, **When** the language is French,
   **Then** dates render as "29 avril 2026" (locale-aware via
   date-fns).
3. **Given** an unsupported language is requested via URL
   query, **When** i18next falls back, **Then** the default
   language (English) is rendered with a single console
   warning, no UI flash.

---

### User Story 8 — First-boot operator runs the setup wizard (Priority: P3)

A brand-new Romarr operator visits the URL and is redirected to
`/setup`. The wizard walks them through five steps: Welcome,
Create Admin (using the setup token from the logs), Create
First Library, Create First Download Client, Create First
Indexer (or skip). At "Done", they land on the Dashboard.

**Why this priority**: Without a guided setup, new operators
hit a 404 or a useless empty Dashboard. Useful but not blocking
day-1 — the API-only flow exists.

**Independent Test**: Boot a fresh database; visit `/`; assert
the redirect to `/setup`; complete the wizard via Playwright;
assert the operator lands on `/` with a working session.

**Acceptance Scenarios**:

1. **Given** an empty user table, **When** any unauthenticated
   visit lands on the app, **Then** the operator is redirected
   to `/setup`.
2. **Given** the Welcome step, **When** the operator completes
   the Create-Admin step with the setup token, **Then** the
   session cookie is set and the wizard advances.
3. **Given** the Indexer step, **When** the operator clicks
   "Skip", **Then** the wizard advances to "Done" without
   creating an indexer.

---

### User Story 9 — Power user uses ⌘+K global search (Priority: P3)

A Romarr power user hits `⌘+K` (Mac) or `Ctrl+K` (Windows /
Linux). A modal opens with a single search input. They type
"sonic"; results group by category: Games, Releases, Settings
pages. Arrow keys navigate; Enter teleports to the chosen
result.

**Why this priority**: A keyboard-driven palette is a
quality-of-life feature. Useful but not blocking.

**Independent Test**: Press `Ctrl+K`; assert the modal opens;
type "sonic"; assert results appear within 200 ms; press
ArrowDown then Enter; assert the route changes.

**Acceptance Scenarios**:

1. **Given** the app is focused, **When** the operator presses
   `⌘+K` / `Ctrl+K`, **Then** the global-search modal opens
   with the input focused.
2. **Given** the modal is open with results, **When** the
   operator presses Enter, **Then** the highlighted result's
   target route is navigated.
3. **Given** an empty input, **When** the modal opens, **Then**
   it shows the most-recent searches from localStorage (up to
   5).

---

### Edge Cases

- The OpenAPI spec changes after `npm run codegen` runs — the
  developer re-runs codegen; types regenerate; build catches
  any breakage at compile time.
- A user without `admin` role tries to access `/settings/general`
  → the route guard returns them to a "Permission denied" page
  with a link back to the Dashboard.
- An OIDC redirect mid-flow loses the SPA state — on return,
  the app reads the session cookie set by the backend and
  resumes the user's intended page (via a stored `returnTo`
  param).
- A user uploads an oversized cover (e.g., 50 MB) for a Game
  → the backend rejects with HTTP 413; the UI shows the
  documented error envelope's `errorMessage`.
- The WebSocket flaps every few seconds — the backoff doubles
  each time (1 s → 2 → 4 → 8 → max 30 s); the offline
  indicator only appears when the gap exceeds 10 s, to avoid
  noisy oscillation.
- The browser disables localStorage (private mode) → preferences
  fall back to in-memory state; UI continues to function but
  preferences don't persist across reloads.
- The user reduces motion via the OS-level "reduce motion"
  setting → the app honours `prefers-reduced-motion`; transitions
  shorten or disable; no parallax effects ever.
- A Game has no cover at all → the `CoverImage` component
  renders a deterministic gradient based on the title hash.
- The user accepts the install prompt then immediately
  uninstalls → the next visit re-shows the install prompt
  after the 28-day Chromium cooldown.
- The push-notification permission is denied → the UI shows a
  "Notifications blocked by browser" hint with a link to the
  browser's setting; no further attempts to prompt.

## Requirements *(mandatory)*

### Functional Requirements

**Mobile-first layout**

- **FR-001**: Every page MUST render correctly at a 360 × 640
  viewport with zero horizontal scrollbars (Constitution
  Article XV).
- **FR-002**: Every interactive control MUST have a hit target
  of at least 44 × 44 CSS pixels on touch devices.
- **FR-003**: A bottom navigation bar MUST be present on
  viewports < 768 px wide, with the documented entries
  (Library, Wanted, Activity, Settings, Search).

**PWA**

- **FR-004**: The application MUST install as a PWA in
  Chromium-based browsers (Lighthouse PWA score ≥ 90).
- **FR-005**: Cached reads MUST work offline (network-first
  for API calls, cache fallback). Mutation endpoints MUST NOT
  be cached.
- **FR-006**: Push notifications MUST be supported via the Web
  Push API; the backend's notification feature provides VAPID
  keys.
- **FR-006a**: The browser permission prompt
  (`Notification.requestPermission()`) MUST fire ONLY in
  response to an explicit operator click on the opt-in button
  in `/settings/ui` or `/settings/connect`. The prompt MUST
  NOT auto-fire on app load, on first authenticated visit, or
  on any engagement-gated heuristic. A one-time, dismissible
  Dashboard banner after first login MAY surface that the
  option exists, but the prompt itself fires only on the
  Settings button click.
- **FR-007**: The PWA's `theme-color` meta MUST follow the
  current theme (dark/light/auto).
- **FR-007a**: When the service worker detects a new bundle
  (a waiting worker exists), the UI MUST surface a
  non-blocking toast — "New version available — Reload" —
  with a Reload button. The new worker MUST call
  `skipWaiting` + `clients.claim` ONLY when the operator
  clicks Reload; the page then reloads. The application MUST
  NOT auto-reload silently and MUST NOT block the operator
  on the prompt; dismissing the toast leaves the existing
  worker active until the next natural reload.

**Routing & auth**

- **FR-008**: The application MUST use a client-side router for
  all internal navigation; full-page reloads MUST occur only
  on initial page load and on sign-out.
- **FR-009**: Protected routes MUST be guarded by an auth
  resolver that consults the `/api/v3/auth/me` endpoint; on
  401, the user is redirected to `/login` with a stored
  `returnTo` query param.
- **FR-009a**: After a successful OIDC round-trip, the browser
  SPA MUST authenticate subsequent requests via the
  `HttpOnly + SameSite=Lax + Secure (over HTTPS)` session
  cookie that the backend's OIDC callback handler sets. The
  SPA MUST NOT receive, store, or read any JWT in JavaScript
  (no localStorage / sessionStorage / in-memory token). Per
  spec 010 FR-022 (clarified), the auth chain at MVP does NOT
  include a generic `Authorization: Bearer JWT` step;
  non-browser clients (CLIs, scripts) authenticate via API
  keys (spec 010 FR-005), not via JWTs. The WebSocket auth on
  `/signalr/messages` uses the same session cookie.
- **FR-010**: An admin-only route MUST refuse to render for a
  non-admin user; the page shows "Permission denied" with a
  link back to the Dashboard.

**i18n**

- **FR-011**: Every visible string MUST come from the i18next
  bundles; hardcoded literal strings in JSX are forbidden
  (eslint rule `react/jsx-no-literals` enforces this on
  components — page-level layouts can hold a small number of
  exceptions documented in the eslint config).
- **FR-012**: The bundles MUST include French and English
  from day one; namespaces: `common`, `library`, `settings`,
  `profiles`, `indexers`, `downloaders`, `errors`,
  `validation`.
- **FR-013**: Switching languages MUST take effect without a
  page reload and persist across reloads (localStorage +
  user preferences PATCH).
- **FR-013b**: User preferences (language, theme, date/time
  format, timezone) MUST follow a "server-wins-on-read,
  last-write-wins-on-write" reconciliation policy.
  `localStorage` MUST be treated as a cache, never as the
  authority. On every app load (after the auth resolver
  returns), the SPA MUST overwrite `localStorage` with the
  fresh `user.preferences` value from `/api/v3/auth/me`.
  Every preference change MUST PATCH `user.preferences`
  immediately; the optimistic UI applies the change locally
  and rolls back on PATCH failure. No conflict UI, no merge
  prompt, no version vectors.
- **FR-013a**: When a translation key has no value in any
  loaded bundle, the i18next `missingKeyHandler` MUST render
  the key with an `[i18n]` prefix in production builds (e.g.,
  `[i18n] library.empty_state_title`) and the bare key in
  development builds. The handler MUST NOT throw and MUST NOT
  render an empty string.
- **FR-014**: Dates MUST render in locale-aware form (e.g.,
  "29 avril 2026" in French, "April 29, 2026" in English) via
  `date-fns` locale modules.

**Theme**

- **FR-015**: The application MUST default to dark mode; light
  and auto modes MUST be available; the choice MUST persist
  in localStorage AND on the user's `preferences` JSON.
- **FR-016**: Theme transitions MUST NOT flash on initial
  page load (the theme is applied before the first render
  via a small inline script).

**Realtime**

- **FR-017**: A WebSocket MUST be opened to
  `/signalr/messages` on app load (auth via cookie session or
  `?apikey=`).
- **FR-018**: Reconnection MUST use exponential backoff
  (1 s → 2 s → 4 s → 8 s → max 30 s).
- **FR-019**: WebSocket events MUST trigger TanStack Query
  invalidations: `gameAdded` invalidates Game queries,
  `queueUpdated` invalidates Queue, `releaseImported`
  invalidates Releases + History, etc. The WebSocket is a
  **notification channel**, not the source of truth — every
  event triggers a re-fetch via REST.
- **FR-020**: A "WebSocket offline" indicator MUST appear in
  the header after ≥ 10 s of disconnection.

**OpenAPI codegen**

- **FR-021**: TypeScript types AND TanStack Query hooks MUST
  be generated from `/api/v3/openapi.json` via an
  `npm run codegen` script. The generated code is committed
  to the repository for stability.
- **FR-022**: A breaking change in the OpenAPI spec MUST cause
  a TypeScript compile-time error rather than a runtime
  failure.

**Pages**

- **FR-023**: The application MUST expose at least the
  documented eleven pages: Dashboard, Library, Add New, Game
  Detail, Wanted, Activity, Calendar, Settings (with the
  documented sub-pages), System (with the documented
  sub-pages), Login, Setup.
- **FR-024**: The Library page MUST support virtual scrolling
  for libraries > 1 000 items, maintaining ≥ 60 fps on
  10 000-item fixtures.
- **FR-025**: The Game Detail page MUST expose six tabbed
  views: Overview (with edit-in-place + per-field locks),
  Releases (with multi-disc accordion), History, Files,
  Manual Search, Notes.
- **FR-025a**: The Overview tab's cover-swap interaction MUST
  call backend-proxied endpoints only:
  `GET /api/v3/cover/{game_id}/sources` to list candidate
  covers (backend aggregates SteamGridDB and any other
  configured providers) and `POST /api/v3/cover/{game_id}`
  with the selected source id to commit the swap. The SPA
  MUST NOT call `steamgriddb.com` directly; no SteamGridDB
  API key is exposed to the browser; no third-party origin
  is added to the CSP for cover swap. Cover image bytes
  themselves continue to be served from
  `/api/v3/cover/{game_id}` (the version query param busts
  the cache after a swap).
- **FR-026**: The Setup wizard MUST guide a fresh operator
  through the documented five steps and redirect any
  unauthenticated visit to `/setup` when the user table is
  empty.
- **FR-026a**: When the user table is **not** empty (an admin
  already exists), any visit to `/setup` — authenticated or
  not — MUST silently redirect to `/` (Dashboard). The wizard
  route returns no content of its own once setup is complete;
  this matches Sonarr / Radarr behaviour and avoids a dead-end
  UI surface.

**ROM-specific components**

- **FR-027**: The application MUST ship the documented
  ROM-specific components as first-class reusable pieces:
  `RegionBadge`, `ConventionBadge`, `DumpStatusIcon`,
  `MultiDiscAccordion`, `HashBadge`, `ScoreBadge`,
  `LanguagePills`, `DatVerifiedBadge`, `PlatformIcon`,
  `CoverImage`. Each component is exported from
  `components/rom/` and consumed by at least two pages.

**Mobile UX**

- **FR-028**: Long-press MUST trigger bulk-select mode on
  Library and Wanted (mobile). Desktop uses checkboxes.
- **FR-029**: Swipe-left on a Queue item MUST open a remove
  action; swipe-right MUST open a retry action.
- **FR-030**: Pull-to-refresh MUST work on every list view
  on mobile.
- **FR-031**: Action sheets (full-width modals from the
  bottom) MUST replace dropdowns on mobile.
- **FR-032**: A floating action button (FAB) MUST be present
  on the primary mutation page (Add on Library, Trigger
  Search on Wanted).

**Global search**

- **FR-033**: `⌘+K` / `Ctrl+K` MUST open a global-search
  modal that searches Games, Releases, and Settings pages.
  Keyboard navigation (arrow keys + Enter) MUST work.

**Accessibility**

- **FR-034**: Every interactive element MUST be reachable via
  keyboard.
- **FR-035**: Icon-only buttons MUST carry `aria-label`.
- **FR-036**: Color contrast MUST meet WCAG AA on every
  documented page.
- **FR-037**: The Dashboard, Library, Game Detail, and
  Settings pages MUST pass `axe-core` CI checks with zero
  errors.
- **FR-038**: The application MUST honour
  `prefers-reduced-motion`.
- **FR-038a**: The application MUST mount a React error
  boundary scoped under the router outlet (one per top-level
  page). When a descendant throws during render, the
  boundary MUST render a localized fallback containing: an
  i18n-keyed error title, a Retry action that resets the
  boundary and remounts the page, a "Back to Dashboard" link,
  and a copyable error id (a short hash of the error
  message + chunk name suitable for inclusion in a bug
  report). The application shell — header, bottom navigation,
  theme, language — MUST remain interactive while the
  fallback is shown. The application MUST NOT mount a single
  global boundary that replaces the whole shell on any error.
- **FR-038b**: Unhandled errors that escape the per-page
  boundary (window `error`, `unhandledrejection`, async work
  after navigation, mutation `onError` re-throws) MUST be
  logged to the browser `console.error` and surface a
  generic localized toast ("Something went wrong"). The
  application MUST NOT POST a crash report to any remote
  endpoint and MUST NOT bundle a third-party error-reporting
  SDK (e.g., Sentry, Bugsnag). A first-party
  `/api/v3/log/frontend` ingest endpoint is explicitly
  deferred to v1+; for MVP the operator's recourse is the
  console output plus the per-page boundary's error id.

**Type safety & quality**

- **FR-039**: `tsc --strict` MUST pass with zero errors on the
  whole frontend.
- **FR-040**: The initial-route bundle MUST be ≤ 500 KB gzip.
- **FR-041**: Test coverage on the critical user paths
  (search, grab, import, profiles) MUST be ≥ 60%.

### Key Entities

- **Page**: One of 11+ top-level routes mapped to a folder
  under `src/pages/`; owns its layout, its data hooks, its
  i18n namespace.
- **ROM Component**: One of 10 first-class reusable pieces in
  `src/components/rom/` consumed across pages.
- **TanStack Query Hook**: A generated hook (one per
  endpoint) under `src/lib/api/`; the only path through which
  a page reads server state.
- **Zustand Store**: A small module of client-only state (UI
  preferences, modal-open state, transient state).
- **WebSocket Subscription**: A typed handler that maps a
  `messageType` to a TanStack Query invalidation + an
  optional toast.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every documented page renders correctly at
  360 × 640 with zero horizontal scrollbars in 100% of
  Playwright snapshot tests across the documented page set.
- **SC-002**: The Library page maintains ≥ 60 fps while
  scrolling a 10 000-Game fixture in Chrome DevTools'
  performance recording.
- **SC-003**: A Lighthouse audit produces an installable PWA
  with score ≥ 90 across Performance, Accessibility, Best
  Practices, and PWA categories on a production build.
- **SC-004**: Switching FR ↔ EN updates 100% of visible
  strings without a page reload across a hand-picked corpus
  of at least 20 strings spanning 5 pages.
- **SC-005**: The dark/light/auto theme toggle persists in
  localStorage AND on the user's `preferences` JSON; first-
  paint after reload renders in the persisted theme without a
  flash.
- **SC-006**: Test coverage on the critical user paths
  (search, grab, import, profiles) is at least 60%.
- **SC-007**: `axe-core` reports zero errors on the
  Dashboard, Library, Game Detail, and Settings pages.
- **SC-008**: `tsc --strict` produces zero errors.
- **SC-009**: The initial-route gzip bundle is ≤ 500 KB.
- **SC-010**: Five Playwright E2E tests cover the critical
  paths end-to-end: search → grab → import; profile edit;
  library scan; first-boot setup wizard; bulk Missing search.

## Assumptions

These resolve the OPEN CLARIFICATIONS supplied with the input,
applying the operator's proposals.

- **Library virtual scrolling**: yes, via TanStack Virtual.
  Performance budget = ≥ 60 fps on 10 000-item fixture
  (SC-002).
- **Cover image storage / serving**: backend serves
  `/api/v3/cover/{game_id}` with `Cache-Control: immutable,
  max-age=86400` plus a version query param so cover changes
  bust the cache.
- **Push notifications for installed PWA**: backend stores
  push subscriptions per user (a small table introduced by
  the Notifications spec as a follow-up); the Notifications
  spec adds a Web Push notification target alongside Apprise.
  This frontend only handles the
  `Notification.requestPermission()` flow + the
  `pushsubscriptionchange` lifecycle.
- **WebSocket reconnection — pending mutation queue**: NO at
  MVP. Show offline indicator after 10 s; disable mutation UI;
  v1+ may add a queue.
- **UI without WebSocket (polling fallback)**: YES. TanStack
  Query handles polling on a sensible interval per resource
  (Queue every 5 s, Activity every 10 s, Library on focus).
  WebSocket is enhancement, not requirement.

Other assumptions:

- The brand color is **Game Boy LCD green `#9BBC0F`** (retro-iconic,
  distinct from every existing *arr palette). Wired into Tailwind
  via the `--primary` CSS variable so a future swap remains a
  one-line change. Used for the active-tab indicator, primary
  buttons, FAB, focus rings, and the PWA `theme-color` meta.
- The `i18next` namespaces ship with empty French translations
  for any string that isn't translated yet; runtime fallback
  is to English. **When a key has no value in any bundle**, the UI
  renders the raw key with an `[i18n]` prefix in production
  (e.g., `[i18n] library.empty_state_title`) and the bare key
  in development. This makes gaps loud in QA without crashing.
  The translation completion percentage is tracked in CI but not
  gating.
- The setup wizard's "skip indexer" path leaves the operator
  on the Dashboard with a banner pointing at
  `/settings/indexers`.
- Generated TanStack Query hooks include both query and
  mutation variants; the `npm run codegen` script regenerates
  them; the generated files live under `src/types/api/` and
  `src/lib/api/generated/` and are committed to the repo.

### Out of Scope

- Native mobile apps — PWA suffices (firm out per the
  constitution).
- Plugin system / extensions for the frontend (firm out).
- Theme builder beyond dark/light/auto (firm out).
- Third-party authentication providers beyond OIDC (Auth
  spec).
- Offline-first writes — only reads cached, writes require a
  connection (deferred to v1+).
- A standalone admin interface separate from `/settings`
  (firm out).
- Server-side rendering — the app is a SPA. SSR would only
  matter for SEO and Romarr is private-network-first.
