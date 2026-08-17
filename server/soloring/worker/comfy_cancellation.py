"""Worker-side Comfy cancellation orchestration (M5A-8; plan §47-§53).

Owns durable cancellation state and lifecycle; the Comfy package owns remote
semantics only. All lifecycle writes are fenced; the persisted prompt_id is
the ONLY cancellation target; Soft Cancel — once durably selected — never
hard-cancels and never publishes outputs (zero Take/Asset), whatever the
remote terminal outcome turns out to be.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncEngine

from soloring.errors import ErrorCode, SoloRingError
from soloring.executors.comfy.cancel import (
    CancellationDecision,
    CancelOutcome,
    cancel_pending,
    cancel_running,
    decide_cancellation,
)
from soloring.executors.comfy.capabilities import CancellationCapability
from soloring.executors.comfy.client import ComfyClient
from soloring.executors.comfy.observe import (
    DisappearanceTracker,
    observe_prompt,
)
from soloring.worker.ownership import (
    OwnershipMutationResult,
    select_owned_soft_cancel,
    transition_owned_generation,
    verify_execution_authority,
)

log = logging.getLogger("soloring.worker.comfy_cancellation")


class CancellationConflict(SoloRingError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, status_code=500)


async def _require_authority_for_remote_effect(
    engine: AsyncEngine, worker_id: str, generation_id: str, what: str
) -> None:
    """CURRENT authority proof immediately before a destructive remote
    cancellation (re-audit R2). A stale worker must never delete/interrupt
    a remote prompt — a later fenced DB rejection cannot undo the external
    effect."""
    r = await verify_execution_authority(engine, worker_id, generation_id)
    if r is not OwnershipMutationResult.OK:
        raise CancellationConflict(
            ErrorCode.LEASE_LOST if r is OwnershipMutationResult.LEASE_LOST
            else ErrorCode.GENERATION_OWNERSHIP_LOST,
            f"authority lost before remote {what} ({r}); refusing the "
            "external effect",
        )


async def reconcile_cancellation(
    engine: AsyncEngine,
    worker_id: str,
    generation_id: str,
    attempt_id: str,
    prompt_id: str,
    client: ComfyClient,
    capability: CancellationCapability,
    tracker: DisappearanceTracker | None = None,
) -> str:
    """Advance one cancel-requested Comfy generation toward `cancelled`.

    Returns the resolved status ("cancelled", or a remote-terminal-driven
    status when the executor result wins the race). Raises on ownership loss
    or invariant violations.
    """
    generation_id = generation_id
    obs = await observe_prompt(
        client, prompt_id=prompt_id, generation_id=generation_id,
        attempt_id=attempt_id, disappearance=tracker,
    )

    # --- terminal executor result wins the race (§11) -----------------------
    if obs.state in ("succeeded", "failed", "cancelled"):
        from soloring.worker.comfy_submission import (  # local: perf only
            _current_submission_state,
        )

        soft = await _read_soft_cancel(engine, generation_id, worker_id)
        if soft:
            # Soft Cancel committed: discard outputs, publish nothing.
            log.info(
                "SOFT CANCEL discard: gen=%s remote=%s -> cancelled (no "
                "publication)", generation_id, obs.state,
            )
            r = await transition_owned_generation(
                engine, worker_id, generation_id, "cancelled",
            )
            _require_ok(r, generation_id)
            return "cancelled"
        # No soft cancel: normal terminal semantics (completion wins §11).
        status = "succeeded" if obs.state == "succeeded" else obs.state
        return status  # caller drives the normal import/terminal path

    if obs.state == "lost":
        # Job disappeared: interruption-class, never a manufactured cancel.
        r = await transition_owned_generation(
            engine, worker_id, generation_id, "interrupted",
            error_code=ErrorCode.EXECUTOR_JOB_LOST,
            error_message=obs.detail or "COMFY_JOB_LOST",
        )
        _require_ok(r, generation_id)
        return "interrupted"

    # --- active: choose the path ----------------------------------------------
    decision = decide_cancellation(obs.state, capability)
    if decision.action == "soft_cancel":
        selected = await select_owned_soft_cancel(
            engine, worker_id, generation_id
        )
        if not selected:
            raise CancellationConflict(
                ErrorCode.GENERATION_OWNERSHIP_LOST,
                "authority lost while selecting soft cancel",
            )
        # No destructive remote request; the loop observes to terminal and
        # discards on the next reconcile pass.
        log.info("SOFT CANCEL selected: gen=%s (%s)",
                 generation_id, decision.reason)
        return "soft_cancel_selected"

    if decision.action == "delete_pending":
        await _require_authority_for_remote_effect(
            engine, worker_id, generation_id, "pending-cancellation"
        )
        outcome = await cancel_pending(client, prompt_id)
        return await _after_remote_cancel(
            engine, worker_id, generation_id, attempt_id, prompt_id,
            client, outcome, tracker,
        )

    # hard_cancel (capability already proved targeted + retry-safe)
    await _require_authority_for_remote_effect(
        engine, worker_id, generation_id, "running-cancellation"
    )
    outcome = await cancel_running(client, prompt_id)
    return await _after_remote_cancel(
        engine, worker_id, generation_id, attempt_id, prompt_id,
        client, outcome, tracker,
    )


async def _after_remote_cancel(
    engine: AsyncEngine,
    worker_id: str,
    generation_id: str,
    attempt_id: str,
    prompt_id: str,
    client: ComfyClient,
    outcome: CancelOutcome,
    tracker: DisappearanceTracker | None,
) -> str:
    """Reconcile after a remote cancellation operation (§4-§6, §11)."""
    if outcome is CancelOutcome.TOO_LATE:
        # Prompt already terminal/absent: authoritative history wins.
        obs = await observe_prompt(
            client, prompt_id=prompt_id, generation_id=generation_id,
            attempt_id=attempt_id, disappearance=tracker,
        )
        if obs.state in ("succeeded", "failed", "cancelled"):
            soft = await _read_soft_cancel(engine, generation_id, worker_id)
            if soft:
                r = await transition_owned_generation(
                    engine, worker_id, generation_id, "cancelled",
                )
                _require_ok(r, generation_id)
                return "cancelled"
            return obs.state
        # Genuinely absent without terminal record.
        r = await transition_owned_generation(
            engine, worker_id, generation_id, "cancelled",
        )
        _require_ok(r, generation_id)
        return "cancelled"

    if outcome is CancelOutcome.ACCEPTED:
        r = await transition_owned_generation(
            engine, worker_id, generation_id, "cancelled",
        )
        _require_ok(r, generation_id)
        return "cancelled"

    # AMBIGUOUS: never re-target, never blind-resend. Re-observe once; the
    # caller's next reconcile iteration reuses the SAME persisted prompt_id.
    log.warning(
        "cancel transport ambiguous for gen=%s prompt=%s — same-target "
        "reconcile on next pass", generation_id, prompt_id,
    )
    return "ambiguous"


def _require_ok(r: OwnershipMutationResult, generation_id: str) -> None:
    if r is not OwnershipMutationResult.OK:
        raise CancellationConflict(
            ErrorCode.GENERATION_OWNERSHIP_LOST,
            f"fenced cancellation transition rejected ({r}) for {generation_id}",
        )


async def _read_soft_cancel(
    engine: AsyncEngine, generation_id: str, worker_id: str
) -> bool:
    from sqlalchemy import text

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT soft_cancel_selected_at, worker_id "
                    "FROM generations WHERE id=:g"
                ),
                {"g": generation_id},
            )
        ).one_or_none()
    if row is None or row.worker_id != worker_id:
        raise CancellationConflict(
            ErrorCode.GENERATION_OWNERSHIP_LOST, "not owned while reading",
        )
    return row.soft_cancel_selected_at is not None
