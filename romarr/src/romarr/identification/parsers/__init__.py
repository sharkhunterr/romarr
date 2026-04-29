"""Filename parsers for ROM identification (FR-021 / FR-022 / FR-023).

Five parsers behind a common interface, dispatched in fixed order:

    No-Intro → Redump → TOSEC → GoodTools → Scene

The :func:`default_dispatcher` factory builds a :class:`ParserDispatcher`
with all five wired in that order — the canonical configuration used by
the identification cascade.
"""

from romarr.identification.parsers.base import (
    BaseFilenameParser,
    ParsedFilename,
    ParserDispatcher,
)
from romarr.identification.parsers.goodtools import GoodToolsParser
from romarr.identification.parsers.no_intro import NoIntroParser
from romarr.identification.parsers.redump import RedumpParser
from romarr.identification.parsers.scene import SceneParser
from romarr.identification.parsers.tosec import TosecParser

__all__ = [
    "BaseFilenameParser",
    "GoodToolsParser",
    "NoIntroParser",
    "ParsedFilename",
    "ParserDispatcher",
    "RedumpParser",
    "SceneParser",
    "TosecParser",
    "default_dispatcher",
]


def default_dispatcher() -> ParserDispatcher:
    """Build the canonical 5-parser dispatcher per FR-023.

    Order: No-Intro → Redump → TOSEC → GoodTools → Scene. The first
    parser whose confidence > 0.7 wins; ties (rare) are broken by this
    enumeration order (Edge Case in spec 001).
    """
    return ParserDispatcher(
        [
            NoIntroParser(),
            RedumpParser(),
            TosecParser(),
            GoodToolsParser(),
            SceneParser(),
        ]
    )
