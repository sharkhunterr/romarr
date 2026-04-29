"""Identification layer — multi-source ROM identification pipeline.

Combines: hash match, Torznab extended attributes, header read, filename
parse — merged with deterministic conflict resolution per FR-011 / FR-012.
"""

from romarr.identification.hasher import Hasher, HashResult, hash_file

__all__ = ["HashResult", "Hasher", "hash_file"]
