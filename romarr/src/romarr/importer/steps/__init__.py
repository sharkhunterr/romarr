"""Pipeline steps for the importer (spec 008).

Each step is a small, focused module — typically a pure function
or a tightly-scoped helper — that the orchestrator threads
together inside :func:`run_import`.

Slices 2-3 ship the pure / wrapper steps:
  * ``multi_disc`` — cue/bin / filename-pattern / side-letter
    detection (slice 2).
  * ``profile_gate`` — composes spec 006's ``ProfileEvaluator``
    (slice 2).
  * ``render`` — composes spec 006's ``NamingTemplateEngine``
    (slice 2).
  * ``hash_step`` — walks the extracted dir and hashes via spec
    001's ``Hasher`` in a threadpool (slice 3).
  * ``dat_match`` — wraps spec 001's ``HashMatchCascade``
    (slice 3).
  * ``identify`` — wraps spec 001's ``Identifier`` (slice 3).

Subsequent slices add ``extract``, ``game_match``, ``move``,
``db_update``, ``lifecycle``, ``notify``.
"""

from romarr.importer.steps.dat_match import DatMatchResult, match_dat
from romarr.importer.steps.hash_step import FormatRule, hash_candidates
from romarr.importer.steps.identify import identify_file
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
    "DatMatchResult",
    "DiscMember",
    "FormatRule",
    "MultiDiscGroup",
    "ProfileGateResult",
    "RenderedDestination",
    "apply_profile_gate",
    "detect_multi_disc",
    "hash_candidates",
    "identify_file",
    "match_dat",
    "parse_cue_referenced_files",
    "render_destination",
]
