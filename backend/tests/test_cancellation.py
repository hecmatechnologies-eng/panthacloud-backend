import asyncio
import uuid

import pytest

from app.core.tasks import (
    cancel_task,
    create_cancellation_event,
    is_cancelled,
    register_task,
    unregister_task,
)


@pytest.mark.asyncio
async def test_task_registration_and_cancellation():
    run_id = uuid.uuid4()
    cancel_event = create_cancellation_event()

    task_executed = False
    cancelled_observed = False

    async def sample_coro():
        nonlocal task_executed, cancelled_observed
        task_executed = True
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            cancelled_observed = True
            raise

    task = asyncio.create_task(sample_coro())
    await register_task(run_id, task, cancel_event)

    # Yield control to event loop so sample_coro enters execution
    await asyncio.sleep(0.01)

    assert not await is_cancelled(run_id)

    # Trigger cancellation
    cancelled = await cancel_task(run_id)
    assert cancelled is True
    assert await is_cancelled(run_id)

    with pytest.raises(asyncio.CancelledError):
        await task

    assert task_executed is True
    assert cancelled_observed is True


@pytest.mark.asyncio
async def test_cancel_nonexistent_task():
    random_id = uuid.uuid4()
    cancelled = await cancel_task(random_id)
    assert cancelled is False
    assert not await is_cancelled(random_id)


@pytest.mark.asyncio
async def test_task_auto_unregisters_on_completion():
    run_id = uuid.uuid4()

    async def quick_coro():
        return 42

    task = asyncio.create_task(quick_coro())
    await register_task(run_id, task)

    result = await task
    assert result == 42

    # Give done_callback a moment to run
    await asyncio.sleep(0.01)
    assert not await is_cancelled(run_id)


@pytest.mark.asyncio
async def test_explicit_unregister():
    run_id = uuid.uuid4()
    task = asyncio.create_task(asyncio.sleep(1))
    await register_task(run_id, task)
    await unregister_task(run_id)
    assert not await is_cancelled(run_id)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
