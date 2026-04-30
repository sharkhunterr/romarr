"""XML parsers for Newznab/Torznab responses.

Pure functions over ``bytes`` → typed value objects. No HTTP, no DB.
The client (spec 004 CLIENT phase) wires these into the httpx layer.
"""

from romarr.indexers.parser.caps import parse_caps
from romarr.indexers.parser.dedup import dedup_by_guid
from romarr.indexers.parser.extended_attrs import (
    extract_extended_attrs,
    normalize_languages,
    normalize_region,
)
from romarr.indexers.parser.search import parse_search

__all__ = [
    "dedup_by_guid",
    "extract_extended_attrs",
    "normalize_languages",
    "normalize_region",
    "parse_caps",
    "parse_search",
]
