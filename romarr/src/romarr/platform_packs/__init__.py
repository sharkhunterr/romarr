"""Platform-pack subsystem (spec 003).

A **Platform Pack** is a YAML document validated against a JSON Schema
and ingested transactionally. The same primitive ships the built-in
catalog (auto-applied on first boot) and ingests community-authored
packs uploaded via the API. A user-override flag (``pack_source =
'user'``) on platform rows protects local customizations from pack
updates.

Three behaviours are constitutional (Article X):

  1. **Data, not code** — adding a console must never widen the schema.
  2. **Idempotency** — re-applying an unchanged pack is a no-op.
  3. **User wins** — locally-overridden platforms survive any future
     pack apply.

Public surface lands here in slices: this slice ships the validator
(pure function), the SCAF module skeleton, and the persistence layer
(``parsing_strategies`` + ``platform_pack_application_log`` tables).
The transactional ingestor + built-in pack + API stubs land in
follow-up slices.
"""

from romarr.platform_packs.builtin import (
    apply_builtin_pack,
    resolve_builtin_pack_path,
)
from romarr.platform_packs.errors import (
    OverrideRequiredError,
    PackValidationError,
    PackVersionConflictError,
    SchemaVersionTooHighError,
    Violation,
)
from romarr.platform_packs.ingestor import IngestSource, ingest_pack
from romarr.platform_packs.override import (
    add_format,
    delete_format,
    mark_overridden,
    release_override,
    update_format,
)
from romarr.platform_packs.types import (
    PackPlatformDiff,
    PackUploadResult,
    ValidateResult,
)
from romarr.platform_packs.validator import (
    ParsedPack,
    validate_cross_refs,
    validate_pack,
    validate_pack_structure,
)
from romarr.platform_packs.yaml_loader import (
    canonicalize,
    compute_contents_hash,
    load_pack,
)

__all__ = [
    "IngestSource",
    "OverrideRequiredError",
    "PackPlatformDiff",
    "PackUploadResult",
    "PackValidationError",
    "PackVersionConflictError",
    "ParsedPack",
    "SchemaVersionTooHighError",
    "ValidateResult",
    "Violation",
    "add_format",
    "apply_builtin_pack",
    "canonicalize",
    "compute_contents_hash",
    "delete_format",
    "ingest_pack",
    "load_pack",
    "mark_overridden",
    "release_override",
    "resolve_builtin_pack_path",
    "update_format",
    "validate_cross_refs",
    "validate_pack",
    "validate_pack_structure",
]
