# Implementation Plan: Authentication & Multi-User

**Branch**: `010-auth-multiuser` | **Date**: 2026-04-29 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification at `specs/010-auth-multiuser/spec.md`
**Depends on**: `002-metadata-aggregation` (Fernet encryption helper).
**Replaces**: every prior spec's development-only no-op admin dependency.

## Summary

The auth subsystem ships:

1. **A `user` table** + **an `api_key` table** + an FK migration that
   converts every `*_by` text column in earlier specs (e.g.,
   `import_history.imported_by`) to FK INTEGER references to
   `user.id`, preserving the `'system'` sentinel.
2. **A chained authentication dependency** that resolves the caller via
   API-key → cookie → JWT → trusted-proxy header in fixed order, with a
   uniform 401 response shape that never discloses which method was
   attempted.
3. **Three RBAC roles** (admin, user, readonly) with implicit
   inheritance (admin ⊃ user ⊃ readonly) and a `@require_role`
   dependency.
4. **Four auth methods**:
   - Forms login + server-side session (Redis preferred, DB fallback).
   - OIDC via Authlib with Authentik-style group-to-role mapping.
   - Trusted-proxy headers (Authentik / Traefik / Caddy front-door).
   - API keys (BLAKE2b-hashed for O(1) lookup, prefix-for-display,
     revocable, optional expiry).
5. **A one-shot initial admin bootstrap** that surfaces a setup token
   in the logs on first boot, valid only while the user table is empty
   AND for 24 hours.

The library choice is **FastAPI-Users** for the user model + bcrypt
password hashing + cookie sessions, plus **Authlib** for the OIDC
client. Both are well-maintained Python packages; no custom auth
crypto.

## Technical Context

**Language/Version**: Python 3.12+
**Primary Dependencies**: SQLAlchemy 2.0 (async), Pydantic v2,
Alembic, `fastapi-users[sqlalchemy,oauth]>=13`,
`authlib>=1.3` (OIDC client), `bcrypt>=4.1` (already a dep from spec
004's app-token hashing), `redis>=5` (preferred session backend;
optional — falls back to DB), `cryptography` (already a dep from
spec 002), structlog. **No new HTTP client.**
**Storage**: SQLite default / PostgreSQL 15+ optional. Two new
tables (`user`, `api_key`) plus an FK conversion of four existing
`*_by` text columns. Server-side session storage either in Redis (if
configured) or in a `session` table (fallback).
**Testing**: pytest, pytest-asyncio, pytest-cov, respx (OIDC mocks),
freezegun (token expiry windows), TestClient (FastAPI), `bcrypt`
fixtures with reduced cost factor for fast tests, an Authlib mock
server fixture for the OIDC round-trip.
**Target Platform**: Linux server in the Romarr Docker image.
**Project Type**: Backend Python module added under `src/romarr/auth/`.
**Performance Goals**:
- Forms-auth login: < 200 ms p95 excluding bcrypt time (cost 12 is
  ~150 ms by design — total < 350 ms p95).
- API-key validation: < 5 ms p95 (BLAKE2b hash + indexed DB lookup).
- OIDC round-trip: < 1 s p95 against a respx-mocked provider.
- Session validation: < 5 ms p95 with Redis, < 20 ms with DB fallback.
**Constraints**:
- 401 responses MUST NOT leak which method was attempted (FR-023).
- API key plaintext exists only in the creation response and the
  hash table (FR-005).
- Setup token consumed on first success (FR-019, FR-021).
- Constant-time comparisons for password (bcrypt does this) and
  API key (BLAKE2b + `secrets.compare_digest`).
**Scale/Scope**:
- Users per instance: typically 1-3 (homelab); up to 50 plausible
  for a small group.
- API keys per user: typically 1-5; up to a few dozen plausible
  for a power user.
- Session count: bounded by active browser tabs + tokens; tens to
  low hundreds.

## Constitution Check

*Gate: must pass before Phase 0 research and again after Phase 1 design.*

| Article | Gate | Status |
|---------|------|--------|
| III — Technology Stack (Locked) | FastAPI-Users + Authlib (well-maintained Python libs); bcrypt; BLAKE2b; Redis; no custom protocol code. | ✅ Conformant. |
| XVI — Quality Gates | ≥ 75% coverage on `auth/` (SC-010); zero ruff warnings; perf budgets above. | ✅ Conformant. |
| XVII — Idempotency & Safety | Setup token one-shot (FR-019–FR-021); API key revocation immediate (FR-007); 401 responses don't leak method (FR-023); password + API key hashed at rest. | ✅ Conformant. |

The constitution does not have a dedicated auth article; the relevant
gates are Article III (locked stack), Article XVI (quality), and
Article XVII (safety). All three are met.

**Result**: GREEN. No constitutional violations; **Complexity Tracking**
stays empty.

## Project Structure

### Documentation (this feature)

```text
specs/010-auth-multiuser/
├── plan.md              # this file
├── spec.md              # user-value specification
├── data-model.md        # user + api_key tables + session fallback + *_by FK migration
├── tasks.md             # 13-phase task list
└── checklists/
    └── requirements.md  # spec-quality checklist
```

### Source Code (additions to the existing repo)

```text
src/romarr/
├── auth/                                # NEW — top-level module
│   ├── __init__.py                       # public re-exports: get_current_user, require_role, AuthChain
│   ├── types.py                          # Role enum, AuthResult, AuthContext
│   ├── errors.py                         # AuthError, UnauthenticatedError, PermissionDenied, ApiKeyExpired, etc.
│   ├── settings.py                       # ROMARR_OIDC_*, ROMARR_TRUST_PROXY_AUTH, ROMARR_BCRYPT_COST, etc.
│   ├── hashing.py                        # bcrypt wrappers + BLAKE2b helpers (constant-time compare)
│   ├── tokens.py                         # generate_api_key, generate_setup_token, key_prefix helpers
│   ├── session/
│   │   ├── __init__.py                   # SessionStore ABC
│   │   ├── redis_backend.py              # Redis session store
│   │   └── db_backend.py                 # DB fallback session store
│   ├── methods/
│   │   ├── __init__.py
│   │   ├── api_key.py                    # X-Api-Key + apikey query → User
│   │   ├── cookie.py                     # session cookie → User
│   │   ├── jwt.py                        # Authorization: Bearer JWT → User (used after OIDC)
│   │   ├── proxy.py                      # trusted-proxy header → User
│   │   └── chain.py                      # AuthChain: tries each method in order, returns first success
│   ├── rbac.py                           # require_role(...) FastAPI dependency
│   ├── oidc/
│   │   ├── __init__.py
│   │   ├── client.py                     # Authlib client setup, discovery
│   │   ├── flow.py                       # /auth/oidc/start + /auth/oidc/callback handlers
│   │   └── group_mapping.py              # PURE map_groups_to_role(claims)
│   ├── setup.py                          # initial admin bootstrap state machine
│   ├── locks.py                          # serialise concurrent setup attempts (1 attempt at a time)
│   ├── models.py                         # User + ApiKey + (optional) Session SQLAlchemy 2.0 models
│   ├── schemas.py                        # Pydantic *Read/*Create/*Update + ApiKeyCreateResponse, OidcStartResponse, etc.
│   └── api/                              # FastAPI router stubs
│       ├── __init__.py
│       ├── auth.py                       # /api/v3/auth/login, /logout, /me, /me/preferences
│       ├── setup.py                      # /api/v3/auth/setup
│       ├── api_keys.py                   # /api/v3/auth/api-key*
│       ├── oidc.py                       # /api/v3/auth/oidc/start, /auth/oidc/callback
│       └── users.py                      # /api/v3/user* (admin-only)
└── db/
    └── alembic/
        └── versions/
            └── 0010_auth.py              # NEW migration: tables + FK conversions of *_by columns

tests/
├── auth/
│   ├── conftest.py                       # FastAPI TestClient, mocked OIDC provider, in-memory Redis fake
│   ├── test_models.py
│   ├── test_migration_0010.py           # *_by column FK conversion preserves 'system' sentinels
│   ├── test_hashing.py                   # bcrypt cost 12 + BLAKE2b verification
│   ├── test_tokens.py                   # API key generation + format
│   ├── test_setup.py                    # one-shot bootstrap state machine
│   ├── session/
│   │   ├── test_redis_backend.py
│   │   └── test_db_backend.py
│   ├── methods/
│   │   ├── test_api_key.py
│   │   ├── test_cookie.py
│   │   ├── test_jwt.py
│   │   ├── test_proxy.py
│   │   └── test_chain.py                # FR-022 ordering + FR-023 generic 401
│   ├── test_rbac.py                     # admin ⊃ user ⊃ readonly
│   ├── oidc/
│   │   ├── test_client.py
│   │   ├── test_flow.py                 # full round-trip with mocked provider
│   │   └── test_group_mapping.py
│   ├── api/
│   │   ├── test_auth_endpoints.py
│   │   ├── test_setup_endpoint.py
│   │   ├── test_api_key_endpoints.py
│   │   ├── test_oidc_endpoints.py
│   │   └── test_user_endpoints.py
│   └── test_replace_dev_only_dependency.py  # confirms no `dev_only_admin` import remains anywhere in the codebase
└── fixtures/
    ├── auth/
    │   ├── oidc_authentik_discovery.json
    │   ├── oidc_id_token_admin_group.txt
    │   ├── oidc_id_token_user_group.txt
    │   └── proxy_headers_corpus.jsonl
```

**Structure Decision**: keep each authentication method as a separate
module under `auth/methods/`. The `chain.py` orchestrator is the only
caller of all five — testing the chain in isolation guarantees that
failed methods cascade correctly to the next without leaking error
shape (FR-023).

The session store is an ABC with two implementations: Redis (preferred)
and DB (fallback). The settings module decides which to instantiate
based on `ROMARR_REDIS_URL`'s reachability at startup.

OIDC group mapping is a **pure function** in `oidc/group_mapping.py`
so it's trivially testable with hypothesis property tests against
randomized claim shapes.

## Phase 0 — Research

Three small research items resolved before code; results captured in
`research.md` if confirmation is needed at code time.

1. **FastAPI-Users vs. building from scratch** — FastAPI-Users 13+
   provides the user model, bcrypt hashing, cookie/JWT auth backends,
   OAuth/OIDC integration, and a router factory. We adopt it
   wholesale; the only thing we add on top is the API-key method (not
   shipped by FastAPI-Users) and the trusted-proxy method.
2. **`*_by` FK conversion strategy** — existing tables carry
   `imported_by TEXT`, `applied_by TEXT`, `added_by TEXT` columns
   defaulting to `'system'`. The migration `0010_auth.py`:
   - Creates a sentinel system user with `id=1, username='system',
     is_active=false, is_superuser=true` so that `'system'` strings
     can be migrated to `1`.
   - Adds new INTEGER columns (`imported_by_id`, `applied_by_id`,
     `added_by_id`).
   - Backfills via `UPDATE table SET imported_by_id = 1 WHERE
     imported_by = 'system'`.
   - Drops the old TEXT columns and renames the new ones to the
     original name.
   - PostgreSQL handles this in `ALTER TABLE`; SQLite uses Alembic's
     `batch_alter_table` for schema reconstruction.
3. **Constant-time comparisons** — bcrypt's verify is constant-time
   by construction. For API keys we use `secrets.compare_digest` on
   the BLAKE2b digest. The 401 response shape MUST match the
   "method-not-disclosed" requirement (FR-023): a single Pydantic
   model with `{detail: "unauthenticated"}`, no further fields, no
   stack traces in production.

No further research items.

## Phase 1 — Design Outputs

- `data-model.md` — DDL for `user`, `api_key`, optional `session`
  fallback table; the `*_by` FK conversion strategy; the value types
  `Role`, `AuthResult`, `AuthContext`.
- No `contracts/` — endpoint stubs only; full payload schemas come
  from FastAPI-Users + the Pydantic models.
- No `quickstart.md` — operator quickstart is the README's "First
  Boot" section; this spec ships only the API.

### Re-check: Constitution after design

Same table as above; nothing in the design pulls a constraint.
**Result**: GREEN.

## Complexity Tracking

> *Empty.* No constitutional violations. No deviations to justify.

## Clarification Deltas (Session 2026-04-29)

The 5 clarifications recorded in `spec.md` add the following architectural
constraints to this plan:

- **Sliding 30-day session TTL** (FR-012a) — `session` table gains
  `last_used_at` and `expires_at = last_used_at + 30 days` columns. Every
  authenticated request that resolves the session updates `last_used_at`
  (best-effort, non-blocking). Idle sessions self-expire. The cookie's
  `Max-Age` tracks `expires_at − now`. Logout immediately revokes.
- **Coarse 3-tier API-key scopes** (FR-009a) — `api_key.scopes` is a
  JSON array whose values are a subset of `["read", "write", "admin"]`.
  The route guard maps `@require_role` annotations to required scopes
  (`readonly` → `read`, `user` → `write`, `admin` → `admin`); higher
  scopes imply lower. NO per-resource fine-grained scopes at MVP.
- **No JWT in the auth chain at MVP** (FR-022 rewritten) — chain is
  API-key (header or query) → session cookie → trusted-proxy header.
  Romarr does NOT mint its own JWTs. The OIDC `id_token` is consumed
  EXCLUSIVELY in the SSO callback flow (FR-014) to establish a session;
  it MUST NOT be accepted as an inbound bearer token. Spec 014 (frontend)
  and spec 013 (REST API) have been brought into alignment.
- **Login endpoint rate limit** (FR-010a) — 10 attempts/minute/source-IP
  on `POST /api/v3/auth/login`. The same cap also applies to
  `POST /api/v3/auth/setup` and `GET /auth/oidc/callback`. HTTP 429 with
  `Retry-After`; bcrypt comparison MUST NOT run when the limit is
  exceeded (no oracle of hash work). Per-user lockout stays out of scope
  (DoS surface).
- **Single `role` text column; drop `is_superuser`** (FR-001/FR-002/FR-003
  rewritten) — `user` schema MUST NOT carry an `is_superuser` column.
  Only `role TEXT NOT NULL DEFAULT 'user' CHECK (role IN ('admin','user','readonly'))`.
  `User.is_superuser` is a Python read-only property `self.role == 'admin'`.

### Migration delta

`0010_auth.py`:
- `user.role TEXT NOT NULL DEFAULT 'user'` (single column; no `is_superuser`)
- `session.last_used_at TIMESTAMP NOT NULL`,
  `session.expires_at TIMESTAMP NOT NULL` (or DB default
  `last_used_at + interval '30 days'`)
- `api_key.scopes JSON NOT NULL DEFAULT '["read"]'` constrained to
  subsets of `{"read", "write", "admin"}` at the validator layer
- The `*_by` text columns on prior specs (`import_history.imported_by`,
  `platform_pack.applied_by`, `application.applied_by`,
  `blocklist.added_by`) become FK INTEGER references to `user.id` per
  the existing migration plan; the `'system'` sentinel is preserved as
  a row in `user` with `id = 0` so existing rows backfill cleanly.
