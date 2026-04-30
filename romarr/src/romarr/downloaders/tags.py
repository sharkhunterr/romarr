"""Constants + helpers for the per-grab tag set.

Every grab Romarr issues carries the standard ``romarr`` tag plus a
``romarr-{platform-slug}`` tag so the user can filter their client
UI by Romarr-managed downloads, and Romarr can re-discover its own
items on cold start (FR-013).

Once the importer hardlinks/moves a download into the library, the
``romarr-imported`` tag is added so the lifecycle policy knows the
download is safe to remove (per Library.lifecycle_policy).
"""

from __future__ import annotations

TAG_ROMARR = "romarr"
TAG_IMPORTED = "romarr-imported"
_PLATFORM_TAG_PREFIX = "romarr-"


def tag_for_platform(platform_slug: str) -> str:
    """Return the per-platform tag for ``platform_slug``.

    ``platform_slug`` MUST already be in canonical slug form (lowercase,
    hyphenated) — the foundation's :class:`Platform.slug` constraint
    enforces that on the persistence side.
    """
    if not platform_slug:
        raise ValueError("platform_slug must be a non-empty slug")
    return f"{_PLATFORM_TAG_PREFIX}{platform_slug}"


def standard_tag_set(platform_slug: str) -> list[str]:
    """The canonical tag list applied to every grab Romarr issues.

    Returned as a list (not a set) so callers preserve insertion
    order when serialising to qBit / SAB query parameters.
    """
    return [TAG_ROMARR, tag_for_platform(platform_slug)]


__all__ = [
    "TAG_IMPORTED",
    "TAG_ROMARR",
    "standard_tag_set",
    "tag_for_platform",
]
