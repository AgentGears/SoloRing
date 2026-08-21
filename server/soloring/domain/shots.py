"""ShotService (plan §9, §10).

Shot creation makes active-Project verification + number allocation ONE atomic
operation:

  * primary path (SQLite >= 3.35): a single
    ``INSERT ... SELECT ... WHERE EXISTS(active project) ... RETURNING``
    statement — the existence check and the COALESCE(MAX)+1 allocation run
    together under SQLite's statement write lock.
  * fallback path (SQLite < 3.35, no RETURNING): one checked-out connection
    with ``BEGIN IMMEDIATE`` performing verify -> MAX -> INSERT -> read.

A split "check Project, then insert Shot" across transactions is never used.
"""

from __future__ import annotations

import contextlib

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from soloring.api.schemas.shots import ShotCreate, ShotPatch
from soloring.assets.models import Asset
from soloring.db.models import Shot, ShotReference
from soloring.db.sqlite import sqlite_supports_returning
from soloring.db.timeutil import DB_NOW_SQL
from soloring.domain import canon
from soloring.domain.ids import is_uuid, new_uuid
from soloring.domain.now import db_now
from soloring.domain.normalize import (
    normalize_optional_creative,
    normalize_required_text,
)
from soloring.domain.snapshots import ReferenceRef
from soloring.errors import (
    ErrorCode,
    SoloRingError,
    internal_invariant,
    not_found,
    validation_error,
)

_INSERT_RETURNING = f"""
INSERT INTO shots (
    id, project_id, shot_number, title, subject, action, environment,
    framing, camera_motion, lens, mood, duration_ms, created_at, updated_at
)
SELECT
    :id, :project_id,
    COALESCE((SELECT MAX(shot_number) FROM shots WHERE project_id = :project_id), 0) + 1,
    :title, :subject, :action, :environment, :framing, :camera_motion, :lens, :mood,
    :duration_ms, {DB_NOW_SQL}, {DB_NOW_SQL}
WHERE EXISTS (
    SELECT 1 FROM projects WHERE id = :project_id AND deleted_at IS NULL
)
RETURNING id, shot_number
"""

_INSERT_PLAIN = f"""
INSERT INTO shots (
    id, project_id, shot_number, title, subject, action, environment,
    framing, camera_motion, lens, mood, duration_ms, created_at, updated_at
)
VALUES (
    :id, :project_id, :shot_number, :title, :subject, :action, :environment,
    :framing, :camera_motion, :lens, :mood, :duration_ms, {DB_NOW_SQL}, {DB_NOW_SQL}
)
"""


async def _load_active(session: AsyncSession, shot_id: str) -> Shot:
    if not is_uuid(shot_id):
        raise not_found(ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id} not found.")
    shot = await session.get(Shot, shot_id)
    if shot is None or shot.deleted_at is not None:
        raise not_found(ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id} not found.")
    return shot


def _normalize_payload(data: ShotCreate) -> dict:
    subject = normalize_required_text(data.subject)
    if not subject:
        raise validation_error("Shot subject must not be empty.")
    return {
        "title": normalize_optional_creative(data.title),
        "subject": subject,
        "action": normalize_optional_creative(data.action),
        "environment": normalize_optional_creative(data.environment),
        "framing": normalize_optional_creative(data.framing),
        "camera_motion": normalize_optional_creative(data.camera_motion),
        "lens": normalize_optional_creative(data.lens),
        "mood": normalize_optional_creative(data.mood),
        "duration_ms": data.duration_ms,
    }


def _is_shot_number_uniqueness_error(exc: IntegrityError) -> bool:
    """True iff `exc` is the (project_id, shot_number) UNIQUE violation.

    A CHECK / NOT NULL / FK / any-other integrity failure is NOT a numbering
    collision and must not trigger the numbering retry policy.
    """
    orig = getattr(exc, "orig", None)
    msg = str(orig) if orig is not None else str(exc)
    return "UNIQUE constraint failed" in msg and "shot_number" in msg


async def _execute_shot_insert(session: AsyncSession, params: dict):
    """Run the atomic INSERT...SELECT...WHERE EXISTS...RETURNING.

    Extracted to its own name so the collision-retry policy can be fault-tested
    deterministically (plan §10.1, §50.4). Returns the row or None.
    """
    from sqlalchemy import text

    return (await session.execute(text(_INSERT_RETURNING), params)).first()


async def _create_returning(session: AsyncSession, params: dict, project_id: str) -> Shot:
    for attempt in (0, 1):
        try:
            row = await _execute_shot_insert(session, params)
            if row is None:
                # WHERE EXISTS false -> project missing/deleted.
                raise not_found(
                    ErrorCode.PROJECT_NOT_FOUND, f"Project {project_id} not found."
                )
            await session.commit()
            return await _load_active(session, params["id"])
        except IntegrityError as exc:
            await session.rollback()
            if not _is_shot_number_uniqueness_error(exc):
                # Unrelated integrity failure: not a numbering collision, and a
                # raw DB exception must never cross the boundary (plan §10.1).
                raise internal_invariant(
                    "Unexpected integrity error during Shot creation."
                )
            if attempt:
                raise internal_invariant(
                    "Shot number allocation failed after retry."
                )
            continue
    # unreachable
    raise internal_invariant("Shot number allocation exhausted retries.")


async def _create_fenced(engine: AsyncEngine, params: dict, project_id: str) -> None:
    from sqlalchemy import text

    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            exists = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM projects WHERE id = :pid AND deleted_at IS NULL"
                    ),
                    {"pid": project_id},
                )
            ).first()
            if exists is None:
                await conn.exec_driver_sql("ROLLBACK")
                raise not_found(
                    ErrorCode.PROJECT_NOT_FOUND, f"Project {project_id} not found."
                )
            next_num = (
                await conn.execute(
                    text(
                        "SELECT COALESCE(MAX(shot_number), 0) + 1 "
                        "FROM shots WHERE project_id = :pid"
                    ),
                    {"pid": project_id},
                )
            ).scalar()
            await conn.execute(text(_INSERT_PLAIN), {**params, "shot_number": next_num})
            await conn.exec_driver_sql("COMMIT")
        except IntegrityError:
            # Fenced path cannot collide (atomic MAX+INSERT under one lock);
            # any integrity failure here is an invariant violation, never raw.
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise internal_invariant(
                "Unexpected integrity error during Shot creation."
            )


async def create_shot(
    session: AsyncSession, project_id: str, data: ShotCreate
) -> Shot:
    if not is_uuid(project_id):
        raise not_found(ErrorCode.PROJECT_NOT_FOUND, f"Project {project_id} not found.")
    payload = _normalize_payload(data)
    params = {"id": new_uuid(), "project_id": project_id, **payload}
    if sqlite_supports_returning():
        return await _create_returning(session, params, project_id)
    await _create_fenced(session.bind, params, project_id)
    return await _load_active(session, params["id"])


async def get_shot(session: AsyncSession, shot_id: str) -> Shot:
    return await _load_active(session, shot_id)


async def list_shots(session: AsyncSession, project_id: str) -> list[Shot]:
    # Verify the parent project is active first.
    from soloring.domain.projects import _get_active

    await _get_active(session, project_id)
    res = await session.execute(
        select(Shot)
        .where(Shot.project_id == project_id, Shot.deleted_at.is_(None))
        .order_by(Shot.shot_number)
    )
    return list(res.scalars().all())


async def _reference_refs(executor, shot_id: str) -> list[ReferenceRef]:
    """Reference identity (asset_id + blob_hash + role + position) for snapshots.

    Works with both AsyncSession and AsyncConnection executors. Returns
    ReferenceRef values sorted by the canonical (role, position, asset_id).
    """
    res = await executor.execute(
        select(
            ShotReference.asset_id,
            Asset.blob_hash,
            ShotReference.role,
            ShotReference.position,
        )
        .join(Asset, ShotReference.asset_id == Asset.id)
        .where(ShotReference.shot_id == shot_id)
    )
    refs = [
        ReferenceRef(
            asset_id=row.asset_id,
            blob_hash=row.blob_hash,
            role=row.role,
            position=row.position,
        )
        for row in res
    ]
    refs.sort(key=lambda r: (r.role, r.position, r.asset_id))
    return refs


async def snapshot_references(session: AsyncSession, shot_id: str) -> list[ReferenceRef]:
    """References contributing to the working snapshot (plan §13)."""
    return await _reference_refs(session, shot_id)


# Columns of the shot-detail read unit; mapping keys match ShotRead fields.
_DETAIL_COLUMNS = (
    Shot.id,
    Shot.project_id,
    Shot.shot_number,
    Shot.title,
    Shot.subject,
    Shot.action,
    Shot.environment,
    Shot.framing,
    Shot.camera_motion,
    Shot.lens,
    Shot.mood,
    Shot.duration_ms,
    Shot.approved_take_id,
    Shot.created_at,
    Shot.updated_at,
)


def _visual_blob_store(settings=None):
    """Physical-bytes authority for the visual resolver (r2-gate B2):
    the RUNNING APP's Settings when supplied, else the process
    singleton."""
    from soloring.assets.blob_store import BlobStore
    from soloring.settings import get_settings

    if settings is not None:
        return BlobStore(settings)
    return BlobStore(get_settings())


async def read_shot_detail(engine: AsyncEngine, shot_id: str, *, settings=None):
    """One bounded consistent read unit (M2 §3.2, §47; M6C §48).

    Explicit BEGIN on one checked-out connection so the shot row, its
    references, the approved-provenance traversal, AND the semantic
    dependency resolution against current approvals all derive from ONE
    SQLite read snapshot. AsyncSession alone does not hold a read snapshot
    for SELECT-only sequences under Python sqlite3's legacy transaction
    handling; this is the same explicit-transaction pattern proven by the
    ownership module. M6-F15: the effective working hash therefore reflects
    current approvals even when the Shot row itself is untouched.

    Returns (shot_mapping, refs, differs_from_approved, resolved_deps,
    effective_hash, readiness) where readiness is the M7B §7 projection:
    continuity_state_ready + nullable hash/differs when unresolved.
    """
    from soloring.continuity.snapshots import (
        effective_working_snapshot_hash,
        resolve_working_dependencies,
    )
    from soloring.continuity.state import (
        readiness_projection,
        resolve_effective_feature_state,
        resolve_effective_relation_state,
    )
    # M7C §10.3 structural singularity: the effective states resolved in
    # THIS read unit flow into the SAME builder capture would use — the
    # working hash is the hash of the exact value capture would persist.

    if not is_uuid(shot_id):
        raise not_found(ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id} not found.")
    async with engine.connect() as conn:
        # Explicit driver BEGIN establishes the WAL read snapshot; the TERMINAL
        # commit/rollback go through SQLAlchemy so its transaction bookkeeping
        # stays in sync with the driver (conn.in_transaction() is accurate).
        await conn.exec_driver_sql("BEGIN")
        try:
            shot = (
                await conn.execute(
                    select(*_DETAIL_COLUMNS).where(
                        Shot.id == shot_id, Shot.deleted_at.is_(None)
                    )
                )
            ).mappings().first()
            if shot is None:
                raise not_found(
                    ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id} not found."
                )
            refs = await _reference_refs(conn, shot_id)
            # Dependencies resolve BEFORE the canon comparison so the hash
            # handed to canon is the SAME effective snapshot identity the
            # working hash exposes (M6C re-gate: one builder, one value).
            resolved = await resolve_working_dependencies(conn, shot_id)
            outcome = await resolve_effective_feature_state(conn, shot_id)
            relation_outcome = await resolve_effective_relation_state(
                conn, shot_id
            )
            readiness = readiness_projection(outcome, relation_outcome)
            # M8 §52: visual resolution only after semantic readiness, on
            # the same pinned snapshot (one coherent unit). When M7 is not
            # ready the composed result projects blocked (§52.1) — M7
            # blockers surface through visual_continuity_issues and the
            # visual flag is false; NULL-as-ready is never fabricated.
            from soloring.visual.readiness import resolve_visual_readiness

            visual_result = await resolve_visual_readiness(
                conn, shot_id,
                readiness["continuity_state_ready"],
                readiness["readiness_issues"],
                resolved, outcome.states,
                blob_store=_visual_blob_store(settings),
            )
            if readiness["continuity_state_ready"]:
                effective_hash = effective_working_snapshot_hash(
                    shot, refs, resolved, outcome.states,
                    relation_outcome.relation_states,
                    visual_result.pack,
                )
                differs = await canon.differs_from_approved(
                    conn, shot, refs, effective_hash
                )
            else:
                # No authoritative working snapshot exists (M7B §7): the
                # hash and the canon comparison are both NULL — never a
                # fabricated hash, never a misleading "matches".
                effective_hash = None
                differs = None
            await conn.commit()
            return (
                shot, refs, differs, resolved, effective_hash, readiness,
                visual_result,
            )
        except Exception:
            with contextlib.suppress(Exception):
                await conn.rollback()
            raise


async def patch_shot(
    session: AsyncSession, shot_id: str, data: ShotPatch
) -> Shot:
    shot = await _load_active(session, shot_id)
    provided = data.model_fields_set
    if "subject" in provided:
        subject = normalize_required_text(data.subject)
        if not subject:
            raise validation_error("Shot subject must not be empty.")
        shot.subject = subject
    if "title" in provided:
        shot.title = normalize_optional_creative(data.title)
    for field in (
        "action", "environment", "framing", "camera_motion", "lens", "mood",
    ):
        if field in provided:
            setattr(shot, field, normalize_optional_creative(getattr(data, field)))
    if "duration_ms" in provided:
        shot.duration_ms = data.duration_ms
    shot.updated_at = await db_now(session)
    await session.commit()
    await session.refresh(shot)
    return shot


async def delete_shot(session: AsyncSession, shot_id: str) -> None:
    """Fenced soft-delete (M7B §11): a Shot anchoring an active Feature
    transition is not deletable — same DELETE idempotency policy as
    Projects otherwise."""
    import contextlib as _cl

    from sqlalchemy import text as _text

    if not is_uuid(shot_id):
        raise not_found(ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id} not found.")
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            row = (
                await conn.execute(
                    _text(
                        "SELECT deleted_at FROM shots WHERE id = :sid"
                    ),
                    {"sid": shot_id},
                )
            ).first()
            if row is None:
                await conn.exec_driver_sql("ROLLBACK")
                raise not_found(
                    ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id} not found."
                )
            if row.deleted_at is not None:
                await conn.exec_driver_sql("COMMIT")  # idempotent 204
                return
            anchored = (
                await conn.execute(
                    _text(
                        "SELECT 1 FROM continuity_feature_transitions "
                        "WHERE anchor_type = 'shot' AND anchor_id = :sid "
                        "AND deleted_at IS NULL LIMIT 1"
                    ),
                    {"sid": shot_id},
                )
            ).first()
            if anchored is not None:
                await conn.exec_driver_sql("ROLLBACK")
                raise SoloRingError(
                    ErrorCode.CONTINUITY_ANCHOR_IN_USE,
                    f"Shot {shot_id} anchors an active Feature transition.",
                    status_code=409,
                )
            anchored_relation = (
                await conn.execute(
                    _text(
                        "SELECT 1 FROM continuity_relation_transitions "
                        "WHERE anchor_type = 'shot' AND anchor_id = :sid "
                        "AND deleted_at IS NULL LIMIT 1"
                    ),
                    {"sid": shot_id},
                )
            ).first()
            if anchored_relation is not None:
                await conn.exec_driver_sql("ROLLBACK")
                raise SoloRingError(
                    ErrorCode.CONTINUITY_ANCHOR_IN_USE,
                    f"Shot {shot_id} anchors an active Relation transition.",
                    status_code=409,
                )
            await conn.execute(
                _text(
                    "UPDATE shots SET deleted_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'), updated_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :sid"
                ),
                {"sid": shot_id},
            )
            await conn.exec_driver_sql("COMMIT")
        except SoloRingError:
            raise
        except Exception as exc:
            with _cl.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            from soloring.continuity.entities import _translate_op_error

            raise _translate_op_error(exc, "shot deletion") from exc
