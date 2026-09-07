"""Current inspection + captured-graph-only historical reader (frozen R3
§14.5/§20/§24.6-24.7).

The current projection reuses the ONE resolver inside one coherent read
(same connection, M10 composed before M13). The historical reader walks
the captured graph only — it never re-derives current binding candidates,
never reads the current Shot selection, never resolves current PI
transitions/tracks, and never consults current M10 approval.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.errors import ErrorCode, SoloRingError, internal_invariant
from soloring.production_world.binding import _validate_stored_binding
from soloring.production_world.resolver import (
    resolve_production_world,
)


async def inspect_production_world(session: AsyncSession,
                                   shot_id: str) -> dict:
    """GET /shots/{shot_id}/production-world (§14.5) — the resolver-derived
    status projection from ONE coherent read."""
    from soloring.continuity.snapshots import resolve_working_dependencies
    from soloring.spatial.resolver import resolve_spatial_continuity

    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN")
        try:
            shot = (
                await conn.execute(
                    text("SELECT id FROM shots WHERE id = :s "
                         "AND deleted_at IS NULL"), {"s": shot_id},
                )
            ).first()
            if shot is None:
                raise SoloRingError(
                    ErrorCode.SHOT_NOT_FOUND,
                    f"Shot {shot_id!r} not found.", status_code=404)
            resolved = await resolve_working_dependencies(conn, shot_id)
            m10 = await resolve_spatial_continuity(
                conn, shot_id=shot_id, resolved_dependencies=resolved)
            outcome = await resolve_production_world(
                conn, shot_id=shot_id, resolved_dependencies=resolved,
                m10_spatial_result=m10)
            await conn.commit()
        except Exception:
            import contextlib

            with contextlib.suppress(Exception):
                await conn.rollback()
            raise
    return {
        "shot_id": shot_id,
        "selected": outcome.selected,
        "binding_id": outcome.binding_id,
        "binding_hash": outcome.binding_hash,
        "binding_current_complete": outcome.binding_current_complete,
        "stale_details": list(outcome.stale_details),
        "ready": outcome.ready,
        "issues": [dict(i) for i in outcome.issues],
        "production_world": outcome.pack,
        "production_world_hash": outcome.production_world_hash,
    }


async def read_captured_production_world(
    session: AsyncSession, revision_id: str,
) -> dict:
    """Historical §24.7 projection — captured graph ONLY (§20.2/§20.3).

    Verifies the immutable binding (integrity tier), reads the captured
    parent + PI children, and fails closed when any pinned immutable
    dependency is unreachable. Never performs current readiness."""
    async with session.bind.connect() as conn:
        from soloring.domain.ids import is_uuid

        if not is_uuid(revision_id):
            raise SoloRingError(
                ErrorCode.SHOT_NOT_FOUND,
                f"ShotRevision {revision_id!r} not found.", status_code=404)
        rev = (
            await conn.execute(
                text("SELECT id, snapshot_json FROM shot_revisions "
                     "WHERE id = :r"), {"r": revision_id},
            )
        ).first()
        if rev is None:
            raise SoloRingError(
                ErrorCode.SHOT_NOT_FOUND,
                f"ShotRevision {revision_id!r} not found.", status_code=404)
        import json as _json

        snapshot = _json.loads(rev.snapshot_json)
        captured = snapshot.get("production_world") if isinstance(
            snapshot, dict) else None
        parent = (
            await conn.execute(
                text(
                    "SELECT production_world_hash, binding_id, "
                    "binding_hash, composition_revision_id, "
                    "composition_revision_hash, "
                    "spatial_world_revision_id, "
                    "spatial_world_revision_hash FROM "
                    "shot_revision_production_worlds "
                    "WHERE shot_revision_id = :r"),
                {"r": revision_id},
            )
        ).mappings().one_or_none()
        if captured is None:
            if parent is not None:
                raise internal_invariant(
                    f"ShotRevision {revision_id}: stored M13 children "
                    "without schema-6 production_world content")
            return {"revision_id": revision_id, "schema_version":
                    snapshot.get("schema_version"), "captured": False}

        if parent is None:
            raise internal_invariant(
                f"ShotRevision {revision_id}: schema-6 production_world "
                "content without stored M13 parent row")
        # exact parent projection equality with the embedded pack
        b = captured["binding"]
        if (parent["production_world_hash"] is None
                or parent["binding_id"] != b["binding_id"]
                or parent["binding_hash"] != b["binding_hash"]):
            raise internal_invariant(
                f"ShotRevision {revision_id}: M13 parent row disagrees "
                "with the captured pack")
        # captured-graph-only closure: the immutable binding must verify;
        # an unreachable pinned binding is corrupt historical state (§20.3),
        # never a friendly 404
        from soloring.errors import not_found as _nf

        try:
            stored_binding = await _validate_stored_binding(
                conn, parent["binding_id"])
        except SoloRingError as exc:
            if exc.status_code == 404:
                raise internal_invariant(
                    f"ShotRevision {revision_id}: the captured binding "
                    f"{parent['binding_id']} is unreachable — corrupt "
                    "historical state") from exc
            raise
        # §20.2/§30.8: every pinned entry's immutable spatial
        # interpretation must exist and verify (captured-graph-only — the
        # interpretation table is immutable historical closure, §21)
        from soloring.production_world.canonical import (
            verify_stored_interpretation,
        )

        for e in stored_binding["entries"]:
            irow = (
                await conn.execute(
                    text(
                        "SELECT production_revision_id, schema_version, "
                        "x_mm, y_mm, z_mm, yaw_udeg, pitch_udeg, "
                        "roll_udeg, interpretation_json, "
                        "interpretation_hash FROM "
                        "production_revision_spatial_interpretations "
                        "WHERE production_revision_id = :r"),
                    {"r": e["production_revision_id"]},
                )
            ).first()
            if irow is None or (irow.interpretation_hash
                                != e["spatial_interpretation_hash"]):
                raise internal_invariant(
                    f"ShotRevision {revision_id}: pinned spatial "
                    "interpretation is missing or does not match the "
                    "captured entry")
            parents = (
                await conn.execute(
                    text(
                        "SELECT pr.snapshot_hash, (SELECT c.blob_hash FROM "
                        "production_revision_closures c WHERE "
                        "c.production_revision_id = pr.id AND "
                        "c.contract_key = 'retained_blob' AND "
                        "c.contract_version = 1) AS blob_hash FROM "
                        "production_revisions pr WHERE pr.id = :r"),
                    {"r": e["production_revision_id"]},
                )
            ).first()
            if parents is None or parents.blob_hash is None:
                raise internal_invariant(
                    f"ShotRevision {revision_id}: interpretation parent "
                    "closure is unreachable")
            try:
                verify_stored_interpretation(
                    interpretation_json=irow.interpretation_json,
                    interpretation_hash=irow.interpretation_hash,
                    x_mm=irow.x_mm, y_mm=irow.y_mm, z_mm=irow.z_mm,
                    yaw_udeg=irow.yaw_udeg, pitch_udeg=irow.pitch_udeg,
                    roll_udeg=irow.roll_udeg,
                    row_production_revision_id=irow.production_revision_id,
                    parent_snapshot_hash=parents.snapshot_hash,
                    parent_blob_hash=parents.blob_hash)
            except SoloRingError as exc:
                raise internal_invariant(
                    f"ShotRevision {revision_id}: pinned spatial "
                    f"interpretation is corrupt: {exc.message}") from exc
        frows = (
            await conn.execute(
                text(
                    "SELECT position, composition_id, occurrence_id, "
                    "feature_id, feature_key, feature_kind, value_type, "
                    "unit, value_json, value_hash, source_anchor_type, "
                    "source_anchor_id, source_boundary FROM "
                    "shot_revision_production_instance_feature_states "
                    "WHERE shot_revision_id = :r ORDER BY position"),
                {"r": revision_id},
            )
        ).mappings().all()
        srows = (
            await conn.execute(
                text(
                    "SELECT position, composition_id, occurrence_id, "
                    "production_instance_track_id, requirement, x_mm, "
                    "y_mm, z_mm, yaw_udeg, pitch_udeg, roll_udeg, "
                    "source_transition_id, source_anchor_type, "
                    "source_anchor_id, source_boundary FROM "
                    "shot_revision_production_instance_spatial_states "
                    "WHERE shot_revision_id = :r ORDER BY position"),
                {"r": revision_id},
            )
        ).mappings().all()
        return {
            "revision_id": revision_id,
            "schema_version": snapshot.get("schema_version"),
            "captured": True,
            "captured_as_history": True,
            "production_world_hash": parent["production_world_hash"],
            "binding": {
                "binding_id": stored_binding["binding_id"],
                "binding_hash": stored_binding["binding_hash"],
                "composition_revision_id":
                    stored_binding["composition_revision_id"],
                "composition_revision_hash":
                    stored_binding["composition_revision_hash"],
                "spatial_world_revision_id":
                    stored_binding["spatial_world_revision_id"],
                "spatial_world_revision_hash":
                    stored_binding["spatial_world_revision_hash"],
                "subjects": stored_binding["subjects"],
                "entries": stored_binding["entries"],
            },
            "captured_feature_states": [dict(r) for r in frows],
            "captured_spatial_states": [dict(r) for r in srows],
        }
