"""Stale-active Generation reconciliation (plan §54, §62-§67; M3B).

Runs UNCONDITIONALLY after every successful lease-authority cycle — recovery
derives from persisted state and timestamps, never worker memory.

Decision matrix per stale Generation (current authority = this worker):

    preparing, attempt identity known (M3C)
        → ADOPT + IDEMPOTENT RE-SUBMIT: submission identity is the durable
          (generation, attempt) pair, so recovery rejoins the existing
          external job if the crash happened after submit — or creates it
          exactly once if it didn't. Never duplicates external execution.

    preparing, attempt identity missing (legacy/corrupt rows only)
        → REQUEUE (plan §64): preserves queued_at, clears ownership.

    preparing, handle persisted (crash between submit-persist and
    submitted transition — plan §65 ambiguity window)
        → ADOPT the existing job (never resubmit).

    submitted / running
        → ADOPT: continue polling the durable handle (plan §66).
          Persisted cancellation intent is completed by the new owner.

    importing
        → ADOPT + REPLAY import: idempotent publication (plan §67).
          Staging from the previous attempt may be gone; the executor
          regenerates identical deterministic bytes into the recovering
          attempt's namespace, and the importer's output-key identity
          guarantees no duplicate Blob/Asset/Take.

    terminal
        → unreachable by the stale scan; left untouched.

Losing local authority stops MUTATION authority but never destroys
potentially recoverable external execution: nothing here cancels an external
job unless a persisted cancellation request says to.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncEngine

from soloring.executors.fake import FakeExecutor, handle_from_json
from soloring.settings import Settings
from soloring.worker.execution import drive_generation, new_attempt_id
from soloring.worker.ownership import (
    OwnershipMutationResult,
    adopt_stale_generation,
    find_stale_active_generations,
    requeue_stale_preparing_generation,
)

log = logging.getLogger("soloring.worker.recovery")


async def reconcile_stale_generations(
    engine: AsyncEngine,
    worker_id: str,
    settings: Settings,
    executor: FakeExecutor | None = None,
    comfy_client=None,
) -> int:
    """Reconcile all stale active Generations; returns actions taken.

    Cheap steady-state no-op: the stale scan is indexed
    (ix_generations_active_recovery) and typically returns nothing.
    """
    executor = executor or FakeExecutor()
    stale = await find_stale_active_generations(
        engine, settings.generation_heartbeat_stale_seconds
    )
    if not stale:
        return 0

    acted = 0
    for row in stale:
        if row["worker_id"] == worker_id:
            # Our own active work is not stale-in-another-incarnation; the
            # executor loop heartbeats it. (A truly stalled own job is a bug
            # surfaced by tests, not a recovery case.)
            continue

        gid = row["id"]
        status = row["status"]
        has_handle = row["executor_job_id"] is not None

        if status == "preparing" and row["attempt_id"] is None:
            # Legacy/corrupt row with no durable attempt identity: safe only
            # when no handle exists (verified inside the fence).
            r = await requeue_stale_preparing_generation(engine, worker_id, gid)
            if r is OwnershipMutationResult.OK:
                log.info("RECOVERY: requeued legacy stale preparing %s", gid)
                acted += 1
            elif r is OwnershipMutationResult.GENERATION_NOT_ACTIVE:
                r2 = await adopt_stale_generation(engine, worker_id, gid)
                if r2 is OwnershipMutationResult.OK:
                    await _continue(engine, settings, worker_id, gid, row,
                                    executor, comfy_client)
                    acted += 1
            continue

        # preparing+handle, submitted, running, importing → adopt + continue.
        r = await adopt_stale_generation(engine, worker_id, gid)
        if r is OwnershipMutationResult.OK:
            log.info(
                "RECOVERY: adopted stale %s %s (cancel_intent=%s)",
                status, gid, row["cancel_requested_at"] is not None,
            )
            await _continue(engine, settings, worker_id, gid, row, executor,
                            comfy_client)
            acted += 1
    return acted


async def _continue(
    engine: AsyncEngine,
    settings: Settings,
    worker_id: str,
    generation_id: str,
    row: dict,
    executor: FakeExecutor,
    comfy_client=None,
) -> None:
    """Continue an adopted Generation toward a terminal state.

    Dispatch is by the PERSISTED executor, exactly like the claim loop: comfy
    rows re-enter the M5A-10 pipeline, whose submission protocol resolves
    durable state first (rediscover-only; never a second POST).
    """
    # The PERSISTED attempt identity is reused: re-submission is idempotent
    # (rejoins the existing external job), and staging stays namespaced to
    # the original attempt.
    attempt = row.get("attempt_id") or new_attempt_id()

    if row.get("executor") == "comfy":
        from soloring.executors.comfy.client import ComfyClient
        from soloring.worker.comfy_pipeline import drive_comfy_generation

        owns_client = comfy_client is None
        client = comfy_client or ComfyClient(
            settings.comfy_base_url or "http://127.0.0.1:8188",
            client_id=worker_id,
        )
        try:
            await drive_comfy_generation(
                engine, settings, worker_id, generation_id, attempt, client,
            )
        finally:
            if owns_client:
                await client.aclose()
        return

    handle = None
    if row["executor_handle_json"]:
        handle = handle_from_json(row["executor_handle_json"])
    await drive_generation(
        engine, settings, worker_id, generation_id, attempt, executor,
        existing_handle=handle,
    )
