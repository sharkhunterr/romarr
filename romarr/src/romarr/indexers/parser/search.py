"""``t=search`` / ``t=rss`` response parser (T027).

Newznab/Torznab returns RSS 2.0 with a few standard ``<enclosure>``
fields plus a forest of ``<torznab:attr>`` / ``<grabarr:attr>``
extended attributes. We extract every common field, project the
extended attrs onto :class:`SearchResult` slots with the correct
:class:`FieldProvenance`, and drop unknown attributes silently.

Anything the parser can't recover from on a single ``<item>`` —
missing GUID, broken size — causes that one item to be skipped
with a structured warning; the rest of the response still parses.
"""

from __future__ import annotations

import contextlib
import logging
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from lxml import etree

from romarr.domain.enums import NamingConvention
from romarr.indexers.errors import IndexerProtocolError
from romarr.indexers.parser.dedup import dedup_by_guid
from romarr.indexers.parser.extended_attrs import (
    extract_extended_attrs,
    normalize_languages,
    normalize_region,
)
from romarr.indexers.types import (
    DatSource,
    FieldProvenance,
    SearchResult,
)

logger = logging.getLogger(__name__)


def _parse_publish_date(raw: str) -> datetime | None:
    """RSS 2.0 dates are RFC 822; Torznab also emits ISO sometimes."""
    if not raw:
        return None
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt


def _project_attr(
    *,
    name: str,
    value: str,
    provenance: FieldProvenance,
    fields: dict[str, Any],
) -> None:
    """Map one extended attribute onto the SearchResult dict in place.

    Unknown attribute names are ignored. Bad values (e.g. region
    codes we don't understand) are dropped with a structured warning;
    the field stays None.
    """
    n = name.lower()
    if n == "region":
        iso = normalize_region(value)
        if iso is None:
            logger.warning(
                "indexers.parser.unknown_region",
                extra={"value": value, "provenance": provenance.value},
            )
            return
        fields["region"] = iso
        fields["region_provenance"] = provenance
    elif n in ("language", "languages"):
        langs = normalize_languages(value)
        if langs:
            fields["languages"] = langs
            fields["languages_provenance"] = provenance
    elif n == "revision":
        fields["revision"] = value
        fields["revision_provenance"] = provenance
    elif n in ("dump_tag", "dump_tags", "dumptags"):
        # Comma / pipe / semicolon separated.
        tags = [
            t.strip()
            for t in value.replace(";", ",").replace("|", ",").split(",")
            if t.strip()
        ]
        if tags:
            fields["dump_tags"] = tags
            fields["dump_tags_provenance"] = provenance
    elif n in ("hash_sha1", "sha1"):
        fields["hash_sha1"] = value.lower()
        fields["hash_sha1_provenance"] = provenance
    elif n in ("hash_crc32", "crc32"):
        fields["hash_crc32"] = value.lower()
        fields["hash_crc32_provenance"] = provenance
    elif n in ("naming_convention", "convention"):
        try:
            fields["naming_convention"] = NamingConvention(value.lower())
            fields["naming_convention_provenance"] = provenance
        except ValueError:
            logger.warning(
                "indexers.parser.unknown_convention", extra={"value": value}
            )
    elif n in ("dat_source", "dat"):
        try:
            fields["dat_source"] = DatSource(value.lower())
            fields["dat_source_provenance"] = provenance
        except ValueError:
            logger.warning(
                "indexers.parser.unknown_dat_source", extra={"value": value}
            )
    elif n == "size" and "size_bytes" not in fields:
        with contextlib.suppress(TypeError, ValueError):
            fields["size_bytes"] = int(value)
    elif n == "seeders":
        with contextlib.suppress(TypeError, ValueError):
            fields["seeders"] = int(value)
    elif n == "peers":
        with contextlib.suppress(TypeError, ValueError):
            fields["peers"] = int(value)
    elif n == "files":
        with contextlib.suppress(TypeError, ValueError):
            fields["files"] = int(value)
    elif n == "infohash":
        fields["info_hash"] = value.lower()
    elif n == "magneturl":
        fields["magnet_url"] = value
    elif n == "category":
        try:
            cat = int(value)
        except (TypeError, ValueError):
            return
        cats = list(fields.get("categories", []))
        if cat not in cats:
            cats.append(cat)
        fields["categories"] = cats
    # Slice 402 — extra standard attrs we now project onto
    # ``SearchResult``. ``downloadvolumefactor`` / ``upload...``
    # are private-tracker freeleech / bonus signals; ``grabs`` is
    # the download counter used as a popularity signal; the rest
    # carry operator-facing context (year, genre, NFO link).
    elif n == "grabs":
        with contextlib.suppress(TypeError, ValueError):
            fields["grabs"] = int(value)
    elif n in ("downloadvolumefactor", "download_volume_factor"):
        with contextlib.suppress(TypeError, ValueError):
            fields["download_volume_factor"] = float(value)
    elif n in ("uploadvolumefactor", "upload_volume_factor"):
        with contextlib.suppress(TypeError, ValueError):
            fields["upload_volume_factor"] = float(value)
    elif n in ("description", "comments", "release_notes"):
        if value and "description" not in fields:
            fields["description"] = value
    elif n == "year":
        with contextlib.suppress(TypeError, ValueError):
            fields["year"] = int(value)
    elif n == "genre":
        if value:
            fields["genre"] = value
    elif n in ("info", "info_url", "infourl"):
        if value:
            fields["info_url"] = value
    elif n in ("nfo", "nfo_url", "nfourl"):
        if value:
            fields["nfo_url"] = value


def _parse_item(item: etree._Element, *, indexer_id: int) -> SearchResult | None:
    fields: dict[str, Any] = {
        "indexer_id": indexer_id,
        "categories": [],
    }

    guid_el = item.find("./guid")
    title_el = item.find("./title")
    link_el = item.find("./link")
    if guid_el is None or title_el is None or link_el is None:
        return None
    guid = (guid_el.text or "").strip()
    title = (title_el.text or "").strip()
    link = (link_el.text or "").strip()
    if not (guid and title and link):
        return None

    fields["guid"] = guid
    fields["title"] = title
    fields["link"] = link

    enc = item.find("./enclosure")
    if enc is not None:
        size = enc.get("length")
        if size and size.isdigit():
            fields["size_bytes"] = int(size)

    pub = item.find("./pubDate")
    if pub is not None and pub.text:
        fields["publish_date"] = _parse_publish_date(pub.text)

    # ``<category>`` elements (numeric IDs preferred) — RSS 2.0 form.
    for cat_el in item.iterfind("./category"):
        text = (cat_el.text or "").strip()
        if text and text.isdigit():
            cat_id = int(text)
            if cat_id not in fields["categories"]:
                fields["categories"].append(cat_id)

    # Extended attrs override RSS-level fields where they overlap.
    for attr in extract_extended_attrs(item).values():
        _project_attr(
            name=attr.name,
            value=attr.value,
            provenance=attr.provenance,
            fields=fields,
        )

    try:
        return SearchResult.model_validate(fields)
    except Exception as exc:  # pragma: no cover — guard
        logger.warning(
            "indexers.parser.item_drop", extra={"guid": guid, "err": str(exc)}
        )
        return None


def parse_search(xml_bytes: bytes, *, indexer_id: int) -> list[SearchResult]:
    """Parse an RSS 2.0 search response into :class:`SearchResult`s.

    The dedup-by-GUID step (FR-026) is applied before returning.
    """
    parser = etree.XMLParser(resolve_entities=False, recover=True)
    try:
        root = etree.fromstring(xml_bytes, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise IndexerProtocolError(f"search XML parse error: {exc}") from exc
    if root is None:
        raise IndexerProtocolError("search response was empty")

    items: list[SearchResult] = []
    # ``<channel><item>...`` for RSS 2.0; some indexers nest deeper —
    # ``.//item`` is conservative and works either way.
    for item in root.iterfind(".//item"):
        parsed = _parse_item(item, indexer_id=indexer_id)
        if parsed is not None:
            items.append(parsed)

    return dedup_by_guid(items)


__all__ = ["parse_search"]
