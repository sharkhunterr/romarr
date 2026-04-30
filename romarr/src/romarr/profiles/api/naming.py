"""Naming profile CRUD + /preview — /api/v3/rom/namingprofile.

PUT and POST validate the supplied template through the sandbox
engine before persistence (FR-028 — fail at save). The /preview
endpoint renders a candidate template against an existing release
without persisting anything; admin-only since it can probe arbitrary
release IDs (FR-032a).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from romarr.api.dependencies import get_db, require_admin
from romarr.auth import Principal
from romarr.profiles.api._shared import make_crud_router
from romarr.profiles.errors import (
    SandboxViolationError,
    TemplateSyntaxError,
    TemplateUnknownTokenError,
)
from romarr.profiles.models import NamingProfile
from romarr.profiles.naming import (
    DumpTokens,
    GameTokens,
    NamingTemplateEngine,
    PlatformTokens,
    ReleaseTokens,
)
from romarr.profiles.schemas import (
    NamingPreviewRequest,
    NamingProfileCreate,
    NamingProfileRead,
    NamingProfileUpdate,
)
from romarr.profiles.types import NamingPreviewResponse

# Build the standard CRUD surface; /preview is appended below.
router: APIRouter = make_crud_router(
    label="namingprofile",
    base_path="/api/v3/rom/namingprofile",
    tag="NamingProfiles",
    model_cls=NamingProfile,
    schema_read=NamingProfileRead,
    schema_create=NamingProfileCreate,
    schema_update=NamingProfileUpdate,
)


_ENGINE = NamingTemplateEngine()


class _PreviewSampleRelease(BaseModel):
    """Synthetic release facts used when no DB row matches the requested
    sample id — keeps preview useful in fresh deployments where the
    library is empty.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    game: GameTokens = GameTokens(
        Title="Sonic the Hedgehog",
        SortTitle="Sonic the Hedgehog",
        Year="1991",
        Publisher="Sega",
    )
    release: ReleaseTokens = ReleaseTokens(
        Region="USA",
        Languages="en",
        Revision="",
        Tags="[!]",
        OriginalName="Sonic the Hedgehog (USA).md",
    )
    dump: DumpTokens = DumpTokens(Extension="md", Hash="abc123")
    platform: PlatformTokens = PlatformTokens(Slug="megadrive", Name="Mega Drive")


@router.post(
    "/preview",
    response_model=NamingPreviewResponse,
    summary=(
        "Render a candidate naming template against a sample release "
        "without persisting (admin only). Returns the rendered filename."
    ),
)
async def preview_template(
    payload: NamingPreviewRequest,
    _admin: Annotated[Principal, Depends(require_admin)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NamingPreviewResponse:
    """Render the supplied template against the sample release.

    Spec 001's ``Release`` table will land before spec 006's preview
    is wired against real rows; today we use a synthetic sample so
    operators can iterate on templates the moment they install.
    Once the search engine slice exposes a release-fetch helper, this
    endpoint will look up ``payload.sample_release_id`` and replace
    the synthetic facts with the real ones.
    """
    del db  # session unused while sample_release_id is synthetic
    sample = _PreviewSampleRelease()
    try:
        rendered = _ENGINE.render(
            payload.profile.template,
            game=sample.game,
            release=sample.release,
            dump=sample.dump,
            platform=sample.platform,
            replace_illegal=payload.profile.replace_illegal_chars,
        )
    except (
        TemplateSyntaxError,
        TemplateUnknownTokenError,
        SandboxViolationError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "errorMessage": "template_invalid",
                "errorCode": "template_invalid",
                "details": str(exc),
            },
        ) from exc

    return NamingPreviewResponse(rendered=rendered)
