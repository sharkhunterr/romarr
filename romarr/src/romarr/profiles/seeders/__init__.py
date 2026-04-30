"""First-boot seeder for the six profile types (Phase 5 — FR-002, FR-003, FR-003a).

Single public entry point: :func:`seed_defaults`. The runner reads
JSON files alongside this module, validates each row through its
matching Pydantic ``*Create`` schema, and applies upsert logic
keyed off ``seed_key`` + ``is_user_modified``.

Per FR-003a clarification:

  * **Seeded rows are owned by the seeder** until the operator
    edits one. Edit flips ``is_user_modified`` to true (the API
    layer handles the flip in the same transaction).
  * The seeder skips any row where ``is_user_modified = true`` —
    operator changes are sacred. This MVP does NOT push schema
    updates onto operator-touched rows even when the default
    catalogue evolves; that policy is revisited in v1+.
  * The seeder upserts (insert or refresh) rows where
    ``is_user_modified = false`` so a release that adds a column or
    changes a default cleanly applies on the next boot.
"""

from romarr.profiles.seeders.runner import (
    SCENE_GROUPS,
    SEED_DIR,
    load_scene_groups,
    seed_defaults,
)

__all__ = ["SCENE_GROUPS", "SEED_DIR", "load_scene_groups", "seed_defaults"]
