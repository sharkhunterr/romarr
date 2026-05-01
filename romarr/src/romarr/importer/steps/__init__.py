"""Pipeline steps for the importer (spec 008).

Each step is a small, focused module — typically a pure function
or a tightly-scoped helper — that the orchestrator threads
together inside :func:`run_import`.

Slice 2 (this slice) ships:
  * ``multi_disc`` — cue/bin / filename-pattern / side-letter
    detection.
  * ``profile_gate`` — composes spec 006's ``ProfileEvaluator``.
  * ``render`` — composes spec 006's ``NamingTemplateEngine``.

Subsequent slices add ``hash``, ``dat_match``, ``identify``,
``game_match``, ``move``, ``db_update``, ``lifecycle``, ``notify``.
"""

from romarr.importer.steps.multi_disc import (
    DiscMember,
    MultiDiscGroup,
    detect_multi_disc,
    parse_cue_referenced_files,
)
from romarr.importer.steps.profile_gate import (
    ProfileGateResult,
    apply_profile_gate,
)
from romarr.importer.steps.render import (
    RenderedDestination,
    render_destination,
)

__all__ = [
    "DiscMember",
    "MultiDiscGroup",
    "ProfileGateResult",
    "RenderedDestination",
    "apply_profile_gate",
    "detect_multi_disc",
    "parse_cue_referenced_files",
    "render_destination",
]
