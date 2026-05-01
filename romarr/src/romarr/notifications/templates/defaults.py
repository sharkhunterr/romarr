"""Default Jinja2 templates for the seven notification events.

Operator-supplied overrides live on the ``notification.*_format``
columns; an empty/null override falls back to the default below.
The variable namespaces are sourced from the corresponding
:class:`romarr.notifications.types` payload models — see each
template's signature for what's available.

Adjusted from spec ``data-model.md`` so the variable references
match the actual payload field shapes (e.g.,
``{{ game.platform_name }}`` rather than the doc's
``{{ platform.name }}`` shorthand — the dispatcher's payload
carries platform name + slug on the ``GameRef``, not in a
separate ``platform`` namespace).
"""

from __future__ import annotations

from romarr.notifications.types import EventType

DEFAULT_TEMPLATES: dict[EventType, str] = {
    EventType.ON_GRAB: (
        "🎯 Grabbed: {{ game.title }} ({{ release.region }}) "
        "— {{ release.name }} from {{ indexer.name }}"
    ),
    EventType.ON_IMPORT: (
        "✅ Imported: {{ game.title }} ({{ game.platform_name }}, "
        "{{ release.region }}) — DAT "
        "{{ '✓' if dump.dat_verified else '?' }}"
    ),
    EventType.ON_UPGRADE: (
        "⬆️ Upgraded: {{ game.title }} ({{ game.platform_name }}) "
        "— replaced '{{ old_release.name }}' with "
        "'{{ new_release.name }}'"
    ),
    EventType.ON_FAIL: (
        "❌ Failed: {{ release.name }} — {{ error_msg }}"
    ),
    EventType.ON_HEALTH_ISSUE: (
        "{{ '⚠️' if severity == 'warning' "
        "else ('🚨' if severity == 'error' else '✅') }} "
        "Health: {{ component }} — {{ message }}"
    ),
    EventType.ON_DAT_UPDATE: (
        "📥 DAT updated: {{ source }} {{ platform }} → "
        "{{ entries_count }} entries"
    ),
    EventType.ON_GAME_ADDED: (
        "➕ New game: {{ game.title }} ({{ game.platform_name }})"
    ),
}
"""Map :class:`EventType` to the default Jinja2 template string."""


__all__ = ["DEFAULT_TEMPLATES"]
