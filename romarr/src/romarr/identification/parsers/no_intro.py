"""No-Intro filename parser.

No-Intro names follow a documented bracketed convention:

    Title (Region) (Language) (Rev N) [tags]

Examples:
    Sonic the Hedgehog (USA).md
    Super Mario World (Europe) (Rev 1).sfc
    Final Fantasy IX (USA) (Disc 1).cue
    Sonic the Hedgehog (USA, Europe) (En,Fr,De).md
    Sonic the Hedgehog (USA) [b].md  <- bad dump tag

The parser extracts:
- ``title`` (everything before the first ``(``)
- ``regions`` (mapped from No-Intro forms like ``USA`` → ISO-3166-1 ``US``)
- ``languages`` (e.g., ``En,Fr`` → ``["en", "fr"]``)
- ``revision`` (e.g., ``Rev 1``)
- ``dump_status`` (from bracketed tags ``[b]`` ``[h]`` ``[!]`` etc.)
- ``confidence`` based on how many of these landed cleanly.
"""

from __future__ import annotations

import re

from romarr.domain.enums import DumpStatus, NamingConvention
from romarr.identification.parsers.base import BaseFilenameParser, ParsedFilename

# No-Intro region label → ISO-3166-1 alpha-2 (Assumptions in spec 001).
_NO_INTRO_REGION_MAP: dict[str, str] = {
    "USA": "US",
    "EUR": "EU",
    "EUROPE": "EU",
    "JPN": "JP",
    "JAPAN": "JP",
    "WORLD": "WW",
    "AUS": "AU",
    "AUSTRALIA": "AU",
    "BRA": "BR",
    "BRAZIL": "BR",
    "CHN": "CN",
    "CHINA": "CN",
    "FRA": "FR",
    "FRANCE": "FR",
    "GER": "DE",
    "GERMANY": "DE",
    "ITA": "IT",
    "ITALY": "IT",
    "KOR": "KR",
    "KOREA": "KR",
    "NLD": "NL",
    "NETHERLANDS": "NL",
    "ESP": "ES",
    "SPAIN": "ES",
    "SWE": "SE",
    "SWEDEN": "SE",
    "GBR": "GB",
    "UK": "GB",
    "USA, EUROPE": "US,EU",  # handled via comma-split below
}

# Two-letter language codes commonly used in No-Intro language tags.
# Lowercase = output ISO-639-1; uppercase keys are the No-Intro form.
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

# Bracketed tags map to dump_status / informational tag list.
_TAG_TO_DUMP_STATUS: dict[str, DumpStatus] = {
    "!": DumpStatus.VERIFIED,
    "b": DumpStatus.BADDUMP,
    "o": DumpStatus.OVERDUMP,
    "h": DumpStatus.HACK,
    "p": DumpStatus.PROTO,
    "t": DumpStatus.TRAINER,
    "T": DumpStatus.TRANSLATION,
    "a": DumpStatus.UNKNOWN,  # alternate dump
    "f": DumpStatus.UNKNOWN,  # fixed dump
}

_PAREN_RE = re.compile(r"\(([^()]+)\)")
_SQBRACKET_RE = re.compile(r"\[([^\[\]]+)\]")
_REVISION_RE = re.compile(r"^Rev(?:ision)? ?([0-9A-Za-z]+)$", re.IGNORECASE)


class NoIntroParser(BaseFilenameParser):
    """No-Intro convention parser."""

    convention = NamingConvention.NO_INTRO

    def _parse_basename(self, stem: str) -> ParsedFilename:
        # Title is everything up to the first parenthesis or square bracket.
        first_open = min(
            (idx for idx in (stem.find("("), stem.find("[")) if idx != -1),
            default=len(stem),
        )
        title = stem[:first_open].strip()

        regions: list[str] = []
        languages: list[str] = []
        revision: str | None = None
        tags_misc: list[str] = []
        dump_status = DumpStatus.UNKNOWN

        # Extract every parenthesised group.
        for group in _PAREN_RE.findall(stem):
            group_clean = group.strip()
            if not group_clean:
                continue

            # Revision?
            rev_match = _REVISION_RE.match(group_clean)
            if rev_match:
                revision = f"Rev {rev_match.group(1).strip()}"
                continue

            # Multi-region comma list?
            mapped_regions = self._extract_regions(group_clean)
            if mapped_regions:
                regions.extend(mapped_regions)
                continue

            # Language list (e.g., ``En,Fr``)?
            mapped_langs = self._extract_languages(group_clean)
            if mapped_langs:
                languages.extend(mapped_langs)
                continue

            # Disc / side markers — keep as informational tag.
            if group_clean.startswith(("Disc ", "Side ", "CD ")):
                tags_misc.append(group_clean)
                continue

            # Unknown bracket content → informational tag.
            tags_misc.append(group_clean)

        # Square-bracketed tags carry dump_status hints.
        for tag in _SQBRACKET_RE.findall(stem):
            tag_clean = tag.strip()
            tags_misc.append(f"[{tag_clean}]")
            # Match the leading character of the tag (e.g., ``[b]`` or ``[h2]``).
            head = tag_clean[0] if tag_clean else ""
            if head in _TAG_TO_DUMP_STATUS:
                dump_status = _TAG_TO_DUMP_STATUS[head]

        # Confidence heuristic: full title + at least one region pulls the
        # parser comfortably above the 0.7 threshold; revision and language
        # bumps reach 0.95+.
        confidence = self._score(
            has_title=bool(title),
            n_regions=len(regions),
            n_languages=len(languages),
            has_revision=revision is not None,
            has_dump_tag=dump_status != DumpStatus.UNKNOWN,
        )

        # Dedup + canonicalise ordering.
        regions_sorted = tuple(sorted(set(regions)))
        languages_sorted = tuple(sorted(set(languages)))

        return ParsedFilename(
            title=title or stem,
            regions=regions_sorted,
            languages=languages_sorted,
            revision=revision,
            dump_status=dump_status,
            tags=tuple(tags_misc),
            convention=NamingConvention.NO_INTRO,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_regions(group: str) -> list[str]:
        """Return ISO codes if ``group`` is a region label, else empty list."""
        parts = [p.strip().upper() for p in group.split(",")]
        out: list[str] = []
        for p in parts:
            if p in _NO_INTRO_REGION_MAP:
                # The map may carry comma-joined codes for special cases;
                # split them back out.
                for code in _NO_INTRO_REGION_MAP[p].split(","):
                    out.append(code)
            else:
                # Bail out — even one non-region in the group means this
                # group probably isn't a region label.
                return []
        return out

    @staticmethod
    def _extract_languages(group: str) -> list[str]:
        """Return ISO-639-1 codes if ``group`` is a language list, else empty."""
        parts = [p.strip().upper() for p in group.split(",")]
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
        n_regions: int,
        n_languages: int,
        has_revision: bool,
        has_dump_tag: bool,
    ) -> float:
        """Heuristic confidence score in [0, 1]."""
        if not has_title:
            return 0.0

        # Base for "I see a title and at least one bracketed group I
        # could interpret".  We grant 0.5 just for matching the
        # title-then-bracket shape.
        score = 0.5

        if n_regions >= 1:
            score += 0.30
        if n_languages >= 1:
            score += 0.10
        if has_revision:
            score += 0.05
        if has_dump_tag:
            score += 0.05

        return min(score, 1.0)
