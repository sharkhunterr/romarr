"""Filename-rendering step (FR-024 / pipeline step 9).

Wraps spec 006's :class:`NamingTemplateEngine` to produce the
final destination path for an import. Pure: no I/O, no DB
access — the caller preloads the Naming profile, the four token
namespaces, the library root, and the multi-disc parent (if any).

The full destination path is:

    <library_root> /
        [<platform_slug>/ if naming_profile.platform_subfolder]
        [<game_subfolder>/ if naming_profile.multi_disc_subfolder
                            and the release has > 1 disc]
        <rendered_basename>.<dump_extension>

The renderer never touches the filesystem — :class:`PathExistence`
checks (FR-024 destination collision) live with the MOVE step.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from romarr.profiles.naming.engine import NamingTemplateEngine
    from romarr.profiles.naming.tokens import (
        DumpTokens,
        GameTokens,
        PlatformTokens,
        ReleaseTokens,
    )


@dataclass(frozen=True)
class _NamingProfileShape:
    """Duck-typed shape the renderer reads from a Naming profile.
    Concrete callers pass either the SQLAlchemy ORM row or a
    Pydantic schema — both expose these attributes."""

    template: str
    platform_subfolder: bool
    multi_disc_subfolder: bool
    replace_illegal_chars: bool


@dataclass(frozen=True)
class RenderedDestination:
    """Result of :func:`render_destination`.

    ``path`` is the full destination path the MOVE step writes to.
    ``basename`` is the last segment without the extension — useful
    for log lines and for the multi-disc subfolder name.
    """

    path: Path
    basename: str
    extension: str


def render_destination(
    *,
    engine: NamingTemplateEngine,
    profile: object,
    library_root: Path,
    game: GameTokens,
    release: ReleaseTokens,
    dump: DumpTokens,
    platform: PlatformTokens,
    multi_disc_total: int = 1,
) -> RenderedDestination:
    """Render the destination path the MOVE step will materialise.

    ``profile`` is duck-typed against
    :class:`_NamingProfileShape`; the project's
    :class:`romarr.profiles.models.NamingProfile` and its
    :class:`NamingProfileRead` schema both satisfy it.

    ``multi_disc_total`` lets the renderer toggle the per-game
    subfolder when ``profile.multi_disc_subfolder`` is true. Pass
    ``1`` for single-disc imports.
    """
    template = profile.template
    platform_subfolder = bool(getattr(profile, "platform_subfolder", True))
    multi_disc_subfolder = bool(
        getattr(profile, "multi_disc_subfolder", True)
    )
    replace_illegal = bool(getattr(profile, "replace_illegal_chars", True))

    rendered = engine.render(
        template,
        game=game,
        release=release,
        dump=dump,
        platform=platform,
        replace_illegal=replace_illegal,
    )
    rendered = rendered.strip().lstrip("/").lstrip("\\")
    if not rendered:
        raise ValueError(
            "rendered naming template produced an empty basename"
        )

    extension = dump.Extension.lstrip(".")
    basename = rendered

    parts: list[str] = [str(library_root)]
    if platform_subfolder and platform.Slug:
        parts.append(platform.Slug)
    if multi_disc_subfolder and multi_disc_total > 1:
        # Group all discs under one folder named after the canonical
        # game title (sort title preferred when present so localised
        # variants sort consistently).
        parts.append(_safe_dirname(game.SortTitle or game.Title))

    full_name = f"{basename}.{extension}" if extension else basename
    parts.append(full_name)

    return RenderedDestination(
        path=Path(*parts),
        basename=basename,
        extension=extension,
    )


def _safe_dirname(name: str) -> str:
    """Sanitise a directory name. The naming engine already
    sanitises the rendered template; we only handle the
    multi-disc subfolder which is built outside the engine."""
    name = name.strip()
    if not name:
        return "untitled"
    # Replace path separators and a few characters that are
    # platform-illegal (Windows + macOS); leave the rest alone.
    illegal = '<>:"/\\|?*'
    for ch in illegal:
        name = name.replace(ch, "_")
    return name


__all__ = ["RenderedDestination", "render_destination"]
