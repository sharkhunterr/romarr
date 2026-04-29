"""Scene-style filename parser.

Scene release names follow conventions like:

    Sonic.the.Hedgehog.USA-DEMENT
    Final.Fantasy.IX.USA.Disc.1-DEMENT
    Some_Title.JPN-GROUP.bin

Distinctive features:
- Words separated by ``.`` (or sometimes ``_``)
- A trailing ``-GROUP`` token is the release-group name
- Region tokens (USA / EUR / JPN / WORLD) are uppercased
- No bracketed groups like the No-Intro / GoodTools / TOSEC styles

This parser scores low when the input has bracketed groups (those
shapes are claimed by earlier parsers in the dispatcher cascade).

Implementation note: ``os.path.splitext`` cannot be trusted for Scene
names because the dotted shape (``Foo.USA-DEMENT``) makes splitext
peel off ``.USA-DEMENT`` as a fake extension. The parser overrides
:meth:`parse` to strip only known ROM extensions.
"""

from __future__ import annotations

import os
import re

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.identification.parsers.base import BaseFilenameParser, ParsedFilename

# Known real ROM/disc extensions — anything else is left in the stem
# so the dotted Scene shape survives ``parse``.
_KNOWN_ROM_EXTENSIONS = frozenset(
    {
        ".nes", ".unf", ".unif",
        ".sfc", ".smc",
        ".md", ".gen", ".bin",
        ".gb", ".gbc", ".gba",
        ".n64", ".v64", ".z64",
        ".iso", ".cue", ".chd", ".gdi", ".cdi",
        ".cso", ".pbp",
        ".7z", ".zip", ".rar",
    }
)

_SCENE_REGION_MAP: dict[str, str] = {
    "USA": "US",
    "EUR": "EU",
    "EUROPE": "EU",
    "JPN": "JP",
    "JAPAN": "JP",
    "WORLD": "WW",
    "AUS": "AU",
    "BRAZIL": "BR",
    "FRANCE": "FR",
    "GERMANY": "DE",
    "ITALY": "IT",
    "KOREA": "KR",
    "NETHERLANDS": "NL",
    "SPAIN": "ES",
    "UK": "GB",
}


class SceneParser(BaseFilenameParser):
    """Scene-NFO convention parser."""

    convention = NamingConvention.SCENE

    def parse(self, filename: str) -> ParsedFilename:
        """Override the default ``parse`` to avoid splitext misclassification.

        ``os.path.splitext("Sonic.the.Hedgehog.USA-DEMENT")`` returns
        ``("Sonic.the.Hedgehog", ".USA-DEMENT")`` which mangles the
        Scene-style stem. We only strip an extension when it's a real
        ROM/disc extension we recognise.
        """
        base = os.path.basename(filename)
        # Strip a real ROM extension if one is present; otherwise keep
        # the full basename so the dotted Scene shape survives.
        if "." in base:
            head, dot, tail = base.rpartition(".")
            if dot and f".{tail.lower()}" in _KNOWN_ROM_EXTENSIONS:
                base = head
        return self._parse_basename(base)

    def _parse_basename(self, stem: str) -> ParsedFilename:
        # Refuse if the filename uses bracketed groups — that's not Scene.
        if "(" in stem or "[" in stem:
            return ParsedFilename(title=stem, confidence=0.0)

        # Split off the trailing -GROUP marker (if any).
        release_group: str | None = None
        title_part = stem
        if "-" in stem:
            head, _, tail = stem.rpartition("-")
            # Group names are conventionally short, all-letters or
            # short alphanumeric labels. Refuse if the tail looks like
            # a normal title token instead.
            if tail and tail.isascii() and 2 <= len(tail) <= 16 and tail.isupper():
                release_group = tail
                title_part = head

        # Normalise word separators: dots and underscores → spaces.
        tokens = re.split(r"[._]", title_part)
        tokens = [t for t in tokens if t]

        if not tokens:
            return ParsedFilename(title=stem, confidence=0.0)

        # Walk tokens from the right, peeling off region + disc markers
        # until we hit a token that doesn't look like metadata.
        regions: list[str] = []
        tags: list[str] = []

        while tokens:
            tail = tokens[-1].upper()
            if tail in _SCENE_REGION_MAP:
                regions.append(_SCENE_REGION_MAP[tail])
                tokens.pop()
                continue
            # Disc N marker
            if tail.startswith("DISC") and tokens[-2:] and tokens[-1].upper() == "DISC":
                # actually the disc marker is "Disc.N" → two tokens
                pass
            if len(tokens) >= 2 and tokens[-2].upper() == "DISC" and tail.isdigit():
                tags.append(f"Disc {tail}")
                tokens.pop()
                tokens.pop()
                continue
            break

        if not tokens:
            return ParsedFilename(title=stem, confidence=0.0)

        title = " ".join(tokens)

        # Confidence climbs sharply once we've identified at least one
        # region AND a release group.
        confidence = self._score(
            has_title=bool(title),
            n_regions=len(regions),
            has_release_group=release_group is not None,
            n_tokens=len(tokens),
        )

        extra: dict[str, str] = {}
        if release_group is not None:
            extra["release_group"] = release_group

        return ParsedFilename(
            title=title,
            regions=tuple(sorted(set(regions))),
            languages=(),
            revision=None,
            dump_status=DumpStatus.UNKNOWN,
            tags=tuple(tags),
            convention=NamingConvention.SCENE,
            confidence=confidence,
            extra=extra,
        )

    @staticmethod
    def _score(
        *,
        has_title: bool,
        n_regions: int,
        has_release_group: bool,
        n_tokens: int,
    ) -> float:
        if not has_title:
            return 0.0
        # A bare title with no region or group looks like noise.
        if not has_release_group and n_regions == 0:
            return 0.0
        score = 0.30
        if has_release_group:
            score += 0.40
        if n_regions >= 1:
            score += 0.25
        if n_tokens >= 2:  # multi-word title is a Scene signal
            score += 0.05
        return min(score, 1.0)
