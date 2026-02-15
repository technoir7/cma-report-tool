"""
Request context management.

Holds thread-local/async-local state for the current request's Run ID.
"""

from contextvars import ContextVar
from uuid import UUID

# Current Run ID for the request context
_run_id_ctx: ContextVar[str | None] = ContextVar("run_id", default=None)


def get_run_id() -> str | None:
    """Get the current request's Run ID."""
    return _run_id_ctx.get()


def set_run_id(run_id: str):
    """Set the current request's Run ID."""
    _run_id_ctx.set(run_id)


def reset_run_id():
    """Reset the current request's Run ID."""
    _run_id_ctx.set(None)
