"""CL010 — pack security fixtures.

Two adversarial fixtures pinned by the spec:
  - ``yaml_python_object_apply.yaml``: a ``!!python/object/apply``
    tag must be refused by ``yaml.SafeLoader``. A successful
    parse of this file is a security regression (FR-001a).
  - ``zip_bomb.yaml``: a "zip bomb"-style oversize body must be
    refused by ``MAX_PACK_BYTES`` before the YAML parser sees
    it. The real test for the cap synthesises bytes; this
    fixture pins the operator-facing intent.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
import yaml

from romarr.platform_packs.yaml_loader import (
    MAX_PACK_BYTES,
    PackTooLargeError,
    load_pack,
)


def test_python_object_apply_rejected_by_safe_loader(
    pack_yaml: Callable[[str], bytes],
) -> None:
    """SafeLoader refuses ``!!python/object/apply:os.system [...]``.

    PyYAML maps this to a ``ConstructorError`` — a subclass of
    ``YAMLError``. We assert on the base class so a future
    PyYAML refactor that swaps the concrete exception still
    counts as "loader rejected the input"."""
    body = pack_yaml("invalid_yaml/yaml_python_object_apply.yaml")
    with pytest.raises(yaml.YAMLError):
        load_pack(body)


def test_zip_bomb_synthetic_caught_by_size_cap() -> None:
    """A body larger than ``MAX_PACK_BYTES`` is rejected pre-parse.

    We don't need the real fixture file for this assertion —
    the synthetic byte buffer matches the operator-facing intent
    (a malicious pack tries to OOM the parser; the loader's size
    cap stops it cold) and avoids checking-in a 1 MiB+ blob."""
    body = b"a" * (MAX_PACK_BYTES + 1)
    with pytest.raises(PackTooLargeError):
        load_pack(body)
