"""Redump filename parser.

Redump is the disc-based-platform analogue of No-Intro and uses a
nearly identical bracketed convention with one notable extension:
the ``(Disc N)`` marker is mandatory for multi-disc sets.

Examples:
    Final Fantasy IX (USA) (Disc 1).cue
    Metal Gear Solid (Europe) (Disc 1).cue
    Resident Evil 2 (Japan) (Rev 1).cue

The parser shares logic with :class:`NoIntroParser` (same region map,
same language pills, same dump-status tag convention) so we
delegate to it under the hood and just override the convention tag.
"""

from __future__ import annotations

import re

from romarr.domain.enums import NamingConvention
from romarr.identification.parsers.base import BaseFilenameParser, ParsedFilename
from romarr.identification.parsers.no_intro import NoIntroParser

# Disc-based formats Redump uses canonically — when we see one of these
# extensions on the filename we lean toward Redump even when the rest
# of the structure could match No-Intro.
_DISC_EXTENSIONS = frozenset({".cue", ".bin", ".chd", ".iso", ".gdi", ".cdi"})

_DISC_MARKER_RE = re.compile(r"\((?:Disc|CD)\s+\d+\)", re.IGNORECASE)


class RedumpParser(BaseFilenameParser):
    """Redump convention parser.

    Falls back to :class:`NoIntroParser`'s implementation since the two
    conventions share the bracketed shape, then overrides the
    ``convention`` field on the result.
    """

    convention = NamingConvention.REDUMP

    def __init__(self) -> None:
        self._no_intro = NoIntroParser()

    def parse(self, filename: str) -> ParsedFilename:
        # Run No-Intro's parser to get the structured shape...
        result = self._no_intro.parse(filename)

        # ...then re-tag as Redump only when this looks like a disc
        # release. Otherwise return a low-confidence Redump result so
        # the dispatcher keeps walking down the parser cascade.
        ext = filename.lower().rsplit(".", 1)
        is_disc_extension = (
            len(ext) > 1 and f".{ext[-1]}" in _DISC_EXTENSIONS
        )
        has_disc_marker = bool(_DISC_MARKER_RE.search(filename))

        if not (is_disc_extension or has_disc_marker):
            # Doesn't look like a Redump candidate — return a zero-
            # confidence unknown so the dispatcher passes the file
            # along to the next parser.
            return ParsedFilename(
                title=result.title,
                regions=result.regions,
                languages=result.languages,
                revision=result.revision,
                dump_status=result.dump_status,
                tags=result.tags,
                convention=NamingConvention.UNKNOWN,
                confidence=0.0,
            )

        # Re-tag as Redump and bump the confidence slightly because we
        # also matched the disc-extension/disc-marker signal.
        return ParsedFilename(
            title=result.title,
            regions=result.regions,
            languages=result.languages,
            revision=result.revision,
            dump_status=result.dump_status,
            tags=result.tags,
            convention=NamingConvention.REDUMP,
            confidence=min(result.confidence + 0.05, 1.0)
            if result.confidence > 0
            else 0.0,
        )

    def _parse_basename(self, stem: str) -> ParsedFilename:
        # Unused — we override ``parse`` directly because we need the
        # original filename's extension to classify confidently.
        raise NotImplementedError
