"""RevisionService (plan §14).

Lazy capture: build the canonical snapshot from current working state, then
insert-or-reuse with bounded retry. A failed insert means one of two things and
they are NOT conflated (plan §14.3):

  * (shot_id, snapshot_hash) already present -> concurrent identical snapshot;
    return the existing revision (convergence).
  * (shot_id, revision_number) taken by a different snapshot -> revision-number
    collision; re-allocate and retry.

Exhausting the retry budget becomes a stable INTERNAL_INVARIANT_VIOLATION; a raw
IntegrityError never escapes.
"""

from __future__ import annotations

import contextlib
from types import SimpleNamespace

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.db.models import Shot, ShotRevision
from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.domain.ids import new_uuid
from soloring.domain.shots import _load_active, _reference_refs
from soloring.errors import ErrorCode, internal_invariant, not_found

MAX_REVISION_ATTEMPTS = 5


async def _snapshot_one_read(session: AsyncSession, shot_id: str):
    """Shot + references + resolved semantic dependencies + effective M7
    Feature state from ONE SQLite read snapshot (audit F2; M6 §55; M7B §9).

    An AsyncSession alone does not hold a read snapshot across sequential
    SELECT-only statements under Python sqlite3's legacy transaction
    handling, so a concurrent writer could combine two different database
    states (subject from before, references from after) into one captured
    revision — a creative state that never existed. The explicit BEGIN on
    one checked-out connection is the same pattern read_shot_detail uses
    for working-vs-approved comparison. M6C extends the same unit to load
    the working dependency rows and resolve them against current approvals,
    so a capture can never mix dependency states from two moments (§58/§59).

    M7B extends the SAME unit (never a second connection — that would race)
    with the effective Feature-state resolution, and enforces the temporary
    capture gates INSIDE the read transaction's authority: unassigned +
    relevant temporal data → NARRATIVE_CONTEXT_REQUIRED; nonempty effective
    Feature state → NARRATIVE_STATE_CAPTURE_UNAVAILABLE (until M7C). Zero
    effective state keeps the exact existing schema-1/2 path.
    """
    from soloring.continuity.snapshots import resolve_working_dependencies
    from soloring.continuity.state import (
        capture_unavailable,
        narrative_context_required,
        resolve_effective_feature_state,
    )

    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN")
        try:
            row = (
                await conn.execute(
                    select(
                        Shot.subject, Shot.action, Shot.environment,
                        Shot.framing, Shot.camera_motion, Shot.lens,
                        Shot.mood, Shot.duration_ms,
                    ).where(Shot.id == shot_id, Shot.deleted_at.is_(None))
                )
            ).mappings().one_or_none()
            if row is None:
                raise not_found(
                    ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id} not found."
                )
            shot = SimpleNamespace(**dict(row))
            refs = await _reference_refs(conn, shot_id)
            resolved = await resolve_working_dependencies(conn, shot_id)
            outcome = await resolve_effective_feature_state(conn, shot_id)
            if not outcome.assigned and outcome.relevant_temporal_data:
                raise narrative_context_required(shot_id)
            if outcome.states:
                raise capture_unavailable()
            await conn.commit()
            return shot, refs, resolved
        except Exception:
            with contextlib.suppress(Exception):
                await conn.rollback()
            raise


async def _allocate_number(conn, shot_id: str) -> int:
    """MAX(revision_number)+1 inside the caller's held write lock (seam for
    the bounded defense-in-depth collision tests)."""
    return (
        await conn.execute(
            text(
                "SELECT COALESCE(MAX(revision_number), 0) + 1 "
                "FROM shot_revisions WHERE shot_id = :sid"
            ),
            {"sid": shot_id},
        )
    ).scalar()


async def _persist_revision_fenced(
    engine,
    shot_id: str,
    snapshot_json: str,
    snapshot_hash: str,
    spec_json: str | None,
    spec_hash: str | None,
    resolved,
) -> str:
    """The ShotRevision write phase as ONE BEGIN IMMEDIATE unit (M6 §9/§57,
    M6C re-gate blocker 2):

        BEGIN IMMEDIATE
        ↓ reuse lookup by (shot_id, snapshot_hash)
        ↓ existing? -> return the winner's id
        ↓ MAX(revision_number)+1
        ↓ INSERT ShotRevision (parent first — the UOW has no mapper
          relationship to order these tables and SQLite FKs are immediate)
        ↓ INSERT all dependency rows from the SAME captured value
        ↓ COMMIT

    Under the held write lock a revision-number collision is structurally
    impossible, so the bounded retry exists purely as defense in depth for
    the uniqueness constraints; exhaustion is an invariant violation.
    """
    from soloring.generation.repository import busy_error, is_busy_error

    for _ in range(MAX_REVISION_ATTEMPTS):
        revision_id = new_uuid()
        async with engine.connect() as conn:
            try:
                await conn.exec_driver_sql("BEGIN IMMEDIATE")
                existing = (
                    await conn.execute(
                        text(
                            "SELECT id FROM shot_revisions "
                            "WHERE shot_id = :sid AND snapshot_hash = :h"
                        ),
                        {"sid": shot_id, "h": snapshot_hash},
                    )
                ).first()
                if existing is not None:
                    await conn.exec_driver_sql("COMMIT")
                    return existing[0]

                number = await _allocate_number(conn, shot_id)
                await conn.execute(
                    text(
                        "INSERT INTO shot_revisions "
                        "(id, shot_id, revision_number, snapshot_json, "
                        " snapshot_hash, continuity_spec_json, "
                        " continuity_spec_hash, created_at) "
                        "VALUES (:id, :sid, :num, :sj, :sh, :cj, :ch, "
                        "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
                    ),
                    {
                        "id": revision_id,
                        "sid": shot_id,
                        "num": number,
                        "sj": snapshot_json,
                        "sh": snapshot_hash,
                        "cj": spec_json,
                        "ch": spec_hash,
                    },
                )
                for dep in resolved:
                    await conn.execute(
                        text(
                            "INSERT INTO shot_revision_entity_dependencies "
                            "(shot_revision_id, entity_id, entity_revision_id, "
                            " role, position, source) "
                            "VALUES (:rid, :eid, :erv, :role, :pos, :src)"
                        ),
                        {
                            "rid": revision_id,
                            "eid": dep.entity_id,
                            "erv": dep.entity_revision_id,
                            "role": dep.role,
                            "pos": dep.position,
                            "src": dep.source,
                        },
                    )
                await conn.exec_driver_sql("COMMIT")
                return revision_id
            except IntegrityError:
                with contextlib.suppress(Exception):
                    await conn.exec_driver_sql("ROLLBACK")
                continue
            except OperationalError as exc:
                with contextlib.suppress(Exception):
                    await conn.exec_driver_sql("ROLLBACK")
                if is_busy_error(exc):
                    raise busy_error() from exc
                raise internal_invariant(
                    "Unexpected database error during revision persistence."
                ) from exc

    raise internal_invariant("Revision capture exhausted retries.")


async def capture_revision(session: AsyncSession, shot_id: str) -> ShotRevision:
    """Capture/reuse the immutable ShotRevision (v1 or v2, plan §52/§56-§57).

    Zero dependencies -> the EXACT v1 snapshot form with NULL continuity
    columns (byte-identical to pre-M6 captures). One or more -> schema v2
    whose continuity block, the persisted continuity columns, and the
    immutable dependency rows all derive from the SAME in-memory resolved
    value captured by the consistent read. Persistence is the fenced
    BEGIN IMMEDIATE unit above.
    """
    from soloring.continuity.snapshots import (
        build_capturable_snapshot,
        continuity_spec_bytes,
    )

    shot, refs, resolved = await _snapshot_one_read(session, shot_id)
    snapshot, continuity_spec = build_capturable_snapshot(shot, refs, resolved)
    snapshot_hash = canonical_hash(snapshot)
    snapshot_json = canonical_json_str(snapshot)
    if continuity_spec is not None:
        spec_json, spec_hash = continuity_spec_bytes(continuity_spec)
    else:
        spec_json, spec_hash = None, None

    revision_id = await _persist_revision_fenced(
        session.bind, shot_id, snapshot_json, snapshot_hash,
        spec_json, spec_hash, resolved,
    )
    revision = await session.get(ShotRevision, revision_id)
    assert revision is not None
    return revision


async def list_revisions(session: AsyncSession, shot_id: str) -> list[dict]:
    """Summary-only revision list; snapshot_json is never selected (plan §16).

    M6C: the summary includes continuity_spec_hash (NULL for v1 revisions)
    so the UI can expose historical continuity provenance per revision."""
    await _load_active(session, shot_id)
    res = await session.execute(
        select(
            ShotRevision.id,
            ShotRevision.shot_id,
            ShotRevision.revision_number,
            ShotRevision.snapshot_hash,
            ShotRevision.continuity_spec_hash,
            ShotRevision.created_at,
        )
        .where(ShotRevision.shot_id == shot_id)
        .order_by(ShotRevision.revision_number)
    )
    return [
        {
            "id": r.id,
            "shot_id": r.shot_id,
            "revision_number": r.revision_number,
            "snapshot_hash": r.snapshot_hash,
            "continuity_spec_hash": r.continuity_spec_hash,
            "created_at": r.created_at,
        }
        for r in res
    ]
