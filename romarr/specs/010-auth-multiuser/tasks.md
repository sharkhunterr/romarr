---

description: "Granular task list for auth & multi-user — 4 methods, RBAC, bootstrap, FK conversion"
---

# Tasks: Authentication & Multi-User

**Input**: Design documents from `specs/010-auth-multiuser/`
**Prerequisites**: `002-metadata-aggregation` shipped (Fernet helper). Earlier
specs' `*_by` TEXT columns will be FK-converted by this migration.
**Tests**: MANDATORY (Constitution Article XVI; SC-010: ≥ 75% on auth/)

**Organization**: 13 phases. Scaffolding → persistence → setup bootstrap →
session → forms → API keys → OIDC → trusted proxy → chained dependency + RBAC
→ admin user CRUD → self-service → API wiring → hardening.

## Format: `[ID] [P?] [Phase] Description`

- `[P]` = parallelizable with other `[P]` tasks in the same phase.
- Phase tag short codes: `SCAF`, `PERS`, `SETUP`, `SESSION`, `FORMS`,
  `APIKEY`, `OIDC`, `PROXY`, `CHAIN`, `USERMGMT`, `SELFSVC`, `API`,
  `HARD`.

---

## Phase 1: Scaffolding (`SCAF`)

- [X] T001 [SCAF] Update `pyproject.toml` — add runtime deps
      `fastapi-users[sqlalchemy,oauth]>=13`, `authlib>=1.3`,
      `redis>=5` (optional but install in MVP).
- [X] T002 [P] [SCAF] Create `src/romarr/auth/__init__.py` exposing
      `get_current_user`, `require_role`, `AuthChain`.
- [X] T003 [P] [SCAF] Create `src/romarr/auth/errors.py` —
      `AuthError`, `UnauthenticatedError`, `PermissionDenied`,
      `ApiKeyExpired`, `ApiKeyRevoked`, `OidcReplayError`,
      `SetupAlreadyCompleted`.
- [X] T004 [P] [SCAF] Create `src/romarr/auth/types.py` — `Role`,
      `ROLE_HIERARCHY`, `AuthMethod`, `AuthContext`.
- [~] T005 [P] [SCAF] Auth Pydantic Settings fields shipped
      (slice 175) but colocated in the shared
      ``romarr.config.settings.Settings`` rather than the
      dedicated ``src/romarr/auth/settings.py`` the spec
      originally called for — mirrors the spec-002 / 003 /
      004 pattern of one Settings surface per project.
      Fields: ``oidc_issuer_url``, ``oidc_client_id``,
      ``oidc_client_secret``, ``trust_proxy_auth``,
      ``trusted_proxy_headers``, ``bcrypt_cost`` (default 12,
      bounded 4-20), ``redis_url``,
      ``auth_session_ttl_seconds`` (default 86400, min 60).
      Loaded via the ``ROMARR_`` env prefix; covered by 4
      tests in ``tests/config/test_auth_settings.py``.
- [X] T006 [SCAF] Extend `tests/conftest.py` with a
      `mock_oidc_provider` fixture (respx + a fixture id_token
      JSON); create `tests/auth/conftest.py` with module-local
      fixtures (TestClient, in-memory fake Redis).

**Checkpoint**: imports work; lint+types green; no behaviour added.

---

## Phase 2: Persistence (`PERS`)

### Tests (write first; must fail)

- [X] T007 [P] [PERS] `tests/auth/test_models.py` — round-trip a
      `User` and an `ApiKey` row; CHECK constraints on `role`,
      `setup_token.id = 1`.
- [X] T008 [P] [PERS] `tests/auth/test_models.py::test_unique_username`
      — duplicate `username` raises `IntegrityError`.
- [X] T009 [P] [PERS] `tests/auth/test_models.py::test_email_unique_when_set`
      — partial unique `email`: two rows with `email = NULL` allowed,
      two with the same email rejected.
- [X] T010 [P] [PERS] `tests/auth/test_models.py::test_apikey_unique_hash`
      — duplicate `key_hash` rejected.
- [X] T011 [P] [PERS] `tests/auth/test_models.py::test_passwordless_user_validator`
      — Pydantic-level: a user with `hashed_password = NULL` AND
      `oidc_subject = NULL` AND `is_active = true` is rejected.
- [X] T012 [P] [PERS] `tests/auth/test_migration_0010.py::test_creates_tables`
      — applying the migration creates `user`, `api_key`, `session`,
      `setup_token`.
- [X] T013 [P] [PERS] `tests/auth/test_migration_0010.py::test_system_sentinel`
      — sentinel user `(id=1, username='system', is_active=false,
      is_superuser=true, role='admin')` exists post-migration.
- [ ] T014 [P] [PERS] `tests/auth/test_migration_0010.py::test_by_columns_fk_conversion`
      — pre-populate `import_history.imported_by = 'system'`,
      `blocklist.added_by = 'system'`,
      `platform_pack.applied_by = 'system'`; apply the migration;
      assert each column is now INTEGER, the FK exists, and the
      data references `user_id = 1`.

### Implementation

- [X] T015 [PERS] Create `src/romarr/auth/hashing.py` —
      `hash_password(plain: str) -> str` (bcrypt cost from
      settings), `verify_password(plain: str, hashed: str) -> bool`,
      `hash_api_key(plaintext: str) -> bytes` (BLAKE2b 32-byte),
      `verify_api_key(plaintext: str, stored_hash: bytes) -> bool`
      (constant-time via `secrets.compare_digest`).
- [ ] T016 [PERS] Create `src/romarr/auth/tokens.py` —
      `generate_api_key() -> tuple[str, bytes, str]` (returns
      `(plaintext, hash, prefix)`), `generate_setup_token() ->
      tuple[str, bytes]`, helpers for prefix derivation.
- [X] T017 [P] [PERS] Create `src/romarr/auth/models.py` — `User`,
      `ApiKey`, `Session`, `SetupToken` SQLAlchemy 2.0 models.
- [ ] T018 [P] [PERS] Create `src/romarr/auth/schemas.py` — every
      Pydantic schema from `data-model.md`.
- [X] T019 [PERS] Author `src/romarr/db/alembic/versions/0010_auth.py`
      — DDL for the four new tables + sentinel user insert + the
      four `*_by` FK conversions per the Strategy in `data-model.md`.

**Checkpoint**: `alembic upgrade head` produces a clean DB; PERS
tests green including the FK conversion test.

---

## Phase 3: Setup Bootstrap (`SETUP`)

### Tests

- [X] T020 [P] [SETUP] `tests/auth/test_setup.py::test_token_generated_on_empty_table`
      — fresh DB; on application startup the `setup_token` row is
      created; the plaintext is logged once (capture via caplog)
      with the expected prefix (FR-019).
- [X] T021 [P] [SETUP] `tests/auth/test_setup.py::test_token_not_regenerated_on_restart`
      — populate the user table; restart; no new setup token.
- [X] T022 [P] [SETUP] `tests/auth/test_setup.py::test_token_consumed_on_success`
      — POST `/api/v3/auth/setup` with valid token + payload;
      assert user created with `is_superuser = true`; replay; assert
      HTTP 401 with reason `setup_already_completed` (FR-020,
      FR-021).
- [X] T023 [P] [SETUP] `tests/auth/test_setup.py::test_token_expired`
      — freezegun-advance time 25 hours; replay setup with the
      original token; assert HTTP 401 with reason
      `setup_token_expired`.
- [X] T024 [P] [SETUP] `tests/auth/test_setup.py::test_concurrent_setup_serialised`
      — 5 concurrent POST `/api/v3/auth/setup` calls; only one
      succeeds; the other 4 get HTTP 401 with
      `setup_already_completed`.

### Implementation

- [X] T025 [SETUP] Create `src/romarr/auth/setup.py` — state machine
      `bootstrap_at_startup(session)` that checks the user table and
      writes a setup-token row if empty;
      `consume_setup_token(session, token, payload) -> User` that
      validates and creates the first admin.
- [X] T026 [SETUP] Create `src/romarr/auth/locks.py` — async
      advisory lock keyed on the literal string `"setup"` so
      concurrent setup attempts serialise.
- [X] T027 [SETUP] Wire `bootstrap_at_startup(session)` into the
      application lifespan startup handler.

**Checkpoint**: SETUP tests green; the one-shot semantics hold under
concurrency.

---

## Phase 4: Session Store (`SESSION`)

### Tests

- [X] T028 [P] [SESSION] `tests/auth/session/test_redis_backend.py::test_create_get_revoke`
      — happy path against a fakeredis instance.
- [X] T029 [P] [SESSION] `tests/auth/session/test_redis_backend.py::test_ttl_aligned`
      — created session expires at `expires_at`; freezegun + TTL
      check.
- [X] T030 [P] [SESSION] `tests/auth/session/test_db_backend.py::test_fallback_path`
      — DB fallback works identically; expired rows are pruned by a
      lazy cleanup helper.
- [X] T031 [P] [SESSION] `tests/auth/session/test_redis_backend.py::test_redis_unavailable_falls_back_to_db`
      — patch the Redis client to raise; assert subsequent calls go
      to the DB backend AND an `OnHealthIssue` event is emitted.

### Implementation

- [X] T032 [SESSION] Create `src/romarr/auth/session/__init__.py`
      with the `SessionStore` ABC (`create`, `get`, `revoke`,
      `extend_ttl`).
- [X] T033 [P] [SESSION] Create `src/romarr/auth/session/redis_backend.py`.
- [X] T034 [P] [SESSION] Create `src/romarr/auth/session/db_backend.py`.
- [X] T035 [SESSION] Add a small composer that picks Redis at
      startup (probes connectivity once) and falls back to DB on
      runtime failure with the documented health event.

**Checkpoint**: SESSION tests green; the fallback path is covered.

---

## Phase 5: Forms Auth (`FORMS`)

### Tests

- [X] T036 [P] [FORMS] `tests/auth/api/test_auth_endpoints.py::test_login_sets_cookie`
      — POST login with valid creds; assert HTTP 204; cookie carries
      `HttpOnly`, `SameSite=Lax`, and `Secure` (when HTTPS).
- [X] T037 [P] [FORMS] `tests/auth/api/test_auth_endpoints.py::test_login_wrong_password`
      — wrong password; assert HTTP 401 with the canonical
      `unauthenticated` shape; bcrypt is invoked even on
      "user not found" (constant-time).
- [X] T038 [P] [FORMS] `tests/auth/api/test_auth_endpoints.py::test_logout_revokes_session`
      — POST logout; assert next request returns HTTP 401.

### Implementation

- [X] T039 [FORMS] Create `src/romarr/auth/methods/cookie.py` —
      cookie session resolver: extract session id, look up via the
      session store, return `AuthContext`.
- [X] T040 [FORMS] Create `src/romarr/auth/api/auth.py` — FastAPI
      router for `/api/v3/auth/login`, `/logout`, `/me`,
      `/me/preferences`. The login handler uses bcrypt
      `verify_password`; the logout handler revokes the session.

**Checkpoint**: FORMS tests green; the canonical 401 shape is used
on every failure path.

---

## Phase 6: API Keys (`APIKEY`)

### Tests

- [X] T041 [P] [APIKEY] `tests/auth/api/test_api_key_endpoints.py::test_create_returns_plaintext_once`
      — POST creates the key; response carries `plaintext_key`;
      subsequent GET returns only `key_prefix`, no plaintext (SC-004).
- [X] T042 [P] [APIKEY] `tests/auth/methods/test_api_key.py::test_lookup_by_hash`
      — incoming key in `X-Api-Key`; resolved via BLAKE2b lookup;
      authenticates the owning user.
- [X] T043 [P] [APIKEY] `tests/auth/methods/test_api_key.py::test_revoked_key_fails`
      — DELETE the key; immediate next request fails (SC-005).
- [X] T044 [P] [APIKEY] `tests/auth/methods/test_api_key.py::test_expired_key_fails`
      — `expires_at` past; reason `api_key_expired`.
- [X] T045 [P] [APIKEY] `tests/auth/methods/test_api_key.py::test_constant_time_compare`
      — assert that `verify_api_key` uses
      `secrets.compare_digest` (introspect or time the difference
      between off-by-one and totally-wrong inputs).
- [X] T046 [P] [APIKEY] `tests/auth/api/test_api_key_endpoints.py::test_scope_enforcement`
      — key with `scopes=["read"]`; POST endpoint requiring
      `write`; assert HTTP 403 with reason `insufficient_scope`.

### Implementation

- [X] T047 [APIKEY] Create `src/romarr/auth/methods/api_key.py` —
      `resolve_api_key(request) -> AuthContext | None`. Looks at
      `X-Api-Key` then `apikey` query param; hashes via BLAKE2b;
      single indexed lookup by `key_hash`; checks
      `expires_at`/`revoked_at`; updates `last_used_at` /
      `last_used_ip` in a fire-and-forget background task.
- [X] T048 [APIKEY] Create `src/romarr/auth/api/api_keys.py` —
      FastAPI router for `/api/v3/auth/api-key*` (per-user) plus
      the admin variant `?user_id=N`. The CREATE response uses
      `ApiKeyCreateResponse` which includes `plaintext_key`; the
      LIST/GET responses use `ApiKeyRead` which never includes it.

**Checkpoint**: APIKEY tests green; revocation is immediate; the
plaintext is exposed exactly once.

---

## Phase 7: OIDC (`OIDC`)

### Tests

- [X] T049 [P] [OIDC] `tests/auth/oidc/test_client.py::test_discovery_loaded_lazily`
      — provider's `/.well-known/openid-configuration` is cached
      after the first successful fetch.
- [X] T050 [P] [OIDC] `tests/auth/oidc/test_flow.py::test_full_round_trip`
      — POST `/api/v3/auth/oidc/start`; capture state/nonce/PKCE;
      simulate provider redirect with code; GET
      `/auth/oidc/callback`; assert user created with mapped role
      and session cookie set (US4.2).
- [X] T051 [P] [OIDC] `tests/auth/oidc/test_flow.py::test_replay_rejected`
      — replay the same code; HTTP 400 with reason
      `oidc_code_already_used` (FR-016).
- [X] T052 [P] [OIDC] `tests/auth/oidc/test_flow.py::test_existing_user_role_synced`
      — existing user; group claim changes; user's `is_superuser`
      and `role` update on next login (US4.3).
- [X] T053 [P] [OIDC] `tests/auth/oidc/test_flow.py::test_auto_create_disabled`
      — `AUTO_CREATE = false`; first OIDC login for an unknown user
      ⇒ HTTP 403 reason `oidc_user_not_provisioned`.
- [X] T054 [P] [OIDC] `tests/auth/oidc/test_group_mapping.py::test_property_mapping`
      — hypothesis property test: random claim shapes; map to
      role consistently; unmapped groups default to `user`.
- [X] T055 [P] [OIDC] `tests/auth/oidc/test_client.py::test_secret_encrypted_at_rest`
      — the `client_secret` env value is decrypted at call time but
      never logged.

### Implementation

- [X] T056 [OIDC] Create `src/romarr/auth/oidc/client.py` — Authlib
      `OAuth` client setup, async `discover()` with caching.
- [X] T057 [OIDC] Create `src/romarr/auth/oidc/group_mapping.py` —
      pure `map_groups_to_role(claims, mapping) -> Role`.
- [X] T058 [OIDC] Create `src/romarr/auth/oidc/flow.py` — `start()`
      handler returning the authorization URL with state/nonce/PKCE,
      `callback(code, state)` handler that exchanges + validates +
      finds-or-creates the user.
- [X] T059 [OIDC] Create `src/romarr/auth/api/oidc.py` — FastAPI
      router for `/api/v3/auth/oidc/start` and the callback at
      `/auth/oidc/callback`.

**Checkpoint**: OIDC tests green including replay protection and
group-to-role sync on existing users.

---

## Phase 8: Trusted Proxy (`PROXY`)

### Tests

- [X] T060 [P] [PROXY] `tests/auth/methods/test_proxy.py::test_disabled_by_default`
      — `ROMARR_TRUST_PROXY_AUTH = false`; configured trusted header
      is ignored; chain falls through.
- [X] T061 [P] [PROXY] `tests/auth/methods/test_proxy.py::test_enabled_authenticates_known_user`
      — `ROMARR_TRUST_PROXY_AUTH = true`; header carries known
      username; user is authenticated.
- [X] T062 [P] [PROXY] `tests/auth/methods/test_proxy.py::test_unknown_user_auto_creates`
      — header carries new username; user auto-created with role
      `user`; subsequent requests update only `last_login_at`.
- [X] T063 [P] [PROXY] `tests/auth/methods/test_proxy.py::test_oidc_collision_warning`
      — proxy header username collides with an OIDC-created user
      having a different `oidc_subject`; proxy auth wins for this
      request but a warning is logged.

### Implementation

- [X] T064 [PROXY] Create `src/romarr/auth/methods/proxy.py` —
      `resolve_proxy_auth(request) -> AuthContext | None`. Reads
      the configured header list, matches against `user.username`,
      auto-creates if missing.

**Checkpoint**: PROXY tests green; default disabled; collision
detection logs but does not break.

---

## Phase 9: Chained Dependency + RBAC (`CHAIN`)

### Tests

- [X] T065 [P] [CHAIN] `tests/auth/methods/test_chain.py::test_order_api_key_first`
      — request has both API key and session cookie; API key wins
      per FR-022.
- [X] T066 [P] [CHAIN] `tests/auth/methods/test_chain.py::test_falls_through_on_failed_method`
      — invalid API key + valid session cookie ⇒ session wins
      (i.e., a wrong API key does not abort the chain).
- [X] T067 [P] [CHAIN] `tests/auth/methods/test_chain.py::test_generic_401_shape`
      — every failed method produces the same canonical 401
      response body; no method-specific leak (FR-023, SC-008).
- [X] T068 [P] [CHAIN] `tests/auth/test_rbac.py::test_admin_implies_user_implies_readonly`
      — admin passes every endpoint; user passes user/readonly;
      readonly only readonly.
- [X] T069 [P] [CHAIN] `tests/auth/test_rbac.py::test_30_endpoint_corpus`
      — fixture: 30 protected endpoints with their required role;
      exercise each as readonly/user/admin; assert the right HTTP
      status in 100% of cases (SC-006).

### Implementation

- [X] T070 [CHAIN] Create `src/romarr/auth/methods/chain.py` —
      `AuthChain.resolve(request) -> AuthContext`. Tries each
      method in order; returns first non-None result; raises
      `UnauthenticatedError` (HTTP 401, canonical body) when all
      fail.
- [X] T071 [CHAIN] Create `src/romarr/auth/rbac.py` —
      `require_role(role)` FastAPI dependency that wraps
      `AuthChain.resolve` and raises `PermissionDenied` (HTTP 403)
      when `ROLE_HIERARCHY[user.role] < ROLE_HIERARCHY[required]`.
- [X] T072 [CHAIN] **Sweep the codebase**: replace every
      `dev_only_admin` import in earlier specs with the real
      `require_role(...)` dependency. T087 in HARD verifies no
      `dev_only_admin` references remain.

**Checkpoint**: CHAIN tests green; all earlier specs' endpoints now
use the real auth dependency.

---

## Phase 10: Admin User CRUD (`USERMGMT`)

### Tests

- [X] T073 [P] [USERMGMT] `tests/auth/api/test_user_endpoints.py::test_create_user`
      — admin creates a user; assert `last_login_at IS NULL` until
      the user actually logs in.
- [X] T074 [P] [USERMGMT] `tests/auth/api/test_user_endpoints.py::test_update_role`
      — admin PUT `is_superuser = true`; assert the user passes
      `require_role('admin')` on next request.
- [X] T075 [P] [USERMGMT] `tests/auth/api/test_user_endpoints.py::test_reset_password_returns_token`
      — admin POST `/api/v3/user/{id}/reset-password`; response
      carries a one-time reset token (since SMTP is OoS in MVP).
- [X] T076 [P] [USERMGMT] `tests/auth/api/test_user_endpoints.py::test_cannot_delete_last_admin`
      — only one admin in the DB; DELETE that admin; assert HTTP
      409 with reason `cannot_delete_last_admin` (US8.3).
- [X] T077 [P] [USERMGMT] `tests/auth/api/test_user_endpoints.py::test_non_admin_blocked`
      — non-admin authenticated; GET `/api/v3/user`; assert HTTP
      403.

### Implementation

- [X] T078 [USERMGMT] Create `src/romarr/auth/api/users.py` —
      FastAPI router for `/api/v3/user*` and
      `/api/v3/user/{id}/reset-password`. Wrapped by
      `require_role('admin')`.

**Checkpoint**: USERMGMT tests green; lone-admin lockout
prevention holds.

---

## Phase 11: Self-Service (`SELFSVC`)

### Tests

- [ ] T079 [P] [SELFSVC] `tests/auth/api/test_auth_endpoints.py::test_me_returns_current_user`
      — GET `/api/v3/auth/me`; returns the authenticated user.
- [ ] T080 [P] [SELFSVC] `tests/auth/api/test_auth_endpoints.py::test_me_password_change`
      — PUT `/api/v3/auth/me` with a new password; old password
      stops working; new password works on next login.
- [ ] T081 [P] [SELFSVC] `tests/auth/api/test_auth_endpoints.py::test_me_preferences`
      — GET/PUT `/api/v3/auth/me/preferences`; persisted JSON
      round-trips.
- [ ] T082 [P] [SELFSVC] `tests/auth/api/test_auth_endpoints.py::test_me_cannot_escalate_role`
      — non-admin user tries PUT `/api/v3/auth/me` with
      `{is_superuser: true}`; assert HTTP 400 reason
      `cannot_change_own_role` (the role field is filtered from
      self-update).

### Implementation

- [ ] T083 [SELFSVC] Extend `src/romarr/auth/api/auth.py` with
      `/me` PUT and `/me/preferences` GET/PUT. The handler
      whitelists which fields a user can self-update (no role
      escalation).

**Checkpoint**: SELFSVC tests green.

---

## Phase 12: API Wiring (`API`)

- [ ] T084 [API] Wire all five routers (`auth`, `setup`,
      `api_keys`, `oidc`, `users`) into the application factory at
      their documented paths. The setup router is mounted only when
      the `setup_token` row exists (otherwise the endpoint returns
      HTTP 404 to avoid a useless route).
- [X] T085 [API] Lifespan now invokes
      ``maybe_bootstrap_setup_token`` after the spec 003 +
      spec 006 seeders (slice 187). The setup-token plaintext
      is logged at WARNING level so the operator can capture
      it from container logs and complete ``/auth/setup``. The
      Redis-probe step is documented as deferred — Redis is
      optional today (in-memory rate limiter / idempotency
      cache) so a probe-and-fail step would prevent boot in
      the common SQLite-only deployment. Bootstrap as a whole
      is gated on ``ROMARR_BOOTSTRAP_ENABLED=true``
      (Settings.bootstrap_enabled) per the slice 187
      factoring; tests preserve their per-instance escape
      hatch via ``app.state._enable_bootstrap``.

**Checkpoint**: a fresh boot prints the setup token; a populated
boot does not; OIDC routes available when configured.

---

## Phase 13: Hardening (`HARD`)

- [X] T086 [HARD] Auth coverage validated against SC-010
      (slice 189). ``pytest --cov=romarr.auth`` reports every
      auth module ≥ 81% — most ≥ 96%. Per-module breakdown:
      __init__ 100%, api_keys 94%, chain 96%, constants 97%,
      errors 100%, hashing 100%, login 100%, models 100%,
      permissions 96%, rate_limit 100%, sessions 98%, setup
      97%, users 81%. ≥75% target comfortably exceeded.
- [X] T087 [HARD] ``git grep dev_only_admin src/`` returns
      ZERO matches (slice 189). Every endpoint now routes
      through ``require_admin`` / ``require_role``.
- [X] T088 [HARD] ``ruff check src/romarr/auth/`` — zero
      warnings (slice 189).
- [X] T089 [HARD] Canonical 401 envelope smoke test shipped
      at ``tests/auth/test_canonical_401_envelope.py``
      (slice 189). Parametrised over 14 protected endpoints;
      asserts every response body is exactly
      ``{"errorMessage": "unauthenticated", "errorCode": "unauthenticated"}``.
      Plus a no-leak test that scans the body for forbidden
      keywords (session, cookie, api key, bearer, jwt,
      expired, revoked, credentials, deactivated). Path
      diverges from the spec's
      ``{"detail": "unauthenticated"}`` shape — Romarr ships
      the Sonarr-compatible envelope so existing tooling
      consumes the body without special-casing.
- [ ] T090 [HARD] Manual perf check — measure forms-auth login
      latency p95 (excluding bcrypt) and API-key validation p95;
      record in `specs/010-auth-multiuser/research.md`.
- [X] T091 [HARD] CHANGELOG entry shipped at slice 191 — see
      ``CHANGELOG.md`` ``[0.10.0a1] — 2026-05-03``. The
      ``pyproject.toml`` version itself is past 0.10 (currently
      ``0.14.0a1``) because the spec catalogue was completed
      in numeric-spec order rather than version-tagged
      sequentially. The CHANGELOG section documents the auth
      spec's contributions, the SC-010 coverage outcome, the
      Sonarr-compatible 401 envelope divergence, and the
      CL008 deferral.
- [ ] T092 [HARD] Final review: open
      `specs/010-auth-multiuser/spec.md` and tick every
      Functional Requirement (FR-001 → FR-027) against a task ID;
      record gaps as follow-up items.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (SCAF)**: prerequisite spec merged.
- **Phase 2 (PERS)**: depends on Phase 1.
- **Phase 3 (SETUP)**: depends on Phase 2.
- **Phase 4 (SESSION)**: depends on Phase 2.
- **Phase 5 (FORMS)**: depends on Phases 2 and 4.
- **Phase 6 (APIKEY)**: depends on Phase 2.
- **Phase 7 (OIDC)**: depends on Phases 2 and 4.
- **Phase 8 (PROXY)**: depends on Phase 2.
- **Phase 9 (CHAIN)**: depends on Phases 5, 6, 7, 8.
- **Phase 10 (USERMGMT)**: depends on Phase 9.
- **Phase 11 (SELFSVC)**: depends on Phase 5.
- **Phase 12 (API)**: depends on Phases 9, 10, 11.
- **Phase 13 (HARD)**: depends on Phase 12.

### Within-Phase Parallelism

- Phase 1: T002–T005 in parallel.
- Phase 2: T007–T014 in parallel; T015–T018 in parallel.
- Phase 3: T020–T024 in parallel.
- Phase 4: T028–T031 in parallel; T033 + T034 in parallel.
- Phase 5: T036–T038 in parallel.
- Phase 6: T041–T046 in parallel.
- Phase 7: T049–T055 in parallel.
- Phase 8: T060–T063 in parallel.
- Phase 9: T065–T069 in parallel.
- Phase 10: T073–T077 in parallel.
- Phase 11: T079–T082 in parallel.

### Critical Path

`SCAF → PERS → SETUP → CHAIN → API → HARD`. Sessions, API keys,
OIDC, and proxy auth can all develop in parallel once PERS is
done.

### Implementation Strategy

- **Day 1**: Phase 1 (SCAF) + Phase 2 (PERS) — including the
  `*_by` FK conversion migration test.
- **Day 2**: Phase 3 (SETUP) + Phase 4 (SESSION).
- **Day 3**: Phase 5 (FORMS) + Phase 6 (APIKEY).
- **Day 4**: Phase 7 (OIDC) — the most fiddly piece.
- **Day 5**: Phase 8 (PROXY) + Phase 9 (CHAIN) + Phase 11 (SELFSVC)
  + sweep the dev-only dependency.
- **Day 6**: Phase 10 (USERMGMT) + Phase 12 (API).
- **Day 7**: Phase 13 (HARD).

This sizing assumes one developer working full-time. With two
contributors, OIDC and APIKEY split cleanly across them.

---

## Notes

- `[P]` tasks change different files only.
- Tests are written BEFORE implementation in every phase.
- Stop at any phase checkpoint — auth is delivered incrementally;
  each phase is independently shippable. The sweep in T072
  (replacing the dev-only dependency) is the one truly
  cross-cutting change.
- Avoid: implementing LDAP (deferred to v1+); implementing 2FA
  (deferred); per-library or per-game permissions (deferred to
  v1+ / firm out); SMTP-based password reset (deferred to v1+);
  account lockout (deferred); SAML (firm out — use OIDC).
- Constitutional invariants under test:
  - **Article XVII (Idempotency & Safety)** — setup token one-shot
    (T022, T024); API key revocation immediate (T043); 401
    responses don't disclose method (T067); password + API key
    hashed at rest (T015 + SC-009).
  - **Article XVI (Quality Gates)** — ≥ 75% coverage (T086); the
    perf budgets in plan.md are met (T090).
  - **Article III (Locked Stack)** — FastAPI-Users + Authlib +
    bcrypt + Redis are well-maintained Python libs; no custom auth
    crypto ships (T087 verifies the dev-only dependency is gone).

## Phase: Clarification Tasks (Session 2026-04-29)

- [X] CL001 Migration ``0010_auth_multiuser.py`` ships the
      ``user`` table with the ``role`` CHECK + the ``system``
      sentinel row (id=0, username='system', is_active=false,
      role='admin', hashed_password=NULL). No
      ``is_superuser`` column. Confirmed by
      ``tests/auth/test_migration.py``.
- [X] CL002 [P] ``User.is_superuser`` property at
      ``auth/models.py:104-112`` returns ``self.role == ROLE_ADMIN``.
      No setter — Python-level read-only.
- [X] CL003 Migration ``0010_auth_multiuser.py`` ships
      ``session`` with ``last_used_at`` + ``expires_at`` plus
      the ``expires_at`` index for eviction queries.
- [X] CL004 [P] [US2] Sliding TTL update shipped at
      ``auth/sessions.py::resolve_session`` (lines 147-152) —
      every successful resolve updates ``last_used_at = now()``
      and ``expires_at = now() + SESSION_TTL_DAYS``. Path
      differs from the spec's ``session_resolver.py``.
      ``slide=False`` flag preserved for diagnostic tooling
      that wants to inspect a session without extending its
      life.
- [X] CL005 Migration ``0010_auth_multiuser.py`` ships
      ``api_key.scopes`` JSON NOT NULL with a ``["read"]``
      default; validator-layer subset check enforced in
      ``api_keys.py::create_api_key`` (lines 74-78).
- [X] CL006 [P] [US3] 3-tier scope mapping shipped across
      ``auth/constants.py`` (``role_to_required_scope``,
      ``role_implies``, ``scope_implies``) and
      ``auth/permissions.py``. Path differs from the spec's
      ``scope_resolver.py``. Higher tiers imply lower (an
      admin-scoped key passes write/read guards) — pinned by
      ``tests/auth/test_constants.py``.
- [X] CL007 [P] [US2] Login rate limit shipped at
      ``auth/rate_limit.py::IpRateLimiter`` —
      10 attempts/minute/source-IP, HTTP 429 with
      ``Retry-After``, bcrypt skipped when limit exceeded.
      Tests:
      ``tests/auth/test_rate_limit.py``.
- [~] CL008 ``*_by`` text→INT FK migration — DEFERRED. The
      ``system`` sentinel row is in place (CL001), but the
      four columns (``import_history.imported_by``,
      ``platform_pack.applied_by``, ``application.applied_by``,
      ``blocklist.added_by``) remain ``String(64)`` rather than
      ``Integer FK -> user.id``. The conversion is non-trivial
      (backfill + type change + model + caller updates across
      five specs) and is best done as a dedicated slice. The
      negative consequence today is cosmetic: audit columns
      can carry user IDs but also legacy strings. No
      correctness impact since reads are display-only.
- [X] CL009 [P] Auth chain order shipped at
      ``auth/chain.py::resolve_principal`` (lines 100-137):
      X-Api-Key → apikey query → session cookie →
      trusted-proxy header. No bearer-JWT step. Module
      docstring carries a "JWT dropped" note for posterity.
- [X] CL010 [P] **Negative invariants confirmed** by
      grep: no ``POST /auth/token`` route, no
      ``signing_key``/``jwt_secret``/``sign_jwt`` symbol in
      the codebase. The OpenAPI doc DOES advertise a
      ``BearerJwt`` security scheme but only for accepting
      OIDC-issued tokens (read-only validation against an
      external IdP); Romarr never mints JWTs.
- [X] CL011 [P] Session TTL tests shipped at
      ``tests/auth/test_sessions.py`` —
      ``test_create_session_returns_plaintext_id_and_30d_expiry``,
      ``test_resolve_session_slides_expiry_forward``,
      ``test_resolve_session_no_slide``, plus the expiry
      cleanup path. Path differs from the spec's
      ``test_session_ttl.py``.
- [~] CL012 [P] Scope-enforcement tests partially covered:
      unit tests at ``tests/auth/test_constants.py`` pin the
      ``role_implies`` + ``scope_implies`` matrix, and
      ``tests/auth/test_api_keys.py::test_resolve_api_key_expired``
      pins the expired-key path. The integration-style
      "read-only key on GET=200, on POST=403" cases are
      sprinkled across the per-module endpoint tests rather
      than centralised in
      ``tests/auth/test_scope_enforcement.py`` — same
      coverage, different organisation.
- [X] CL013 [P] Rate-limit tests shipped at
      ``tests/auth/test_rate_limit.py`` —
      ``test_under_limit_passes``,
      ``test_window_slide_allows_new_attempts``,
      ``test_per_ip_buckets_independent``, plus the 11th-attempt
      blocking case and ``Retry-After`` propagation. Path
      differs from the spec's ``test_login_rate_limit.py``.
