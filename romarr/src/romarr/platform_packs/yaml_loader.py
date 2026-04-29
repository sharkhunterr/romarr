"""Hardened YAML loader + canonicalization for content-hash stability.

  - ``load_pack`` uses :class:`yaml.SafeLoader` mandatorily (FR-001a)
    and rejects anything bigger than 1 MiB at the entry point (FR-001b).
  - ``canonicalize`` re-emits the parsed document as compact, sort-keyed
    JSON. SHA-256 over those bytes gives a hash that is stable against
    YAML cosmetic edits (key reorderings, comment additions, trailing
    whitespace) — the property ``contents_hash`` needs (FR-009).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import yaml

# Hard 1 MiB cap on incoming pack body — anything bigger is rejected
# with a request-level 413 by the API layer; the loader enforces the
# same bound at the parse boundary as a defense in depth (FR-001b).
MAX_PACK_BYTES: int = 1 << 20  # 1 MiB

# Per-pack platform count cap (FR-001c). Validation enforces this; the
# loader exposes the constant so the API layer can short-circuit
# obviously-oversized uploads without parsing.
MAX_PLATFORMS_PER_PACK: int = 200


class PackTooLargeError(ValueError):
    """The pack body exceeds :data:`MAX_PACK_BYTES`."""


def load_pack(content: bytes) -> dict[str, Any]:
    """Parse a YAML pack body into a Python dict.

    Raises :class:`PackTooLargeError` over the size cap;
    :class:`yaml.YAMLError` on parse failures (the validator's
    boundary catches and re-raises as :class:`PackValidationError`).
    """
    if len(content) > MAX_PACK_BYTES:
        raise PackTooLargeError(
            f"pack body is {len(content)} bytes; maximum allowed is "
            f"{MAX_PACK_BYTES} bytes (1 MiB)"
        )
    parsed = yaml.safe_load(content)
    if parsed is None:
        return {}
    if not isinstance(parsed, dict):
        raise yaml.YAMLError(
            f"pack root must be a mapping; got {type(parsed).__name__}"
        )
    return parsed


def canonicalize(parsed: dict[str, Any]) -> bytes:
    """Re-emit the parsed pack as compact, sort-keyed JSON bytes.

    Two YAML files that parse to the same Python dict produce the
    same canonical byte string — which makes the SHA-256 over the
    output stable against whitespace / key-ordering edits.
    """
    return json.dumps(parsed, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def compute_contents_hash(parsed: dict[str, Any]) -> str:
    """Return the hex SHA-256 of the canonicalized pack."""
    return hashlib.sha256(canonicalize(parsed)).hexdigest()
