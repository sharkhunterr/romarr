"""Pipeline import-purity smoke test (T080 / FR-016).

The decision pipeline is supposed to be a pure function over a
preloaded :class:`LibraryState` — no DB session, no HTTP client,
no ad-hoc logging. This test parses ``romarr.search.pipeline``
with :mod:`ast` and asserts the source file imports nothing from
the IO-side-effecting libraries the project uses elsewhere.

It deliberately checks the source AST rather than the runtime
:func:`sys.modules` closure: package ``__init__`` re-exports drag
unrelated modules into the closure, but they never appear inside
``pipeline.py`` itself, which is what the constitution gates.
"""

from __future__ import annotations

import ast
from pathlib import Path

import romarr.search.pipeline

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


def test_pipeline_source_imports_no_io_libraries() -> None:
    source_path = Path(romarr.search.pipeline.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    roots = _collect_imports(tree)
    leaks = sorted(roots & _FORBIDDEN_ROOTS)
    assert not leaks, (
        f"romarr.search.pipeline imports IO-side-effecting libraries: "
        f"{leaks}. The decision pipeline must operate on the preloaded "
        f"LibraryState only (FR-016)."
    )


def test_pipeline_source_imports_no_search_io_helpers() -> None:
    """The pipeline must not reach into preload / cache / clients —
    those are the ROUNDS layer's job. Defensive: if a future refactor
    accidentally pulls a session-aware helper into pipeline.py, this
    test catches it before the purity property test does."""
    source_path = Path(romarr.search.pipeline.__file__)
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden_search_modules = {
        "romarr.search.preload",
        "romarr.search.cache",
        "romarr.search._clients",
        "romarr.search.history",
        "romarr.search.dispatch",
        "romarr.search.rounds",
    }
    leaks: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for forbidden in forbidden_search_modules:
                if (
                    node.module == forbidden
                    or node.module.startswith(forbidden + ".")
                ):
                    leaks.append(node.module)
    assert not leaks, (
        f"romarr.search.pipeline reaches into ROUNDS-layer helpers: "
        f"{sorted(set(leaks))}. The pipeline must consume only the "
        f"preloaded LibraryState (FR-016)."
    )
