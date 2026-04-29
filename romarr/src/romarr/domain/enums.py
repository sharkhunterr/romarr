"""Domain enums — DumpStatus + NamingConvention.

Stored as strings in the database for portability between SQLite and
PostgreSQL and so external tooling can read them without a translation
table.
"""

from __future__ import annotations

from enum import StrEnum


class DumpStatus(StrEnum):
    """Authoritative dump-quality classification.

    Order is preference-relevant: ``verified`` is best, ``baddump`` /
    ``overdump`` are worst.
    """

    VERIFIED = "verified"
    GOOD = "good"
    PROTO = "proto"
    BETA = "beta"
    DEMO = "demo"
    SAMPLE = "sample"
    HACK = "hack"
    TRAINER = "trainer"
    TRANSLATION = "translation"
    BADDUMP = "baddump"
    OVERDUMP = "overdump"
    UNKNOWN = "unknown"


class NamingConvention(StrEnum):
    """Filename naming convention recognised by the parsers."""

    NO_INTRO = "no-intro"
    REDUMP = "redump"
    TOSEC = "tosec"
    GOODTOOLS = "goodtools"
    SCENE = "scene"
    UNKNOWN = "unknown"
