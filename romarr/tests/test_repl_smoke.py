"""REPL smoke test (spec 001 T088, SC-008).

Pins the constitutional invariant that the foundation domain
+ identification public surface imports without booting
FastAPI. Catches a regression where someone accidentally
imports ``romarr.api.app`` from ``romarr.domain`` (which
would create a cyclic + slow-import dependency).
"""

from __future__ import annotations

import sys


def test_domain_and_identification_import_without_fastapi() -> None:
    """``from romarr.domain.models import Game, Release, Dump``
    plus ``from romarr.identification import Identifier`` must
    succeed without ever pulling in ``fastapi`` or
    ``romarr.api``."""
    # Force a clean slate so a previous test's API imports
    # don't fool the assertion.
    forbidden_prefixes = ("fastapi", "romarr.api")
    for name in list(sys.modules):
        if name.startswith(forbidden_prefixes):
            del sys.modules[name]

    from romarr.domain.models import Dump, Game, Release  # noqa: F401
    from romarr.identification import Identifier  # noqa: F401

    leaked = sorted(
        name
        for name in sys.modules
        if name.startswith(forbidden_prefixes)
    )
    assert leaked == [], (
        f"foundation imports must not pull in FastAPI / romarr.api; "
        f"leaked: {leaked}"
    )


def test_domain_models_are_constructable() -> None:
    """The three top-level models can be instantiated in
    isolation (no DB session). This rules out the regression
    where a model accidentally requires a session in
    ``__init__``."""
    from romarr.domain.models import Dump, Game, Release

    game = Game(platform_id=1, slug="sonic", title="Sonic")
    release = Release(game_id=1, name="Sonic (USA)")
    dump = Dump(
        release_id=1,
        path="/tmp/sonic.md",
        original_filename="sonic.md",
        size_bytes=524288,
        format="raw",
        crc32="abcd1234",
    )

    assert game.title == "Sonic"
    assert release.name == "Sonic (USA)"
    assert dump.path == "/tmp/sonic.md"
