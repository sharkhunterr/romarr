"""``romarr`` CLI entry point.

Ships only the ``metadata reencrypt`` sub-command stub at this slice
(spec 002 T067). Future specs add ``setup``, ``backup``, ``library``,
etc. — each as its own sub-parser.
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

    if args.command == "metadata" and args.metadata_command == "reencrypt":
        return _metadata_reencrypt(args)

    parser.print_help()
    return 2


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
