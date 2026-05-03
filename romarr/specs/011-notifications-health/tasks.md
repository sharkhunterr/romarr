---

description: "Granular task list for notifications & health"
---

# Tasks: Notifications & Health

**Input**: Design documents from `specs/011-notifications-health/`
**Prerequisites**: `001-foundation`, `002-metadata-aggregation`, `004-indexers`,
`005-download-clients`, `006-profiles`, `008-import-pipeline`,
`009-library-exporters`, `010-auth-multiuser` shipped.
**Tests**: MANDATORY (Constitution Article XVI; SC-009: ≥ 75% on
notifications/)

**Organization**: 10 phases. Scaffolding → persistence → channel + Apprise
wrapper → webhook target → templates → dispatcher → health engine →
test endpoint → API → hardening.

## Format: `[ID] [P?] [Phase] Description`

- `[P]` = parallelizable with other `[P]` tasks in the same phase.
- Phase tag short codes: `SCAF`, `PERS`, `CHANNEL`, `WEBHOOK`,
  `TEMPLATES`, `DISPATCH`, `HEALTH`, `TESTEP`, `API`, `HARD`.

---

## Phase 1: Scaffolding (`SCAF`)

- [X] T001 [SCAF] ``apprise>=1.7`` already shipped with foundation
      (spec 002 — required by Apprise URL validation in
      provider configs). No version bump needed.
- [X] T002 [P] [SCAF] Create `src/romarr/notifications/__init__.py`
      exposing the slice-1 surface (errors + types). Engine /
      dispatcher / health-loop exports land in their slices.
- [X] T003 [P] [SCAF] Create `src/romarr/notifications/errors.py` —
      `NotificationError`, `AppriseInvalidUrl`, `TemplateError`,
      `WebhookRetryExhausted`, `HealthCheckTimeout`.
- [X] T004 [P] [SCAF] Create `src/romarr/notifications/types.py` —
      `EventType` / `HealthStatus` / `ComponentCategory` enums,
      ``HealthCheckResult`` + ``HealthSnapshot``, ``GameRef`` /
      ``ReleaseRef`` / ``DumpRef`` / ``IndexerRef`` /
      ``DownloadClientRef`` value types, the seven event
      payload models, and the discriminated ``EventPayload``
      union (Pydantic v2 ``Annotated[..., Field(discriminator=
      "event_type")]``). All frozen.
- [X] T005 [SCAF] Extend `tests/conftest.py` to register
      ``romarr.notifications.models``. ``respx_apprise_mock`` and
      ``mock_event_channel`` fixtures land with the CHANNEL +
      DISPATCH slices that need them.

**Checkpoint**: imports work; lint+types green; no behaviour added.

---

## Phase 2: Persistence (`PERS`)

### Tests (write first; must fail)

- [X] T006 [P] [PERS] `tests/notifications/test_models.py::test_notification_round_trip`
      and ``test_health_check_round_trip`` — round-trip both
      tables; CHECK constraints on ``last_status`` and
      ``health_check.status`` reject unknown values.
- [X] T007 [P] [PERS] `tests/notifications/test_models.py::test_notification_unique_name`
      — duplicate ``name`` raises ``IntegrityError``.
- [X] T008 [P] [PERS] `tests/notifications/test_models.py::test_health_check_unique_component`
      — duplicate ``component`` raises.
- [X] T009 [P] [PERS] `tests/notifications/test_models.py::test_notification_create_requires_at_least_one_event`
      — ``NotificationCreate`` rejects all-False ``on_*`` (FR-005);
      ``test_notification_create_with_one_flag_succeeds`` covers
      the symmetric pass.
- [ ] T010 [P] [PERS] `tests/notifications/test_models.py::test_template_validates_at_save`
      — ``on_import_format`` referencing an unknown variable
      rejected at save time (re-uses spec 006's renderer).
      *(Deferred — spec 006's renderer integration lands with
      the TEMPLATES slice; today templates persist as opaque
      strings and the dispatcher will validate at render time.)*
- [X] T011 [P] [PERS] `tests/notifications/test_migration_0011.py`
      — 2 tests: ``test_migration_creates_both_tables`` (every
      documented column + UNIQUE constraints) and
      ``test_migration_is_reversible`` (downgrade to
      ``0008_import_pipeline`` drops both tables).

### Implementation

- [X] T012 [PERS] Create `src/romarr/notifications/models.py` —
      ``Notification`` and ``HealthCheck`` SQLAlchemy 2.0 models.
      ``health_check`` carries the persisted debouncer columns
      (``last_emitted_state``, ``last_emitted_at``) per Q2 so a
      flapping-then-restarted Romarr doesn't re-spam the
      operator.
- [X] T013 [P] [PERS] Create `src/romarr/notifications/schemas.py`
      — ``NotificationCreate / Update / Read``,
      ``HealthCheckRead``, ``TestNotificationResponse``,
      ``HealthSnapshotResponse``. ``NotificationRead`` masks
      ``apprise_url_encrypted`` into
      ``apprise_url_redacted: '<scheme>://...'`` via the
      ``from_orm_row`` helper (no encryption decoded on read
      paths). The ``at-least-one-event`` cross-field validator
      runs in ``_NotificationBase`` so both Create and Read
      enforce it.
- [X] T014 [PERS] Author `src/romarr/db/alembic/versions/0011_notifications.py`
      — DDL for both tables. ``down_revision='0008_import_pipeline'``
      so the migration sits at the tail of the chain. Reversible
      downgrade.

**Checkpoint**: `alembic upgrade head` clean; PERS tests green.

---

## Phase 3: Channel + Apprise Wrapper (`CHANNEL`)

### Tests

- [X] T015 [P] [CHANNEL] `tests/notifications/test_channel.py::test_back_pressure_drops_oldest_when_full`
      — fill the queue without consumers, publish 6 with
      max_buffer=5, assert oldest dropped and dropped_count
      incremented (FR-026, SC-008). Plus
      ``test_dropped_count_per_notification`` proving the
      counter is per-notification — a slow consumer doesn't lose
      events for a fast one.
- [X] T016 [P] [CHANNEL] `tests/notifications/test_channel.py::test_serial_per_notification`
      — within one notification, callbacks run one at a time
      (timeline assertion: enter-0/exit-0/enter-1/exit-1/...).
      Plus ``test_parallel_across_notifications`` (asyncio.Event
      handshake that would deadlock if dispatch were globally
      serial) and ``test_subscriber_failure_recorded_and_dispatch_continues``
      (a flaky callback doesn't poison the channel).
- [X] T017 [P] [CHANNEL] `tests/notifications/test_apprise_wrapper.py::test_happy_path_returns_success`
      — parametrised over 5 services (Discord, Telegram, ntfys,
      Slack, Gotify) with apprise.notify mocked to True; each
      returns ``AppriseSendResult(success=True)``.
- [X] T018 [P] [CHANNEL] `tests/notifications/test_apprise_wrapper.py::test_invalid_apprise_url_raises`
      — Apprise rejects the URL ⇒ wrapper raises
      ``AppriseInvalidUrl`` carrying the scheme prefix only
      (FR-004). Plus ``test_apprise_returns_false_surfaces_error``,
      ``test_apprise_raises_surfaces_error``, and
      ``test_url_decrypted_per_call`` (Fernet plaintext doesn't
      live in memory between dispatches).

### Implementation

- [X] T019 [CHANNEL] Create `src/romarr/notifications/channel.py`
      — ``EventChannel`` with per-notification ``asyncio.Queue``
      (default 10 000-event cap), overflow-drops-oldest +
      dropped_count per notification, serial-per-notification
      dispatch via one task per subscriber, per-subscriber
      ``last_error`` recording. ``publish`` yields via
      ``await asyncio.sleep(0)`` so a tight publish loop doesn't
      starve dispatcher tasks. ``drain`` uses ``Queue.join()``
      to wait for in-flight callbacks too, not just empty
      queues.
- [X] T020 [CHANNEL] Create `src/romarr/notifications/apprise_wrapper.py`
      — async ``send(*, notification, title, body, notify_type)
      -> AppriseSendResult``. Decrypts the Fernet-wrapped URL on
      every call (no plaintext in memory between dispatches);
      validates via ``Apprise.add`` (False ⇒
      ``AppriseInvalidUrl``); ``apobj.notify`` runs in a
      threadpool. Failure paths surface as
      ``AppriseSendResult(success=False, error_message=...)`` so
      the dispatcher can record the audit row and keep draining;
      only validation-time misuse raises.

**Checkpoint**: channel back-pressure works; Apprise wrapper
delivers 5 services in mock tests.

---

## Phase 4: Webhook Target (Sonarr/Radarr-compat) (`WEBHOOK`)

### Tests

- [X] T021 [P] [WEBHOOK] `tests/notifications/test_webhook_sonarr_compat.py::test_grab_payload_matches_fixture`
      — fixture `sonarr_webhook_fixtures/grab_payload.json`;
      build payload from our `OnGrabPayload`; assert byte-for-byte
      match modulo optional-field order (SC-003).
- [X] T022 [P] [WEBHOOK] `tests/notifications/test_webhook_sonarr_compat.py::test_download_payload_matches_fixture`
      — same shape for `OnImport` (Sonarr calls it `Download`).
- [X] T023 [P] [WEBHOOK] `tests/notifications/test_webhook_sonarr_compat.py::test_isupgrade_flag`
      — payload from `OnUpgradePayload`; `isUpgrade = true`.
- [X] T024 [P] [WEBHOOK] `tests/notifications/test_webhook_retry.py::test_503_retries_with_backoff`
      — respx-mocked 503; assert 3 attempts at 1 s / 5 s / 30 s
      via captured-sleep recorder (no freezegun needed — we
      monkeypatch `asyncio.sleep` so the schedule is observed
      symbolically rather than via wall clock).
- [X] T025 [P] [WEBHOOK] `tests/notifications/test_webhook_retry.py::test_after_three_failures_marks_failed`
      — final failure: `WebhookRetryExhausted` carries the
      structured 503 message; the dispatcher will record it on
      `last_status = "failed"` / `last_error` (audit columns
      already present per slice 1).
- [X] T026 [P] [WEBHOOK] `tests/notifications/test_webhook_retry.py::test_immediate_success_no_backoff`
      — first attempt succeeds; no backoff inserted.

### Implementation

- [X] T027 [WEBHOOK] Create `src/romarr/notifications/webhook.py` —
      async `send_webhook(notification, target_url, payload_dict)`
      using httpx with tenacity retry (3 attempts, 1 s / 5 s /
      30 s backoff; 30 s slot is documented but unreached because
      we stop after the 3rd attempt). Returns
      `WebhookSendResult`; raises `WebhookRetryExhausted` when
      all 3 attempts fail on 5xx / connection errors.
- [X] T028 [WEBHOOK] Create
      `src/romarr/notifications/templates/payload_builders.py` —
      pure functions
      `build_apprise_message(payload, notification) -> str` and
      `build_sonarr_webhook_body(payload, notification) -> dict`
      that map an `EventPayload` to a Sonarr-shaped JSON body.
      Per FR-006a, the Sonarr remap is documented in
      `docs/api/notification/webhook-payloads.md`; empty fields
      emit as `0` / `""` rather than being omitted.

**Checkpoint**: WEBHOOK tests green; the Sonarr fixtures match
byte-for-byte.

---

## Phase 5: Templates (`TEMPLATES`)

### Tests

- [X] T029 [P] [TEMPLATES] `tests/notifications/templates/test_defaults.py::test_all_seven_render`
      — render each of the seven default templates against fixture
      `EventPayload`s; assert the documented expected strings.
- [X] T030 [P] [TEMPLATES] `tests/notifications/templates/test_renderer.py::test_uses_spec_006_sandbox`
      — confirm the renderer imports
      `romarr.profiles.naming.engine.NamingTemplateEngine`-style
      sandbox primitives; static-analysis-style assertion.
- [X] T031 [P] [TEMPLATES] `tests/notifications/templates/test_unknown_variable.py::test_corpus_of_10_bad_templates`
      — at least 10 templates from
      `tests/fixtures/notifications/bad_templates/`; each is
      rejected at save with the documented structured error
      (SC-007).
- [X] T032 [P] [TEMPLATES] `tests/notifications/templates/test_payload_builders.py::test_apprise_vs_webhook_differ`
      — same `OnImportPayload` produces a string for Apprise and
      a dict for Sonarr-webhook; the dict matches the fixture.
      *(Picked up alongside T027/T028 in the WEBHOOK slice.)*

### Implementation

- [X] T033 [TEMPLATES] Create
      `src/romarr/notifications/templates/defaults.py` — Python
      strings for the 7 default templates (verbatim from
      `data-model.md`).
- [X] T034 [TEMPLATES] Create
      `src/romarr/notifications/templates/renderer.py` —
      `render_event(notification, payload) -> str` consulting
      `notification.<event>_format` first, falling back to the
      default. Uses spec 006's sandbox.

**Checkpoint**: TEMPLATES tests green; the bad-template corpus is
all rejected.

---

## Phase 6: Dispatcher (`DISPATCH`)

### Tests

- [X] T035 [P] [DISPATCH] `tests/notifications/test_dispatcher.py::test_event_flag_filter_blocks_unsubscribed`
      — notification with `on_import = true`, `on_grab = false`;
      OnGrab event ⇒ NOT delivered; OnImport ⇒ delivered.
- [X] T036 [P] [DISPATCH] `tests/notifications/test_dispatcher.py::test_tag_filter_intersection_match`
      / `test_tag_filter_no_intersection_skips`
      / `test_tag_filter_empty_game_tags_skips` —
      notification with `tags = ["family-friendly"]`;
      Game tags `["family-friendly", "platformer"]` ⇒ delivered;
      non-overlapping or empty Game tags ⇒ NOT delivered (FR-014).
- [X] T037 [P] [DISPATCH] `tests/notifications/test_dispatcher.py::test_empty_tags_match_all`
      — notification with `tags = []`; every event ⇒ delivered
      (FR-015).
- [X] T038 [P] [DISPATCH] `tests/notifications/test_dispatcher.py::test_disabled_notification_never_delivers`
      — notification with `enabled = false` ⇒ never delivered.
- [X] T039 [P] [DISPATCH] `tests/notifications/test_dispatcher.py::test_upgrade_fires_both_events`
      — `OnUpgrade` is emitted alongside `OnImport` for an upgrade;
      a notification subscribed to both flags receives **two**
      messages (US8.1).
- [X] T040 [P] [DISPATCH] `tests/notifications/test_dispatcher.py::test_records_last_status_on_success`
      / `test_records_last_status_on_failure` /
      `test_apprise_exception_recorded_as_failure` — successful
      delivery sets `last_status = "success"`; failure (returned
      OR raised) sets `"failed"` with `last_error` populated.

### Implementation

- [X] T041 [DISPATCH] Create `src/romarr/notifications/dispatcher.py`
      — pure-function `dispatch_to_notification(*, notification,
      event, send_apprise, send_webhook) -> DispatchOutcome`:
      1. enabled / event-flag / health-severity / tag-intersection
         filters (in order);
      2. render via the appropriate builder
         (`build_apprise_message` for Apprise schemes,
         `build_sonarr_webhook_body` for `json`/`jsons`);
      3. call the right transport (Apprise vs httpx webhook);
      4. update `last_used_at`, `last_status`, `last_error` on
         the ORM row in place; caller commits.
      The transport callables are injected so tests can stub
      them without HTTP. The `EventChannel` from slice 2 supplies
      the per-notification fan-out / serialization.

**Checkpoint**: dispatcher tests green; tag and event filtering
work; double-event for upgrades works.

---

## Phase 7: Health Engine (`HEALTH`)

### Tests

- [X] T042 [P] [HEALTH] `tests/notifications/health/test_engine.py::test_runs_all_categories`
      — populate the DB with one indexer, one download client,
      one library; run `HealthEngine.refresh()`; assert per-
      category results recorded in `health_check`. Plus
      ``test_second_cycle_with_no_change_emits_nothing`` and
      ``test_recovery_emits_exactly_one_recovered_event`` for
      FR-021a coverage.
- [X] T043 [P] [HEALTH] ``IndexerHealthCheck`` shipped at
      ``src/romarr/notifications/health/checks/indexer.py``
      (slice 186) — wraps a ``NewznabClient`` factory, calls
      ``client.caps()``, maps reachable→ok / probe-failure→
      warning / construction-failure→error. Always closes
      the client (best-effort). Tests at
      ``tests/notifications/health/checks/test_indexer.py``
      cover all three branches.
- [X] T044 [P] [HEALTH] ``DownloadClientHealthCheck`` shipped
      at
      ``src/romarr/notifications/health/checks/download_client.py``
      (slice 186) — wraps spec 005's ``test_connection()``
      adapter. ok message includes the version string the
      adapter returns; warning carries the connection-test
      exception class + message; error fires on construction
      failure. Tests at
      ``tests/notifications/health/checks/test_download_client.py``.
- [X] T045 [P] [HEALTH] `tests/notifications/health/checks/test_dat_freshness.py`
      — DAT 31 days old → `warning`; 91 days old → `error`;
      29 days old → `ok`; exact 30-day boundary → `warning`
      (FR-019).
- [X] T046 [P] [HEALTH] `tests/notifications/health/checks/test_disk_space.py`
      — `free = min × 1.2` → `warning`; `free = min × 0.5` →
      `error`; `free = min × 2` → `ok`; `free = min` exactly →
      `warning` (FR-020 boundary).
- [X] T047 [P] [HEALTH] `tests/notifications/health/checks/test_db.py`
      — fast round-trip → `ok`; slow round-trip (sleep 100 ms,
      threshold 50 ms) → `warning`; query exception propagates
      to the engine's ``run_check`` wrapper for error-mapping.
- [X] T048 [P] [HEALTH] ``MetadataProviderHealthCheck`` shipped
      at
      ``src/romarr/notifications/health/checks/metadata_provider.py``
      (slice 186) — wraps a ``MetadataProvider``'s
      ``health_check()`` method (every provider in
      ``src/romarr/metadata/providers/`` already implements
      it, no spec 002 follow-up needed). Tests at
      ``tests/notifications/health/checks/test_metadata_provider.py``
      cover ok / warning (provider returns False) / error
      (provider raises) branches.

      Original deferral note (preserved for context): *(was
      deferred — needs spec 002's per-provider `health_check()`
      hook, which is itself deferred to a metadata follow-up)*
- [X] T049 [P] [HEALTH] `tests/notifications/health/checks/test_library_path.py`
      — stat takes 200 ms (real `asyncio.sleep`), timeout 50 ms
      → `error` with reason `timeout`. Missing path →
      `FileNotFoundError`. Existing path → `ok`.
- [X] T050 [P] [HEALTH] `tests/notifications/health/test_debouncer.py::test_emit_only_on_transition`
      — same component, 10 cycles all `error` ⇒ exactly **one**
      transition emitted (SC-004).
- [X] T051 [P] [HEALTH] `tests/notifications/health/test_debouncer.py::test_recovery_emits_recovered_severity`
      — `error → ok` transition emits exactly one transition
      with `severity = 'recovered'` (FR-022); same for
      `warning → ok`.
- [X] T052 [P] [HEALTH] `tests/notifications/health/test_debouncer.py::test_warning_to_error_emits_error`
      — escalation transitions emit one event per transition;
      de-escalation `error → warning` also emits (FR-021).
- [X] T053 [P] [HEALTH] `tests/notifications/health/test_snapshot.py::test_overall_status_is_worst_component`
      — one `error` + several `ok`/`warning` ⇒ snapshot's
      `overall_status = "error"`. Plus per-category grouping +
      empty-result handling.

### Implementation

- [X] T054 [HEALTH] Create
      `src/romarr/notifications/health/checks/__init__.py` +
      `base.py` (Protocol + `run_check` runner with timeout-→
      `warning` and exception-→ `error` mapping) and the four
      always-available checks: `db.py`, `dat_freshness.py`,
      `disk_space.py`, `library_path.py`. The remaining three
      categories (indexer, download_client, metadata_provider)
      are deferred to a follow-up slice — they require the
      respective modules' client adapters which are
      cross-module wiring concerns rather than core engine work.
- [X] T055 [HEALTH] Create `src/romarr/notifications/health/debouncer.py`
      — pure `compute_transitions(*, previous, current) ->
      list[Transition]` + `should_emit(transition) -> bool`.
      The state-machine table in the docstring covers all 12
      `(previous, current)` combinations; `None` previous
      (never-emitted) suppresses emission only when current is
      `ok`.
- [X] T056 [HEALTH] Create `src/romarr/notifications/health/engine.py`
      — `HealthEngine.refresh() -> HealthSnapshot` runs all
      checks concurrently with per-check timeout, reads the
      persisted `last_emitted_state` map (FR-021a), computes
      transitions, persists results + transition states in one
      transaction, then fires `OnHealthIssue` events via an
      injected `emit` callable. The engine is stateless across
      cycles (state lives in `health_check`).
- [X] T057 [HEALTH] Periodic ``HealthEngine.refresh()`` cron
      shipped (slice 190). New module at
      ``src/romarr/notifications/health/builder.py`` exposes
      ``build_health_engine(sessionmaker)`` which assembles a
      production engine with: DB ``SELECT 1`` check, metadata
      cache size check, one library-path + disk-space check
      per Library row, one DAT-freshness check per
      ``(source, platform_id)`` pair, one indexer check per
      Indexer, one download-client check per DownloadClient,
      one metadata-provider check per enabled provider.
      Construction is best-effort — a row that fails to build
      its check (decryption failed, bad path, etc.) is logged
      and skipped, and an empty config still yields a working
      engine with the always-on infra checks.
      ``runner_protocol.build_default_registry`` now accepts
      an optional ``health_engine`` and threads it into
      ``HealthCheckAdapter``; the lifespan calls
      ``build_health_engine`` when both ``bootstrap_enabled``
      and ``scheduler_enabled`` are True, stashes the result
      on ``app.state.health_engine``, and passes it to the
      registry. Tests at
      ``tests/notifications/health/test_builder.py`` cover
      empty config, library wiring, indexer wiring, and a
      live ``refresh()`` round-trip against an in-memory
      engine.

**Checkpoint**: HEALTH tests green; debouncing prevents the spam
edge case from US5; the snapshot endpoint reports the right
overall status.

---

## Phase 8: Test Endpoint (`TESTEP`)

### Tests

- [X] T058 [P] [TESTEP] `tests/notifications/api/test_notification_endpoints.py::test_test_endpoint_flows_through_dispatcher`
      — POST `/api/v3/notification/{id}/test`; the dispatcher
      receives a synthetic `OnImportPayload` with placeholder
      data ("Test Game", "Test Release"); the configured Apprise
      URL (mocked via `apprise.notify`) receives it.
- [X] T059 [P] [TESTEP] `tests/notifications/api/test_notification_endpoints.py::test_test_endpoint_returns_structured_error`
      — Apprise transport raises `ConnectionError`; the response
      carries `success=false` and a structured error message.
      Plus `test_test_endpoint_requires_admin` for FR-024b.

### Implementation

- [X] T060 [TESTEP] Implement the synthetic-event helper in
      `src/romarr/notifications/dispatcher.py::trigger_test(notification)`
      and route it from `src/romarr/notifications/api/notifications.py::test_notification`.
      The synthetic event bypasses the filter chain (FR-016 —
      "send one regardless of subscription state").

**Checkpoint**: test endpoint works for at least Discord and ntfy
(mock-tested).

---

## Phase 9: API (`API`)

### Tests

- [X] T061 [P] [API] `tests/notifications/api/test_notification_endpoints.py::test_full_crud_round_trip`
      — POST/GET/PUT/DELETE round-trip on
      `/api/v3/notification`. GET responses never expose the
      plaintext Apprise URL (FR-024).
- [X] T062 [P] [API] `tests/notifications/api/test_notification_endpoints.py::test_get_returns_redacted_url`
      — response includes `apprise_url_redacted = "<scheme>://..."`
      and never the full URL.
- [X] T063 [P] [API] `tests/notifications/api/test_notification_endpoints.py::test_invalid_apprise_url_returns_400`
      — POST with a bad URL ⇒ HTTP 400 with the underlying
      Apprise message (FR-004). Plus
      `test_bad_template_rejected_at_save` for FR-013.
- [X] T064 [P] [API] `tests/notifications/api/test_health_endpoint.py::test_unauthenticated_health_returns_status_only`
      — GET `/api/v3/health` without auth ⇒ HTTP 200 with only
      `{status: "ok"|"warning"|"error"}` (FR-024a). Plus
      `test_unauthenticated_empty_db_returns_ok` for the fresh-
      DB edge case.
- [X] T065 [P] [API] `tests/notifications/api/test_health_endpoint.py::test_admin_sees_full_breakdown`
      — same endpoint with admin auth ⇒ full structured `message`
      fields + `by_category` breakdown visible. Plus
      `test_readonly_user_also_sees_full_breakdown` for the
      FR-024a clarification (any auth role, not admin only).
- [X] T066 [P] [API] `tests/notifications/api/test_health_refresh_admin_only.py`
      — `POST /api/v3/health/refresh`: admin → 200 (falls back
      to persisted snapshot when no engine wired); user → 403;
      readonly → 403; unauthenticated → 401.
- [X] T067 [P] [API] `tests/notifications/api/test_webhook_payloads_doc.py`
      — `GET /api/v3/notification/webhook-payloads.md` returns
      the documented schemas as `text/markdown`; reference
      keys (`series.title`, `tvdbId`, `FR-006a`) present.

### Implementation

- [X] T068 [API] Create `src/romarr/notifications/api/notifications.py`
      — FastAPI router for `/api/v3/notification*` and
      `/api/v3/notification/{id}/test`. Mutating endpoints +
      `/test` admin-gated (FR-024b); reads accessible to any
      authenticated user.
- [X] T069 [P] [API] Create
      `src/romarr/notifications/api/health.py` — `GET
      /api/v3/health` tiered (anonymous → status only, any auth
      role → full breakdown, FR-024a) and `POST /api/v3/health/refresh`
      admin-only (FR-024b).
- [X] T070 [P] [API] Create
      `src/romarr/notifications/api/webhook_payloads_md.py`
      — serves the FR-006a cross-walk doc from
      `docs/api/notification/webhook-payloads.md` as
      `text/markdown` (lru_cached at module scope; the doc
      ships with the binary).
- [X] T071 [API] Wire all three routers into the application
      factory (`src/romarr/api/app.py`). The webhook-payloads
      router is mounted before the CRUD router so the
      `/webhook-payloads.md` path doesn't get pattern-matched
      as a `{notification_id}` integer.

**Checkpoint**: API tests green; the unauthenticated health
endpoint redacts; the refresh endpoint is admin-only.

---

## Phase 10: Hardening (`HARD`)

- [X] T072 [HARD] Run `pytest --cov=romarr.notifications` —
      **achieved 90.2% coverage** on the notifications module
      (SC-009 floor: 75%). 1023 of 1134 statements covered;
      uncovered branches are mostly defensive error paths (a
      few unreachable-by-design branches in the dispatcher's
      transport-exception handler and the snapshot's empty-DB
      fallback) plus the four lifespan-wired API methods that
      the next slice's wiring exercises end-to-end.
- [X] T073 [HARD] `ruff check src/romarr/notifications/`:
      zero warnings.
- [X] T074 [HARD] `tests/notifications/test_article_xiv_gate.py`
      — static scan asserting that only `apprise` (+ `httpx`
      for the webhook target's generic HTTP transport, +
      `tenacity` for retry, + project-internals) appears under
      `src/romarr/notifications/`. Forbidden patterns:
      `discord` / `discord_py` / `discord.py`, `telegram`,
      `python_telegram_bot`, `slack_sdk`, `slack`, `requests`,
      `pushover`, `gotify`, `ntfy`. The gate also confirms
      that `import apprise` IS present so the test isn't
      vacuous.
- [X] T075 [HARD] Performance budget characterisation in
      `specs/011-notifications-health/research.md`. The
      dispatcher's per-(notification, event) pure-function
      design + the channel's bounded buffers + the engine's
      concurrent check execution (with per-check timeouts)
      structurally bound the budgets the spec calls out;
      end-to-end measurement deferred to v1+.
- [X] T076 [HARD] `pyproject.toml::version = "0.11.0a1"` +
      `src/romarr/__init__.py::__version__` synced + CHANGELOG
      entry summarising the spec 011 surface (notifications +
      Sonarr webhooks + tiered health endpoint + Apprise
      plugin-loading hardening + four built-in health checks).
- [X] T077 [HARD] FR sweep — every FR-001 → FR-027 traces to
      a task ID:
      * **FR-001 / FR-001a** (Apprise as unified transport,
        plugin loading hardening) → CL007 + apprise_init.py +
        Article XIV gate test + test_apprise_plugins_off.py.
      * **FR-002 / FR-003** (notification persistence + Fernet
        encryption) → SCAF + PERS slice (T005-T013).
      * **FR-004** (invalid Apprise URL → 400) → API slice
        (`test_invalid_apprise_url_returns_400`).
      * **FR-005** (at least one event flag) → schemas.py
        validator + `test_at_least_one_event_required`.
      * **FR-006 / FR-006a / FR-007** (Sonarr v3-shape
        webhooks + retry) → WEBHOOK slice (T021-T028) +
        `docs/api/notification/webhook-payloads.md`.
      * **FR-008** (seven event types on in-process channel) →
        types.py + channel.py + dispatcher.py.
      * **FR-009** (OnImport + OnUpgrade for upgrades) →
        `test_upgrade_fires_both_events`. The upstream emit
        is the importer's responsibility (spec 008 FR);
        spec 011 asserts the dispatcher routes both.
      * **FR-010** (event payloads as Pydantic models) →
        types.py.
      * **FR-011 / FR-012 / FR-013** (default templates,
        sandboxed engine, save-time validation) →
        TEMPLATES slice (T029-T034).
      * **FR-014 / FR-015** (tag intersection / empty matches
        all) → DISPATCH slice (T036-T037).
      * **FR-016** (test endpoint flows through real
        dispatcher) → TESTEP slice (T058-T060).
      * **FR-017 / FR-018 / FR-019 / FR-020** (health engine,
        persisted state, DAT freshness, disk thresholds) →
        HEALTH slice. **FR-018 partial**: the `health_check`
        table also persists `last_emitted_state` per FR-021a.
      * **FR-021 / FR-021a / FR-022** (debouncer, persisted
        last_emitted_state, recovered severity) → debouncer.py
        + engine.py.
      * **FR-023** (CRUD + test + schema endpoints) → API
        slice (T068-T071).
      * **FR-024 / FR-024a / FR-024b** (URL redaction, tiered
        health, admin-only mutations) → API slice
        (`test_get_returns_redacted_url`,
        `test_unauthenticated_health_returns_status_only`,
        `test_admin_sees_full_breakdown`,
        `test_create_requires_admin`).
      * **FR-025** (audit columns updated post-dispatch) →
        dispatcher's `_send_and_record`.
      * **FR-026 / FR-027** (queue cap + serial-per-
        notification fan-out) → channel.py + corresponding
        tests.
      Gaps recorded as deferred follow-ups (NOT FR drift):
      * T043 / T044 / T048 — cross-module health checks
        (indexer, download client, metadata provider) —
        unblocked once each spec's client adapter exposes a
        health-probe hook. The base Protocol +
        `run_check` runner are ready to receive them.
      * T057 — periodic refresh wiring lives in spec 012's
        Tasks scheduler. `HealthEngine.refresh()` is callable
        directly from the API endpoint until then.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (SCAF)**: prerequisite specs merged.
- **Phase 2 (PERS)**: depends on Phase 1.
- **Phase 3 (CHANNEL)**: depends on Phase 2.
- **Phase 4 (WEBHOOK)**: depends on Phase 2; can run in parallel
  with Phase 3.
- **Phase 5 (TEMPLATES)**: depends on Phase 1 + spec 006's
  renderer; can run in parallel with Phases 3 + 4.
- **Phase 6 (DISPATCH)**: depends on Phases 3, 4, 5.
- **Phase 7 (HEALTH)**: depends on Phase 2 + spec 008's event
  channel + spec 005's connection helpers + spec 002's provider
  health helpers. Can run in parallel with Phase 6.
- **Phase 8 (TESTEP)**: depends on Phase 6.
- **Phase 9 (API)**: depends on Phases 7 and 8.
- **Phase 10 (HARD)**: depends on Phase 9.

### Within-Phase Parallelism

- Phase 1: T002–T004 in parallel.
- Phase 2: T006–T011 in parallel; T012 + T013 in parallel.
- Phase 3: T015–T018 in parallel; T019 + T020 in parallel.
- Phase 4: T021–T026 in parallel; T027 + T028 in parallel.
- Phase 5: T029–T032 in parallel; T033 + T034 in parallel.
- Phase 6: T035–T040 in parallel.
- Phase 7: T042–T053 in parallel; T054 in parallel; T055 + T056
  sequential at the end.
- Phase 8: T058 + T059 in parallel.
- Phase 9: T061–T067 in parallel; T068–T070 in parallel.

### Critical Path

`SCAF → PERS → (CHANNEL || TEMPLATES) → DISPATCH → API → HARD`.
Health and Webhook phases run in parallel with Dispatch.

### Implementation Strategy

- **Day 1**: Phase 1 (SCAF) + Phase 2 (PERS) + start Phase 5
  (TEMPLATES — pure functions).
- **Day 2**: Phase 3 (CHANNEL) + Phase 4 (WEBHOOK) in parallel.
- **Day 3**: Phase 5 finish + Phase 6 (DISPATCH).
- **Day 4**: Phase 7 (HEALTH) — most diverse code, the seven
  per-component checks.
- **Day 5**: Phase 8 (TESTEP) + Phase 9 (API).
- **Day 6**: Phase 10 (HARD).

This sizing assumes one developer working full-time. With two,
WEBHOOK + CHANNEL split cleanly across them on Day 2.

---

## Notes

- `[P]` tasks change different files only.
- Tests are written BEFORE implementation in every phase.
- Stop at any phase checkpoint — notifications & health are
  delivered incrementally; each phase is independently shippable.
- Avoid: writing UI for notification config (UI spec); building a
  custom rule engine (deferred to v1+); batching/digests (v1+);
  Web Push to PWA (UI spec); SMTP integration beyond Apprise (firm
  out — Article XIV); throttling per-channel (Apprise handles this).
- Constitutional invariants under test:
  - **Article XIV (Notifications)** — single Apprise backend; T074
    statically asserts no other transport library in
    `notifications/`. Sonarr-format webhook payloads validated
    byte-for-byte against captured fixtures (T021-T023, SC-003).
  - **Article XVII (Idempotency & Safety)** — debounced health
    emission (T050-T052, SC-004); encrypted Apprise URLs (T062 +
    SC-006); webhook retries bounded (T024-T025, SC-002).
  - **Article XVI (Quality Gates)** — ≥ 75% coverage (T072); 5 s
    p95 delivery (SC-001); 200 ms p95 cached health (SC-005).
  - **Article XI (Naming Discipline) — sandbox carry-over** —
    template engine re-uses spec 006's primitives; no second sandbox
    implementation (T030).

## Phase: Clarification Tasks (Session 2026-04-29)

- [X] CL001 [P] [US4] Implement tiered `GET /api/v3/health` response in `src/romarr/notifications/api/health.py` — public callers receive ONLY `{status: "ok" | "warning" | "error"}` + HTTP 200; authenticated callers (any role) receive the full per-component breakdown with messages (FR-024a)
- [X] CL002 Migration `0011_notifications.py` adds
      `health_check.last_emitted_state VARCHAR(16) NULL CHECK
      (last_emitted_state IS NULL OR last_emitted_state IN
      ('ok','warning','error'))` — shipped (verified at
      lines 142 + 158-160). Constraint name
      `ck_health_check_last_emitted_state`. The model side
      (`notifications/models.py` lines 38-39, 147, 159)
      mirrors the same constraint. (FR-018 amended)
- [X] CL003 [P] [US5] Implement transition comparison against persisted `last_emitted_state` in `src/romarr/notifications/health/engine.py` — every cycle (including first post-restart) compares new check status to persisted column; updates column in same transaction as emission. NULL → emit only on non-`ok` first cycle. Restarts invisible to subscribers (FR-021a). Verified via `test_second_cycle_with_no_change_emits_nothing` + `test_recovery_emits_exactly_one_recovered_event`.
- [X] CL004 [P] Implement Sonarr v3 envelope semantic remap in `src/romarr/notifications/templates/payload_builders.py` — `series.title ← game.title`; `series.tvdbId ← game.igdb_id || 0`; `series.path ← ""` (library context not yet plumbed through payloads — emits empty string per FR-006a invariant); `episodes[]` always one element representing the Release; `release.quality.quality.name ← release.naming_convention` (closest Romarr analogue to Sonarr "quality"); `release.indexer ← indexer.name`; empty fields emit as `0` / `""` never omitted (FR-006a)
- [X] CL005 [P] Document the full field-by-field cross-walk at `docs/api/notification/webhook-payloads.md`
- [X] CL006 [P] [Admin] Wire admin-role gate on every mutating notification endpoint AND on `POST /notification/{id}/test` (SSRF surface — fires outbound HTTP) in `src/romarr/notifications/api/notifications.py` (FR-024b). Verified via `test_create_requires_admin` / `test_test_endpoint_requires_admin`.
- [X] CL007 [P] Initialize Apprise with custom-plugin loading **disabled** in `src/romarr/notifications/apprise_init.py` — reads `ROMARR_APPRISE_ALLOW_CUSTOM_PLUGINS` env var (default `false`, case-insensitive); skips `data/apprise-plugins/` discovery when off (FR-001a). Threaded into `apprise_wrapper._validate_url` via `build_apprise_asset()` so every wrapper-built `Apprise` instance honors the flag.
- [X] CL008 [P] `ROMARR_APPRISE_ALLOW_CUSTOM_PLUGINS` flag documented in `specs/011-notifications-health/research.md` with the code-execution-surface warning. README/quickstart updates land with the spec 015 frontend slice (which adds the operator-facing settings UI).
- [X] CL009 [P] Add tests in `tests/notifications/api/test_health_endpoint.py` covering: unauthenticated request → only `{status}` returned; authenticated request → full breakdown with messages
- [X] CL010 [P] Add tests in `tests/notifications/health/test_engine.py` + `test_debouncer.py` covering: failing component → emit once; component still failing → no further emissions across 10 cycles. Restart-safety is structurally guaranteed by reading `last_emitted_state` from the DB row at the start of each cycle (FR-021a) — no in-memory state to cross a restart boundary.
- [X] CL011 [P] Tests in `tests/notifications/test_webhook_sonarr_compat.py` covering: OnImport on Sonic / Mega Drive → series.title="Sonic the Hedgehog", series.tvdbId=igdb_id, episodes[0] populated; missing fields → 0/""; schema validates against fixtures `sonarr_webhook_fixtures/grab_payload.json` + `download_payload.json`
- [X] CL012 [P] Tests in `tests/notifications/test_apprise_plugins_off.py` covering: env unset → custom plugins NOT loaded; env=true → custom plugins loaded; case-insensitive flag handling; every non-`true` value (false / FALSE / 0 / no / off / "") keeps plugins off; built-in providers still work with the hardened asset.
