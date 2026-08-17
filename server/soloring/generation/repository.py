"""Generation persistence repository (plan §37, §40, §35).

One persistence primitive: ``create_generation(session, draft, inputs)``.
Generation and its GenerationInputs commit atomically or not at all.

Serialization-first discipline (mirrors Shot numbering, plan §37.2): the FIRST
statement of the write unit is the Generation insert itself, so validation of
the active Shot / matching ShotRevision happens inside the atomic INSERT's
WHERE EXISTS rather than in a prior deferred-transaction read. This closes the
WAL read→write upgrade race against a concurrent Shot soft-delete (which would
otherwise surface as a raw OperationalError):

  * RETURNING path (SQLite >= 3.35):
        INSERT ... SELECT <draft values>,
                   COALESCE(MAX(generation_number), 0) + 1
        WHERE EXISTS(active Shot) AND EXISTS(revision belongs to Shot)
        RETURNING id, generation_number
    then input bindings are validated and inserted in the SAME transaction;
    a binding failure rolls the whole thing back (no Generation, no inputs).

  * fallback path: one checked-out connection, ``BEGIN IMMEDIATE`` acquiring
    the write lock up front, then validate / allocate / insert / verify.

``UNIQUE(shot_id, generation_number)`` remains the final guard with a
retry-once policy that recognizes ONLY that exact constraint. Raw database
exceptions never cross this boundary: SQLite BUSY/LOCKED lock failures
(including the fallback's ``BEGIN IMMEDIATE`` acquisition) translate to the
stable ``SQLITE_BUSY`` error; every other Integrity/Operational failure
translates to the internal-invariant error.
"""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from uuid import uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import undefer

from soloring.assets.models import Asset
from soloring.db.models import Generation, GenerationInput, Shot, ShotRevision
from soloring.db.sqlite import sqlite_supports_returning
from soloring.db.timeutil import DB_NOW_SQL
from soloring.domain.ids import is_uuid
from soloring.errors import ErrorCode, SoloRingError, internal_invariant, not_found
from soloring.generation.drafts import GenerationDraft
from soloring.generation.input_mapping import ResolvedGenerationInput

_NOW = DB_NOW_SQL

# Atomic insert: number allocation + active-Shot + revision validation in ONE
# statement. First write of the transaction, so write serialization is held
# before any validation read (plan §37, §40).
_INSERT_RETURNING = f"""
INSERT INTO generations (
    id, shot_id, shot_revision_id, generation_number, status, operation,
    executor, workflow_id, workflow_version, workflow_template_hash,
    manifest_hash, model, model_version, compiled_prompt, negative_prompt,
    prompt_compiler_version, seed, parameters_json, workflow_spec_json,
    workflow_spec_hash, rerun_of_generation_id, created_at, updated_at, queued_at
)
SELECT
    :id, :shot_id, :shot_revision_id,
    COALESCE(
        (SELECT MAX(generation_number) FROM generations WHERE shot_id = :shot_id),
        0
    ) + 1,
    'queued', :operation, :executor,
    :workflow_id, :workflow_version, :workflow_template_hash,
    :manifest_hash, :model, :model_version, :compiled_prompt, :negative_prompt,
    :prompt_compiler_version, :seed, :parameters_json, :workflow_spec_json,
    :workflow_spec_hash, :rerun_of_generation_id,
    {_NOW}, {_NOW}, {_NOW}
WHERE EXISTS (
    SELECT 1 FROM shots WHERE id = :shot_id AND deleted_at IS NULL
)
AND EXISTS (
    SELECT 1 FROM shot_revisions
    WHERE id = :shot_revision_id AND shot_id = :shot_id
)
RETURNING id, generation_number
"""

_INSERT_PLAIN = f"""
INSERT INTO generations (
    id, shot_id, shot_revision_id, generation_number, status, operation,
    executor, workflow_id, workflow_version, workflow_template_hash,
    manifest_hash, model, model_version, compiled_prompt, negative_prompt,
    prompt_compiler_version, seed, parameters_json, workflow_spec_json,
    workflow_spec_hash, rerun_of_generation_id, created_at, updated_at, queued_at
)
VALUES (
    :id, :shot_id, :shot_revision_id, :shot_number,
    'queued', :operation, :executor,
    :workflow_id, :workflow_version, :workflow_template_hash,
    :manifest_hash, :model, :model_version, :compiled_prompt, :negative_prompt,
    :prompt_compiler_version, :seed, :parameters_json, :workflow_spec_json,
    :workflow_spec_hash, :rerun_of_generation_id,
    {_NOW}, {_NOW}, {_NOW}
)
"""


# Exact SQLite constraint signature of UNIQUE(shot_id, generation_number).
_UNIQUE_NUMBER_SIGNATURE = (
    "UNIQUE constraint failed: generations.shot_id, generations.generation_number"
)


def _is_generation_number_uniqueness_error(exc: IntegrityError) -> bool:
    """True iff `exc` is exactly the (shot_id, generation_number) UNIQUE violation.

    Unrelated CHECK/FK/other-UNIQUE failures (including a hypothetical
    superset unique constraint) are NOT number collisions and must not be
    retried as such. SQLite emits this exact message for this constraint;
    the natural-race tests run real violations, so wording drift is caught.
    """
    orig = getattr(exc, "orig", None)
    msg = str(orig) if orig is not None else str(exc)
    return msg == _UNIQUE_NUMBER_SIGNATURE


# Primary SQLite result codes for lock contention (extended codes are masked
# down to these via code & 0xFF).
_SQLITE_BUSY_CODE = 5
_SQLITE_LOCKED_CODE = 6


def is_busy_error(exc: OperationalError) -> bool:
    """True iff `exc` is a SQLite BUSY/LOCKED lock-acquisition failure.

    Prefers the numeric sqlite_errorcode (primary code, covering extended
    result codes like SQLITE_BUSY_SNAPSHOT) when present; falls back to the
    common message forms for exceptions raised without a code attached.
    """
    orig = getattr(exc, "orig", None)
    code = getattr(orig, "sqlite_errorcode", None)
    if code is not None and (code & 0xFF) in (_SQLITE_BUSY_CODE, _SQLITE_LOCKED_CODE):
        return True
    m = str(orig if orig is not None else exc).lower()
    return (
        "database is locked" in m
        or "database table is locked" in m
        or "database schema is locked" in m
    )


def busy_error() -> SoloRingError:
    """Transient contention, translated to the stable code (plan §100, §37.1)."""
    return SoloRingError(
        ErrorCode.SQLITE_BUSY,
        "Database is busy; retry the request shortly.",
        status_code=503,
    )


def _invalid(message: str) -> SoloRingError:
    return SoloRingError(ErrorCode.VALIDATION_ERROR, message, status_code=422)


def _draft_params(draft: GenerationDraft, generation_id: str) -> dict:
    return {
        "id": generation_id,
        "shot_id": draft.shot_id,
        "shot_revision_id": draft.shot_revision_id,
        "operation": draft.operation.value,
        "executor": draft.executor,
        "workflow_id": draft.workflow_id,
        "workflow_version": draft.workflow_version,
        "workflow_template_hash": draft.workflow_template_hash,
        "manifest_hash": draft.manifest_hash,
        "model": draft.model,
        "model_version": draft.model_version,
        "compiled_prompt": draft.compiled_prompt,
        "negative_prompt": draft.negative_prompt,
        "prompt_compiler_version": draft.prompt_compiler_version,
        "seed": draft.seed,
        "parameters_json": draft.parameters_json,
        "workflow_spec_json": draft.workflow_spec_json,
        "workflow_spec_hash": draft.workflow_spec_hash,
        "rerun_of_generation_id": draft.rerun_of_generation_id,
    }


async def execute_fresh_generation_insert(
    conn, draft: GenerationDraft, generation_id: str, generation_number: int
) -> None:
    """Persist one fresh-queue Generation row from a durable spec draft.

    The shared insertion contract for the fenced create fallback and Exact
    Rerun (M6P gate review): the statement enumerates exactly the durable
    specification columns plus fresh queue lifecycle (``status='queued'``,
    server-generated timestamps), and every execution-attempt-scoped column
    is absent so it initializes NULL / its server default — the §13 total
    initialization rule, made structural. Runs on a caller-provided
    connection inside the caller's BEGIN IMMEDIATE unit.
    """
    await conn.execute(
        text(_INSERT_PLAIN),
        {**_draft_params(draft, generation_id), "shot_number": generation_number},
    )


async def execute_generation_input_insert(
    conn,
    *,
    generation_id: str,
    input_key: str,
    reference_role: str | None,
    position: int,
    asset_id: str,
    blob_hash: str,
) -> None:
    """Persist one historical GenerationInput binding on a caller connection."""
    await conn.execute(
        text(
            "INSERT INTO generation_inputs "
            "(generation_id, asset_id, input_key, reference_role, "
            " position, blob_hash) "
            "VALUES (:gid, :aid, :ik, :rr, :pos, :bh)"
        ),
        {
            "gid": generation_id,
            "aid": asset_id,
            "ik": input_key,
            "rr": reference_role,
            "pos": position,
            "bh": blob_hash,
        },
    )


async def _execute_generation_insert(session: AsyncSession, params: dict):
    """Run the atomic INSERT..SELECT..WHERE EXISTS..RETURNING.

    Extracted so the collision-retry policy can be fault-tested deterministically
    (plan §37.1). Returns the inserted row, or None when the WHERE EXISTS
    rejected the Shot/Revision.
    """
    return (await session.execute(text(_INSERT_RETURNING), params)).first()


async def _distinguish_rejection(session: AsyncSession, shot_id: str) -> SoloRingError:
    """After a zero-row insert, classify SHOT_NOT_FOUND vs revision mismatch."""
    await session.rollback()
    shot = await session.get(Shot, shot_id)
    if shot is None or shot.deleted_at is not None:
        return not_found(ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id} not found.")
    return _invalid("ShotRevision does not exist or does not belong to this Shot.")


async def _validate_bindings(
    session: AsyncSession, inputs: Sequence[ResolvedGenerationInput]
) -> None:
    for inp in inputs:
        asset = await session.get(Asset, inp.asset_id)
        if asset is None:
            raise _invalid(f"GenerationInput asset {inp.asset_id} does not exist.")
        if asset.blob_hash != inp.blob_hash:
            raise _invalid(
                f"GenerationInput blob_hash mismatch for asset {inp.asset_id}."
            )


async def _add_inputs(session: AsyncSession, generation_id: str, inputs) -> None:
    for inp in inputs:
        session.add(
            GenerationInput(
                generation_id=generation_id,
                asset_id=inp.asset_id,
                input_key=inp.input_key,
                reference_role=inp.reference_role,
                position=inp.position,
                blob_hash=inp.blob_hash,
            )
        )


async def _create_returning(
    session: AsyncSession, draft: GenerationDraft, inputs
) -> Generation:
    generation_id = str(uuid4())
    params = _draft_params(draft, generation_id)
    for attempt in (0, 1):
        try:
            row = await _execute_generation_insert(session, params)
            if row is None:
                # WHERE EXISTS rejected: Shot missing/deleted, or revision
                # mismatch. The insert itself was atomic, so classify after
                # rolling the (empty) transaction back.
                raise await _distinguish_rejection(session, draft.shot_id)

            # Write lock held from the insert onward: binding validation and
            # input insertion run in the same serialized transaction. A
            # failure here rolls back the tentative Generation entirely.
            try:
                await _validate_bindings(session, inputs)
                await _add_inputs(session, generation_id, inputs)
                await session.commit()
            except SoloRingError:
                await session.rollback()
                raise

            generation = await session.get(Generation, generation_id)
            assert generation is not None
            return generation
        except IntegrityError as exc:
            await session.rollback()
            if not _is_generation_number_uniqueness_error(exc):
                raise internal_invariant(
                    "Unexpected integrity error during Generation creation."
                )
            if attempt:
                raise internal_invariant(
                    "Generation number allocation failed after retry."
                )
            continue
        except OperationalError as exc:
            # Lock contention is NOT a number collision: never retried here.
            with contextlib.suppress(Exception):
                await session.rollback()
            if is_busy_error(exc):
                raise busy_error() from exc
            raise internal_invariant(
                "Unexpected database error during Generation creation."
            ) from exc
    raise internal_invariant("Generation number allocation exhausted retries.")


async def _create_fenced(
    engine: AsyncEngine, draft: GenerationDraft, inputs
) -> str:
    """RETURNING-less fallback: one connection, BEGIN IMMEDIATE first (§37.2).

    The write lock is acquired BEFORE any validation read, so the same
    Shot-delete race cannot invalidate a read snapshot mid-transaction.
    """
    generation_id = str(uuid4())
    async with engine.connect() as conn:
        try:
            # BEGIN IMMEDIATE inside the guard: a lock-timeout here must be
            # translated, not leaked raw (plan §37.1).
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            shot_row = (
                await conn.execute(
                    text("SELECT 1 FROM shots WHERE id = :sid AND deleted_at IS NULL"),
                    {"sid": draft.shot_id},
                )
            ).first()
            if shot_row is None:
                await conn.exec_driver_sql("ROLLBACK")
                raise not_found(
                    ErrorCode.SHOT_NOT_FOUND, f"Shot {draft.shot_id} not found."
                )

            rev_row = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM shot_revisions "
                        "WHERE id = :rid AND shot_id = :sid"
                    ),
                    {"rid": draft.shot_revision_id, "sid": draft.shot_id},
                )
            ).first()
            if rev_row is None:
                await conn.exec_driver_sql("ROLLBACK")
                raise _invalid(
                    "ShotRevision does not exist or does not belong to this Shot."
                )

            number = (
                await conn.execute(
                    text(
                        "SELECT COALESCE(MAX(generation_number), 0) + 1 "
                        "FROM generations WHERE shot_id = :sid"
                    ),
                    {"sid": draft.shot_id},
                )
            ).scalar()
            await execute_fresh_generation_insert(conn, draft, generation_id, number)

            for inp in inputs:
                asset_row = (
                    await conn.execute(
                        text("SELECT blob_hash FROM assets WHERE id = :aid"),
                        {"aid": inp.asset_id},
                    )
                ).first()
                if asset_row is None or asset_row.blob_hash != inp.blob_hash:
                    await conn.exec_driver_sql("ROLLBACK")
                    raise _invalid(
                        f"GenerationInput binding invalid for asset {inp.asset_id}."
                    )
                await execute_generation_input_insert(
                    conn,
                    generation_id=generation_id,
                    input_key=inp.input_key,
                    reference_role=inp.reference_role,
                    position=inp.position,
                    asset_id=inp.asset_id,
                    blob_hash=inp.blob_hash,
                )
            await conn.exec_driver_sql("COMMIT")
            return generation_id
        except IntegrityError:
            # Under BEGIN IMMEDIATE the number cannot collide; any integrity
            # failure here is an invariant violation, never a raw exception.
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise internal_invariant(
                "Unexpected integrity error during Generation creation."
            )
        except OperationalError as exc:
            # Includes BEGIN IMMEDIATE lock-acquisition timeouts. BUSY is a
            # stable transient error; anything else is an invariant violation.
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if is_busy_error(exc):
                raise busy_error() from exc
            raise internal_invariant(
                "Unexpected database error during Generation creation."
            ) from exc


async def create_generation(
    session: AsyncSession,
    draft: GenerationDraft,
    inputs: Sequence[ResolvedGenerationInput],
) -> Generation:
    """Atomically persist a queued Generation plus its input bindings (§40)."""
    if sqlite_supports_returning():
        return await _create_returning(session, draft, inputs)
    generation_id = await _create_fenced(session.bind, draft, inputs)
    generation = await session.get(Generation, generation_id)
    assert generation is not None
    return generation


# --- Reads (plan §35): lightweight vs full --------------------------------


async def get_generation(session: AsyncSession, generation_id: str) -> Generation:
    if not is_uuid(generation_id):
        raise not_found(
            ErrorCode.GENERATION_NOT_FOUND, f"Generation {generation_id} not found."
        )
    generation = await session.get(Generation, generation_id)
    if generation is None:
        raise not_found(
            ErrorCode.GENERATION_NOT_FOUND, f"Generation {generation_id} not found."
        )
    return generation


async def get_generation_full(session: AsyncSession, generation_id: str) -> Generation:
    """Full provenance read: explicitly loads the deferred large payloads."""
    if not is_uuid(generation_id):
        raise not_found(
            ErrorCode.GENERATION_NOT_FOUND, f"Generation {generation_id} not found."
        )
    res = await session.execute(
        select(Generation)
        .where(Generation.id == generation_id)
        .options(
            undefer(Generation.workflow_spec_json),
            undefer(Generation.executor_submission_json),
            undefer(Generation.error_details_json),
        )
    )
    generation = res.scalars().first()
    if generation is None:
        raise not_found(
            ErrorCode.GENERATION_NOT_FOUND, f"Generation {generation_id} not found."
        )
    return generation


async def list_generation_inputs(
    session: AsyncSession, generation_id: str
) -> list[GenerationInput]:
    await get_generation(session, generation_id)
    res = await session.execute(
        select(GenerationInput)
        .where(GenerationInput.generation_id == generation_id)
        .order_by(GenerationInput.input_key, GenerationInput.position)
    )
    return list(res.scalars().all())
