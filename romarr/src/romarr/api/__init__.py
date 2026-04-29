"""HTTP API surface — FastAPI app + routers (specs 010 + 013).

The auth router lands here in this slice; later specs (003 / 004 /
005 / 006 / 007 / 008 / 009 / 011 / 012 / 013) register their own
routers under the same app via :func:`create_app`.
"""

from romarr.api.app import create_app

__all__ = ["create_app"]
