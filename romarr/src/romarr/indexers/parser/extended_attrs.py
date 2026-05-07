"""Extended-attribute extraction with provenance tracking (T025).

Both standard ``torznab:attr`` elements and the Romarr-specific
``grabarr:*`` extension carry name/value pairs that the parser
projects onto :class:`SearchResult` fields. Each extracted value
records its :class:`FieldProvenance` so the operator UI can show
"this region came from the indexer's extended attrs" vs "this
region came from filename parsing".

Region normalisation:

  - region codes are coerced to two-letter ISO 3166-1 alpha-2
    where we recognize the input (``USA`` → ``US``, ``Europe`` →
    ``EU``, ``WORLD`` → ``WW`` …). That matches the foundation
    filename parser's output shape so the pipeline sees a single
    vocabulary regardless of which surface produced the region.
  - language codes are coerced to two-letter ISO 639-1.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from romarr.indexers.types import FieldProvenance, ParsedTorznabAttr

if TYPE_CHECKING:
    from lxml import etree as _etree

logger = logging.getLogger(__name__)


# Region inputs we know how to translate. Anything else is dropped.
# Output: two-letter ISO 3166-1 alpha-2 (with ``WW`` for worldwide,
# matching the foundation no-intro parser's convention).
_REGION_TO_ISO: dict[str, str] = {
    # ISO-style passthrough.
    "us": "US",
    "eu": "EU",
    "jp": "JP",
    "ja": "JP",
    "kr": "KR",
    "cn": "CN",
    "tw": "TW",
    "br": "BR",
    "au": "AU",
    "uk": "UK",
    "gb": "UK",
    # No-Intro / Redump three-letter forms.
    "usa": "US",
    "eur": "EU",
    "jpn": "JP",
    "kor": "KR",
    "chn": "CN",
    "twn": "TW",
    "bra": "BR",
    "aus": "AU",
    "fra": "FR",
    "fr": "FR",
    "ger": "DE",
    "de": "DE",
    "deu": "DE",
    "ita": "IT",
    "it": "IT",
    "spa": "ES",
    "es": "ES",
    # Long-form spellings the parser hands us when an indexer doesn't
    # canonicalise (``Sonic the Hedgehog (Europe)`` etc.). Without
    # these the long forms returned ``None`` and the region_profile
    # gate sat at score=0 / fallback for every result that wasn't
    # already a 2- or 3-letter code.
    "united states": "US",
    "america": "US",
    "europe": "EU",
    "european": "EU",
    "japan": "JP",
    "japanese": "JP",
    "korea": "KR",
    "china": "CN",
    "taiwan": "TW",
    "brazil": "BR",
    "australia": "AU",
    "united kingdom": "UK",
    "france": "FR",
    "germany": "DE",
    "italy": "IT",
    "spain": "ES",
    # Worldwide → ``WW`` to match the foundation parser.
    "world": "WW",
    "wor": "WW",
    "ww": "WW",
}

_LANGUAGE_TO_ISO: dict[str, str] = {
    "en": "en",
    "english": "en",
    "fr": "fr",
    "french": "fr",
    "francais": "fr",
    "français": "fr",
    "de": "de",
    "german": "de",
    "deutsch": "de",
    "es": "es",
    "spanish": "es",
    "espanol": "es",
    "español": "es",
    "it": "it",
    "italian": "it",
    "italiano": "it",
    "ja": "ja",
    "jp": "ja",
    "japanese": "ja",
    "ko": "ko",
    "korean": "ko",
    "zh": "zh",
    "chinese": "zh",
    "pt": "pt",
    "portuguese": "pt",
    "ru": "ru",
    "russian": "ru",
}

_TORZNAB_NS = "http://torznab.com/schemas/2015/feed"
_GRABARR_NS = "https://romarr.example/schemas/grabarr"


def normalize_region(raw: str) -> str | None:
    """Return the canonical ISO region code, or ``None`` if unknown."""
    if not raw:
        return None
    return _REGION_TO_ISO.get(raw.strip().lower())


def normalize_languages(raw: str | list[str]) -> list[str]:
    """Coerce a raw language list (CSV string or list) to ISO codes.

    Unknown entries are silently dropped; the remainder is deduped
    while preserving order.
    """
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.replace(";", ",").split(",")]
    else:
        parts = [str(p).strip() for p in raw]
    out: list[str] = []
    seen: set[str] = set()
    for p in parts:
        if not p:
            continue
        iso = _LANGUAGE_TO_ISO.get(p.lower())
        if iso and iso not in seen:
            seen.add(iso)
            out.append(iso)
    return out


def _provenance_for(namespace: str | None) -> FieldProvenance | None:
    """Map the XML namespace URI of an ``<attr>`` element to provenance."""
    if namespace is None:
        return None
    if namespace == _TORZNAB_NS:
        return FieldProvenance.TORZNAB
    if namespace == _GRABARR_NS:
        return FieldProvenance.GRABARR
    return None


def extract_extended_attrs(
    item_element: _etree._Element,
) -> dict[str, ParsedTorznabAttr]:
    """Walk every ``<*:attr name=... value=...>`` child of ``item_element``.

    Returns a map keyed on the attribute's ``name``. When a name
    appears in BOTH namespaces, the ``grabarr:`` value wins because
    the extended namespace is opt-in and operators only use it to
    override Torznab's standard value (FR-005a).
    """
    out: dict[str, ParsedTorznabAttr] = {}
    # ``{*}attr`` matches any namespace; iterate so we can pick out
    # the namespace URI per element to attribute provenance.
    for el in item_element.iterfind(".//{*}attr"):
        # ``el.tag`` is ``{namespace_uri}attr`` for namespaced
        # attributes; ``str(el.tag)`` round-trips for both.
        tag = str(el.tag)
        ns: str | None = None
        if tag.startswith("{") and "}" in tag:
            ns = tag[1 : tag.index("}")]
            local = tag[tag.index("}") + 1 :]
        else:
            local = tag
        if local != "attr":
            continue
        name = el.get("name") or ""
        value = el.get("value") or ""
        if not name or not value:
            continue
        provenance = _provenance_for(ns)
        if provenance is None:
            # Unknown namespace; ignore silently rather than fail
            # the whole parse.
            continue
        # Grabarr wins over Torznab on collision.
        existing = out.get(name)
        if existing is None or (
            existing.provenance == FieldProvenance.TORZNAB
            and provenance == FieldProvenance.GRABARR
        ):
            out[name] = ParsedTorznabAttr(
                name=name, value=value, provenance=provenance
            )
    return out


__all__ = [
    "extract_extended_attrs",
    "normalize_languages",
    "normalize_region",
]
