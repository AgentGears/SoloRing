"""One-shot submission authority primitives (M5A-1; plan §6-§11 as amended).

State machine (one-way, DB-CHECK-enforced):

    not_started → submission_possible → confirmed | uncertain

The not_started → submission_possible transition is the ONLY source of
MAY_POST, and the right it grants is not reconstructible from persisted
state: a successor that sees submission_possible (or confirmed/uncertain) may
only ever REDISCOVER — never re-invoke the remote submission. This
deliberately prefers possible lost execution over possible duplicate
expensive execution (v0.1 §65, M5 §9).

All operations are fenced exactly like the other ownership helpers: one
connection, one BEGIN IMMEDIATE, lease + generation ownership verified inside
the transaction.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from soloring.db.timeutil import db_now_sql
from soloring.errors import SoloRingError
from soloring.worker.ownership import (
    LEASE_NAME,
    TERMINAL_STATUSES,
    OwnershipMutationResult,
    SubmissionPermission,
    _immediate_transaction,
)


async def _submission_row(conn, generation_id: str):
    return (
        await conn.execute(
            text(
                "SELECT worker_id, status, attempt_id, "
                "executor_submission_state, executor_submission_json, "
                "executor_job_id FROM generations WHERE id = :gid"
            ),
            {"gid": generation_id},
        )
    ).one_or_none()


async def _lease_owner(conn) -> str | None:
    row = (
        await conn.execute(
            text("SELECT worker_id FROM worker_leases WHERE name = :name"),
            {"name": LEASE_NAME},
        )
    ).one_or_none()
    return row.worker_id if row is not None else None


async def persist_owned_executor_submission(
    engine: AsyncEngine,
    worker_id: str,
    generation_id: str,
    attempt_id: str,
    submission_json: str,
    submission_hash: str,
) -> OwnershipMutationResult:
    """Persist the executor submission artifact BEFORE submission becomes
    possible (M5 §24, §31). One fenced transaction verifying: lease owned,
    Generation owned, attempt matches, active, submission_state == not_started,
    and no executor_job_id yet."""
    async with _immediate_transaction(engine) as conn:
        if await _lease_owner(conn) != worker_id:
            return OwnershipMutationResult.LEASE_LOST

        row = await _submission_row(conn, generation_id)
        if row is None:
            return OwnershipMutationResult.NOT_FOUND
        if row.worker_id != worker_id:
            return OwnershipMutationResult.GENERATION_OWNERSHIP_LOST
        if row.status in TERMINAL_STATUSES:
            return OwnershipMutationResult.GENERATION_NOT_ACTIVE
        if row.attempt_id != attempt_id:
            return OwnershipMutationResult.GENERATION_STATE_CONFLICT
        if row.executor_submission_state != "not_started":
            return OwnershipMutationResult.GENERATION_STATE_CONFLICT
        if row.executor_job_id is not None:
            return OwnershipMutationResult.GENERATION_STATE_CONFLICT

        await conn.execute(
            text(
                "UPDATE generations SET executor_submission_json = :sj, "
                "executor_submission_hash = :sh, "
                f"heartbeat_at = {db_now_sql()}, updated_at = {db_now_sql()} "
                "WHERE id = :gid AND worker_id = :wid"
            ),
            {"sj": submission_json, "sh": submission_hash,
             "gid": generation_id, "wid": worker_id},
        )
        return OwnershipMutationResult.OK


async def mark_submission_possible(
    engine: AsyncEngine,
    worker_id: str,
    generation_id: str,
    attempt_id: str,
) -> SubmissionPermission:
    """The durable pre-POST boundary (M5 §8-§9, as amended).

    Requires the submission artifact to already be persisted. Only the caller
    whose fenced not_started → submission_possible transition COMMITS receives
    MAY_POST; every subsequent path receives REDISCOVER_ONLY.
    """
    async with _immediate_transaction(engine) as conn:
        if await _lease_owner(conn) != worker_id:
            return SubmissionPermission.LEASE_LOST

        row = await _submission_row(conn, generation_id)
        if row is None:
            return SubmissionPermission.GENERATION_NOT_ACTIVE
        if row.worker_id != worker_id:
            return SubmissionPermission.GENERATION_OWNERSHIP_LOST
        if row.status in TERMINAL_STATUSES:
            return SubmissionPermission.GENERATION_NOT_ACTIVE
        if row.attempt_id != attempt_id:
            return SubmissionPermission.SUBMISSION_STATE_CONFLICT
        if row.executor_submission_state != "not_started":
            return SubmissionPermission.REDISCOVER_ONLY
        if row.executor_submission_json is None:
            return SubmissionPermission.SUBMISSION_STATE_CONFLICT

        await conn.execute(
            text(
                "UPDATE generations SET executor_submission_state = "
                "'submission_possible', "
                f"submission_possible_at = {db_now_sql()}, "
                f"heartbeat_at = {db_now_sql()}, updated_at = {db_now_sql()} "
                "WHERE id = :gid AND worker_id = :wid AND "
                "executor_submission_state = 'not_started'"
            ),
            {"gid": generation_id, "wid": worker_id},
        )
        return SubmissionPermission.MAY_POST


async def confirm_owned_submission(
    engine: AsyncEngine,
    worker_id: str,
    generation_id: str,
    attempt_id: str,
    executor_job_id: str,
    handle_json: str,
) -> OwnershipMutationResult:
    """submission_possible → confirmed, persisting the real executor handle
    (M5 §33 steps 10-11). One-way: only from submission_possible."""
    async with _immediate_transaction(engine) as conn:
        if await _lease_owner(conn) != worker_id:
            return OwnershipMutationResult.LEASE_LOST

        row = await _submission_row(conn, generation_id)
        if row is None:
            return OwnershipMutationResult.NOT_FOUND
        if row.worker_id != worker_id:
            return OwnershipMutationResult.GENERATION_OWNERSHIP_LOST
        if row.status in TERMINAL_STATUSES:
            return OwnershipMutationResult.GENERATION_NOT_ACTIVE
        if row.attempt_id != attempt_id:
            return OwnershipMutationResult.GENERATION_STATE_CONFLICT
        if row.executor_submission_state != "submission_possible":
            return OwnershipMutationResult.GENERATION_STATE_CONFLICT

        await conn.execute(
            text(
                "UPDATE generations SET executor_submission_state = 'confirmed', "
                "executor_job_id = :job, executor_handle_json = :hj, "
                f"heartbeat_at = {db_now_sql()}, updated_at = {db_now_sql()} "
                "WHERE id = :gid AND worker_id = :wid"
            ),
            {"job": executor_job_id, "hj": handle_json,
             "gid": generation_id, "wid": worker_id},
        )
        return OwnershipMutationResult.OK


async def mark_submission_uncertain(
    engine: AsyncEngine,
    worker_id: str,
    generation_id: str,
    attempt_id: str,
) -> OwnershipMutationResult:
    """submission_possible → uncertain (M5 §37): unresolved ambiguity after
    bounded rediscovery. Permanently ineligible for automatic resubmission —
    uncertain can never return to submission_possible."""
    async with _immediate_transaction(engine) as conn:
        if await _lease_owner(conn) != worker_id:
            return OwnershipMutationResult.LEASE_LOST

        row = await _submission_row(conn, generation_id)
        if row is None:
            return OwnershipMutationResult.NOT_FOUND
        if row.worker_id != worker_id:
            return OwnershipMutationResult.GENERATION_OWNERSHIP_LOST
        if row.status in TERMINAL_STATUSES:
            return OwnershipMutationResult.GENERATION_NOT_ACTIVE
        if row.attempt_id != attempt_id:
            return OwnershipMutationResult.GENERATION_STATE_CONFLICT
        if row.executor_submission_state != "submission_possible":
            return OwnershipMutationResult.GENERATION_STATE_CONFLICT

        await conn.execute(
            text(
                "UPDATE generations SET executor_submission_state = 'uncertain', "
                f"heartbeat_at = {db_now_sql()}, updated_at = {db_now_sql()} "
                "WHERE id = :gid AND worker_id = :wid"
            ),
            {"gid": generation_id, "wid": worker_id},
        )
        return OwnershipMutationResult.OK


async def select_owned_soft_cancel(
    engine: AsyncEngine,
    worker_id: str,
    generation_id: str,
) -> bool:
    """Durably select Soft Cancel (M5A-8 §1). Returns True when selected
    (including idempotent re-selection); False when authority was lost.

    Requires the persisted cancel intent (CHECK-enforced). One-way: there is
    no transition back to NULL. Adoption preserves it unchanged because
    adopt only rewrites worker_id/heartbeats.
    """
    async with _immediate_transaction(engine) as conn:
        if await _lease_owner(conn) != worker_id:
            return False
        row = (
            await conn.execute(
                text(
                    "SELECT worker_id, status, soft_cancel_selected_at, "
                    "cancel_requested_at FROM generations WHERE id = :gid"
                ),
                {"gid": generation_id},
            )
        ).one_or_none()
        if row is None or row.worker_id != worker_id:
            return False
        if row.status in TERMINAL_STATUSES:
            return False  # terminal already; nothing to select
        if row.soft_cancel_selected_at is not None:
            return True  # idempotent
        if row.cancel_requested_at is None:
            # Caller ordering bug: intent must be persisted first.
            raise SoloRingError(
                "INTERNAL_INVARIANT_VIOLATION",
                "soft cancel requires persisted cancel intent",
                status_code=500,
            )
        await conn.execute(
            text(
                "UPDATE generations SET soft_cancel_selected_at = "
                f"{db_now_sql()}, updated_at = {db_now_sql()} "
                "WHERE id = :gid AND worker_id = :wid"
            ),
            {"gid": generation_id, "wid": worker_id},
        )
        return True
