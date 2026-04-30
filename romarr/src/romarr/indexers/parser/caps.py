"""``t=caps`` response parser (T024).

Newznab's caps response shape (XML):

  <caps>
    <server version="..." title="..."/>
    <searching>
      <search available="yes" supportedParams="q,cat"/>
      <tv-search available="no"/>
      ...
    </searching>
    <categories>
      <category id="1000" name="Console">
        <subcat id="1010" name="NDS"/>
        ...
      </category>
    </categories>
  </caps>

We extract the server label, the searching map, and the flat list
of (sub)category IDs. Anything unrecognised is silently ignored.
"""

from __future__ import annotations

from lxml import etree

from romarr.indexers.errors import IndexerProtocolError
from romarr.indexers.types import IndexerCapabilities


def _parse_xml(content: bytes) -> etree._Element:
    try:
        # ``recover=True`` lets us tolerate trivially-broken XML
        # (trailing whitespace, BOM) without aborting the parse.
        parser = etree.XMLParser(resolve_entities=False, recover=True)
        return etree.fromstring(content, parser=parser)
    except etree.XMLSyntaxError as exc:
        raise IndexerProtocolError(f"caps XML parse error: {exc}") from exc


def parse_caps(xml_bytes: bytes) -> IndexerCapabilities:
    root = _parse_xml(xml_bytes)
    if root is None:
        raise IndexerProtocolError("caps response was empty")

    server_el = root.find("./server")
    server: str | None = None
    if server_el is not None:
        server = server_el.get("title") or server_el.get("version")

    searching: dict[str, dict[str, object]] = {}
    searching_block = root.find("./searching")
    if searching_block is not None:
        for child in searching_block:
            tag = etree.QName(child).localname  # strip any namespace prefix
            available = (child.get("available") or "").lower() == "yes"
            supported = child.get("supportedParams") or ""
            params = [p.strip() for p in supported.split(",") if p.strip()]
            searching[tag] = {
                "available": available,
                "supportedParams": params,
            }

    categories: list[int] = []
    cats_block = root.find("./categories")
    if cats_block is not None:
        for cat in cats_block.iterfind(".//category"):
            cid = cat.get("id")
            if cid is not None and cid.isdigit():
                categories.append(int(cid))
        for sub in cats_block.iterfind(".//subcat"):
            sid = sub.get("id")
            if sid is not None and sid.isdigit():
                categories.append(int(sid))

    # Informational hint: which extended-attr names are advertised in
    # the caps. Many indexers don't advertise these; absence here is
    # not an error — the parser still extracts them when present.
    extended_attrs_supported: list[str] = []
    for hint in root.iterfind(".//attribute"):
        name = hint.get("name")
        if name:
            extended_attrs_supported.append(name)

    return IndexerCapabilities(
        server=server,
        searching=searching,
        categories=sorted(set(categories)),
        extended_attrs_supported=sorted(set(extended_attrs_supported)),
    )


__all__ = ["parse_caps"]
