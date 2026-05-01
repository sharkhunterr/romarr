"""FastAPI routers for the notifications + health subsystem (spec 011)."""

from romarr.notifications.api.health import router as health_router
from romarr.notifications.api.notifications import (
    router as notifications_router,
)
from romarr.notifications.api.webhook_payloads_md import (
    router as webhook_payloads_md_router,
)

__all__ = [
    "health_router",
    "notifications_router",
    "webhook_payloads_md_router",
]
