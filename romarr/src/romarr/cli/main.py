"""``romarr`` CLI entry point.

Sub-commands:

  - ``serve`` — boot the FastAPI app via uvicorn. Honours the
    ``ROMARR_BOOTSTRAP_ENABLED``, ``ROMARR_SCHEDULER_ENABLED``,
    and ``ROMARR_AUTO_MIGRATE`` env-driven settings flags.
  - ``migrate`` — run alembic ``upgrade head`` against the
    configured database. Equivalent to the ``alembic upgrade
    head`` CLI but doesn't require the alembic binary on PATH.
  - ``metadata reencrypt`` — rotate the encryption master key
    (spec 002 stub, full impl deferred to 0.2).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="romarr",
        description="Self-hosted ROM acquisition manager",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # serve — uvicorn bootstrap
    serve = sub.add_parser(
        "serve",
        help="Boot the FastAPI app under uvicorn.",
    )
    serve.add_argument(
        "--host",
        default="0.0.0.0",
        help="Bind host (default 0.0.0.0).",
    )
    serve.add_argument(
        "--port",
        type=int,
        default=8585,
        help="Bind port (default 8585 — Romarr's reserved port).",
    )
    serve.add_argument(
        "--reload",
        action="store_true",
        help="Enable uvicorn auto-reload (development only).",
    )
    serve.add_argument(
        "--log-level",
        default="info",
        choices=("critical", "error", "warning", "info", "debug", "trace"),
        help="uvicorn log level (default info).",
    )

    # migrate — alembic upgrade-head
    migrate = sub.add_parser(
        "migrate",
        help="Run ``alembic upgrade head`` against the configured database.",
    )
    migrate.add_argument(
        "--database-url",
        default=None,
        help=(
            "Override ``ROMARR_DATABASE_URL`` for this run. "
            "Defaults to whatever the Settings layer resolves."
        ),
    )

    # metadata reencrypt — preserved from earlier slices
    metadata = sub.add_parser(
        "metadata",
        help="Metadata-aggregation administration commands",
    )
    metadata_sub = metadata.add_subparsers(dest="metadata_command", required=True)

    reencrypt = metadata_sub.add_parser(
        "reencrypt",
        help=(
            "Rotate the master encryption key for stored provider "
            "credentials. Decrypts every encrypted row with the OLD "
            "key, re-encrypts with the NEW key, in a single transaction."
        ),
    )
    reencrypt.add_argument(
        "--old-key",
        required=True,
        help="The current ROMARR_AUTH_SECRET_KEY value.",
    )
    reencrypt.add_argument(
        "--new-key",
        required=True,
        help="The new ROMARR_AUTH_SECRET_KEY value to roll forward to.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch a CLI invocation. Returns the process exit code."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "serve":
        return _serve(args)
    if args.command == "migrate":
        return _migrate(args)
    if args.command == "metadata" and args.metadata_command == "reencrypt":
        return _metadata_reencrypt(args)

    parser.print_help()
    return 2


def _serve(args: argparse.Namespace) -> int:
    """Boot the FastAPI app via uvicorn.

    Runs ``alembic upgrade head`` first when
    ``ROMARR_AUTO_MIGRATE=true`` is set — the lifespan can't
    do this itself because Alembic's env.py drives its own
    ``asyncio.run`` loop which conflicts with uvicorn's.
    """
    from romarr.config.settings import get_settings

    settings = get_settings()
    if settings.auto_migrate:
        from romarr.db.migrations import upgrade_head_sync

        try:
            upgrade_head_sync(settings.database_url)
        except Exception as exc:
            print(
                f"romarr serve: pre-boot migrate failed: "
                f"{exc.__class__.__name__}: {exc}",
                file=sys.stderr,
            )
            return 1

    import uvicorn

    uvicorn.run(
        "romarr.api.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level=args.log_level,
    )
    return 0


def _migrate(args: argparse.Namespace) -> int:
    """Run ``alembic upgrade head`` synchronously."""
    from romarr.db.migrations import upgrade_head_sync

    try:
        upgrade_head_sync(args.database_url)
    except Exception as exc:
        print(f"romarr migrate: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1
    print("romarr migrate: alembic upgrade head OK")
    return 0


def _metadata_reencrypt(args: argparse.Namespace) -> int:
    """Stub for the rotation flow. Full implementation lands in a
    follow-up slice once the auth-spec key-management layer ships."""
    raise NotImplementedError(
        "rotation implemented in 0.2 — the reencrypt CLI stub is in "
        "place so callers can target a stable interface, but the "
        "decrypt-old → re-encrypt-new transaction lands in a follow-up "
        "slice once the auth-spec key-management surface stabilises."
    )


if __name__ == "__main__":  # pragma: no cover — direct ``python -m`` entry
    sys.exit(main())
