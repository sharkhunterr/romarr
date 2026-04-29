<!--
SYNC IMPACT REPORT
==================
Version change: (uninitialized template) → 1.0.0
Bump rationale: Initial ratification of the Romarr constitution. All articles are
new; there is no prior baseline to compare against, so the change is recorded as
a MAJOR initial release per the governance versioning policy.

Modified principles:
  - All template placeholders replaced with concrete articles I–XVIII.

Added sections:
  - Article I — Project Identity & Distribution
  - Article II — Scope (In) and Anti-Scope (Out)
  - Article III — Technology Stack (Locked)
  - Article IV — API Conventions & Compatibility Surface
  - Article V — Profile-Driven Decisions
  - Article VI — Identification Cascade
  - Article VII — Indexer Strategy
  - Article VIII — Download Client Strategy
  - Article IX — Metadata Aggregation
  - Article X — Platform Extensibility (Data, Not Code)
  - Article XI — Naming Discipline
  - Article XII — Library Discipline
  - Article XIII — Domain Model
  - Article XIV — Notifications
  - Article XV — User Interface Discipline
  - Article XVI — Quality Gates
  - Article XVII — Idempotency & Safety
  - Article XVIII — Governance

Removed sections:
  - None (template placeholders only).

Templates requiring updates:
  - ✅ .specify/templates/plan-template.md — reviewed; the generic
    "Constitution Check" gate naturally references whichever articles are in
    force. No edits required for v1.0.0; planners must apply Articles III, IV,
    V, VI, XI, XII, XIII, XVI, XVII as gates.
  - ✅ .specify/templates/spec-template.md — reviewed; structure (User
    Scenarios, Requirements, Success Criteria, Assumptions) is consistent with
    Articles V, XV, XVI, XVII. No edits required.
  - ✅ .specify/templates/tasks-template.md — reviewed; Setup / Foundational /
    User Story phasing is compatible with Article XVI (Quality Gates) and
    Article XII (Library Discipline). No edits required.
  - ⚠ README.md — not yet present at repository root. When created, it MUST
    reference this constitution and surface the Article I project identity
    block.
  - ⚠ docs/quickstart.md — not yet present. When created, it MUST inherit the
    PUID/PGID, default port 8585, and Docker distribution constraints from
    Article I.

Follow-up TODOs:
  - None deferred. All placeholders in this file are resolved.
-->

# Romarr Constitution

Romarr is a self-hosted ROM acquisition manager for the *arr ecosystem.
Bookshelf-equivalent UX and concepts, RomM-equivalent metadata model,
Radarr-compatible REST API surface. This document is the single source of
authority. When any specification, plan, task list, or implementation conflicts
with the constitution, the constitution wins.

## Core Principles

### I. Project Identity & Distribution

- The project name is **Romarr**. The name MUST be used verbatim in code,
  documentation, package metadata, container labels, and user-facing copy.
- License: **GPL-3.0-or-later**. Every source file SHOULD carry an SPDX header;
  every published artifact MUST ship the LICENSE text.
- Default HTTP port: **8585**. The port MUST be overridable via the
  `ROMARR_PORT` environment variable. No other override mechanism is allowed.
- Distribution: a **single multi-arch Docker image** (`linux/amd64`,
  `linux/arm64`) with the frontend bundled into the same image. No separate
  frontend image, no host-side build step required for end users.
- The container MUST run unprivileged and respect mappable `PUID`/`PGID`
  following LinuxServer.io conventions. Hardcoded UIDs/GIDs are forbidden.

**Rationale:** A predictable identity (name, port, license, container shape)
is what lets the *arr ecosystem treat Romarr as a peer.

### II. Scope (In) and Anti-Scope (Out)

In scope (any of these belong inside Romarr):
- ROM acquisition: search, grab, import, rename, hardlink/move into a library.
- ROM identification via DAT files (No-Intro, Redump, TOSEC), filename parsing,
  hash matching, and header reading.
- Multi-source metadata aggregation.
- Profile-driven decisions across Quality, Region, Dump, Language, Naming, and
  Custom Format axes.
- Multi-library management.
- Downstream integrations: RomM, ES-DE, Batocera, Recalbox, LaunchBox.
- A mobile-first responsive PWA web UI.

Firmly out of scope (these MUST NOT be added without a constitutional amendment):
- BIOS / firmware management.
- Emulation or playback (RomM owns this).
- Save data sync.
- PC game backlog / Steam / GOG (Questarr's domain).
- ROM hosting or distribution.

**Rationale:** Tight scope is what differentiates an *arr from a swiss-army-knife
manager. Each "out" line below is an experience-driven boundary.

### III. Technology Stack (Locked)

The following stack is locked. Deviations require a constitutional amendment.

Backend:
- Python 3.12+, FastAPI (async), SQLAlchemy 2.0 (async), Pydantic v2, Alembic.
- Database: SQLite by default; PostgreSQL 15+ optional, sharing the same
  SQLAlchemy models. Two model trees are forbidden.
- Cache / queue: Redis 7+.
- Scheduler: APScheduler.
- HTTP client: `httpx` (async). No `requests`, no `urllib3` direct.

Frontend:
- React 18, TypeScript in `strict` mode, Vite, Tailwind 3.x, shadcn/ui.
- State: Zustand for client state, TanStack Query v5 for server state.
- Realtime: FastAPI WebSockets.

Cross-cutting:
- Auth: FastAPI-Users + Authlib OIDC, plus per-user API keys.
- i18n: i18next. French and English MUST ship from day one.
- Notifications: **Apprise only**. No ad-hoc per-channel integrations.
- Tests: pytest + pytest-asyncio + pytest-cov (backend); Vitest + Testing
  Library (frontend).
- Lint: `ruff` plus `mypy --strict` on `domain/` and `identification/`;
  ESLint + Prettier on the frontend.

**Rationale:** A locked stack is the cheapest way to keep contributors aligned
and to make CI deterministic.

### IV. API Conventions & Compatibility Surface

- The REST API MUST be served under `/api/v3/*` and MUST follow
  Sonarr v3 / Radarr v3 conventions wherever resources overlap, so that
  existing tooling (Notifiarr, Recyclarr, Janitorr, Homepage, Homarr,
  Organizr, Overseerr-style request managers) works transparently.
- WebSocket compatibility MUST be exposed at `/signalr/messages` mirroring
  Sonarr's signal protocol.
- ROM-specific endpoints (regions, dumps, DATs, naming previews, etc.) MUST
  live under `/api/v3/rom/*` to clearly separate them from the
  Sonarr/Radarr-compatibility surface.
- OpenAPI 3.1 MUST be auto-generated and served at `/api/v3/openapi.json`,
  with both Swagger UI and ReDoc reachable from the running instance.

**Rationale:** The compatibility surface is a contract with the *arr
ecosystem. Mixing ROM-specific endpoints into compatibility paths would break
that contract.

### V. Profile-Driven Decisions

- Every grab, upgrade, and import decision MUST flow from declarative profiles.
  No business logic for these decisions is permitted to be hardcoded.
- There are exactly **six profile types**: Quality, Region, Dump, Language,
  Naming, Custom Format. Adding a seventh requires a constitutional amendment.
- Each library carries exactly one profile of each type. Profiles MUST be
  reusable across libraries.
- Profile changes MUST NOT trigger destructive actions automatically.
  Re-evaluation may queue manual-review work, but file deletes/moves require
  explicit user action.

**Rationale:** Profile-driven decisions are how the *arr family stays
configurable without forking. Hardcoding a rule "just for now" always becomes
forever.

### VI. Identification Cascade

- Source priority is fixed: **hash match (highest authority) > Torznab
  extended attributes > header read > filename parse**.
- Hash matching uses three backends queried **in parallel**:
  1. local DAT cache (No-Intro, Redump, TOSEC), refreshed weekly;
  2. Hasheous API;
  3. PlayMatch API.
  Romarr MUST consume these as remote services. Self-hosting any of these
  microservices inside Romarr is forbidden.
- The filename parser MUST support four conventions: No-Intro (default),
  GoodTools, TOSEC, Scene release naming.
- Header readers MUST cover at minimum iNES, Mega Drive, and ISO9660 in MVP.
- DAT verification is **on by default**. Disabling DAT verification requires
  per-library explicit opt-in by the user.
- Conflicts between sources MUST be logged but MUST NOT block the pipeline;
  the higher-authority source wins, and the conflict is surfaced to the user.

**Rationale:** A cascade with explicit authority avoids the "one source said
X, another said Y, we silently picked one" trap that plagues identification
pipelines.

### VII. Indexer Strategy

- **Prowlarr-first.** Native Newznab / Torznab is supported for direct
  configuration, but Prowlarr is the recommended and documented path.
- Romarr MUST NOT implement indexer-specific protocols. Every indexer is
  reached via Newznab / Torznab. HTTP-direct sources are the responsibility
  of Prowlarr or Grabarr, not Romarr.
- Romarr MUST be able to register itself as a Prowlarr application via
  `/api/v3/applications` for bidirectional indexer sync.
- Romarr MAY consume optional extended Torznab attributes (`region`,
  `languages`, `revision`, `dump_tags`, `hash`) when emitted by Grabarr or
  compatible indexers, but MUST never require them and MUST fall back to
  filename parsing.

**Rationale:** Implementing per-indexer scrapers is how *arr projects
accumulate technical debt. Prowlarr exists; Romarr defers to it.

### VIII. Download Client Strategy

- MVP MUST support **qBittorrent** and **SABnzbd**.
- v1 MUST add Transmission, Deluge, and NZBGet.
- v2+ MAY add rTorrent.
- Each integration MUST use an official or well-maintained Python client
  library. Custom protocol implementations are forbidden.
- Romarr MUST auto-manage the following categories and tags:
  `romarr`, `romarr-{platform-slug}`, `romarr-imported`.
- Lifecycle policy (hardlink + seed / move + remove / copy + keep) MUST be
  configurable **per library**, not globally.

**Rationale:** Download client integrations are where data loss happens.
Battle-tested libraries plus per-library lifecycle keeps the blast radius
small.

### IX. Metadata Aggregation

- Romarr MUST integrate the following nine providers (modeled after RomM):
  IGDB (primary, Twitch OAuth), ScreenScraper (recommended free alternative,
  user/password), MobyGames (paid API key, optional), LaunchBox Games DB
  (community, free), SteamGridDB (covers only, manual override),
  RetroAchievements (achievements enrichment, no matching role),
  HowLongToBeat (durations enrichment), Hasheous (hash matching, IGDB+ proxy),
  PlayMatch (alternative hash matching).
- Aggregation MUST be **per-field, priority-ordered**. The user configures
  priority lists per field type in Settings.
- Re-matching against a new provider MUST NOT destroy existing field values.
  The bug pattern of RomM issue #1770 is forbidden by design.
- Each field MUST be manually lockable; locked fields MUST be skipped during
  refresh.
- Cover art MUST be fetched and stored locally. Screenshots are out of scope
  to keep storage manageable.
- Cache TTL MUST be configurable per provider, with a default of 30 days.

**Rationale:** Per-field priority and lockability are what separate a good
metadata manager from one that silently overwrites curated data.

### X. Platform Extensibility (Data, Not Code)

- Platforms MUST be **data, not code**. The console list, format list, naming
  tokens, and metadata IDs live in the database and MUST be editable via the
  UI Settings.
- **Platform Packs** are YAML files versioned by date (e.g., `2026.04.001`)
  that ship platform definitions in bulk.
- Platform Pack format MUST be generic and self-contained: it defines
  platforms, formats, header signatures, naming tokens, parsing strategies,
  and metadata-provider mappings.
- Users MUST be able to apply built-in packs (shipped with Romarr) and to
  override locally without breaking subsequent updates. Community pack
  repository integration is **deferred to v1+**.
- Schema migrations MUST NOT be required when a pack adds a platform or
  format. Schema-level extensibility MUST be built in via reference tables
  and JSONB metadata columns.
- MVP supports built-in packs and manual upload only.

**Rationale:** Adding "Atari Lynx support" must never require a code change
or a database migration. Pack format is the API.

### XI. Naming Discipline

- Naming conventions are **first-class objects**, never hardcoded constants.
- Romarr MUST support: No-Intro (default), Redump (CD-based), TOSEC, GoodTools
  (legacy), ES-DE friendly, RomM friendly, and a custom user template.
- Naming Profiles MUST use a Jinja2-like template engine with an explicit
  token vocabulary. Free-form Python expressions in templates are forbidden.
- Templates MUST be validated against golden fixtures per convention. A
  convention without fixtures cannot ship.

**Rationale:** Filename layout is the user-visible surface of every imported
ROM. Treating it as a first-class object enables ES-DE and RomM
interoperability without forks.

### XII. Library Discipline

- **Hardlinks are the default** when moving from the download client to the
  library. Move/copy is used **only** when hardlink is impossible (e.g., a
  cross-filesystem boundary).
- **Imports MUST be idempotent.** Re-importing the same file MUST produce
  no change.
- Multi-library MUST be supported from MVP. Each library has its own profiles
  and destination root.
- **Multiple Releases per Game MUST be allowed.** A user MAY keep USA + EUR +
  JPN and a hack version of the same game simultaneously. Cutoff/upgrade
  logic MUST be per-Release, not per-Game.
- Library scans MUST use `inotify` when available, with polling as the
  fallback.

**Rationale:** ROM collectors keep multiple regions and revisions. A library
model that assumes "one canonical copy per game" is wrong for this domain.

### XIII. Domain Model

The canonical model is:

```
Platform 1───* Game 1───* Release 1───0..1 Dump
```

- A Game is bound to **exactly one Platform**. Sonic 1 on Mega Drive and
  Sonic 1 on GBA are two distinct Games, even though they share a title.
- A Game MAY have any number of Releases. Each Release represents a region /
  revision / dump-status variant.
- A Release MAY have zero Dumps (wanted, not yet acquired) or one Dump
  (imported). Storing multiple historical Dumps per Release is supported but
  disabled by default.
- Multi-disc sets MUST use a `parent_release_id` self-reference: the Disc-1
  Release is the parent; discs 2+ point to it.

This model is deliberately chosen over a "global Game / multi-platform
Release" model. Any specification that proposes to share a Game across
platforms MUST first amend this article.

**Rationale:** Simpler queries, simpler UI, simpler imports, no shared-state
coordination across platforms.

### XIV. Notifications

- All outbound notifications MUST go through Apprise. Ad-hoc per-channel
  integrations are forbidden.
- Webhook payloads MUST match Sonarr/Radarr formats so Notifiarr and similar
  tooling consume Romarr events transparently.
- The notification event set MUST include at least: `OnGrab`, `OnImport`,
  `OnUpgrade`, `OnFail`, `OnHealthIssue`, `OnDatUpdate`, `OnGameAdded`.

**Rationale:** Apprise solves the long tail of notification destinations once.
Webhook compatibility lets the existing *arr notification ecosystem just work.

### XV. User Interface Discipline

- **Mobile-first.** Every view MUST function on a 360-pixel-wide viewport.
  Desktop-only layouts are forbidden.
- The UI MUST ship as an installable PWA with push notification support.
- Visual design MUST use shadcn/ui primitives + Tailwind. Dark mode is
  default; light and auto modes MUST be available.
- i18n: French and English MUST ship from day one. The architecture MUST
  support community translations without code changes.
- ROM-specific UI components MUST be first-class: region badges with country
  indicators, naming convention badges (No-Intro/Redump/TOSEC), dump status
  icons, multi-disc accordions.

**Rationale:** A retro-collector audience overwhelmingly browses on phones
near the console. Desktop-first would lose them.

### XVI. Quality Gates

Coverage:
- Backend test coverage MUST be ≥ 80% on `domain/` and `identification/`,
  and ≥ 70% overall.
- Frontend test coverage MUST be ≥ 60% on critical user paths
  (search, grab, import, profiles).

Performance:
- Hash 1 GB ROM in **< 10 s** on a local SSD.
- Library scan of **10,000 ROMs in < 5 min**.
- Search 1 game across 5 indexers in **< 8 s p95**.
- REST API response **< 200 ms p95**, excluding search/scan operations.

Static analysis:
- `ruff` (Python), `eslint` + `prettier` (TypeScript): **zero warnings on
  `master`**.
- `mypy --strict` on `domain/` and `identification/`. TypeScript `strict`
  mode everywhere on the frontend.

Any spec or PR that lowers a coverage floor or relaxes a performance target
MUST be promoted to a constitutional amendment.

**Rationale:** Quality gates only work when they are absolute and visible.
Squishy targets get re-negotiated under deadline pressure.

### XVII. Idempotency & Safety

- All API write operations MUST be idempotent where conceptually possible
  (`PUT`, `DELETE`).
- `POST` endpoints MUST accept an optional `Idempotency-Key` header.
- Destructive actions MUST be confirmed twice in the UI: first a modal with a
  resource summary, then a Delete button inside the modal that has a
  one-second activation delay.
- Imported files MUST NOT be deleted automatically without **explicit
  per-library opt-in**.

**Rationale:** Romarr touches user-curated files. The cost of an accidental
delete is unrecoverable; the cost of two extra clicks is negligible.

## Governance

### XVIII. Governance

- This constitution is the **single source of authority**. When a
  specification, plan, task list, or implementation conflicts with the
  constitution, the constitution wins.
- **Constitutional amendments** require:
  1. A documented reason (problem statement and motivation).
  2. A review of all existing specifications under `specs/` for consistency,
     with each affected spec either updated or explicitly grandfathered.
  3. A version bump per the policy below, and an entry in the amendment
     history at the bottom of this file.
- Specifications that violate the constitution MUST be blocked from
  implementation. The `/speckit-plan` Constitution Check gate is the
  designated enforcement point.
- New principles introduced through specifications MUST be promoted to
  constitutional articles before being relied on across the codebase. Ad-hoc
  principles living only in a spec are not binding.
- **Versioning policy** (semantic):
  - **MAJOR** — a backward-incompatible governance or principle removal /
    redefinition.
  - **MINOR** — a new principle or section added, or material expansion of
    existing guidance.
  - **PATCH** — clarifications, wording fixes, non-semantic refinements.
- Compliance review: every PR description MUST cite the article numbers it
  exercises or modifies. CI MAY enforce this via a PR template check.

**Version**: 1.0.0 | **Ratified**: 2026-04-28 | **Last Amended**: 2026-04-28

## Amendment History

- **1.0.0 — 2026-04-28** — Initial ratification. Establishes Articles I–XVIII
  defining project identity, scope, technology stack, API conventions, the
  profile-driven decision discipline, the identification cascade, indexer and
  download-client strategy, metadata aggregation rules, platform
  extensibility (data-not-code), naming and library discipline, the canonical
  domain model, notifications, UI discipline, quality gates, idempotency &
  safety, and governance.
