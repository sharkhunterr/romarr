"""Sandboxed Jinja2 template engine for naming profiles (FR-024..FR-028).

The engine is a thin shell around
:class:`jinja2.sandbox.ImmutableSandboxedEnvironment` that:

  1. clears the default filter / test / global dicts and registers
     ONLY the four allowed filters (FR-025);
  2. overrides ``is_safe_attribute`` to consult
     :data:`romarr.profiles.naming.tokens.TOKEN_WHITELIST` so attribute
     access is rejected at RENDER time even if the AST walk missed it;
  3. parses every operator-supplied template at SAVE time and walks
     the AST to reject unknown top-level names, unknown attribute
     accesses on the four namespaces, and unknown filter calls
     (FR-028 — fail at save, not at render); and
  4. renders the result through
     :func:`romarr.profiles.naming.postprocess.postprocess` so the
     filename is safe for the filesystem (FR-026, FR-027).

Why ImmutableSandboxedEnvironment and not the bare SandboxedEnvironment?
The frozen Pydantic namespaces already make the context immutable,
but ``ImmutableSandboxedEnvironment`` ALSO blocks call attempts on
non-whitelisted callables — so if an operator manages to slip a
callable token through a future code change, render still raises
rather than executing it. Defence-in-depth.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from jinja2 import nodes
from jinja2.exceptions import SecurityError, UndefinedError
from jinja2.exceptions import TemplateSyntaxError as _JinjaTemplateSyntaxError
from jinja2.sandbox import ImmutableSandboxedEnvironment

from romarr.profiles.errors import (
    SandboxViolationError,
    TemplateSyntaxError,
    TemplateUnknownTokenError,
)
from romarr.profiles.naming.filters import ALLOWED_FILTERS
from romarr.profiles.naming.postprocess import postprocess
from romarr.profiles.naming.tokens import (
    TOKEN_WHITELIST,
    DumpTokens,
    GameTokens,
    PlatformTokens,
    ReleaseTokens,
)

if TYPE_CHECKING:
    from jinja2.environment import Template

_ALLOWED_NAMESPACES = frozenset(TOKEN_WHITELIST)


class _RomarrSandbox(ImmutableSandboxedEnvironment):
    """Jinja sandbox with the per-namespace attribute whitelist enforced.

    The default sandbox blocks dunder access; we additionally require
    that any non-dunder attr be on the documented allowlist for the
    object's namespace class.
    """

    def is_safe_attribute(self, obj: object, attr: str, value: object) -> bool:
        if attr.startswith("_"):
            return False
        cls_name = type(obj).__name__.removesuffix("Tokens")
        allowed = TOKEN_WHITELIST.get(cls_name)
        if allowed is None:
            return False
        return attr in allowed


def _build_env() -> _RomarrSandbox:
    env = _RomarrSandbox(autoescape=False)
    # Clear Jinja's default surface area so operators can't reach
    # ``length``, ``default``, ``join``, ``string``, ``escape``, …
    env.filters.clear()
    env.tests.clear()
    env.globals.clear()
    for name, fn in ALLOWED_FILTERS.items():
        env.filters[name] = fn
    return env


# Module-level env — building it is cheap but reuse keeps render
# performance under the < 1 ms budget called out in plan.md.
_ENV = _build_env()


class NamingTemplateEngine:
    """Validate-at-save, render-at-import naming engine.

    Stateless after construction — the env is module-level, so a
    single instance suffices for the whole process. Tests construct
    fresh instances anyway because it's free.
    """

    def __init__(self) -> None:
        self._env = _ENV

    # ---- save-time validation (FR-028) -----------------------------------

    def validate(self, template: str) -> None:
        """Parse and walk the AST. Raises a structured error on rejection.

        Catches three classes of operator typos before they ever land
        in a render hot-path:

          * ``TemplateSyntaxError`` — Jinja couldn't parse the source.
          * ``TemplateUnknownTokenError`` — the template references a
            top-level name that isn't ``Game`` / ``Release`` / ``Dump`` /
            ``Platform``, OR an attribute that isn't on the documented
            allowlist for its namespace.
          * ``SandboxViolationError`` — the template uses a filter
            outside the four-allowed set, or invokes anything callable.
        """
        try:
            tree = self._env.parse(template)
        except _JinjaTemplateSyntaxError as exc:
            raise TemplateSyntaxError(
                f"template parse failed: {exc.message} (line {exc.lineno})"
            ) from exc

        for name_node in tree.find_all((nodes.Name,)):
            if not isinstance(name_node, nodes.Name):  # pragma: no cover
                continue
            if (
                name_node.ctx == "load"
                and name_node.name not in _ALLOWED_NAMESPACES
            ):
                raise TemplateUnknownTokenError(
                    f"unknown top-level token {name_node.name!r} — allowed: "
                    f"{sorted(_ALLOWED_NAMESPACES)!r}"
                )

        for getattr_node in tree.find_all((nodes.Getattr,)):
            if not isinstance(getattr_node, nodes.Getattr):  # pragma: no cover
                continue
            target = getattr_node.node
            if isinstance(target, nodes.Name) and target.name in _ALLOWED_NAMESPACES:
                allowed = TOKEN_WHITELIST[target.name]
                if getattr_node.attr not in allowed:
                    raise TemplateUnknownTokenError(
                        f"unknown attribute {target.name}.{getattr_node.attr!r} — "
                        f"allowed for {target.name}: {sorted(allowed)!r}"
                    )

        for filter_node in tree.find_all((nodes.Filter,)):
            if (
                isinstance(filter_node, nodes.Filter)
                and filter_node.name not in ALLOWED_FILTERS
            ):
                raise SandboxViolationError(
                    f"filter {filter_node.name!r} is not on the allowlist; "
                    f"allowed filters: {sorted(ALLOWED_FILTERS)!r}"
                )

        # Calls (other than filter calls) are forbidden — operator
        # templates must not invoke anything on the namespace tokens.
        for call_node in tree.find_all((nodes.Call,)):
            if isinstance(call_node, nodes.Call):
                raise SandboxViolationError(
                    "function/method invocation is not allowed in naming templates"
                )

    # ---- render (validates then runs through postprocess) ----------------

    def render(
        self,
        template: str,
        *,
        game: GameTokens,
        release: ReleaseTokens,
        dump: DumpTokens,
        platform: PlatformTokens,
        replace_illegal: bool = True,
    ) -> str:
        """Render ``template`` with the given namespace objects.

        Validates the template first so operator-edited rows that
        slipped past the API surface still fail with the same
        structured error rather than a Jinja exception.
        """
        self.validate(template)
        compiled: Template = self._env.from_string(template)
        try:
            rendered = compiled.render(
                Game=game, Release=release, Dump=dump, Platform=platform
            )
        except SecurityError as exc:
            raise SandboxViolationError(
                f"sandbox security violation at render time: {exc}"
            ) from exc
        except UndefinedError as exc:
            # Strict-undefined is the default in ImmutableSandboxedEnvironment;
            # treat as a rendering-time signal of an unreachable token.
            raise TemplateUnknownTokenError(
                f"undefined token at render time: {exc}"
            ) from exc

        return postprocess(rendered, replace_illegal=replace_illegal)


# ---------------------------------------------------------------------------
# Public re-exports
# ---------------------------------------------------------------------------


_ = Any  # Pydantic re-exports a type; keep ``Any`` referenced for ruff-T


__all__ = ["NamingTemplateEngine"]
