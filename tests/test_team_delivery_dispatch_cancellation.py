"""Repeated cancellation cannot release a delivery while its real worker thread is active."""
import asyncio
import threading

import pytest

from core.delivery_management.domain import DeliveryPhase
from core.project_setup.delivery import DeliveryRequest
from tests.test_team_delivery_dispatch import ControlledBranchExecutor, prepared


async def event_loop_barrier() -> None:
    processed = asyncio.Event()
    asyncio.get_running_loop().call_soon(processed.set)
    await processed.wait()


@pytest.mark.asyncio
async def test_repeated_cancellation_keeps_worker_ownership_until_thread_finishes(tmp_path):
    engine = ControlledBranchExecutor()
    engine.barrier = threading.Barrier(2)
    handoff, app, _ = await prepared(tmp_path, engine)
    request = DeliveryRequest(handoff, "catalogue")
    task = asyncio.create_task(app.deliveries.dispatch(request))
    await asyncio.to_thread(engine.barrier.wait, 30)
    try:
        task.cancel()
        await event_loop_barrier()
        task.cancel()
        await event_loop_barrier()
        assert not task.done(), "dispatch released ownership while its worker thread was still running"
        duplicate = await app.deliveries.resume(request)
        assert duplicate.phase == DeliveryPhase.RUNNING
        assert len(engine.calls) == 1
    finally:
        engine.release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    completed = await app.deliveries.dispatch(request)
    assert completed.phase == DeliveryPhase.COMPLETE
    assert len(engine.calls) == 1
