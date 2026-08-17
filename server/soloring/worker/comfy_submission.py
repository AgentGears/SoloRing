"""Worker-side Comfy submission orchestration (M5A-6; M5 plan §33, §8-§11).

Owns the durable submission protocol — the layer the M5 amendment pinned:

    worker/ownership.py            fenced DB primitives (M5A-1)
    worker/comfy_submission.py     THIS module: the durable protocol
    executors/comfy/*             remote semantics only (DB-free)

Sequence (§33):

    materialize inputs
    ↓ translate (M5A-5)
    ↓ persist_owned_executor_submission()          [fenced]
    ↓ mark_submission_possible()                  [fenced, one-shot permit]
    ↓ MAY_POST?
    ├─ yes → final authority check → client.submit_prompt() EXACTLY ONCE
    └─ no  → rediscover only
    ↓
    accepted → confirm_owned_submission() (atomic handle+confirmed, M5A-1)
    ambiguous → bounded monotonic rediscovery grace
    ↓ 1 match → confirm; >1 → COMFY_DUPLICATE_ATTEMPT; 0 until expiry
      → mark_submission_uncertain() [fenced] → Generation interrupted

No DB session spans a network call or a discovery sleep (§16).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

from sqlalchemy.ext.asyncio import AsyncEngine

from soloring.domain.canonical import canonical_json_bytes
from soloring.errors import ErrorCode, SoloRingError
from soloring.executors.comfy.client import (
    ComfyAPIError,
    ComfyClient,
    PromptAccepted,
    PromptRejected,
    SubmissionAmbiguous,
)
from soloring.executors.comfy.executor import (
    RediscoveryConflict,
    RediscoveryResult,
    find_attempt,
)
from soloring.settings import Settings
from soloring.worker.ownership import (
    LeaseRetentionResult,
    OwnershipMutationResult,
    SubmissionPermission,
    confirm_owned_submission,
    mark_submission_possible,
    mark_submission_uncertain,
    persist_owned_executor_submission,
    refresh_worker_lease,
)

log = logging.getLogger("soloring.worker.comfy_submission")

POLL_INTERVAL = 0.05  # tests override grace; interval stays small


class SubmissionConflict(SoloRingError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message, status_code=500)


async def _current_submission_state(
    engine: AsyncEngine, generation_id: str, worker_id: str
) -> str | None:
    """Read (generation worker, submission state) — None on lost authority."""
    from sqlalchemy import text

    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT worker_id, executor_submission_state "
                    "FROM generations WHERE id=:g"
                ),
                {"g": generation_id},
            )
        ).one_or_none()
    if row is None or row.worker_id != worker_id:
        return None
    return row.executor_submission_state


async def run_comfy_submission(
    engine: AsyncEngine,
    settings: Settings,
    worker_id: str,
    generation_id: str,
    attempt_id: str,
    payload_document: dict | None,
    client: ComfyClient,
    grace_seconds: float = 1.0,
) -> str:
    """Drive one Comfy attempt from artifact to confirmed-or-uncertain.

    Returns the confirmed prompt_id, or "" when the attempt resolved
    uncertain/interrupted. Raises SubmissionConflict for invariant failures.

    Recovery-aware (audit F12): when the durable state is already
    submission_possible (a crashed predecessor consumed the permit), this
    frame enters REDISCOVER_ONLY without re-persisting the artifact —
    ``payload_document`` may be None on that path because no artifact is
    minted here; when already confirmed, it proceeds to idempotent /
    conflict-checked confirmation; uncertain resolves to "" immediately.
    """
    state = await _current_submission_state(engine, generation_id, worker_id)
    if state is None:
        raise SubmissionConflict(
            ErrorCode.GENERATION_OWNERSHIP_LOST,
            "generation not owned by this worker (adopt first)",
        )

    permission: SubmissionPermission
    if state in ("submission_possible", "confirmed", "uncertain"):
        # A predecessor durably consumed (or resolved) the permit: this frame
        # NEVER posts. Confirmed/uncertain flow straight to idempotent /
        # conflict-checked handling or the uncertain terminal short-circuit.
        permission = SubmissionPermission.REDISCOVER_ONLY
        if state == "uncertain":
            return ""  # permanently ineligible; nothing to rediscover toward
    else:
        if payload_document is None:
            # Caller ordering bug: only a REDISCOVER_ONLY frame may omit the
            # payload — a fresh permit must mint the artifact first.
            raise SubmissionConflict(
                ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                "submission payload required for a not_started attempt",
            )
        # Canonical bytes = the M5A-5 submission_artifact contract: the
        # persisted bytes ARE the hashed bytes, byte-identical to the pure
        # translator's artifact form.
        submission_json = canonical_json_bytes(payload_document).decode("utf-8")
        import hashlib

        submission_hash = hashlib.sha256(
            submission_json.encode("utf-8")
        ).hexdigest()

        r = await persist_owned_executor_submission(
            engine, worker_id, generation_id, attempt_id,
            submission_json, submission_hash,
        )
        if r is not OwnershipMutationResult.OK:
            log.error("submission artifact persist rejected (%s) for %s",
                      r, generation_id)
            raise SubmissionConflict(
                ErrorCode.GENERATION_OWNERSHIP_LOST,
                f"artifact persistence rejected: {r}",
            )

        permission = await mark_submission_possible(
            engine, worker_id, generation_id, attempt_id
        )
        if permission is SubmissionPermission.LEASE_LOST or permission is (
            SubmissionPermission.GENERATION_OWNERSHIP_LOST
        ):
            raise SubmissionConflict(
                ErrorCode.GENERATION_OWNERSHIP_LOST,
                f"authority lost before submission boundary: {permission}",
            )
        if permission is SubmissionPermission.SUBMISSION_STATE_CONFLICT:
            raise SubmissionConflict(
                ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                "submission-state ordering violation",
            )

    if permission is SubmissionPermission.MAY_POST:
        # Final authority gate immediately before consuming the permit
        # (§10, re-audit R1): heartbeat-refresh (RETAINED/LOST — compared
        # correctly; the historical `is None` test could never fire) AND the
        # full lease + Generation ownership proof in ONE fenced unit. A
        # worker that lost either must never reach /prompt. The unavoidable
        # check→POST race is safe: successors see durable
        # submission_possible and are REDISCOVER_ONLY.
        from soloring.worker.ownership import verify_execution_authority

        if await refresh_worker_lease(engine, worker_id) is (
            LeaseRetentionResult.LOST
        ):
            raise SubmissionConflict(
                ErrorCode.LEASE_LOST, "lease lost before POST",
            )
        authority = await verify_execution_authority(
            engine, worker_id, generation_id
        )
        if authority is not OwnershipMutationResult.OK:
            raise SubmissionConflict(
                ErrorCode.LEASE_LOST if authority is (
                    OwnershipMutationResult.LEASE_LOST
                ) else ErrorCode.GENERATION_OWNERSHIP_LOST,
                f"authority lost before POST ({authority})",
            )

        try:
            outcome = await client.submit_prompt(payload_document)
        except SubmissionAmbiguous as exc:
            log.warning(
                "COMFY_SUBMIT_UNCERTAIN: %s gen=%s attempt=%s — "
                "entering bounded rediscovery",
                exc.detail, generation_id, attempt_id,
            )
            return await _rediscover_until_resolved(
                engine, settings, worker_id, generation_id, attempt_id,
                client, grace_seconds,
            )

        if isinstance(outcome, PromptRejected):
            # Contract-proven conclusive rejection: the executor never
            # accepted the work; a normal failure, not ambiguity.
            raise SubmissionConflict(
                ErrorCode.EXECUTOR_UNAVAILABLE,
                f"Comfy rejected the prompt: {outcome.detail}",
            )

        assert isinstance(outcome, PromptAccepted)
        return await _confirm_or_conflict(
            engine, worker_id, generation_id, attempt_id, outcome.prompt_id
        )

    # REDISCOVER_ONLY: this frame never held the permit (recovery path).
    return await _rediscover_until_resolved(
        engine, settings, worker_id, generation_id, attempt_id,
        client, grace_seconds,
    )


async def _confirm_or_conflict(
    engine: AsyncEngine,
    worker_id: str,
    generation_id: str,
    attempt_id: str,
    prompt_id: str,
) -> str:
    """Atomic confirm; idempotent for the same P; conflict for Q != P."""
    handle = json.dumps({"kind": "comfy", "prompt_id": prompt_id})
    r = await confirm_owned_submission(
        engine, worker_id, generation_id, attempt_id, prompt_id, handle
    )
    if r is OwnershipMutationResult.OK:
        return prompt_id
    if r is OwnershipMutationResult.GENERATION_STATE_CONFLICT:
        # Either already confirmed with this P (idempotent) or with a
        # different Q (invariant conflict). Distinguish by reading state —
        # a pure read, no session spans anything questionable here.
        from sqlalchemy import text

        async with engine.connect() as conn:
            row = (
                await conn.execute(
                    text(
                        "SELECT executor_job_id FROM generations WHERE id=:g"
                    ),
                    {"g": generation_id},
                )
            ).one_or_none()
        if row is not None and row.executor_job_id == prompt_id:
            return prompt_id  # idempotent re-confirmation
        raise SubmissionConflict(
            ErrorCode.COMFY_EXECUTOR_HANDLE_CONFLICT,
            f"attempt already confirmed as {row.executor_job_id if row else None!r}; "
            f"refusing to replace with {prompt_id!r}",
        )
    raise SubmissionConflict(
        ErrorCode.GENERATION_OWNERSHIP_LOST,
        f"confirmation rejected: {r}",
    )


async def _rediscover_until_resolved(
    engine: AsyncEngine,
    settings: Settings,
    worker_id: str,
    generation_id: str,
    attempt_id: str,
    client: ComfyClient,
    grace_seconds: float,
) -> str:
    """Bounded, monotonic rediscovery (§8, §37).

    One match → confirm/adopt immediately; duplicate/conflict → stop with an
    invariant failure; temporary read failure → bounded retry WITHOUT resetting
    the grace deadline; absent until deadline → fenced uncertain → "".
    """
    deadline = time.monotonic() + grace_seconds
    while True:
        try:
            result: RediscoveryResult = await find_attempt(
                client, generation_id, attempt_id
            )
        except RediscoveryConflict as exc:
            raise SubmissionConflict(
                ErrorCode.COMFY_DUPLICATE_ATTEMPT,
                f"rediscovery invariant failure ({exc.kind}): {exc}",
            )
        except ComfyAPIError:
            # Transient read failure: bounded retry, grace NOT reset (§8).
            if time.monotonic() >= deadline:
                return await _mark_uncertain(
                    engine, worker_id, generation_id, attempt_id
                )
            await asyncio.sleep(POLL_INTERVAL)
            continue

        if result.outcome == "adopt":
            return await _confirm_or_conflict(
                engine, worker_id, generation_id, attempt_id,
                result.prompt_id,
            )

        # absent
        if time.monotonic() >= deadline:
            return await _mark_uncertain(
                engine, worker_id, generation_id, attempt_id
            )
        await asyncio.sleep(POLL_INTERVAL)


async def _mark_uncertain(
    engine: AsyncEngine, worker_id: str, generation_id: str, attempt_id: str
) -> str:
    """Grace expired → fenced uncertain; the attempt is permanently
    ineligible for automatic resubmission (returns "")."""
    r = await mark_submission_uncertain(
        engine, worker_id, generation_id, attempt_id
    )
    if r is not OwnershipMutationResult.OK:
        # Authority lost at the boundary: the successor owns the decision.
        log.error("uncertain transition rejected (%s) for %s", r, generation_id)
        raise SubmissionConflict(
            ErrorCode.GENERATION_OWNERSHIP_LOST,
            f"could not mark uncertain: {r}",
        )
    log.warning(
        "EXECUTOR_SUBMISSION_UNCERTAIN: gen=%s attempt=%s — grace expired "
        "with no marker evidence",
        generation_id, attempt_id,
    )
    return ""
