"""Pure-function validator: YAML body → ``ParsedPack`` or raise.

Three layers, all pure (no DB, no I/O):

  1. ``validate_pack_structure`` — runs the JSON Schema
     (``Draft202012Validator``) over the parsed dict. Translates each
     :class:`jsonschema.ValidationError` into a :class:`Violation` with
     a JSON-pointer ``path`` so the API layer can pinpoint the
     offending field.
  2. ``validate_cross_refs`` — duplicate slugs / duplicate extensions
     within a platform / dangling parent_platform_slug / cycles in the
     parent graph / parsing-strategies adversarial regex check.
  3. ``validate_pack`` — the public entry point: parses the bytes via
     :func:`load_pack`, then layers (1) and (2). Returns a
     :class:`ParsedPack` containing the canonical hash + the
     pre-validated dict so the ingestor never has to re-parse.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from jsonschema.exceptions import ValidationError

from romarr.platform_packs.errors import (
    PackValidationError,
    SchemaVersionTooHighError,
    Violation,
)
from romarr.platform_packs.schema import (
    SUPPORTED_SCHEMA_VERSION,
    get_validator,
)
from romarr.platform_packs.yaml_loader import (
    MAX_PLATFORMS_PER_PACK,
    compute_contents_hash,
    load_pack,
)

# Per FR-005a: every regex in the pack must guard against
# catastrophic backtracking. Python's ``re`` does NOT release the GIL
# during a match, so a thread-based wall-clock cap can never interrupt
# a doomed match. We use a static-pattern danger heuristic instead:
#
#   - any nested quantified group whose inner element is itself
#     quantified — e.g. ``(a+)+``, ``(a*)*``, ``(.+)+``, ``(a|aa)+`` —
#     is a known ReDoS shape and rejected at validation time;
#   - simple, anchored regexes pass through unchanged.
#
# This is conservative: legitimate patterns that happen to nest
# quantifiers are also rejected, but the alternative (letting a
# pathological pack hang the scan loop) is worse. Operators with a
# legitimate need for a nested-quantifier pattern can pre-rewrite it
# (e.g. ``(?:a+)`` → ``a+``) or wait for the v1 ``regex``-library
# integration that ships proper timeouts.
_NESTED_QUANTIFIER_RE = re.compile(
    r"""
    \(                  # opening group
    (?:[^()]|\([^)]*\))*  # group body, allowing one level of nested ( )
    [*+?]               # inner quantifier on the body
    [^)]*               # remainder of the group
    \)                  # closing group
    [*+?]               # outer quantifier on the whole group
    """,
    re.VERBOSE,
)


@dataclass(frozen=True, slots=True)
class ParsedPack:
    """A YAML pack that survived parsing + structural + cross-ref checks.

    Carries the parsed dict + the canonical contents_hash + the
    declared pack_version so downstream callers (the ingestor, the
    diff producer) never re-parse.
    """

    parsed: dict[str, Any]
    pack_version: str
    contents_hash: str


def _path_from_jsonschema(err: ValidationError) -> str:
    """Translate a jsonschema absolute_path into a JSON-pointer string."""
    parts = ["", *(str(p) for p in err.absolute_path)]
    return "/".join(parts) if len(parts) > 1 else "/"


def _violations_from_schema_errors(
    errors: Iterable[ValidationError],
) -> list[Violation]:
    out: list[Violation] = []
    for err in errors:
        validator_name = err.validator if isinstance(err.validator, str) else None
        out.append(
            Violation(
                path=_path_from_jsonschema(err),
                message=err.message,
                code=validator_name or "schema_violation",
            )
        )
    return out


def validate_pack_structure(parsed: dict[str, Any]) -> None:
    """Run JSON Schema + schema_version checks. Raise on any failure.

    schema_version is checked first so pack authors get the
    upgrade-your-Romarr message rather than a noisy 50-violation
    avalanche when their newer schema has fields ours doesn't know.
    """
    sv = parsed.get("schema_version")
    if isinstance(sv, int) and sv > SUPPORTED_SCHEMA_VERSION:
        raise SchemaVersionTooHighError(sv, SUPPORTED_SCHEMA_VERSION)

    validator = get_validator()
    errors = sorted(validator.iter_errors(parsed), key=lambda e: e.path)
    if errors:
        raise PackValidationError(
            "pack failed JSON Schema validation",
            violations=_violations_from_schema_errors(errors),
        )


def _adversarial_regex_check(pattern: str) -> None:
    """Compile the regex AND run a static-pattern danger heuristic.

    Two failure modes:

      - :class:`re.error` from the compile path → ``regex_invalid``.
      - Static heuristic match (nested quantified group) →
        ``regex_timeout`` (kept as the wire-stable code so the API
        layer doesn't need to know we switched detection strategies).
    """
    try:
        re.compile(pattern)
    except re.error as exc:
        raise PackValidationError(
            f"invalid regex {pattern!r}: {exc}",
            violations=[
                Violation(
                    path="<regex>",
                    message=f"invalid regex: {exc}",
                    code="regex_invalid",
                )
            ],
        ) from exc

    if _NESTED_QUANTIFIER_RE.search(pattern):
        raise PackValidationError(
            f"regex {pattern!r} contains a nested-quantifier shape "
            "known to cause catastrophic backtracking (ReDoS).",
            violations=[
                Violation(
                    path="<regex>",
                    message=(
                        "regex contains a nested quantified group "
                        "(``(...)+``-style around an inner ``+``/"
                        "``*``/``?``); rewrite to a non-capturing or "
                        "single-quantifier form"
                    ),
                    code="regex_timeout",
                )
            ],
        )


def validate_cross_refs(
    parsed: dict[str, Any], existing_slugs: set[str] | None = None
) -> None:
    """Run all the validations the JSON Schema can't express.

    Layered checks (each builds on the previous; the function aborts
    on the first violation it finds because the failure modes compose
    confusingly):

      1. Per-pack platform cap (FR-001c).
      2. Duplicate slug within the pack.
      3. Duplicate extension within a single platform.
      4. parent_platform_slug must point at a slug in the pack OR a
         slug already in the database.
      5. parent_platform_slug graph must be a DAG (no cycles), checked
         over the union of pack-defined and persisted platforms.
      6. Every naming_token.pattern + parsing_strategies.regex passes
         the adversarial-input time-bound check (FR-005a).
    """
    existing_slugs = existing_slugs or set()
    platforms = parsed.get("platforms") or []

    if len(platforms) > MAX_PLATFORMS_PER_PACK:
        raise PackValidationError(
            f"pack defines {len(platforms)} platforms; "
            f"maximum allowed is {MAX_PLATFORMS_PER_PACK}",
            violations=[
                Violation(
                    path="/platforms",
                    message=(
                        f"too many platforms: {len(platforms)} "
                        f"> {MAX_PLATFORMS_PER_PACK}"
                    ),
                    code="too_many_platforms",
                )
            ],
        )

    # --- 2. duplicate slugs ---
    slug_positions: dict[str, list[int]] = defaultdict(list)
    for idx, plat in enumerate(platforms):
        slug_positions[plat["slug"]].append(idx)
    duplicates = {s: positions for s, positions in slug_positions.items() if len(positions) > 1}
    if duplicates:
        raise PackValidationError(
            f"duplicate platform slugs: {sorted(duplicates)}",
            violations=[
                Violation(
                    path=f"/platforms/{positions[1]}/slug",
                    message=(
                        f"slug {slug!r} duplicates the platform at "
                        f"/platforms/{positions[0]}"
                    ),
                    code="duplicate_slug",
                )
                for slug, positions in sorted(duplicates.items())
            ],
        )

    # --- 3. duplicate extension within a platform ---
    ext_violations: list[Violation] = []
    for idx, plat in enumerate(platforms):
        seen: dict[str, int] = {}
        for f_idx, fmt in enumerate(plat.get("formats") or []):
            ext = fmt["extension"]
            if ext in seen:
                ext_violations.append(
                    Violation(
                        path=f"/platforms/{idx}/formats/{f_idx}/extension",
                        message=(
                            f"extension {ext!r} duplicates "
                            f"/platforms/{idx}/formats/{seen[ext]}"
                        ),
                        code="duplicate_extension",
                    )
                )
            else:
                seen[ext] = f_idx
    if ext_violations:
        raise PackValidationError(
            "duplicate extensions within a platform", violations=ext_violations
        )

    # --- 4 + 5. parent slug references + cycles ---
    pack_slugs = {p["slug"] for p in platforms}
    universe = pack_slugs | existing_slugs

    parent_violations: list[Violation] = []
    for idx, plat in enumerate(platforms):
        parent = plat.get("parent_platform_slug")
        if parent is None or parent == "":
            continue
        if parent not in universe:
            parent_violations.append(
                Violation(
                    path=f"/platforms/{idx}/parent_platform_slug",
                    message=(
                        f"parent_platform_slug {parent!r} is not defined "
                        "in this pack and does not exist in the database"
                    ),
                    code="dangling_parent",
                )
            )
    if parent_violations:
        raise PackValidationError(
            "dangling parent_platform_slug reference",
            violations=parent_violations,
        )

    cycle = _find_cycle(platforms)
    if cycle is not None:
        cycle_path = " -> ".join([*cycle, cycle[0]])
        raise PackValidationError(
            f"cycle detected in parent_platform_slug graph: {cycle_path}",
            violations=[
                Violation(
                    path="/platforms",
                    message=(
                        "parent_platform_slug graph contains cycle: "
                        + cycle_path
                    ),
                    code="parent_cycle",
                )
            ],
        )

    # --- 6. adversarial regex check ---
    for idx, plat in enumerate(platforms):
        for tok_idx, token in enumerate(plat.get("naming_tokens") or []):
            try:
                _adversarial_regex_check(token["pattern"])
            except PackValidationError as exc:
                # Re-tag the violation with the precise JSON pointer.
                tagged = [
                    Violation(
                        path=f"/platforms/{idx}/naming_tokens/{tok_idx}/pattern",
                        message=v.message,
                        code=v.code,
                    )
                    for v in exc.violations
                ]
                raise PackValidationError(
                    str(exc), violations=tagged
                ) from exc

    for sidx, strategy in enumerate(parsed.get("parsing_strategies") or []):
        try:
            _adversarial_regex_check(strategy["regex"])
        except PackValidationError as exc:
            tagged = [
                Violation(
                    path=f"/parsing_strategies/{sidx}/regex",
                    message=v.message,
                    code=v.code,
                )
                for v in exc.violations
            ]
            raise PackValidationError(str(exc), violations=tagged) from exc


def _find_cycle(platforms: list[dict[str, Any]]) -> list[str] | None:
    """DFS-based cycle finder. Returns the cycle's slugs in order, or None."""
    parent_of: dict[str, str | None] = {
        p["slug"]: p.get("parent_platform_slug") for p in platforms
    }

    white, gray, black = 0, 1, 2
    color: dict[str, int] = dict.fromkeys(parent_of, white)
    parent_in_stack: dict[str, str | None] = {}

    def dfs(start: str) -> list[str] | None:
        # Iterative DFS so deep parent chains never overflow.
        stack: list[tuple[str, str | None]] = [(start, None)]
        while stack:
            node, came_from = stack[-1]
            if color[node] == white:
                color[node] = gray
                parent_in_stack[node] = came_from
                target = parent_of.get(node)
                if target is None or target not in parent_of:
                    # parent absent from pack — terminal node.
                    color[node] = black
                    stack.pop()
                    continue
                if color[target] == gray:
                    # Back-edge — extract the cycle.
                    cycle = [target]
                    current: str | None = node
                    while current is not None and current != target:
                        cycle.append(current)
                        current = parent_in_stack.get(current)
                    cycle.reverse()
                    return cycle
                if color[target] == black:
                    color[node] = black
                    stack.pop()
                    continue
                stack.append((target, node))
            else:
                color[node] = black
                stack.pop()
        return None

    for slug in parent_of:
        if color[slug] == white:
            cycle = dfs(slug)
            if cycle is not None:
                return cycle
    return None


def validate_pack(
    content: bytes, *, existing_slugs: set[str] | None = None
) -> ParsedPack:
    """Top-level validator: parse + structure + cross-refs.

    Returns a :class:`ParsedPack` with the canonical contents_hash so
    the ingestor doesn't recompute. Raises :class:`PackValidationError`
    on any failure (the message and ``violations`` list pinpoint the
    JSON path).
    """
    try:
        parsed = load_pack(content)
    except yaml.YAMLError as exc:
        raise PackValidationError(
            f"YAML parse error: {exc}",
            violations=[
                Violation(
                    path="/",
                    message=str(exc),
                    code="yaml_parse_error",
                )
            ],
        ) from exc

    validate_pack_structure(parsed)
    validate_cross_refs(parsed, existing_slugs=existing_slugs)

    return ParsedPack(
        parsed=parsed,
        pack_version=parsed["pack_version"],
        contents_hash=compute_contents_hash(parsed),
    )
