"""TOSEC filename parser.

TOSEC names follow a documented pattern with explicit publisher and
year fields:

    Title v1.0 (Publisher)(YYYY)(Region)(Language)(Other)[!].ext
    Title (1992)(Publisher)(US)(en)[h]

Distinctive features versus No-Intro:
- Year is a parenthesised 4-digit value
- Publisher is a parenthesised string (often ALL CAPS or a known label)
- Multiple parentheses chain without separator
- Square-bracket dump-status tags are nearly identical to No-Intro

This parser focuses on the high-signal markers (year + publisher) and
defers extensive coverage of TOSEC's many optional fields to a later
slice — the corpus-recall test in spec 001 SC-003 only requires 95%
on a representative sample.
"""

from __future__ import annotations

import re

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.identification.parsers.base import BaseFilenameParser, ParsedFilename

# Same region letters TOSEC uses (mostly No-Intro-shaped).
_TOSEC_REGION_MAP: dict[str, str] = {
    "US": "US",
    "USA": "US",
    "EU": "EU",
    "EUR": "EU",
    "EUROPE": "EU",
    "JP": "JP",
    "JPN": "JP",
    "JAPAN": "JP",
    "WORLD": "WW",
    "AU": "AU",
    "BR": "BR",
    "DE": "DE",
    "FR": "FR",
    "GB": "GB",
    "IT": "IT",
    "KR": "KR",
    "NL": "NL",
    "ES": "ES",
}

_LANG_MAP: dict[str, str] = {
    "EN": "en",
    "FR": "fr",
    "DE": "de",
    "ES": "es",
    "IT": "it",
    "JA": "ja",
    "KO": "ko",
    "NL": "nl",
    "PT": "pt",
    "RU": "ru",
    "SV": "sv",
    "ZH": "zh",
}

_TAG_TO_DUMP_STATUS: dict[str, DumpStatus] = {
    "!": DumpStatus.VERIFIED,
    "b": DumpStatus.BADDUMP,
    "h": DumpStatus.HACK,
    "p": DumpStatus.PROTO,
    "t": DumpStatus.TRAINER,
    "T": DumpStatus.TRANSLATION,
    "o": DumpStatus.OVERDUMP,
}

# Detect a 4-digit year token (1970-2099 covers the realistic range).
_YEAR_RE = re.compile(r"^(?:19[7-9]\d|20\d{2})$")
_PAREN_RE = re.compile(r"\(([^()]+)\)")
_SQBRACKET_RE = re.compile(r"\[([^\[\]]+)\]")


class TosecParser(BaseFilenameParser):
    """TOSEC convention parser."""

    convention = NamingConvention.TOSEC

    def _parse_basename(self, stem: str) -> ParsedFilename:
        first_open = min(
            (idx for idx in (stem.find("("), stem.find("[")) if idx != -1),
            default=len(stem),
        )
        title = stem[:first_open].strip()

        regions: list[str] = []
        languages: list[str] = []
        publisher: str | None = None
        year: str | None = None
        tags: list[str] = []
        dump_status = DumpStatus.UNKNOWN

        groups = _PAREN_RE.findall(stem)
        # The first parenthesis after the title is conventionally the
        # year in TOSEC; the second is the publisher; the third is the
        # region code. We'll walk all groups and classify each.
        for group in groups:
            group_clean = group.strip()
            if not group_clean:
                continue

            if year is None and _YEAR_RE.match(group_clean):
                year = group_clean
                continue

            upper = group_clean.upper()
            if upper in _TOSEC_REGION_MAP:
                regions.append(_TOSEC_REGION_MAP[upper])
                continue

            # Comma- or hyphen-joined region/language list?
            mapped_regions = self._extract_regions(group_clean)
            if mapped_regions:
                regions.extend(mapped_regions)
                continue

            mapped_langs = self._extract_languages(group_clean)
            if mapped_langs:
                languages.extend(mapped_langs)
                continue

            # First non-region/non-language alphabetic group looks like a
            # publisher; subsequent ones become tags.
            if publisher is None and group_clean and not group_clean[0].isdigit():
                publisher = group_clean
                continue

            tags.append(group_clean)

        for raw_tag in _SQBRACKET_RE.findall(stem):
            tag_clean = raw_tag.strip()
            tags.append(f"[{tag_clean}]")
            head = tag_clean[0] if tag_clean else ""
            if head in _TAG_TO_DUMP_STATUS:
                dump_status = _TAG_TO_DUMP_STATUS[head]

        # TOSEC confidence: title + year is a strong signal (publisher
        # alone isn't enough since "(USA)" can look like a one-word
        # publisher to the cursory parser).
        confidence = self._score(
            has_title=bool(title),
            has_year=year is not None,
            has_publisher=publisher is not None,
            n_regions=len(regions),
            has_dump_tag=dump_status != DumpStatus.UNKNOWN,
        )

        extra: dict[str, str] = {}
        if year is not None:
            extra["year"] = year
        if publisher is not None:
            extra["publisher"] = publisher

        return ParsedFilename(
            title=title or stem,
            regions=tuple(sorted(set(regions))),
            languages=tuple(sorted(set(languages))),
            revision=None,
            dump_status=dump_status,
            tags=tuple(tags),
            convention=NamingConvention.TOSEC,
            confidence=confidence,
            extra=extra,
        )

    @staticmethod
    def _extract_regions(group: str) -> list[str]:
        parts = [p.strip().upper() for p in re.split(r"[,\-]", group)]
        out: list[str] = []
        for p in parts:
            if p in _TOSEC_REGION_MAP:
                out.append(_TOSEC_REGION_MAP[p])
            else:
                return []
        return out

    @staticmethod
    def _extract_languages(group: str) -> list[str]:
        parts = [p.strip().upper() for p in re.split(r"[,\-]", group)]
        if not parts or any(len(p) != 2 for p in parts):
            return []
        out: list[str] = []
        for p in parts:
            if p in _LANG_MAP:
                out.append(_LANG_MAP[p])
            else:
                return []
        return out

    @staticmethod
    def _score(
        *,
        has_title: bool,
        has_year: bool,
        has_publisher: bool,
        n_regions: int,
        has_dump_tag: bool,
    ) -> float:
        if not has_title:
            return 0.0
        # TOSEC requires a year to score above the No-Intro threshold;
        # otherwise the dispatcher would pick TOSEC for clean No-Intro
        # files.
        if not has_year:
            return 0.4
        score = 0.55
        if has_publisher:
            score += 0.20
        if n_regions >= 1:
            score += 0.15
        if has_dump_tag:
            score += 0.05
        return min(score, 1.0)
