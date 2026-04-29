# Feature Specification: Authentication & Multi-User

**Feature Branch**: `010-auth-multiuser` (branch creation skipped: git repo lives in parent dir)
**Created**: 2026-04-29
**Status**: Draft
**Depends on**:
- `002-metadata-aggregation` — `ROMARR_AUTH_SECRET_KEY`-derived encryption helper
  re-used to encrypt OIDC client-secret + indexer/RomM API keys at rest
  (already a Constitution Article XVII gate).
- All earlier specs that have a `*_by` text column (e.g.,
  `import_history.imported_by`, `platform_pack.applied_by`,
  `application.applied_by`, `blocklist.added_by`) — those columns become FK
  INTEGER references to `user.id` once this spec lands.
**Replaces**: every prior spec's "development-only no-op admin dependency". From
this spec onwards, every protected endpoint runs through the real chained auth
dependency.
**Input**: User description: "Build the authentication and authorization layer. Four auth methods (forms, basic, OIDC, API keys), three-tier RBAC (admin/user/readonly), initial admin bootstrap on first boot, server-side session store."

## Clarifications

### Session 2026-04-29

- Q: What TTL policy do server-side sessions follow? → A: Sliding 30-day expiry. Each session row carries `expires_at = last_used_at + 30 days`; every authenticated request that uses the session bumps `last_used_at` (and therefore `expires_at`) forward. Sessions idle for more than 30 days self-expire and return HTTP 401 on next use. Logout (FR-011) revokes immediately. No absolute cap at MVP
- Q: What's the API-key scope vocabulary? → A: Three coarse scopes mirroring the RBAC tiers: `read` (every `GET` endpoint), `write` (every `POST` / `PUT` / `DELETE` on non-admin endpoints), `admin` (every admin-only endpoint). A key's `scopes` is any subset of `["read", "write", "admin"]`. The route guard checks `endpoint_required_scope ∈ key.scopes` for keys; sessions follow the role chain. No per-resource fine-grained scopes at MVP
- Q: Who issues the JWT in `Authorization: Bearer JWT` (FR-022's auth chain)? → A: Drop the JWT path entirely at MVP. The auth chain is API-key (header or query) → session cookie → trusted-proxy header. CLIs and scripts use API keys (FR-005). The OIDC provider's `id_token` is consumed exclusively in the SSO callback flow (FR-014) and never appears as an inbound `Authorization: Bearer` token. Romarr does NOT mint its own JWTs at MVP — a future spec may revisit this if a concrete need surfaces
- Q: How does Romarr defend against brute-force on `POST /api/v3/auth/login` given that account lockout is out of scope? → A: Per-source-IP rate limit of 10 login attempts/minute. HTTP 429 above the threshold. Per-user lockout stays deferred (it's a DoS surface). Bcrypt cost 12 plus the IP rate limit are the two defense layers at MVP
- Q: How is the `is_superuser` vs `role` data-model inconsistency resolved? → A: Drop `is_superuser` from the schema. Only the `role` text column exists (`'admin' | 'user' | 'readonly'`). `User.is_superuser` becomes a read-only Python property derived from `self.role == 'admin'`; never persisted, never UPDATE-able. Single source of truth; no divergence class

## User Scenarios & Testing *(mandatory)*

### User Story 1 — First-boot operator becomes admin in under 60 seconds (Priority: P1)

A Romarr operator launches the container for the first time. The user
table is empty. On startup, Romarr generates a one-time setup token,
prints it prominently in the logs, and accepts a single
`/api/v3/auth/setup` call carrying that token to create the first
admin user. After that one call, the token is invalidated forever —
even if it has not expired.

**Why this priority**: Without the bootstrap, a fresh instance is
unusable: there is no admin to log in as, no admin to create other
users. This is the very first thing every operator does.

**Independent Test**: Boot a fresh database; tail the logs to capture
the setup token; POST `/api/v3/auth/setup` with the token + an
admin payload; verify the user materialises with `role = 'admin'`;
replay the same POST and verify HTTP 401 (token consumed).

**Acceptance Scenarios**:

1. **Given** an empty user table, **When** the application starts,
   **Then** a setup token is generated, persisted with a 24-hour
   expiry, and printed once to the logs at INFO level using a
   distinctive prefix (e.g., `ROMARR INITIAL SETUP TOKEN:`).
2. **Given** the setup token, **When** the operator POSTs
   `/api/v3/auth/setup` with `{username, password}` plus the
   `X-Setup-Token` header, **Then** the first admin user is created
   with `role = 'admin'` and the token is invalidated.
3. **Given** the setup token has been used (or has expired), **When**
   the same POST is replayed, **Then** the response is HTTP 401 with a
   structured "setup_already_completed" or "setup_token_expired"
   reason; the application does NOT generate a new setup token even
   if the user table somehow returned to empty.
4. **Given** a populated user table, **When** the application
   restarts, **Then** no new setup token is generated.

---

### User Story 2 — Forms login + session for personal use (Priority: P1)

A Romarr operator types their username and password into the login
form, gets a session cookie, and uses Romarr normally. The cookie
carries `HttpOnly`, `SameSite=Lax`, and (over HTTPS) `Secure` flags.
Logout revokes the session immediately.

**Why this priority**: Forms auth is the default and the path most
homelab operators use. Without it, every operator has to set up OIDC
or live with reverse-proxy auth.

**Independent Test**: POST `/api/v3/auth/login` with valid
credentials; assert HTTP 204 with a `Set-Cookie` header carrying
`HttpOnly` and `SameSite=Lax`; subsequent requests with that cookie
return HTTP 200 from `/api/v3/auth/me`; POST `/api/v3/auth/logout`;
the same request returns HTTP 401.

**Acceptance Scenarios**:

1. **Given** a valid username/password pair, **When** the operator
   POSTs `/api/v3/auth/login`, **Then** the response carries a
   `Set-Cookie` header with the session id, `HttpOnly`,
   `SameSite=Lax`, and `Secure` when the server runs over HTTPS.
2. **Given** an active session, **When** the operator POSTs
   `/api/v3/auth/logout`, **Then** the session is revoked
   server-side and the cookie is cleared; subsequent requests with
   the old cookie return HTTP 401.
3. **Given** a wrong password, **When** the operator POSTs
   `/api/v3/auth/login`, **Then** the response is HTTP 401 with a
   constant-time comparison (no timing side channel) and a generic
   "invalid_credentials" message.

---

### User Story 3 — API key for Notifiarr integration (Priority: P1)

A Romarr operator wants Notifiarr to call Romarr's webhook endpoint
without sharing their personal credentials. They create an API key
named "Notifiarr Production" with `read+write` scopes; the key is
displayed once in the UI as `rmk_<43 chars>`; from that moment on
Notifiarr presents the key on every request and Romarr validates it
in O(1) via the indexed BLAKE2b hash.

**Why this priority**: API keys are the integration backbone. Without
them, every external tool (Notifiarr, Recyclarr, Homepage,
Overseerr-style request managers) is locked out.

**Independent Test**: POST `/api/v3/auth/api-key` with
`{name, scopes}`; assert the response carries the **full plaintext
key** exactly once; subsequent GETs return only the prefix
(`key_prefix`); use the key on a protected endpoint via
`X-Api-Key`; assert HTTP 200; revoke the key; the same call now
returns HTTP 401.

**Acceptance Scenarios**:

1. **Given** an authenticated user, **When** they POST
   `/api/v3/auth/api-key` with a `{name, scopes}` body, **Then** the
   response includes the plaintext key exactly once; the database
   stores `key_hash` (BLAKE2b) and `key_prefix` (first 8 chars), never
   the plaintext.
2. **Given** the same key, **When** an integration sends it via
   `X-Api-Key` or via the `apikey=` query parameter, **Then** the
   request authenticates as the owning user with the documented
   scopes.
3. **Given** the key is revoked (DELETE), **When** the integration
   reuses it, **Then** the response is HTTP 401 with reason
   `api_key_revoked`.
4. **Given** the key has an `expires_at` in the past, **When** the
   integration uses it, **Then** the response is HTTP 401 with reason
   `api_key_expired`.

---

### User Story 4 — OIDC SSO via Authentik (Priority: P2)

The operator runs Authentik for SSO across their homelab. They
configure Romarr's OIDC env vars and group-to-role mapping. A user
clicks "Login with SSO", round-trips through Authentik, and lands
back on Romarr authenticated. New users are auto-created if
`AUTO_CREATE = true`; group membership maps to the correct role.

**Why this priority**: OIDC is the dominant homelab pattern; without
it operators with Authentik pull their hair out.

**Independent Test**: Stub an OIDC provider with respx; click the
SSO link; round-trip the redirect dance; verify the user is created
on first login with the `admin` role per group mapping; verify the
session cookie is set.

**Acceptance Scenarios**:

1. **Given** OIDC is enabled and configured, **When** the user
   POSTs `/api/v3/auth/oidc/start`, **Then** the response carries an
   authorization URL with valid state, nonce, and PKCE
   challenge.
2. **Given** the provider redirects back with a valid code, **When**
   `/auth/oidc/callback` runs, **Then** Romarr exchanges the code,
   validates the id_token, looks up the user by `(provider,
   subject)`, and creates a new user with the role mapped from the
   token's groups claim if `AUTO_CREATE = true`.
3. **Given** an OIDC user is found, **When** their group claim
   changes between logins (e.g., promoted from `user` to `admin`),
   **Then** the user's `role` column is updated to match.
4. **Given** OIDC is enabled and a code is replayed, **When**
   `/auth/oidc/callback` runs twice, **Then** the second call fails
   with HTTP 400 and reason `oidc_code_already_used`.

---

### User Story 5 — RBAC blocks readonly users from writing (Priority: P2)

A Romarr operator creates a `readonly` user for a friend who wants
to browse the catalog. The friend tries to POST a new Game; the
request returns HTTP 403 with a structured "permission_denied"
reason.

**Why this priority**: Without enforcement, the role distinction is
cosmetic. The whole point of three-tier RBAC is the gate.

**Independent Test**: Create a `readonly` user; authenticate as
them; attempt POST `/api/v3/game`; assert HTTP 403; the same
attempt as a `user` returns HTTP 200.

**Acceptance Scenarios**:

1. **Given** the authenticated user's role is `readonly`, **When**
   they hit any endpoint protected by `@require_role('user')` or
   `@require_role('admin')`, **Then** the response is HTTP 403 with
   reason `permission_denied`.
2. **Given** the user's role is `admin`, **When** they hit any
   endpoint protected by `@require_role('user')` or
   `@require_role('readonly')`, **Then** the response is HTTP 200
   (admin implies user implies readonly).
3. **Given** an unauthenticated request, **When** it hits any
   protected endpoint, **Then** the response is HTTP 401 with reason
   `unauthenticated`.

---

### User Story 6 — Reverse-proxy auth for Authentik front-door (Priority: P2)

The operator runs Authentik in front of Romarr via Traefik. The
proxy validates the user and forwards the username in the
`X-Authentik-Username` header. Romarr trusts the header (because the
operator has set `ROMARR_TRUST_PROXY_AUTH = true`) and the user
arrives at Romarr already authenticated, no second login.

**Why this priority**: This is how a meaningful chunk of operators
deploy Romarr. Without it, they hit a "log in to Romarr" page after
already logging in to Authentik.

**Independent Test**: Set `ROMARR_TRUST_PROXY_AUTH = true`; send a
GET request carrying `X-Authentik-Username: alice` (configured as a
trusted header); assert the user `alice` is authenticated on the
request; remove the env flag; the same header is now ignored.

**Acceptance Scenarios**:

1. **Given** `ROMARR_TRUST_PROXY_AUTH = true` and the configured
   trusted-header list, **When** a request carries the configured
   header with a known username, **Then** the user is authenticated
   per the header value.
2. **Given** `ROMARR_TRUST_PROXY_AUTH = false`, **When** the same
   header arrives, **Then** it is ignored and the chain falls
   through to the next auth method.
3. **Given** the trusted header carries a username that does NOT
   exist in Romarr, **When** the request runs, **Then** the user is
   auto-created with role `user` (configurable default) the first
   time; subsequent requests update only `last_login_at`.

---

### User Story 7 — Self-service password and preferences (Priority: P3)

A Romarr operator wants to change their own password, switch the UI
theme to dark, and pin a default library. They hit
`/api/v3/auth/me` to update; no admin required.

**Why this priority**: A nice-to-have. The admin UI can do all of
this for operators initially, but self-service is a quality-of-life
expectation.

**Independent Test**: Authenticate as a non-admin user; PUT
`/api/v3/auth/me` with `{password, preferences}`; verify the new
password works on next login and the preferences are persisted.

**Acceptance Scenarios**:

1. **Given** an authenticated user, **When** they PUT
   `/api/v3/auth/me` with a new password, **Then** the password is
   re-hashed (bcrypt cost 12) and persisted; the next
   `/api/v3/auth/login` succeeds with the new password and fails
   with the old.
2. **Given** the same user, **When** they PUT
   `/api/v3/auth/me/preferences`, **Then** the JSON preferences are
   persisted; subsequent GET returns the updated values.

---

### User Story 8 — Admin CRUD on users (Priority: P3)

A Romarr admin manages users via the `/api/v3/user*` endpoints:
list, create, update (including role), delete, and reset another
user's password.

**Why this priority**: Useful but not blocking — most homelab
operators have one or two users. The endpoints are required for
multi-user homelabs and for OIDC group-syncing.

**Independent Test**: As admin, POST `/api/v3/user`; assert the
new user can log in; PUT `/api/v3/user/{id}` to set
`role = 'admin'`; assert the user now has admin role on next
request; DELETE `/api/v3/user/{id}`; assert their next attempted
login fails.

**Acceptance Scenarios**:

1. **Given** admin auth, **When** the admin POSTs `/api/v3/user`,
   **Then** the user is created and `last_login_at` is NULL until
   they actually log in.
2. **Given** admin auth, **When** they POST
   `/api/v3/user/{id}/reset-password`, **Then** a one-time reset
   token is returned in the response (since email/SMTP is out of
   scope in MVP); the affected user can use the token once to
   choose a new password.
3. **Given** the operator deletes themselves (the lone admin),
   **When** the DELETE runs, **Then** it is rejected with HTTP 409
   reason `cannot_delete_last_admin` to avoid lockout.

---

### Edge Cases

- The chained auth dependency must NOT leak which method failed
  (e.g., a wrong API key MUST get the same 401 response shape as a
  wrong password); error messages refer to "unauthenticated" not
  "invalid api key" so attackers cannot probe.
- An OIDC group claim that has no mapping in
  `ROMARR_OIDC_GROUP_TO_ROLE_MAPPING` ⇒ user is created with the
  default role `user` (configurable); a structured warning is logged.
- An OIDC user logs in for the first time with `AUTO_CREATE = false`
  ⇒ the response is HTTP 403 with reason `oidc_user_not_provisioned`;
  the admin must create the user first.
- A trusted-proxy username matches an existing OIDC user (same
  username but different `oidc_subject`) ⇒ the proxy auth wins for
  this request but a structured warning is logged about the
  collision.
- A user is deactivated (`is_active = false`) while they hold an
  active session ⇒ the next request invalidates the session and
  returns HTTP 401 with reason `user_deactivated`.
- An API key is created with empty scopes ⇒ rejected at validation
  with reason `scopes_required`.
- An API key is created with a scope the owner does not have (e.g.,
  a non-admin user creates a key with `admin` scope) ⇒ rejected
  with reason `scope_not_allowed_for_role`.
- The setup token is leaked (e.g., container logs scraped by a third
  party) AND the user table is empty AND the token has not expired
  ⇒ whoever uses it first becomes admin; mitigation is the 24-hour
  expiry plus the explicit operator workflow.
- Two simultaneous setup attempts arrive within milliseconds ⇒
  serialised by the same `(release_id, sha1)` advisory-lock pattern
  used by the import pipeline; only the first succeeds.
- The session-store backend is Redis but Redis is unavailable at
  request time ⇒ fall back to the database session store; emit an
  `OnHealthIssue` event.
- The OIDC provider's `discovery` endpoint is unreachable at startup
  ⇒ Romarr starts but OIDC login attempts fail with HTTP 503 reason
  `oidc_provider_unreachable`; a periodic re-check restores
  availability automatically.

## Requirements *(mandatory)*

### Functional Requirements

**User entity & RBAC**

- **FR-001**: The system MUST persist a `user` table per
  `data-model.md` with `username` (unique), optional `email`
  (unique when set), `hashed_password` (NULLable for OIDC-only
  users), `is_active`, `role` (text, one of
  `'admin' | 'user' | 'readonly'`, default `'user'`),
  `oidc_subject`, `oidc_provider`, `preferences` JSON, and
  timestamps. The schema MUST NOT carry an `is_superuser` column.
- **FR-002**: The system MUST support three RBAC roles encoded
  on the `role` text column: `admin`, `user` (default for
  non-admin active users), `readonly`. A `User.is_superuser`
  Python property MUST exist as a read-only derivation of
  `self.role == 'admin'` for code-paths that read fastapi-users-
  style boolean checks; it MUST NOT be a persisted column nor
  an UPDATE-able attribute.
- **FR-003**: A higher role MUST imply lower roles: `admin` passes
  every `@require_role('user')` and `@require_role('readonly')`
  guard. The role hierarchy is `admin > user > readonly`.

**Password hashing**

- **FR-004**: Passwords MUST be hashed with bcrypt at cost factor
  12; comparisons MUST be constant-time.

**API keys**

- **FR-005**: Each API key MUST be persisted in `api_key` per
  `data-model.md`. The plaintext key MUST be exposed in the API
  response **exactly once** at creation; subsequent reads MUST
  expose only `key_prefix`.
- **FR-006**: API key validation MUST hash the incoming key with
  BLAKE2b and look it up by indexed `key_hash`; the comparison MUST
  be constant-time.
- **FR-007**: Revoking an API key (DELETE) MUST take effect on the
  very next request.
- **FR-008**: A key may carry `expires_at`; an expired key MUST
  fail authentication with reason `api_key_expired` and MUST NOT be
  silently renewed.
- **FR-009**: A key's `scopes` field MUST be enforced against
  endpoint-required scopes; insufficient scope ⇒ HTTP 403 reason
  `insufficient_scope`.
- **FR-009a**: The scope vocabulary MUST be exactly three values:
  `read`, `write`, `admin`. The `scopes` column on `api_key`
  stores a JSON array whose values are a subset of
  `["read", "write", "admin"]`. The route guard MUST map the
  endpoint's `@require_role` annotation to a required scope as
  follows: `@require_role('readonly')` → `read`,
  `@require_role('user')` → `write`, `@require_role('admin')` →
  `admin`. A request authenticated by an API key MUST pass the
  guard iff the key carries the required scope. Higher scopes
  imply lower ones (an `admin`-only key passes a `read` guard;
  a `write` key passes a `read` guard). Per-resource
  fine-grained scopes (`indexer:read`, etc.) MUST NOT be
  introduced at MVP; the coarse trio is the contract.

**Forms auth & sessions**

- **FR-010**: `POST /api/v3/auth/login` MUST accept
  `{username, password}` and on success set a session cookie with
  `HttpOnly`, `SameSite=Lax`, and `Secure` (when the request
  arrived over HTTPS).
- **FR-010a**: `POST /api/v3/auth/login` MUST be rate-limited to
  **10 attempts per minute per source IP**. Above the threshold,
  the endpoint MUST return HTTP 429 with `Retry-After` set and
  MUST NOT perform the bcrypt comparison (so an attacker cannot
  use the failed attempts to oracle the hash work). The rate
  limit MUST count both successful and failed attempts toward
  the bucket so a legitimate operator's successful login still
  contributes (otherwise an attacker mixes successful and failed
  attempts to bypass). The same cap MUST apply to
  `POST /api/v3/auth/setup` (the bootstrap endpoint) and to
  `GET /auth/oidc/callback` to prevent OIDC code-replay
  amplification. Per-user lockout remains Out of Scope per the
  spec's existing deferral; per-IP rate limit plus bcrypt cost
  12 are the two defense layers at MVP.
- **FR-011**: `POST /api/v3/auth/logout` MUST revoke the
  server-side session record AND clear the cookie.
- **FR-012**: Sessions MUST be stored server-side. Redis is the
  preferred backend; the database is the fallback when Redis is
  unavailable.
- **FR-012a**: Each session record MUST carry `last_used_at` and
  `expires_at` columns. `expires_at` MUST equal
  `last_used_at + 30 days` ("sliding 30-day TTL"). Every
  authenticated request that successfully resolves the session
  MUST update `last_used_at` to "now" and recompute `expires_at`
  in the same write (best-effort, never blocking the request per
  FR-027). A session whose `expires_at` is in the past MUST be
  treated as missing on the next request: HTTP 401 is returned
  and the cookie is cleared. The cookie's `Max-Age` MUST track
  `expires_at − now` so the browser drops it at the same moment
  the server does. No absolute lifetime cap is enforced at MVP;
  operators who need one rotate `ROMARR_AUTH_SECRET_KEY` to
  invalidate every session at once.

**OIDC**

- **FR-013**: `POST /api/v3/auth/oidc/start` MUST return an
  authorization URL with valid `state`, `nonce`, and a PKCE
  challenge.
- **FR-014**: `GET /auth/oidc/callback` MUST exchange the code,
  validate the id_token (issuer, audience, expiry, signature), look
  up the user by `(oidc_provider, oidc_subject)`, and either return
  the existing user or auto-create when `AUTO_CREATE = true`.
- **FR-015**: Group-to-role mapping MUST be applied on every login
  per `ROMARR_OIDC_GROUP_TO_ROLE_MAPPING`; an unmapped group MUST
  default to role `user` and log a warning.
- **FR-016**: Replay of an OIDC code MUST fail with HTTP 400.

**Trusted proxy**

- **FR-017**: When `ROMARR_TRUST_PROXY_AUTH = true`, a configured
  list of trusted headers MUST be honoured (default
  `["X-Authentik-Username", "X-Forwarded-User", "Remote-User"]`);
  when `false`, those headers MUST be ignored.
- **FR-018**: A trusted-proxy username that does not match any
  existing user MUST be auto-created with role `user` (configurable
  default).

**Initial admin bootstrap**

- **FR-019**: On startup with an empty user table, the system MUST
  generate a one-time setup token, persist its hash with a 24-hour
  expiry, and print the plaintext token once to the logs.
- **FR-020**: `POST /api/v3/auth/setup` MUST accept the token via
  the `X-Setup-Token` header and a `{username, password}` body;
  success creates the first admin (`role = 'admin'`) and
  invalidates the token immediately.
- **FR-021**: After the first successful setup, no new setup token
  is generated even if the user table returns to empty.

**Chained authentication dependency**

- **FR-022**: Each protected endpoint MUST resolve the caller via
  the chain (in order): API key in `X-Api-Key` header → API key in
  `apikey` query param → session cookie → trusted-proxy header
  (when enabled). At MVP the chain MUST NOT include a generic
  `Authorization: Bearer JWT` step. The OIDC `id_token` is
  consumed exclusively inside `GET /auth/oidc/callback` (FR-014)
  to establish a session cookie — it MUST NOT be accepted as an
  inbound bearer token on protected endpoints. Romarr MUST NOT
  mint its own JWTs at MVP. Non-browser clients (CLIs, scripts,
  Notifiarr-style integrations) use API keys (FR-005).
- **FR-023**: A failed authentication MUST return HTTP 401 with a
  generic reason; the response body MUST NOT disclose which method
  failed.
- **FR-024**: Successful authentication followed by insufficient
  role MUST return HTTP 403 with reason `permission_denied`.

**Encryption at rest**

- **FR-025**: The OIDC client secret MUST be encrypted at rest
  using the existing Fernet helper from spec 002. The setup-token
  hash MUST be stored using BLAKE2b (constant-time comparison; the
  token never leaves the logs).

**API endpoints**

- **FR-026**: The system MUST expose:
  - `POST /api/v3/auth/login`
  - `POST /api/v3/auth/logout`
  - `GET  /api/v3/auth/me`
  - `PUT  /api/v3/auth/me`
  - `GET  /api/v3/auth/me/preferences`
  - `PUT  /api/v3/auth/me/preferences`
  - `POST /api/v3/auth/oidc/start`
  - `GET  /auth/oidc/callback`
  - `POST /api/v3/auth/setup`
  - `GET/POST /api/v3/auth/api-key`,
    `DELETE /api/v3/auth/api-key/{id}`
  - Admin only: `GET/POST /api/v3/user`, `GET/PUT/DELETE
    /api/v3/user/{id}`, `POST /api/v3/user/{id}/reset-password`,
    `GET /api/v3/auth/api-key?user_id=N`.

**Auditing**

- **FR-027**: Every successful authentication MUST update the
  user's `last_login_at`; every API key use MUST update the key's
  `last_used_at` and `last_used_ip`. These updates MUST be
  best-effort (never block the request).

### Key Entities

- **User**: Owns identity (username, email, optional password
  hash, OIDC subject), `role` (single text column,
  `'admin' | 'user' | 'readonly'`), and per-user preferences.
- **API Key**: A revocable credential keyed by BLAKE2b hash. Owns
  scopes, expiry, prefix-for-display, and audit timestamps.
- **Session**: A server-side record bound to a cookie. Stored in
  Redis (preferred) or the database (fallback). Revocable on
  demand.
- **Setup Token**: A one-shot bootstrap credential. Persisted as a
  hash; valid only when the user table is empty AND the token has
  not expired AND the token has not been consumed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator can complete the initial admin bootstrap
  (capture token from logs → POST `/api/v3/auth/setup` →
  authenticated session) in under 60 seconds.
- **SC-002**: The setup token MUST be invalidated after a single
  successful use; replay returns HTTP 401 in 100% of test cases.
- **SC-003**: Forms-auth login completes in under 200 ms p95
  (excluding bcrypt cost). The session cookie carries
  `HttpOnly + SameSite=Lax + Secure (when HTTPS)` in 100% of
  responses.
- **SC-004**: API key creation returns the plaintext exactly once
  in 100% of test cases; subsequent reads return only the prefix in
  100% of test cases. The plaintext value is never logged.
- **SC-005**: API key revocation is effective within 1 second
  in 100% of test cases (a revoked key fails the very next
  authenticated request).
- **SC-006**: A `readonly` user is rejected (HTTP 403) on every
  endpoint protected by `@require_role('user')` or
  `@require_role('admin')` across a fixture corpus of at least 30
  endpoints; an `admin` user passes 100% of those endpoints.
- **SC-007**: An OIDC round-trip against a respx-mocked Authentik
  completes in under 1 second p95 (excluding the mocked provider's
  own latency); group-to-role mapping is applied correctly in 100%
  of test cases.
- **SC-008**: Failed authentication never discloses which auth
  method was attempted: the response body matches the canonical
  HTTP 401 shape in 100% of test cases.
- **SC-009**: Inspecting the database file shows zero plaintext
  passwords, zero plaintext API keys, zero plaintext OIDC client
  secrets in 100% of test cases.
- **SC-010**: Test coverage on the auth module MUST be at least
  75%.

## Assumptions

These resolve the OPEN CLARIFICATIONS supplied with the input,
applying the operator's proposals.

- **API key default lifetime**: never expires by default; the UI
  exposes an optional `expires_at` field on creation. Operators
  who care about key rotation set their own expiry.
- **Setup token regeneration by an existing admin**: not supported.
  The setup token works only when the user table is empty AND the
  token has not been consumed. For the lone admin's lost password,
  manual database intervention is documented as the MVP recovery
  path; recovery via SMTP is deferred.
- **Trusted-proxy headers default list**:
  `["X-Authentik-Username", "X-Forwarded-User", "Remote-User"]`,
  configurable via `ROMARR_TRUSTED_PROXY_HEADERS` (JSON list).
  Recommended values per reverse proxy are documented in the
  README/quickstart.
- **Sessions storage**: server-side with Redis as preferred backend;
  database fallback when Redis is unavailable. Revocable on
  demand.

Other assumptions:

- The existing `*_by` text columns in earlier specs
  (`import_history.imported_by`, `application.applied_by`,
  `platform_pack.applied_by`, `blocklist.added_by`) become FK
  references to `user.id` once this spec lands. The migration
  performs an in-place column-type change with the existing
  `'system'` strings preserved as a sentinel — see `data-model.md`
  for the migration's data preservation strategy.
- bcrypt cost factor 12 is the documented default; operators
  willing to trade login time for resilience can tune it via
  `ROMARR_BCRYPT_COST`. We do not auto-rehash existing passwords on
  cost change; rehash happens on next login.
- The auth chain runs the cheapest checks first (API key hash
  lookup is O(1)) and the most expensive last (bcrypt password
  verification is the costliest); short-circuiting ensures a
  successful early method skips later ones.

### Out of Scope

- LDAP integration (deferred to v1+).
- 2FA / TOTP on local accounts (deferred).
- Per-library permissions (deferred to v1+).
- Per-game permissions (firm out).
- SAML — operators must use OIDC instead.
- Email-based password reset flow with SMTP (deferred to v1+;
  admin-driven reset is the MVP path).
- Account lockout after N failed attempts (deferred).
