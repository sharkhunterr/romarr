"""FastAPI routers for the tasks subsystem (spec 012)."""

from romarr.tasks.api.command import router as command_router
from romarr.tasks.api.runs import router as runs_router
from romarr.tasks.api.tasks import router as tasks_router

__all__ = ["command_router", "runs_router", "tasks_router"]
