"""Worker runtime tests (plan §55, §57, §106, §9).

M0 runtime: acquire/maintain the lease, stand by when another fresh process
holds it, exit cleanly (0) on lease loss or shutdown, and exit non-zero on a
fatal error.
"""

from __future__ import annotations

import asyncio

from soloring.settings import Settings
from soloring.worker.ownership import (
    LeaseAcquisitionResult,
    acquire_worker_lease,
    read_lease,
)
from soloring.worker.runtime import WorkerExit, run_worker


def _fast(settings: Settings) -> Settings:
    # ttl shorter than refresh cadence so a non-refreshing owner goes stale and
    # a standby can take over deterministically.
    settings.worker_lease_ttl_seconds = 1
    settings.worker_lease_refresh_interval_seconds = 2
    settings.worker_poll_interval_seconds = 1
    return settings


async def test_worker_acquires_and_exits_clean_on_stop(settings, engine) -> None:
    _fast(settings)
    stop = asyncio.Event()
    wid = "worker-A"
    task = asyncio.create_task(run_worker(settings=settings, worker_id=wid, stop_event=stop))
    await asyncio.sleep(0.2)
    assert (await read_lease(engine)).worker_id == wid
    stop.set()
    result = await asyncio.wait_for(task, timeout=5)
    assert result == WorkerExit.CLEAN_STOP


async def test_worker_exits_clean_on_lease_loss(settings, engine) -> None:
    """A worker whose lease is taken over exits cleanly (plan §57, §9)."""
    _fast(settings)
    stop = asyncio.Event()
    wid_a = "worker-A"
    task = asyncio.create_task(run_worker(settings=settings, worker_id=wid_a, stop_event=stop))
    await asyncio.sleep(0.2)
    assert (await read_lease(engine)).worker_id == wid_a

    # Take the lease over by repeatedly acquiring until A has gone stale.
    async def takeover() -> None:
        while (await read_lease(engine)).worker_id != "worker-B":
            await acquire_worker_lease(engine, "worker-B", settings.worker_lease_ttl_seconds)
            await asyncio.sleep(0.05)

    await asyncio.wait_for(takeover(), timeout=6)
    # A's next refresh observes LOST and returns a clean lease-loss exit.
    result = await asyncio.wait_for(task, timeout=6)
    assert result == WorkerExit.CLEAN_LEASE_LOST
    assert (await read_lease(engine)).worker_id == "worker-B"


async def test_worker_standby_when_another_holds_lease(settings, engine) -> None:
    """When another fresh process owns the lease, the worker stands by (plan §55)."""
    # Keep a long TTL so the authoritative B never goes stale during the test.
    settings.worker_lease_ttl_seconds = 30
    settings.worker_lease_refresh_interval_seconds = 2
    settings.worker_poll_interval_seconds = 1
    await acquire_worker_lease(engine, "worker-B", ttl_seconds=30)

    stop = asyncio.Event()
    task = asyncio.create_task(
        run_worker(settings=settings, worker_id="worker-A", stop_event=stop)
    )
    await asyncio.sleep(0.4)
    # A must not have stolen the lease; B still owns it.
    assert (await read_lease(engine)).worker_id == "worker-B"
    stop.set()
    result = await asyncio.wait_for(task, timeout=5)
    assert result == WorkerExit.CLEAN_STOP
