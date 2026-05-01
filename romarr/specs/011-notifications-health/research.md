# Research notes — spec 011 (Notifications & Health)

## Performance characterisation (T075)

The performance budget the spec calls out:

- Dispatcher throughput ≥ 100 events/sec sustained per notification
  (channel + apprise wrapper combined, not counting the upstream
  Apprise transport's own rate limits).
- `GET /api/v3/health` p95 — bounded by a single SELECT on
  `health_check` plus a worst-of aggregation; targeted < 50 ms p95
  on SQLite.
- `POST /api/v3/health/refresh` synchronous p95 — bounded by the
  slowest configured check + the per-check 10 s timeout
  (DEFAULT_CHECK_TIMEOUT_SECONDS in `health/checks/base.py`).

**Status**: deferred to v1+ measurement. The structural choices
that gate these budgets are already made and verified by tests:

- Per-notification queue (10 000 events) with overflow
  drop-oldest semantics keeps publishers non-blocking
  (`channel.test_dropped_count_per_notification`).
- The dispatcher is a per-(notification, event) pure function —
  no shared state between notifications, no global locks. Tests
  `test_serial_per_notification` and the channel's `drain()`
  semantics pin the ordering contract.
- The health endpoint's read path is one `select(HealthCheckRow)`
  per call — no per-component fanout when reading the snapshot.
- The refresh endpoint runs all checks via `asyncio.gather` with
  per-check `asyncio.wait_for`; one slow check can't block the
  others (`health/checks/base.py::run_check`).

A real-world perf run lives behind a load-test harness that
isn't part of this slice. When the v1+ effort lands, this
section gets replaced with measured numbers.

## Webhook retry schedule

The spec's `1 s → 5 s → 30 s` schedule is encoded in
`webhook.py::_BACKOFF_SCHEDULE_SECONDS`. With
`stop_after_attempt(3)`, only the first two waits fire (between
attempts 1↔2 and 2↔3); the 30 s slot is documented but
unreached. Kept in the schedule tuple to make a future
"extend to 4 attempts" diff minimal.

## State-machine table (debouncer)

The 12-cell `(previous, current)` matrix in
`debouncer.py::_severity_for_transition` is the single source of
truth for when an `OnHealthIssue` event fires. The full table
is reproduced in the module docstring so a code reader doesn't
have to walk the if-tree.

## Sonarr v3 envelope cross-walk

`docs/api/notification/webhook-payloads.md` is the canonical
contract. Notifiarr / Homepage / Tautulli treat the keys as
opaque structural envelopes — the remap is one-way and lossy.
Adding a new event type extends `payload_builders.py`; the
envelope shape stays unchanged.

## Apprise plugin-loading hardening (FR-001a)

Default-off via `ROMARR_APPRISE_ALLOW_CUSTOM_PLUGINS`. The
hardening sits at one chokepoint:
`apprise_init.build_apprise_asset()` — every Apprise instance
the wrapper builds threads through this, so flipping the flag
takes effect on the next process start. Apprise's 80+ built-in
providers stay available either way; the flag only gates
`data/apprise-plugins/` discovery.

Documented in the README/quickstart with a clear
"code-execution surface" warning so the operator's "I just
want to enable Discord" instinct doesn't accidentally turn on
plugin loading.
