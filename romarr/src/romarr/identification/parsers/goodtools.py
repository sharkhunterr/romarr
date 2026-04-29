"""GoodTools filename parser.

GoodTools is the legacy convention from the early 2000s. Its
filenames look like:

    Title (E) [b].smc          # Europe, bad dump
    Title (U) (V1.1) [!].nes   # USA, version 1.1, verified
    Title (J) [h2].sfc         # Japan, hack version 2
    Title (UE) [T+Fr].smc      # USA + Europe, French translation

Region codes are single letters (U=USA, E=Europe, J=Japan, A=Australia,
F=France, G=Germany, etc.). Tags in square brackets carry dump-status
hints — the ``[b]`` (bad dump), ``[h]`` (hack), ``[t]`` (trainer),
``[o]`` (overdump), ``[!]`` (verified) classes are honoured.

Spec 001 User Story 4 calls out ``sth_e_b.bin`` as the canonical test
case: stem ``sth_e_b`` → underscore-separated GoodTools shorthand
where ``e`` = Europe and ``b`` = bad dump.
"""

from __future__ import annotations

import re

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.identification.parsers.base import BaseFilenameParser, ParsedFilename

# Single-letter region codes used by GoodTools.
_GOODTOOLS_REGION_MAP: dict[str, str] = {
    "U": "US",
    "E": "EU",
    "J": "JP",
    "A": "AU",
    "B": "BR",
    "C": "CN",
    "F": "FR",
    "G": "DE",
    "I": "IT",
    "K": "KR",
    "N": "NL",
    "S": "ES",
    "W": "SE",  # SWeden
    "UK": "GB",
    "Eu": "EU",
    "Us": "US",
    "Jp": "JP",
}

# Multi-letter region groupings (e.g., (UE) = USA + Europe).
_GOODTOOLS_MULTI_REGION = {
    "UE": ("US", "EU"),
    "JU": ("JP", "US"),
    "JE": ("JP", "EU"),
    "JUE": ("JP", "US", "EU"),
    "EUR": ("EU",),
    "USA": ("US",),
    "JPN": ("JP",),
}

_TAG_TO_DUMP_STATUS: dict[str, DumpStatus] = {
    "!": DumpStatus.VERIFIED,
    "b": DumpStatus.BADDUMP,
    "o": DumpStatus.OVERDUMP,
    "h": DumpStatus.HACK,
    "p": DumpStatus.PROTO,
    "t": DumpStatus.TRAINER,
    "T": DumpStatus.TRANSLATION,
}

_PAREN_RE = re.compile(r"\(([^()]+)\)")
_SQBRACKET_RE = re.compile(r"\[([^\[\]]+)\]")


class GoodToolsParser(BaseFilenameParser):
    """GoodTools convention parser.

    Two surface forms are supported:
    1. Bracketed: ``Title (E) [b]`` (the standard form)
    2. Underscored: ``title_e_b`` (the abbreviated form found in some
       legacy dumps; user-story-4 of spec 001 explicitly tests this)
    """

    convention = NamingConvention.GOODTOOLS

    def _parse_basename(self, stem: str) -> ParsedFilename:
        # If we see no parentheses or brackets, fall back to the
        # underscore-shorthand parser (covers `sth_e_b`).
        if "(" not in stem and "[" not in stem:
            return self._parse_underscore_shorthand(stem)

        return self._parse_bracketed(stem)

    # ---- Bracketed form ------------------------------------------------

    def _parse_bracketed(self, stem: str) -> ParsedFilename:
        first_open = min(
            (idx for idx in (stem.find("("), stem.find("[")) if idx != -1),
            default=len(stem),
        )
        title = stem[:first_open].strip()

        regions: list[str] = []
        tags: list[str] = []
        revision: str | None = None
        dump_status = DumpStatus.UNKNOWN

        for group in _PAREN_RE.findall(stem):
            group_clean = group.strip()
            if not group_clean:
                continue

            # Multi-letter region grouping?
            if group_clean in _GOODTOOLS_MULTI_REGION:
                regions.extend(_GOODTOOLS_MULTI_REGION[group_clean])
                continue

            # Single-letter region?
            if (
                len(group_clean) == 1
                and group_clean in _GOODTOOLS_REGION_MAP
            ):
                regions.append(_GOODTOOLS_REGION_MAP[group_clean])
                continue

            # Version tag like ``V1.1`` or ``V1``
            if group_clean.upper().startswith("V") and any(c.isdigit() for c in group_clean):
                revision = group_clean
                continue

            # Anything else → informational tag
            tags.append(group_clean)

        for raw_tag in _SQBRACKET_RE.findall(stem):
            tag_clean = raw_tag.strip()
            tags.append(f"[{tag_clean}]")
            head = tag_clean[0] if tag_clean else ""
            if head in _TAG_TO_DUMP_STATUS:
                dump_status = _TAG_TO_DUMP_STATUS[head]

        confidence = self._score(
            has_title=bool(title),
            n_regions=len(regions),
            has_revision=revision is not None,
            has_dump_tag=dump_status != DumpStatus.UNKNOWN,
        )

        return ParsedFilename(
            title=title or stem,
            regions=tuple(sorted(set(regions))),
            languages=(),
            revision=revision,
            dump_status=dump_status,
            tags=tuple(tags),
            convention=NamingConvention.GOODTOOLS,
            confidence=confidence,
        )

    # ---- Underscore shorthand --------------------------------------- #

    def _parse_underscore_shorthand(self, stem: str) -> ParsedFilename:
        """Parse ``sth_e_b``-style abbreviated GoodTools names.

        Convention: ``<title>_<region>_<dump_tag>``. The trailing
        single-letter tokens are parsed as region (one letter) then
        dump tag (one letter).
        """
        parts = stem.split("_")
        if len(parts) < 2:
            return ParsedFilename(title=stem, confidence=0.0)

        regions: list[str] = []
        dump_status = DumpStatus.UNKNOWN
        tags: list[str] = []

        # Walk the tail tokens. Dump-status tags are checked FIRST
        # because some tag letters (``b``, ``p``, ``t``) collide with
        # region letters (Brazil, …) and the convention puts the dump
        # tag at the very end of the filename. The trailing tag wins
        # when it's the unset dump-status; everything before that is
        # treated as region.
        title_parts = list(parts)
        while title_parts:
            tail = title_parts[-1]
            if (
                tail in _TAG_TO_DUMP_STATUS
                and dump_status == DumpStatus.UNKNOWN
            ):
                dump_status = _TAG_TO_DUMP_STATUS[tail]
                tags.append(f"[{tail}]")
                title_parts.pop()
                continue
            if len(tail) == 1 and tail.upper() in _GOODTOOLS_REGION_MAP:
                regions.append(_GOODTOOLS_REGION_MAP[tail.upper()])
                title_parts.pop()
                continue
            break

        if not title_parts:
            # Couldn't find a title — bail out at low confidence.
            return ParsedFilename(title=stem, confidence=0.0)

        title = "_".join(title_parts)

        # Confidence is moderate-to-high when we recovered both a
        # region and a dump tag.
        confidence = self._score(
            has_title=True,
            n_regions=len(regions),
            has_revision=False,
            has_dump_tag=dump_status != DumpStatus.UNKNOWN,
        )

        return ParsedFilename(
            title=title,
            regions=tuple(sorted(set(regions))),
            languages=(),
            revision=None,
            dump_status=dump_status,
            tags=tuple(tags),
            convention=NamingConvention.GOODTOOLS,
            confidence=confidence,
        )

    @staticmethod
    def _score(
        *,
        has_title: bool,
        n_regions: int,
        has_revision: bool,
        has_dump_tag: bool,
    ) -> float:
        if not has_title:
            return 0.0
        score = 0.45
        if n_regions >= 1:
            score += 0.30
        if has_revision:
            score += 0.05
        if has_dump_tag:
            score += 0.10
        return min(score, 1.0)
