"""Working state vs approved canon (v0.1 plan §94, M2 plan §3.2).

Server-side only; the frontend never recomputes this. The comparison runs
inside the caller's single explicit driver transaction (see
``shots.read_shot_detail``) so the working snapshot and the approved
provenance traversal derive from ONE SQLite read snapshot.

NOTE on mechanism (deviation from the plan's "one AsyncSession transaction"
wording): Python's sqlite3 legacy transaction handling does not open a driver
transaction for SELECT-only sequences, so two reads in one AsyncSession are two
autocommit reads with no held WAL snapshot (proven by the interleave test that
motivated this design). The explicit BEGIN-on-one-connection pattern already
proven by the ownership module is used instead; the plan's requirement — one
bounded consistent read, never mixed snapshots — is what this delivers.

A non-null ``approved_take_id`` with any dangling or cross-Shot provenance link
is a ledger invariant violation: log diagnostics and raise
INTERNAL_INVARIANT_VIOLATION — never silently return false.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from soloring.db.models import Generation, ShotRevision, Take
from soloring.domain.snapshots import ReferenceRef, working_snapshot_hash
from soloring.errors import ErrorCode, SoloRingError

log = logging.getLogger("soloring.domain.canon")


async def _checkpoint() -> None:
    """Fault-injection seam for the deterministic read-snapshot interleave test.

    Fires after the working-state reads and before the provenance traversal.
    Production behavior is a no-op.
    """


def _broken(shot, link: str, **ids: str) -> SoloRingError:
    """Log the integrity failure and build the invariant error (plan §3.2.1).

    `shot` is the read-unit's shot mapping; only safe identifiers are logged.
    """
    log.error(
        "CANON INTEGRITY: broken approved provenance for shot %s "
        "(approved_take_id=%s, broken_link=%s, %s)",
        shot.id,
        shot.approved_take_id,
        link,
        ids,
    )
    return SoloRingError(
        ErrorCode.INTERNAL_INVARIANT_VIOLATION,
        "Approved Take provenance chain is broken.",
        status_code=500,
        details={
            "shot_id": shot.id,
            "approved_take_id": shot.approved_take_id,
            "broken_link": link,
            **ids,
        },
    )


async def differs_from_approved(
    conn: AsyncConnection, shot, refs: list[ReferenceRef], working_hash: str
) -> bool:
    """§94 comparison over the read unit's already-loaded Shot and references.

    Returns False when no canon exists (``approved_take_id IS NULL``) — meaning
    there is no canon to differ from, not that working state matches canon.

    M6C: ``working_hash`` is the EFFECTIVE continuity-aware snapshot hash
    computed by the caller's read unit from the SAME consistent snapshot
    (intent + references + resolved semantic dependencies). There is exactly
    one working-state builder; this function never recomputes one.
    """
    if shot.approved_take_id is None:
        return False

    await _checkpoint()

    take = (
        await conn.execute(
            select(Take.id, Take.shot_id, Take.generation_id).where(
                Take.id == shot.approved_take_id
            )
        )
    ).mappings().first()
    if take is None:
        raise _broken(shot, "approved_take_missing")
    if take.shot_id != shot.id:
        raise _broken(shot, "take_belongs_to_other_shot", take_id=take.id)

    generation = (
        await conn.execute(
            select(Generation.shot_id, Generation.shot_revision_id).where(
                Generation.id == take.generation_id
            )
        )
    ).mappings().first()
    if generation is None:
        raise _broken(
            shot,
            "generation_missing",
            take_id=shot.approved_take_id,
            generation_id=take.generation_id,
        )
    if generation.shot_id != shot.id:
        raise _broken(
            shot,
            "generation_belongs_to_other_shot",
            take_id=shot.approved_take_id,
            generation_id=take.generation_id,
        )

    revision = (
        await conn.execute(
            select(ShotRevision.shot_id, ShotRevision.snapshot_hash).where(
                ShotRevision.id == generation.shot_revision_id
            )
        )
    ).mappings().first()
    if revision is None:
        raise _broken(
            shot,
            "revision_missing",
            take_id=shot.approved_take_id,
            generation_id=take.generation_id,
            revision_id=generation.shot_revision_id,
        )
    if revision.shot_id != shot.id:
        raise _broken(
            shot,
            "revision_belongs_to_other_shot",
            take_id=shot.approved_take_id,
            generation_id=take.generation_id,
            revision_id=generation.shot_revision_id,
        )

    # The caller's effective hash was built by the same canonical builder
    # used for revision capture (plan §6.2), including semantic continuity.
    return working_hash != revision.snapshot_hash
