"""HTTP middleware modules (spec 013 phase MW).

Each submodule exposes a single ``register(app, *, ...)`` function
that the application factory calls during startup. Keeping each
piece in its own module makes ordering explicit (the factory
applies them in the documented stack order) and makes the units
independently testable.
"""

from romarr.api.middleware.cors import register_cors
from romarr.api.middleware.gzip import register_gzip
from romarr.api.middleware.idempotency import register_idempotency

__all__ = ["register_cors", "register_gzip", "register_idempotency"]
