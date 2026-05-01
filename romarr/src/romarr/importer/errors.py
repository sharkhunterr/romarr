"""Domain errors for the importer subsystem (spec 008).

Domain-specific exception names per Article XII; the
``noqa: N818`` markers acknowledge that a few of these names
intentionally diverge from the ruff ``…Error`` convention because
they read more naturally on the call site (``raise GameNotMatched``
mirrors the pipeline-step vocabulary the spec uses).
"""

from __future__ import annotations


class ImporterError(Exception):
    """Base class for every domain-level importer failure."""


class ExtractError(ImporterError):
    """Archive extraction failed (depth-exceeded, bomb, corrupt, etc.).

    The ``rejection_reason`` attribute carries the structured
    ``extract:<sub-reason>`` code for the ``unidentified_dump`` row.
    """

    def __init__(self, message: str, *, rejection_reason: str) -> None:
        super().__init__(message)
        self.rejection_reason = rejection_reason


class MoveError(ImporterError):
    """The atomic-move step failed.

    Typically a permission error, a disk-full condition, or — most
    importantly — a post-copy hash mismatch (FR-018).
    ``rejection_reason`` carries the ``move:<sub-reason>`` code.
    """

    def __init__(self, message: str, *, rejection_reason: str) -> None:
        super().__init__(message)
        self.rejection_reason = rejection_reason


class GameNotMatched(ImporterError):  # noqa: N818 — domain-specific name
    """Identification could not associate the file with a Game above
    the confidence threshold (FR-013). The orchestrator parks the
    file in ``unidentified_dump`` with
    ``rejection_reason='match:no_game'``."""


class ProfileRejected(ImporterError):  # noqa: N818 — domain-specific name
    """A profile gate (Region / Quality / Dump / Language) refused
    the file. ``rejection_reason`` carries the structured
    ``profile:<gate>:<sub-reason>`` code so the operator can see
    which profile rejected and why."""

    def __init__(self, message: str, *, rejection_reason: str) -> None:
        super().__init__(message)
        self.rejection_reason = rejection_reason


class LockTimeout(ImporterError):  # noqa: N818 — domain-specific name
    """The 60-second per-(release_id, sha1) lock could not be
    acquired (FR-034). The caller records the failure as
    ``rejection_reason='lock:timeout'`` and the import is
    retry-eligible."""


class WebhookAuthError(ImporterError):
    """The webhook endpoint received a request whose
    ``X-Romarr-Webhook-Token`` header didn't match the configured
    bearer (FR-002). The handler returns HTTP 401 without logging
    the expected token."""
