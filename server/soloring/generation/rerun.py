"""Exact Rerun service primitive (M6 plan §10–§15; binding §13 correction).

A rerun is a NEW execution attempt of a terminal source Generation's durable
historical specification:

    §12 durable specification fields          ->  copied verbatim
    everything else (execution-attempt state) ->  fresh queue state

The §13 contract is a TOTAL initialization rule, not an exclusion list: the
new row is written only through ``repository.execute_fresh_generation_insert``
— the shared fresh-Generation insertion contract — which enumerates exactly
the durable spec columns plus fresh queue lifecycle (``status='queued'``,
fresh created_at/updated_at/queued_at) and leaves every attempt-scoped
column absent from the statement so it initializes NULL / its server
default:

    attempt_id                  NULL  (minted at claim, per the M3C fence)
    executor_submission_state   'not_started' (server default)
    submission_possible_at      NULL
    executor_submission_json    NULL
    executor_submission_hash    NULL
    executor_job_id             NULL
    executor_handle_json        NULL
    soft_cancel_selected_at     NULL  (one-way durable cancel decision)
    cancel_requested_at         NULL
    cancel_reason               NULL
    claimed_at / heartbeat_at / worker_id          NULL
    progress_current / progress_total / current_node   NULL
    error_code / error_message / error_details_json    NULL
    started_at / completed_at   NULL

The database CHECK constraints (submission_possible => attempt_id,
confirmed => executor_job_id, soft_cancel => cancel intent) are defense in
depth; they are not relied upon to define rerun semantics.

One checked-out connection, ``BEGIN IMMEDIATE`` (plan §9, §14): source load,
terminal-source verification, historical input load, generation-number
allocation, Generation insert, and copied GenerationInput inserts all run
inside the single write-locked transaction. Under IMMEDIATE the allocated
number cannot collide, so an IntegrityError here is an invariant violation,
never a retryable collision.

Availability rule (M6P gate review): rerun depends ONLY on preserved
historical state — the source Generation exists, is terminal, and its
ShotRevision / GenerationInputs remain intact behind their FKs. Current
mutable lifecycle state is deliberately irrelevant: a soft-deleted Shot (or
its soft-deleting Project) still has its full production history, so a
rerun remains available. Normal creation requires an active Shot because it
derives a NEW request from current Shot state; Exact Rerun derives a new
execution attempt entirely from the immutable historical Generation.

Never reads: Shot working fields, ShotReferences, Story World, current
Entity approvals, Shot/Project lifecycle. The source Generation row and its
GenerationInputs are the only inputs, and both are immutable once the
source is terminal.
"""

from __future__ import annotations

import contextlib
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from soloring.db.models import Generation
from soloring.domain.ids import is_uuid
from soloring.errors import ErrorCode, SoloRingError, internal_invariant, not_found
from soloring.generation import repository as repo
from soloring.generation.drafts import GenerationDraft
from soloring.generation.enums import GenerationOperation

_ACTIVE = frozenset({"queued", "preparing", "submitted", "running", "importing"})
_TERMINAL = frozenset({"succeeded", "failed", "interrupted", "cancelled"})

# Source columns forming the §12 durable historical specification.
_SOURCE_SELECT = """
SELECT id, shot_id, shot_revision_id, status, executor,
       workflow_id, workflow_version, workflow_template_hash, manifest_hash,
       model, model_version, compiled_prompt, negative_prompt,
       prompt_compiler_version, seed, parameters_json,
       workflow_spec_json, workflow_spec_hash
FROM generations
WHERE id = :gid
"""

_INPUT_SELECT = """
SELECT input_key, reference_role, position, asset_id, blob_hash
FROM generation_inputs
WHERE generation_id = :gid
ORDER BY input_key, position
"""


def _active_error(source_id: str, status: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.GENERATION_ACTIVE,
        f"Generation {source_id} is still {status}; "
        "only terminal generations can be rerun.",
        status_code=409,
    )


async def _create_rerun_fenced(
    engine: AsyncEngine, source_generation_id: str
) -> str:
    """Persist the rerun inside one BEGIN IMMEDIATE unit; return the new id."""
    if not is_uuid(source_generation_id):
        raise not_found(
            ErrorCode.GENERATION_NOT_FOUND,
            f"Generation {source_generation_id} not found.",
        )
    generation_id = str(uuid4())
    async with engine.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")

            src = (
                await conn.execute(
                    text(_SOURCE_SELECT), {"gid": source_generation_id}
                )
            ).mappings().one_or_none()
            if src is None:
                await conn.exec_driver_sql("ROLLBACK")
                raise not_found(
                    ErrorCode.GENERATION_NOT_FOUND,
                    f"Generation {source_generation_id} not found.",
                )
            if src["status"] in _ACTIVE:
                await conn.exec_driver_sql("ROLLBACK")
                raise _active_error(source_generation_id, src["status"])
            if src["status"] not in _TERMINAL:
                await conn.exec_driver_sql("ROLLBACK")
                raise internal_invariant(
                    f"Generation {source_generation_id} has unknown status "
                    f"{src['status']!r}."
                )

            inputs = (
                await conn.execute(text(_INPUT_SELECT), {"gid": source_generation_id})
            ).mappings().all()

            draft = GenerationDraft(
                shot_id=src["shot_id"],
                shot_revision_id=src["shot_revision_id"],
                operation=GenerationOperation.RERUN,
                executor=src["executor"],
                workflow_id=src["workflow_id"],
                workflow_version=src["workflow_version"],
                workflow_template_hash=src["workflow_template_hash"],
                manifest_hash=src["manifest_hash"],
                model=src["model"],
                model_version=src["model_version"],
                compiled_prompt=src["compiled_prompt"],
                negative_prompt=src["negative_prompt"],
                prompt_compiler_version=src["prompt_compiler_version"],
                seed=src["seed"],
                parameters_json=src["parameters_json"],
                workflow_spec_json=src["workflow_spec_json"],
                workflow_spec_hash=src["workflow_spec_hash"],
                rerun_of_generation_id=src["id"],
            )

            number = (
                await conn.execute(
                    text(
                        "SELECT COALESCE(MAX(generation_number), 0) + 1 "
                        "FROM generations WHERE shot_id = :sid"
                    ),
                    {"sid": src["shot_id"]},
                )
            ).scalar()

            await repo.execute_fresh_generation_insert(
                conn, draft, generation_id, number
            )
            for row in inputs:
                await repo.execute_generation_input_insert(
                    conn,
                    generation_id=generation_id,
                    input_key=row["input_key"],
                    reference_role=row["reference_role"],
                    position=row["position"],
                    asset_id=row["asset_id"],
                    blob_hash=row["blob_hash"],
                )
            await conn.exec_driver_sql("COMMIT")
            return generation_id
        except IntegrityError:
            # Under BEGIN IMMEDIATE the number cannot collide; any integrity
            # failure is an invariant violation, never a raw exception.
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise internal_invariant(
                "Unexpected integrity error during rerun creation."
            )
        except OperationalError as exc:
            # Includes BEGIN IMMEDIATE lock-acquisition timeouts. BUSY is the
            # stable transient error; anything else is an invariant violation.
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if repo.is_busy_error(exc):
                raise repo.busy_error() from exc
            raise internal_invariant(
                "Unexpected database error during rerun creation."
            ) from exc


async def create_rerun(session: AsyncSession, source_generation_id: str) -> Generation:
    """Create the Exact Rerun of a terminal source Generation (§14).

    Returns the freshly queued rerun row. The caller never receives a
    partially initialized Generation: the row and its copied GenerationInputs
    commit atomically inside the fenced write unit.
    """
    generation_id = await _create_rerun_fenced(session.bind, source_generation_id)
    generation = await session.get(Generation, generation_id)
    assert generation is not None
    return generation
