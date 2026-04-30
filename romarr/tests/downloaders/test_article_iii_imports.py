"""Article III static-import test (T066).

Constitutional invariant: each spec layer that needs the at-rest
encryption helper or the circuit breaker MUST import from the single
foundation source. No duplicated implementations across the project.

This test walks the qBit + SAB + factory + circuit_breaker modules'
ASTs and confirms the imports come from the canonical paths.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import romarr.downloaders as downloaders_pkg

_ROOT = Path(downloaders_pkg.__file__).parent


def _imports_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    seen: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                seen.add(f"{node.module}.{alias.name}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                seen.add(alias.name)
    return seen


@pytest.mark.parametrize(
    "module_path",
    [
        "factory.py",
        "implementations/sabnzbd.py",
        "implementations/qbittorrent.py",
        "api/clients.py",
    ],
)
def test_encryption_helper_imported_from_canonical_source(
    module_path: str,
) -> None:
    """Anything that touches credential blobs MUST go through
    :mod:`romarr.metadata.encryption` — no per-module Fernet wiring.
    """
    imports = _imports_in(_ROOT / module_path)
    crypto_imports = {imp for imp in imports if "fernet" in imp.lower()}
    assert crypto_imports == set(), (
        f"{module_path} imports a Fernet symbol directly: {crypto_imports} — "
        "use romarr.metadata.encryption instead (Article III)"
    )
    if any("encrypt" in imp or "decrypt" in imp for imp in imports):
        assert any(
            imp.startswith("romarr.metadata.encryption.")
            for imp in imports
        ), (
            f"{module_path} uses encrypt/decrypt but does not import from "
            "romarr.metadata.encryption (Article III)"
        )


def test_circuit_breaker_reused_from_foundation() -> None:
    """downloaders.circuit_breaker MUST re-export the foundation
    :class:`CircuitBreaker` rather than reimplement the breaker logic.
    """
    imports = _imports_in(_ROOT / "circuit_breaker.py")
    assert any(
        imp.startswith("romarr.identification.circuit_breaker.")
        for imp in imports
    ), (
        "downloaders/circuit_breaker.py must reuse the foundation breaker "
        "(Article III) — found imports: " + repr(sorted(imports))
    )
