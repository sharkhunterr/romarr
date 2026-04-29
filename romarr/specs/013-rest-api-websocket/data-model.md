# Data Model — REST API & WebSocket

This spec introduces three new tables in migration `0013_api.py`. The bulk
of REST API behaviour is layer-only (routing, pagination, auth chain
plumbing); the schema additions are limited to the cross-cutting
infrastructure that didn't fit into any single earlier spec.

## `tag` — global tag definitions (polymorphic)

Per spec 013 Q5 clarification — tags are scoped globally and applied
across multiple entity types via the `tag_assignment` association table.

```sql
CREATE TABLE tag (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       VARCHAR NOT NULL UNIQUE,    -- short slug, e.g., 'family-friendly'
  color      VARCHAR NOT NULL DEFAULT '#9BBC0F',  -- hex, default = brand green
  label      VARCHAR NOT NULL,           -- human-friendly label, e.g., 'Family Friendly'
  created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
  updated_at TIMESTAMP NOT NULL DEFAULT current_timestamp
);

CREATE INDEX idx_tag_name ON tag (name);
```

## `tag_assignment` — polymorphic tag-to-entity m2m

```sql
CREATE TABLE tag_assignment (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  tag_id      INTEGER NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
  entity_type VARCHAR NOT NULL
                CHECK (entity_type IN ('game', 'indexer', 'notification', 'release')),
  entity_id   INTEGER NOT NULL,
  created_at  TIMESTAMP NOT NULL DEFAULT current_timestamp,
  UNIQUE (tag_id, entity_type, entity_id)
);

CREATE INDEX idx_tag_assignment_lookup ON tag_assignment (entity_type, entity_id);
CREATE INDEX idx_tag_assignment_tag ON tag_assignment (tag_id);
```

Cascade rules:
- `tag` row delete → cascade to assignments (FK `ON DELETE CASCADE`).
- Entity row delete (Game / Indexer / Notification / Release) → cascade
  via per-entity-type cleanup hook in the application layer (no ORM-level
  FK on `entity_id` is possible because it spans tables).

The cleanup hooks for each entity type live in:
- `Game.before_delete` — deletes `tag_assignment WHERE entity_type='game' AND entity_id=Game.id`
- `Indexer.before_delete` — same with `entity_type='indexer'`
- `Notification.before_delete` — same with `entity_type='notification'`
- `Release.before_delete` — same with `entity_type='release'`

## `queue_entry` — download queue mirror

Used by spec 005's stuck-grab retry, spec 008's import pipeline, and the
`/api/v3/queue` endpoints.

```sql
CREATE TABLE queue_entry (
  id                          INTEGER PRIMARY KEY AUTOINCREMENT,
  release_id                  INTEGER NOT NULL REFERENCES release(id) ON DELETE CASCADE,
  download_client_id          INTEGER NOT NULL REFERENCES download_client(id) ON DELETE CASCADE,
  download_client_native_id   VARCHAR NOT NULL,    -- info-hash for qBit, nzo_id for SAB
  state                       VARCHAR NOT NULL
                                CHECK (state IN ('queued', 'downloading', 'paused',
                                                 'completed', 'stuck', 'failed', 'pending_retry')),
  progress                    REAL NOT NULL DEFAULT 0.0,    -- 0.0..1.0
  size_bytes                  BIGINT NULL,
  eta_seconds                 INTEGER NULL,
  last_updated_at             TIMESTAMP NOT NULL DEFAULT current_timestamp,
  error_msg                   VARCHAR NULL,
  attempt_count               INTEGER NOT NULL DEFAULT 0,
  last_attempt_at             TIMESTAMP NULL,
  created_at                  TIMESTAMP NOT NULL DEFAULT current_timestamp,
  UNIQUE (download_client_id, download_client_native_id)
);

CREATE INDEX idx_queue_entry_release ON queue_entry (release_id);
CREATE INDEX idx_queue_entry_state ON queue_entry (state);
```

## `idempotency_cache` — Idempotency-Key storage (DB fallback)

Redis is the preferred backend per FR-020 / FR-025. This table is the
fallback when Redis is unavailable.

```sql
CREATE TABLE idempotency_cache (
  key                  VARCHAR NOT NULL,                 -- Idempotency-Key header value
  endpoint             VARCHAR NOT NULL,                 -- e.g., 'POST /api/v3/rom/release/grab'
  request_body_hash    VARCHAR NOT NULL,                 -- hex of SHA-256(JCS-canonical-JSON(body))
                                                          -- or SHA-256(raw bytes) for multipart/binary
  response_status      INTEGER NOT NULL,
  response_body        BLOB NOT NULL,                    -- gzipped JSON or raw response bytes
  response_headers     JSON NOT NULL DEFAULT '{}',       -- subset that affects the cached response
  created_at           TIMESTAMP NOT NULL DEFAULT current_timestamp,
  expires_at           TIMESTAMP NOT NULL,               -- created_at + 24 hours
  PRIMARY KEY (endpoint, key)
);

CREATE INDEX idx_idempotency_cache_expires_at ON idempotency_cache (expires_at);
```

Per spec 013 Q1 clarification — the `request_body_hash` is the hex of
`SHA-256(JCS-canonical-JSON(body))` per RFC 8785 for JSON bodies;
multipart and binary bodies fall back to plain `SHA-256(raw bytes)`.

A replay with a body whose hash differs from the stored value MUST
return HTTP 422 reason `idempotency_key_body_mismatch`.

A periodic cleanup job (runs as part of every other top-level job's
post-completion hook, opportunistic) deletes rows where
`expires_at < now`.

## Cross-spec consistency

- The `tag.color` default `#9BBC0F` matches the Game Boy LCD green
  brand color clarified in spec 014.
- The `idempotency_cache` table is created only when Redis is not
  configured at boot; the migration runs unconditionally so the schema
  is present in case Redis becomes unavailable later.

No other schema changes are introduced by this spec — every other
endpoint reads/writes tables created by earlier specs.
