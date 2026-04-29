"""Identification layer — multi-source ROM identification pipeline.

Combines: hash match, Torznab extended attributes, header read, filename
parse — merged with deterministic conflict resolution per FR-011 / FR-012.
"""

from romarr.identification.circuit_breaker import (
    CircuitBreaker,
    CircuitOpenError,
    CircuitState,
)
from romarr.identification.hasher import Hasher, HashResult, hash_file
from romarr.identification.identifier import (
    Identifier,
    IdentifyOutcome,
    TorznabAttrs,
)

__all__ = [
    "CircuitBreaker",
    "CircuitOpenError",
    "CircuitState",
    "HashResult",
    "Hasher",
    "Identifier",
    "IdentifyOutcome",
    "TorznabAttrs",
    "hash_file",
]
