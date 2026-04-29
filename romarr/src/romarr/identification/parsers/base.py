"""Filename parser interface + dispatcher.

Each concrete parser receives a basename (the file without its
directory or extension) and returns a :class:`ParsedFilename` with a
confidence score in ``[0.0, 1.0]``. The dispatcher runs them in
fixed order — No-Intro → Redump → TOSEC → GoodTools → Scene — and
accepts the first match with ``confidence > 0.7`` (FR-023).
"""

from __future__ import annotations

import abc
import os
from collections.abc import Sequence
from dataclasses import dataclass, field

from romarr.domain.enums import DumpStatus, NamingConvention

PARSER_THRESHOLD = 0.7
"""Per-parser confidence floor (FR-023)."""


@dataclass(frozen=True, slots=True)
class ParsedFilename:
    """Structured output of a single parser invocation.

    Field provenance is implicit — every field comes from the parser's
    interpretation of the filename. Aggregating across multiple
    sources (filename + Torznab + header + DAT) is the matcher's job
    in the layer above.
    """

    title: str
    regions: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    revision: str | None = None
    dump_status: DumpStatus = DumpStatus.UNKNOWN
    tags: tuple[str, ...] = ()
    convention: NamingConvention = NamingConvention.UNKNOWN
    confidence: float = 0.0

    extra: dict[str, str] = field(default_factory=dict)


class BaseFilenameParser(abc.ABC):
    """Common contract for the four parsers."""

    convention: NamingConvention

    def parse(self, filename: str) -> ParsedFilename:
        """Strip extension + directory, then defer to ``_parse_basename``."""
        base = os.path.basename(filename)
        # Multiple compound extensions like ``.cue.bin`` aren't real for
        # the parser's purpose — strip a single extension only.
        stem, _ext = os.path.splitext(base)
        return self._parse_basename(stem)

    @abc.abstractmethod
    def _parse_basename(self, stem: str) -> ParsedFilename:  # pragma: no cover
        """Return a parsed-filename for ``stem`` (extension already removed)."""


class ParserDispatcher:
    """Runs each parser in order and accepts the first above threshold.

    The dispatcher is stateless and deterministic — same input always
    yields the same output (purity invariant per spec 006 FR-007 which
    consumes this layer's outputs).
    """

    def __init__(self, parsers: Sequence[BaseFilenameParser]) -> None:
        if not parsers:
            raise ValueError("ParserDispatcher requires at least one parser")
        self._parsers = tuple(parsers)

    def parse(
        self, filename: str, *, threshold: float = PARSER_THRESHOLD
    ) -> ParsedFilename:
        """Return the winning parse, or an ``UNKNOWN`` shape if none qualify."""
        for parser in self._parsers:
            result = parser.parse(filename)
            if result.confidence > threshold:
                return result

        # No parser cleared the threshold — return an UNKNOWN sentinel.
        # The matcher above this layer falls back to header reads and
        # hash matches.
        stem, _ = os.path.splitext(os.path.basename(filename))
        return ParsedFilename(
            title=stem,
            convention=NamingConvention.UNKNOWN,
            confidence=0.0,
        )
