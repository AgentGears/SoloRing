"""Current Shot production-world selection (frozen M13 R3 §13 / §24.6).

One mutable current pointer per Shot to one exact immutable binding.
Expected-pointer CAS: null expected is create-only; DELETE requires the
exact non-null current pointer. The whole mutation runs under
BEGIN IMMEDIATE with binding integrity verification, in-fence candidate
re-derivation (current-complete check), and bound-subject liveness — so
no committed state ever selects a binding through a terminated
authority-subject occurrence (§22.5).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.db.timeutil import DB_NOW_SQL
from soloring.errors import (
    ErrorCode,
    SoloRingError,
    not_found,
    validation_error,
)
from soloring.production_world.binding import (
    _load_composition_revision,
    _validate_stored_binding,
    binding_current_status,
)

# Test-only seam between pointer comparison and the fence checks.
SELECTION_SEAM = None


def _selection_conflict(message: str, details: dict | None = None):
    return SoloRingError(
        ErrorCode.PRODUCTION_WORLD_SELECTION_CONFLICT, message,
        status_code=409, details=details or {})


def _stale(message: str, details: dict | None = None):
    return SoloRingError(
        ErrorCode.PRODUCTION_WORLD_BINDING_STALE, message,
        status_code=409, details=details or {})


async def _load_selection(conn, shot_id: str):
    return (
        await conn.execute(
            text("SELECT shot_id, binding_id, updated_at FROM "
                 "shot_production_world_selections WHERE shot_id = :s"),
            {"s": shot_id},
        )
    ).first()


async def _verify_selection_preconditions(
    conn, *, shot: dict, binding_id: str,
) -> dict:
    """Integrity + current-completeness + liveness under the fence."""
    stored = await _validate_stored_binding(conn, binding_id)
    current_complete, stale_details = await binding_current_status(
        conn,
        composition_revision_id=stored["composition_revision_id"],
        spatial_world_revision_id=stored["spatial_world_revision_id"],
        stored_value={
            "subjects": stored["subjects"], "entries": stored["entries"],
            "composition_revision": {
                "revision_id": stored["composition_revision_id"],
                "snapshot_hash": stored["composition_revision_hash"]},
            "spatial_world_revision": {
                "revision_id": stored["spatial_world_revision_id"],
                "snapshot_hash": stored["spatial_world_revision_hash"]},
            "schema_version": 1,
        })
    if not current_complete:
        raise _stale(
            "selected binding is no longer current-complete",
            {"stale_details": stale_details})
    # bound-subject liveness: no promoted authority-subject occurrence may
    # be terminated (§13.1/§22.5)
    subject_occurrences = [s["occurrence_id"] for s in stored["subjects"]]
    if subject_occurrences:
        ph = ",".join(f":o{i}" for i in range(len(subject_occurrences)))
        params = {f"o{i}": o for i, o in enumerate(subject_occurrences)}
        terminated = {
            r[0] for r in (
                await conn.execute(
                    text(
                        "SELECT s.occurrence_id FROM "
                        "composition_identity_operation_sources s "
                        "JOIN composition_identity_operations op "
                        "ON op.id = s.operation_id "
                        "WHERE op.composition_id = :cid "
                        "AND s.terminates_identity = 1 AND s.occurrence_id "
                        f"IN ({ph})"),
                        {"cid": stored["composition_id"], **params},
                )
            ).fetchall()}
        if terminated:
            raise _stale(
                "a bound authority-subject occurrence is terminated",
                {"terminated_occurrences": sorted(terminated)})
    # Project coherence: binding's Composition belongs to the Shot Project
    comp = (
        await conn.execute(
            text("SELECT project_id FROM compositions WHERE id = :c"),
            {"c": stored["composition_id"]},
        )
    ).first()
    if comp is None or comp.project_id != shot["project_id"]:
        raise validation_error(
            "selected binding belongs to another Project")
    return stored


async def put_selection(
    session: AsyncSession, shot_id: str, *, binding_id: str,
    expected_binding_id: str | None,
) -> dict:
    if not isinstance(binding_id, str) or not binding_id:
        raise validation_error("binding_id must be a UUID string")
    if expected_binding_id is not None and not isinstance(
            expected_binding_id, str):
        raise validation_error(
            "expected_binding_id must be a UUID string or null")
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        shot = (
            await conn.execute(
                text("SELECT id, project_id, deleted_at FROM shots "
                     "WHERE id = :s"), {"s": shot_id},
            )
        ).first()
        if shot is None or shot.deleted_at is not None:
            raise not_found(
                ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id!r} not found.")
        shot = {"id": shot.id, "project_id": shot.project_id}
        current = await _load_selection(conn, shot_id)

        if expected_binding_id is None:
            if current is not None:
                raise _selection_conflict(
                    "a selection already exists; null expected pointer is "
                    "create-only — GET the current pointer and retry",
                    {"current_binding_id": current.binding_id})
        else:
            if current is None:
                raise _selection_conflict(
                    "no current selection; expected pointer does not match",
                    {"current_binding_id": None})
            if current.binding_id != expected_binding_id:
                raise _selection_conflict(
                    "expected pointer does not match the current selection",
                    {"current_binding_id": current.binding_id})

        if SELECTION_SEAM is not None:
            await SELECTION_SEAM()

        stored = await _verify_selection_preconditions(
            conn, shot=shot, binding_id=binding_id)
        if current is None:
            await conn.execute(
                text(
                    "INSERT INTO shot_production_world_selections "
                    f"(shot_id, binding_id, updated_at) VALUES "
                    f"(:s, :b, {DB_NOW_SQL})"
                ),
                {"s": shot_id, "b": binding_id},
            )
        else:
            await conn.execute(
                text(
                    "UPDATE shot_production_world_selections SET "
                    f"binding_id = :b, updated_at = {DB_NOW_SQL} "
                    "WHERE shot_id = :s"
                ),
                {"s": shot_id, "b": binding_id},
            )
        await conn.exec_driver_sql("COMMIT")
    return await get_selection(session, shot_id) | {
        "binding": await read_binding_summary(session, binding_id)}


async def delete_selection(
    session: AsyncSession, shot_id: str, *, expected_binding_id: str,
) -> None:
    if not isinstance(expected_binding_id, str) or not expected_binding_id:
        raise validation_error(
            "DELETE requires an exact non-null expected_binding_id; no "
            "implicit 'delete whatever is there' exists")
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        shot = (
            await conn.execute(
                text("SELECT id FROM shots WHERE id = :s AND deleted_at "
                     "IS NULL"), {"s": shot_id},
            )
        ).first()
        if shot is None:
            raise not_found(
                ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id!r} not found.")
        current = await _load_selection(conn, shot_id)
        if current is None or current.binding_id != expected_binding_id:
            raise _selection_conflict(
                "expected pointer does not match the current selection",
                {"current_binding_id": (
                    current.binding_id if current else None)})
        await conn.execute(
            text("DELETE FROM shot_production_world_selections "
                 "WHERE shot_id = :s"), {"s": shot_id},
        )
        await conn.exec_driver_sql("COMMIT")


async def get_selection(session: AsyncSession, shot_id: str) -> dict:
    async with session.bind.connect() as conn:
        shot = (
            await conn.execute(
                text("SELECT id FROM shots WHERE id = :s AND deleted_at "
                     "IS NULL"), {"s": shot_id},
            )
        ).first()
        if shot is None:
            raise not_found(
                ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id!r} not found.")
        row = await _load_selection(conn, shot_id)
        if row is None:
            return {"shot_id": shot_id, "binding_id": None,
                    "updated_at": None}
        return {"shot_id": row.shot_id, "binding_id": row.binding_id,
                "updated_at": row.updated_at}


async def read_binding_summary(session: AsyncSession, binding_id: str):
    from soloring.production_world.binding import read_binding
    return await read_binding(session, binding_id)
