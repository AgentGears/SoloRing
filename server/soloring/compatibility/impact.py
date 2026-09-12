"""M15B current-impact inventory and tracking policy (frozen R6 §9/§10/§16).

Read/coordination-only: nothing here mutates a working occurrence's
ProductionRevision source, and discovery never creates an assessment.
Advisory diagnostics are set-oriented, labeled, and excluded from the
compatibility report hash.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from soloring.errors import SoloRingError, validation_error

TRACKING_CODE = "PRODUCTION_COMPATIBILITY_CONFLICT"


def _tracking_conflict(expected: int, actual: int | None) -> SoloRingError:
    return SoloRingError(
        TRACKING_CODE,
        "tracking policy expected-version mismatch",
        status_code=409,
        details={"reason": "tracking_policy_conflict",
                 "expected_policy_version": expected,
                 "actual_policy_version": actual},
    )


async def direct_working_uses(
        conn: AsyncConnection, *, production_revision_id: str) -> list[dict]:
    """§9.1 — the exact updateable use set, set-oriented and ordered."""
    rows = (await conn.execute(text(
        "SELECT w.composition_id, w.occurrence_id, c.project_id "
        "FROM composition_working_occurrences w "
        "JOIN compositions c ON c.id = w.composition_id "
        "WHERE w.production_revision_id = :r "
        "AND w.source_kind = 'production_revision' "
        "ORDER BY w.composition_id, w.occurrence_id"),
        {"r": production_revision_id})).fetchall()
    return [{"composition_id": r.composition_id,
             "occurrence_id": r.occurrence_id,
             "project_id": r.project_id} for r in rows]


async def advisory_references(
        conn: AsyncConnection, *, production_revision_id: str
) -> dict:
    """§9.2 — non-authoritative diagnostics, never in the report hash.

    Three set-oriented query classes:
      * published CompositionRevision references;
      * historical ShotRevision references;
      * current Shot production-world selections pinned through old
        bindings whose entries reference the source revision.
    """
    published = (await conn.execute(text(
        "SELECT cro.composition_revision_id, cro.composition_id "
        "FROM composition_revision_occurrences cro "
        "WHERE cro.production_revision_id = :r "
        "ORDER BY cro.composition_revision_id"),
        {"r": production_revision_id})).fetchall()
    historical = (await conn.execute(text(
        "SELECT srpw.shot_revision_id "
        "FROM shot_revision_production_worlds srpw "
        "JOIN composition_spatial_binding_entries e "
          "ON e.binding_id = srpw.binding_id "
        "WHERE e.production_revision_id = :r "
        "ORDER BY srpw.shot_revision_id"),
        {"r": production_revision_id})).fetchall()
    current_selections = (await conn.execute(text(
        "SELECT s.shot_id, s.binding_id "
        "FROM shot_production_world_selections s "
        "JOIN composition_spatial_binding_entries e "
          "ON e.binding_id = s.binding_id "
        "WHERE e.production_revision_id = :r "
        "ORDER BY s.shot_id"),
        {"r": production_revision_id})).fetchall()
    return {
        "published_composition_references": [
            {"composition_revision_id": r.composition_revision_id,
             "composition_id": r.composition_id} for r in published],
        "historical_shot_references": [
            {"shot_revision_id": r.shot_revision_id}
            for r in historical],
        "current_shot_selections": [
            {"shot_id": r.shot_id, "binding_id": r.binding_id}
            for r in current_selections],
        "advisory_only": True,
        "mutated_by_apply": False,
    }


async def tracking_policy(
        conn: AsyncConnection, *, composition_id: str, occurrence_id: str
) -> dict:
    """§16.1 — absence is never-authored PINNED/version 0."""
    row = (await conn.execute(text(
        "SELECT mode, policy_version FROM "
        "composition_occurrence_revision_tracking "
        "WHERE composition_id = :c AND occurrence_id = :o"),
        {"c": composition_id, "o": occurrence_id})).one_or_none()
    if row is None:
        return {"mode": "PINNED", "policy_version": 0}
    return {"mode": row.mode, "policy_version": row.policy_version}


async def put_tracking_policy(
        conn: AsyncConnection, *, composition_id: str, occurrence_id: str,
        mode: str, expected_policy_version: int) -> dict:
    """§16.1 CAS ladder — ABA-safe; same-mode PUT is idempotent."""
    if mode not in ("PINNED", "TRACK_COMPATIBLE"):
        raise validation_error(
            "mode must be 'PINNED' or 'TRACK_COMPATIBLE'")
    if not isinstance(expected_policy_version, int) or isinstance(
            expected_policy_version, bool) or expected_policy_version < 0:
        raise validation_error(
            "expected_policy_version must be a non-negative integer")
    # the occurrence must be an active direct ProductionRevision-backed
    # working use for policy mutation (terminated/other-source refuses)
    working = (await conn.execute(text(
        "SELECT source_kind FROM composition_working_occurrences "
        "WHERE composition_id = :c AND occurrence_id = :o"),
        {"c": composition_id, "o": occurrence_id})).one_or_none()
    if working is None or working.source_kind != "production_revision":
        raise SoloRingError(
            TRACKING_CODE,
            "tracking policy mutation requires an active direct "
            "ProductionRevision-backed working occurrence",
            status_code=409,
            details={"reason": "occurrence_inactive"})
    current = await tracking_policy(
        conn, composition_id=composition_id, occurrence_id=occurrence_id)
    actual = current["policy_version"]
    if actual != expected_policy_version:
        raise _tracking_conflict(expected_policy_version, actual)
    if current["mode"] == mode and actual == 0:
        return current  # absent/v0 + PUT PINNED: idempotent no-op
    if current["mode"] == mode:
        return current  # existing same-mode: idempotent, no increment
    if actual == 0:
        await conn.execute(text(
            "INSERT INTO composition_occurrence_revision_tracking "
            "(composition_id, occurrence_id, mode, policy_version, "
            "created_at, updated_at) VALUES "
            "(:c, :o, :m, 1, :n, :n)"),
            {"c": composition_id, "o": occurrence_id, "m": mode,
             "n": await _now(conn)})
    else:
        await conn.execute(text(
            "UPDATE composition_occurrence_revision_tracking "
            "SET mode = :m, policy_version = policy_version + 1, "
            "updated_at = :n WHERE composition_id = :c "
            "AND occurrence_id = :o AND policy_version = :e"),
            {"m": mode, "n": await _now(conn), "c": composition_id,
             "o": occurrence_id, "e": expected_policy_version})
        row = (await conn.execute(text(
            "SELECT policy_version FROM "
            "composition_occurrence_revision_tracking "
            "WHERE composition_id = :c AND occurrence_id = :o"),
            {"c": composition_id, "o": occurrence_id})).one()
        if row.policy_version != expected_policy_version + 1:
            raise _tracking_conflict(
                expected_policy_version, row.policy_version)
    return await tracking_policy(
        conn, composition_id=composition_id, occurrence_id=occurrence_id)


async def _now(conn: AsyncConnection) -> str:
    from soloring.db.timeutil import DB_NOW_SQL

    return (await conn.execute(text(f"SELECT {DB_NOW_SQL}"))).scalar_one()


async def update_discovery(
        conn: AsyncConnection, *, production_object_id: str
) -> dict:
    """§16.2 — set-oriented tracked-use info + concrete newer
    candidates; never creates an assessment, never selects latest."""
    obj = (await conn.execute(text(
        "SELECT id, project_id FROM production_objects "
        "WHERE id = :o"), {"o": production_object_id})).one_or_none()
    if obj is None:
        from soloring.errors import not_found, ErrorCode

        raise not_found(
            ErrorCode.PRODUCTION_REVISION_NOT_FOUND,
            f"production object {production_object_id!r} not found")

    # all active tracked uses of any revision of this object (one
    # bounded query class; per-world/candidate shaping is in-memory)
    rows = (await conn.execute(text(
        "SELECT w.composition_id, w.occurrence_id, "
        "w.production_revision_id, t.mode "
        "FROM composition_working_occurrences w "
        "JOIN composition_occurrence_revision_tracking t "
          "ON t.composition_id = w.composition_id "
          "AND t.occurrence_id = w.occurrence_id "
        "WHERE t.mode = 'TRACK_COMPATIBLE' "
        "AND w.source_kind = 'production_revision' "
        "AND w.production_revision_id IN "
          "(SELECT id FROM production_revisions "
          "  WHERE production_object_id = :o) "
        "ORDER BY w.composition_id, w.occurrence_id"),
        {"o": production_object_id})).fetchall()

    candidates = (await conn.execute(text(
        "SELECT id, revision_number, snapshot_hash FROM "
        "production_revisions WHERE production_object_id = :o "
        "ORDER BY revision_number DESC, id ASC"),
        {"o": production_object_id})).fetchall()
    by_number = {r.id: r.revision_number for r in candidates}

    uses = []
    for r in rows:
        current_number = by_number[r.production_revision_id]
        newer = [{"revision_id": c.id,
                  "revision_number": c.revision_number,
                  "snapshot_hash": c.snapshot_hash}
                 for c in candidates
                 if c.revision_number > current_number]
        uses.append({
            "composition_id": r.composition_id,
            "occurrence_id": r.occurrence_id,
            "mode": r.mode,
            "current_revision_id": r.production_revision_id,
            "current_revision_number": current_number,
            "candidates": newer,
            "assessment_created": False,
        })
    return {"production_object_id": production_object_id,
            "tracked_use_count": len(uses),
            "uses": uses,
            "assessment_created": False}
