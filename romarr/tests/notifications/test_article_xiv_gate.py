"""Article XIV transport-dependency gate (T074).

Constitution Article XIV mandates Apprise as the single
notification transport. This module statically scans
``src/romarr/notifications/`` to confirm no ad-hoc
per-service transport library snuck in via a future PR.

Allowed transport-layer dependencies in this module:

  * ``apprise`` — the unified Apprise backend.
  * ``httpx`` — used by the Sonarr-format webhook target
    (``webhook.py``); httpx is a generic HTTP client, not a
    "Discord-specific" or "Telegram-specific" library, so
    it's compatible with Article XIV's "no per-service
    integrations" intent.
  * ``tenacity`` — generic retry library for the webhook
    backoff schedule.
  * Standard library + project-internal imports.

Forbidden:

  * ``discord``, ``discord-py``, ``discord.py``
  * ``python-telegram-bot``, ``telegram``
  * ``slack-sdk``, ``slack_sdk``
  * ``requests`` (synchronous HTTP — should never appear here)
  * Anything else marketed as a service-specific notification
    SDK.
"""

from __future__ import annotations

import re
from pathlib import Path

# Patterns the gate refuses. The list is intentionally broad
# so a future "let's just add the official Discord SDK"
# proposal trips the test before the diff lands.
FORBIDDEN_IMPORT_PATTERNS: tuple[str, ...] = (
    r"^\s*(?:from|import)\s+discord(?:_py|\.py)?\b",
    r"^\s*(?:from|import)\s+telegram\b",
    r"^\s*(?:from|import)\s+python_telegram_bot\b",
    r"^\s*(?:from|import)\s+slack_sdk\b",
    r"^\s*(?:from|import)\s+slack\b",
    r"^\s*(?:from|import)\s+requests\b",
    r"^\s*(?:from|import)\s+pushover\b",
    r"^\s*(?:from|import)\s+gotify\b",
    r"^\s*(?:from|import)\s+ntfy\b",
)


def _notifications_src_dir() -> Path:
    """Walk up to find ``src/romarr/notifications/``."""
    here = Path(__file__).resolve()
    for ancestor in here.parents:
        candidate = ancestor / "src" / "romarr" / "notifications"
        if candidate.is_dir():
            return candidate
    raise RuntimeError(
        "could not locate src/romarr/notifications/ relative to "
        f"{here}"
    )


def _python_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def test_no_forbidden_transport_imports() -> None:
    """Article XIV gate. Walks every ``.py`` file under
    ``src/romarr/notifications/`` and asserts no forbidden
    import line appears. The patterns match the line head so
    embedded references in docstrings / strings don't cause
    false positives."""
    forbidden = [re.compile(p) for p in FORBIDDEN_IMPORT_PATTERNS]
    offenders: list[tuple[Path, int, str]] = []
    for path in _python_files(_notifications_src_dir()):
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for pattern in forbidden:
                if pattern.match(line):
                    offenders.append((path, lineno, line))
    assert offenders == [], (
        "Article XIV gate violated — per-service transport "
        "library imported under src/romarr/notifications/. "
        "Use Apprise instead. Offenders:\n  "
        + "\n  ".join(
            f"{path}:{lineno}: {line.strip()}"
            for path, lineno, line in offenders
        )
    )


def test_apprise_is_the_only_transport_library() -> None:
    """Sanity: Apprise IS imported somewhere under the
    notifications package — otherwise the gate above is
    vacuous (nothing to check)."""
    apprise_seen = False
    pattern = re.compile(r"^\s*import\s+apprise\b")
    for path in _python_files(_notifications_src_dir()):
        if any(
            pattern.match(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ):
            apprise_seen = True
            break
    assert apprise_seen, (
        "Apprise import not found under src/romarr/notifications/ "
        "— the Article XIV gate has nothing to enforce."
    )
