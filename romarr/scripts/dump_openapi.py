"""Dump the backend's OpenAPI 3.1 spec to ``web/openapi.json``.

The frontend's codegen (`pnpm codegen` in `web/`) reads this file
to emit TypeScript types via ``openapi-typescript``. Committing
the JSON snapshot keeps frontend builds reproducible — they
don't need a running backend to type-check.

Usage::

    uv run python scripts/dump_openapi.py

Re-run after any change to the FastAPI route surface; CI can
diff the committed JSON against a fresh dump to catch drift
(see spec 014 T014).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    # Importing here keeps the script a one-shot CLI rather than a
    # module that pulls in romarr at collection time.
    from romarr.api import create_app

    app = create_app()
    schema = app.openapi()

    target = Path(__file__).resolve().parent.parent / "web" / "openapi.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {target.relative_to(target.parent.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
