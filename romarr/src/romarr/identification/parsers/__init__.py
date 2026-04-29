"""Filename parsers for ROM identification (FR-021 / FR-022 / FR-023).

Four parsers behind a common interface:
- No-Intro (default; the most common modern convention)
- Redump (CD/DVD-based platforms)
- TOSEC (broad scope, ageing scene roots)
- GoodTools (legacy)
- Scene (NFO-style names like ``Sonic.USA-DEMENT``)

The :class:`ParserDispatcher` runs each parser in fixed order and
accepts the first whose confidence > 0.7. Ties at threshold are
broken by parser order (deterministic Edge Case behaviour).
"""

from romarr.identification.parsers.base import (
    BaseFilenameParser,
    ParsedFilename,
    ParserDispatcher,
)
from romarr.identification.parsers.no_intro import NoIntroParser

__all__ = [
    "BaseFilenameParser",
    "NoIntroParser",
    "ParsedFilename",
    "ParserDispatcher",
]
