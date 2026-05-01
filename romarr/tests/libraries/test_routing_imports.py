"""Routing-module purity smoke test (T087 / FR-006 / Article XVII).

The router is supposed to be a pure function over preloaded value
types — no DB session, no HTTP client, no logging side effects.
This test parses ``romarr.libraries.routing`` with :mod:`ast` and
asserts the source file imports nothing from the IO-side-effecting
libraries the project uses elsewhere.

It checks the source AST rather than the runtime
:func:`sys.modules` closure: package ``__init__`` re-exports drag
unrelated modules into the closure, but they never appear inside
``routing.py`` itself, which is what the constitution gates.
Same pattern as spec 007's pipeline-purity smoke test.
"""

from __future__ import annotations

import ast
from pathlib import Path

import romarr.libraries.routing

_FORBIDDEN_ROOTS: frozenset[str] = frozenset(
    {
        "sqlalchemy",
        "httpx",
        "aiohttp",
        "requests",
        "redis",
        "logging",
    }
)


def _collect_imports(tree: ast.AST) -> set[str]:
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def test_routing_source_imports_no_io_libraries() -> None:
    source_path = Path(romarr.libraries.routing.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    roots = _collect_imports(tree)
    leaks = sorted(roots & _FORBIDDEN_ROOTS)
    assert not leaks, (
        f"romarr.libraries.routing imports IO-side-effecting libraries: "
        f"{leaks}. The router must operate on the preloaded "
        f"LibrarySnapshot list only (FR-006 / Article XVII)."
    )


def test_routing_source_imports_no_orchestration_helpers() -> None:
    """The router must not reach into the heartbeat loop, the
    scanner, or the exporters — those are orchestration layers
    that compose the router, not the other way around."""
    source_path = Path(romarr.libraries.routing.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden = {
        "romarr.libraries.heartbeat",
        "romarr.libraries.scanner",
        "romarr.libraries.exporters",
        "romarr.libraries.api",
    }
    leaks: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for forbidden_module in forbidden:
                if (
                    node.module == forbidden_module
                    or node.module.startswith(forbidden_module + ".")
                ):
                    leaks.append(node.module)
    assert not leaks, (
        f"romarr.libraries.routing reaches into orchestration "
        f"helpers: {sorted(set(leaks))}. The router must consume "
        f"only preloaded value types (FR-006 / Article XVII)."
    )
