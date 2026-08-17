"""Worker execution loop (M3A happy path + M3B recovery continuation).

Claims queued Generations behind singleton-lease authority and dispatches by
the PERSISTED Generation.executor (M5 §5). The fake drive path below is
Comfy-free (Hard Gate A/B); comfy rows route to worker/comfy_pipeline.py:

    claim (fenced, exclusive, attempt-scoped)
    → load captured execution identity (generation + spec, NEVER current shot)
    → submit (unless recovering an existing handle) → persist handle (fenced)
    → poll inspect → progress writes (fenced) + cancellation reconciliation
    → fetch_outputs → attempt-scoped staging
    → import authority (idempotent)
    → terminal transition (fenced)

Recovery continuation: ``drive_generation`` accepts an existing durable
executor handle, so a new authority holder can ADOPT an in-flight job (never
resubmitting externally expensive work) or replay an interrupted import.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from soloring.assets.blob_store import BlobStore
from soloring.errors import ErrorCode
from soloring.executors.base import (
    CancelResult,
    ExecutionHandle,
    ExecutionObservation,
    ExecutionStatus,
    GenerationExecutionSpec,
)
from soloring.executors.fake import FakeExecutor, handle_from_json, handle_json
from soloring.generation.importer import import_staged_outputs
from soloring.generation.repository import get_generation_full
from soloring.settings import Settings
from soloring.worker.ownership import (
    OwnershipMutationResult,
    claim_next_generation,
    persist_owned_executor_handle,
    read_cancellation_intent,
    transition_owned_generation,
    update_owned_generation_progress,
    verify_execution_authority,
)
from soloring.workflows.manifest import ExpectedOutput

log = logging.getLogger("soloring.worker.execution")


def _build_execution_spec(generation, attempt_id: str) -> GenerationExecutionSpec:
    """Executor input assembled EXCLUSIVELY from captured Generation fields.

    The output contract is derived from the CAPTURED spec (M4 §11): mutating
    the installed manifest after capture cannot reinterpret this execution.
    """
    return GenerationExecutionSpec(
        generation_id=generation.id,
        attempt_id=attempt_id,
        workflow_spec=json.loads(generation.workflow_spec_json),
        workflow_spec_hash=generation.workflow_spec_hash,
        compiled_prompt=generation.compiled_prompt,
        executor=generation.executor,
        template=None,
    )


def spec_outputs(workflow_spec: dict) -> tuple[ExpectedOutput, ...]:
    """Expected outputs from the CAPTURED logical spec (M4)."""
    return tuple(
        ExpectedOutput(
            name=o["name"],
            kind=o["kind"],
            expected_count=o["expected_count"],
            accepted_media_types=(
                tuple(o["accepted_media_types"])
                if o["accepted_media_types"] is not None
                else None
            ),
        )
        for o in workflow_spec.get("outputs", [])
    )


async def _cancel_if_requested(
    engine, worker_id: str, generation_id: str, executor, handle
) -> str | None:
    """Complete a persisted cancellation under current authority (§72-§73).

    Returns "cancelled" when reconciled to the terminal state, "halt" when
    authority was lost (the caller must stop this local drive — never
    cancel remote work merely because authority moved, re-audit R2), else
    None to continue.
    """
    if not await read_cancellation_intent(engine, generation_id):
        return None
    # Destructive external side effect ahead: prove CURRENT authority in
    # one fenced unit immediately before the executor call. A later fenced
    # DB write cannot un-cancel a remote job.
    authority = await verify_execution_authority(
        engine, worker_id, generation_id
    )
    if authority is not OwnershipMutationResult.OK:
        log.error(
            "cancel reconciliation halted (%s) for %s; successor owns it",
            authority, generation_id,
        )
        return "halt"
    result = await executor.cancel(handle)
    if result is CancelResult.CANCELLED:
        await transition_owned_generation(
            engine, worker_id, generation_id, "cancelled",
        )
        return "cancelled"
    # TOO_LATE → the job finished externally; normal polling finalizes it.
    # NOT_FOUND → external job lost; polling's LOST branch handles it.
    return None


async def drive_generation(
    engine: AsyncEngine,
    settings: Settings,
    worker_id: str,
    generation_id: str,
    attempt_id: str,
    executor: FakeExecutor,
    existing_handle: ExecutionHandle | None = None,
) -> str:
    """Drive one Generation to a terminal state under current authority.

    ``existing_handle`` set → recovery continuation: the durable executor job
    is adopted, never resubmitted. ``None`` → fresh submit.
    """
    factory = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)
    blob_store = BlobStore(settings)

    async with factory() as session:
        generation = await get_generation_full(session, generation_id)

    spec = _build_execution_spec(generation, attempt_id)
    outputs = spec_outputs(spec.workflow_spec)

    if existing_handle is None:
        handle = await executor.submit(spec)
        r = await persist_owned_executor_handle(
            engine, worker_id, generation_id, handle.job_id, handle_json(handle)
        )
        if r is not OwnershipMutationResult.OK:
            log.error("handle persistence fenced off (%s) for %s", r, generation_id)
            await transition_owned_generation(
                engine, worker_id, generation_id, "failed",
                error_code=ErrorCode.GENERATION_OWNERSHIP_LOST,
                error_message=str(r),
            )
            return "failed"
        r = await transition_owned_generation(
            engine, worker_id, generation_id, "submitted", started=True
        )
        if r is not OwnershipMutationResult.OK:
            return "failed"
    else:
        handle = existing_handle
        r = await transition_owned_generation(
            engine, worker_id, generation_id, "running"
        )
        if r is not OwnershipMutationResult.OK:
            return "failed"

    last = (None, None, None)
    while True:
        # Cancellation intent is checked BEFORE each observation so a
        # persisted request is reconciled promptly under current authority.
        cancel_outcome = await _cancel_if_requested(
            engine, worker_id, generation_id, executor, handle
        )
        if cancel_outcome == "cancelled":
            return "cancelled"
        if cancel_outcome == "halt":
            # Authority moved mid-drive (re-audit R2): stop this frame
            # without touching remote work; the successor continues.
            return "failed"

        observation: ExecutionObservation = await executor.inspect(handle)
        executor.advance(handle)

        progress = observation.progress
        signature = (progress.current, progress.total, progress.node)
        if signature != last and progress.current is not None:
            r = await update_owned_generation_progress(
                engine, worker_id, generation_id,
                progress.current, progress.total, progress.node,
            )
            if r in (OwnershipMutationResult.LEASE_LOST,
                     OwnershipMutationResult.GENERATION_OWNERSHIP_LOST):
                return "failed"  # fenced mutation says authority is gone
            r = await transition_owned_generation(
                engine, worker_id, generation_id, "running"
            )
            if r in (OwnershipMutationResult.LEASE_LOST,
                     OwnershipMutationResult.GENERATION_OWNERSHIP_LOST):
                return "failed"
            last = signature

        if observation.status is ExecutionStatus.SUCCEEDED:
            break
        if observation.status is ExecutionStatus.CANCELLED:
            await transition_owned_generation(
                engine, worker_id, generation_id, "cancelled"
            )
            return "cancelled"
        if observation.status is ExecutionStatus.FAILED:
            await transition_owned_generation(
                engine, worker_id, generation_id, "failed",
                error_code="EXECUTOR_FAILED",
                error_message=observation.error_message or "executor reported failure",
            )
            return "failed"
        if observation.status is ExecutionStatus.LOST:
            await transition_owned_generation(
                engine, worker_id, generation_id, "interrupted",
                error_code=ErrorCode.EXECUTOR_JOB_LOST,
                error_message="executor lost the job",
            )
            return "interrupted"

    # Staging + import (§80-§82). Attempt-scoped namespace: recovering
    # authorities stage under their OWN attempt, never a previous one's.
    staging_dir = Path(settings.staging_dir) / generation_id / attempt_id
    staged = await executor.fetch_outputs(handle, outputs, staging_dir)

    r = await transition_owned_generation(
        engine, worker_id, generation_id, "importing"
    )
    if r is not OwnershipMutationResult.OK:
        # Fence lost between fetch and publication (audit F1): this worker
        # must STOP — the importer would refuse to mint provenance anyway,
        # and the successor owns the generation now.
        log.error(
            "importing transition fenced off (%s) for %s; halting drive", r,
            generation_id,
        )
        return "failed"
    imported = await import_staged_outputs(
        factory, blob_store, generation, staged,
        expected_outputs=outputs, staging_directory=staging_dir,
        worker_id=worker_id, attempt_id=attempt_id,
    )
    log.info("IMPORTED %s outputs for %s", len(imported), generation_id)

    await transition_owned_generation(engine, worker_id, generation_id, "succeeded")
    try:
        for out in staged:
            out.path.unlink(missing_ok=True)
        staging_dir.rmdir()
    except OSError:
        pass
    return "succeeded"


async def run_claimed_generation(
    engine: AsyncEngine,
    settings: Settings,
    worker_id: str,
    generation_id: str,
    attempt_id: str,
    executor: FakeExecutor,
) -> str:
    """Fresh claim path: submit and drive to terminal."""
    return await drive_generation(
        engine, settings, worker_id, generation_id, attempt_id, executor,
        existing_handle=None,
    )


async def process_next_generation(
    engine: AsyncEngine,
    settings: Settings,
    worker_id: str,
    executor: FakeExecutor | None = None,
    comfy_client=None,
) -> str | None:
    """Claim and run one queued Generation; None when the queue is empty.

    Dispatch is by the PERSISTED Generation.executor (M5 §5): a config change
    alters only FUTURE creations, never how queued historical work executes.
    The fake drive path below stays Comfy-free; comfy rows route to the M5A-10
    pipeline.
    """
    claim = await claim_next_generation(engine, worker_id)
    if claim is None:
        return None
    generation_id, attempt_id = claim

    from sqlalchemy import text

    async with engine.connect() as conn:
        persisted_executor = (await conn.execute(
            text("SELECT executor FROM generations WHERE id = :g"),
            {"g": generation_id},
        )).scalar_one()

    if persisted_executor == "comfy":
        from soloring.executors.comfy.client import ComfyClient
        from soloring.worker.comfy_pipeline import drive_comfy_generation

        owns_client = comfy_client is None
        client = comfy_client or ComfyClient(
            settings.comfy_base_url or "http://127.0.0.1:8188",
            client_id=worker_id,
        )
        try:
            return await drive_comfy_generation(
                engine, settings, worker_id, generation_id, attempt_id, client,
            )
        finally:
            if owns_client:
                await client.aclose()

    return await run_claimed_generation(
        engine, settings, worker_id, generation_id, attempt_id,
        executor or FakeExecutor(),
    )


def new_attempt_id() -> str:
    """Fresh execution-attempt identity (scopes the staging namespace)."""
    return str(uuid4())
