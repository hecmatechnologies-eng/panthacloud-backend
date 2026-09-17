"""Task registry and cooperative cancellation token management.

Provides in-memory tracking of active long-running asyncio tasks (such as integration
pipeline runs and repository analyses). Enables cooperative cancellation via asyncio.Event
tokens and explicit task cancellation, preventing orphan background workloads and race
conditions on state updates.
"""

import asyncio
import logging
import uuid
from typing import Final

logger = logging.getLogger("fussion.core.tasks")

_ACTIVE_TASKS: Final[dict[uuid.UUID, asyncio.Task[object]]] = {}
_CANCELLATION_EVENTS: Final[dict[uuid.UUID, asyncio.Event]] = {}
_REGISTRY_LOCK: Final[asyncio.Lock] = asyncio.Lock()


async def register_task(
    run_id: uuid.UUID,
    task: asyncio.Task[object],
    cancel_event: asyncio.Event | None = None,
) -> None:
    """Register an active task and its optional cooperative cancellation token."""
    async with _REGISTRY_LOCK:
        _ACTIVE_TASKS[run_id] = task
        if cancel_event is not None:
            _CANCELLATION_EVENTS[run_id] = cancel_event

    def _cleanup(_: asyncio.Task[object]) -> None:
        asyncio.create_task(unregister_task(run_id))

    task.add_done_callback(_cleanup)


async def unregister_task(run_id: uuid.UUID) -> None:
    """Remove a task from the active registry once completed, cancelled, or failed."""
    async with _REGISTRY_LOCK:
        _ACTIVE_TASKS.pop(run_id, None)
        _CANCELLATION_EVENTS.pop(run_id, None)


async def cancel_task(run_id: uuid.UUID) -> bool:
    """Signal cooperative cancellation token and issue asyncio.Task.cancel().

    Returns True if the task was found and cancellation was requested, False otherwise.
    """
    async with _REGISTRY_LOCK:
        cancel_event = _CANCELLATION_EVENTS.get(run_id)
        if cancel_event is not None:
            cancel_event.set()

        task = _ACTIVE_TASKS.get(run_id)
        if task is not None and not task.done():
            task.cancel()
            logger.info("Cancellation requested for active task %s", run_id)
            return True

    return False


async def is_cancelled(run_id: uuid.UUID) -> bool:
    """Check whether a cooperative cancellation event has been signaled for run_id."""
    async with _REGISTRY_LOCK:
        event = _CANCELLATION_EVENTS.get(run_id)
        return event.is_set() if event is not None else False


def create_cancellation_event() -> asyncio.Event:
    """Create a fresh cancellation token."""
    return asyncio.Event()
