"""Worker runtime loop (plan §8, §48–§67).

M0 scope: acquire and maintain the singleton lease, stand by when another fresh
process holds it, and exit cleanly on lease loss or shutdown. There is no
queue/executor work yet — ``claim_next_generation`` and real reconciliation
arrive in M3B. The unconditional reconciliation call site (plan §54) is in place
but is a no-op until ``generations`` exists (M1).
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncEngine

from soloring.db.engine import create_soloring_engine
from soloring.settings import Settings, get_settings
from soloring.worker.ownership import (
    LEASE_NAME,
    LeaseAcquisitionResult,
    LeaseRetentionResult,
    acquire_worker_lease,
    refresh_worker_lease,
)
from soloring.worker.recovery import reconcile_stale_generations

log = logging.getLogger("soloring.worker")


def new_worker_id() -> str:
    """Generate a fresh ephemeral worker ID (plan §8).

    Exactly ``str(uuid.uuid4())``. Not configurable, not loaded from the
    environment, not persisted, not derived from hostname/PID/machine identity.
    """
    return str(uuid.uuid4())


class WorkerExit:
    """Clean exit reasons (plan §9: clean shutdown exits 0)."""

    CLEAN_LEASE_LOST = "clean_lease_lost"
    CLEAN_STOP = "clean_stop"


async def _wait(stop_event: asyncio.Event, seconds: float) -> None:
    """Sleep `seconds`, returning early if `stop_event` is set."""
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except asyncio.TimeoutError:
        pass


async def _maintain_lease(
    engine: AsyncEngine,
    worker_id: str,
    settings: Settings,
    stop_event: asyncio.Event,
) -> bool:
    """Refresh the lease until it is lost or shutdown is requested.

    Returns True if the lease was lost (plan §57: clean deauthorization), False
    if shutdown was requested. On loss, stop_event is set so the work loop
    stops claiming immediately. Recoverable work is left for the next
    authoritative worker — we never cancel external execution here.
    """
    while not stop_event.is_set():
        if await refresh_worker_lease(engine, worker_id) is LeaseRetentionResult.LOST:
            stop_event.set()
            return True
        # Plan §54: reconciliation runs on each cycle while authoritative.
        await reconcile_stale_generations(engine, worker_id, settings)
        await _wait(stop_event, settings.worker_lease_refresh_interval_seconds)
    return False


async def _work_loop(
    engine: AsyncEngine,
    worker_id: str,
    settings: Settings,
    stop_event: asyncio.Event,
) -> None:
    """Claim and execute queued Generations while authoritative (M3A)."""
    from soloring.executors.fake import FakeExecutor
    from soloring.worker.execution import process_next_generation

    executor = FakeExecutor()
    while not stop_event.is_set():
        try:
            outcome = await process_next_generation(
                engine, settings, worker_id, executor
            )
        except Exception:  # noqa: BLE001 — one bad generation must not kill the worker
            log.exception("generation execution error")
            outcome = "error"
        if outcome is None:
            await _wait(stop_event, settings.worker_poll_interval_seconds)


async def run_worker(
    *,
    settings: Settings | None = None,
    worker_id: str | None = None,
    stop_event: asyncio.Event | None = None,
) -> str:
    """Run the worker authority loop until lease loss or shutdown.

    `worker_id` defaults to a freshly generated uuid4 (plan §8). It is accepted
    as a parameter only so tests can drive deterministic identities; the real
    entrypoint never reads it from config.
    """
    settings = settings or get_settings()
    stop_event = stop_event or asyncio.Event()
    worker_id = worker_id or new_worker_id()

    engine = create_soloring_engine(settings)
    log.info("worker starting worker_id=%s lease_name=%s", worker_id, LEASE_NAME)
    try:
        while not stop_event.is_set():
            result = await acquire_worker_lease(
                engine, worker_id, settings.worker_lease_ttl_seconds
            )
            if result == LeaseAcquisitionResult.HELD_BY_OTHER:
                # Plan §55: standby — do not process, do not crash-loop, backoff.
                log.info("lease held by another worker; standby (backoff)")
                await _wait(stop_event, settings.worker_poll_interval_seconds * 2)
                continue

            # Authority confirmed (ACQUIRED_NEW / REFRESHED_SELF / TAKEN_OVER).
            log.info("lease authority acquired: %s", result.value)
            # Plan §54: unconditional reconciliation after a successful cycle.
            await reconcile_stale_generations(engine, worker_id, settings)

            # M3A: work only while lease authority holds. The maintainer
            # refreshes the lease in parallel; on loss it sets stop_event so
            # the work loop stops claiming immediately.
            maintainer = asyncio.create_task(
                _maintain_lease(engine, worker_id, settings, stop_event)
            )
            lost = False
            try:
                await _work_loop(engine, worker_id, settings, stop_event)
            finally:
                if not maintainer.done():
                    maintainer.cancel()
                    try:
                        await maintainer
                    except asyncio.CancelledError:
                        pass
                else:
                    lost = maintainer.result() is True

            if lost:
                log.info("lease lost to another worker; clean deauthorization")
                return WorkerExit.CLEAN_LEASE_LOST

        log.info("shutdown requested; clean exit")
        return WorkerExit.CLEAN_STOP
    finally:
        await engine.dispose()
