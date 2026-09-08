"""Production Revision spatial-interpretation service (frozen R3 §4.4/§24.1).

Create-only, immutable, content-verified. One canonical value object
produces the stored JSON, hash, and every scalar projection column.
An identical create converges on the existing row after full stored
validation; a different second meaning is rejected as conflict.
"""

from __future__ import annotations

import json as _json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.db.timeutil import DB_NOW_SQL
from soloring.errors import (
    ErrorCode,
    SoloRingError,
    not_found,
    validation_error,
)
from soloring.production_world.canonical import (
    interpretation_hash,
    interpretation_json,
    interpretation_value,
    parse_interpretation,
    verify_stored_interpretation,
)
from soloring.composition.service import _norm_transform


async def _load_closed_revision(conn, revision_id: str) -> dict:
    row = (
        await conn.execute(
            text(
                "SELECT pr.id, pr.snapshot_hash, po.project_id, "
                "(SELECT c.blob_hash FROM production_revision_closures c "
                " WHERE c.production_revision_id = pr.id "
                " AND c.contract_key = 'retained_blob' "
                " AND c.contract_version = 1) AS blob_hash "
                "FROM production_revisions pr "
                "JOIN production_objects po ON po.id = pr.production_object_id "
                "WHERE pr.id = :rid"
            ),
            {"rid": revision_id},
        )
    ).first()
    if row is None:
        raise not_found(
            ErrorCode.PRODUCTION_REVISION_NOT_FOUND,
            f"production revision {revision_id!r} not found",
        )
    if row.blob_hash is None:
        raise validation_error(
            "production revision has no retained_blob/v1 closure; an M13 "
            "spatial interpretation requires a closed Production Revision")
    return {"id": row.id, "snapshot_hash": row.snapshot_hash,
            "project_id": row.project_id, "blob_hash": row.blob_hash}


async def create_interpretation(
    session: AsyncSession, revision_id: str, *, transform: object,
) -> tuple[dict, bool]:
    """Create (or idempotently converge on) the schema-1 interpretation.

    Returns (read projection, created_flag).
    """
    tr = _norm_transform(transform)
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        parent = await _load_closed_revision(conn, revision_id)
        value = interpretation_value(
            production_revision_id=parent["id"],
            production_revision_hash=parent["snapshot_hash"],
            retained_blob_hash=parent["blob_hash"],
            transform=tr,
        )
        ihash = interpretation_hash(value)
        ijson = interpretation_json(value)

        existing = (
            await conn.execute(
                text(
                    "SELECT production_revision_id, schema_version, x_mm, "
                    "y_mm, z_mm, yaw_udeg, pitch_udeg, roll_udeg, "
                    "interpretation_json, interpretation_hash, created_at "
                    "FROM production_revision_spatial_interpretations "
                    "WHERE production_revision_id = :rid"
                ),
                {"rid": revision_id},
            )
        ).first()
        if existing is not None:
            # Frozen §4.4: identical request returns the existing exact
            # interpretation only after full stored-byte/hash/projection
            # validation; a different second meaning is a conflict.
            verify_stored_interpretation(
                interpretation_json=existing.interpretation_json,
                interpretation_hash=existing.interpretation_hash,
                x_mm=existing.x_mm, y_mm=existing.y_mm, z_mm=existing.z_mm,
                yaw_udeg=existing.yaw_udeg, pitch_udeg=existing.pitch_udeg,
                roll_udeg=existing.roll_udeg,
                row_production_revision_id=existing.production_revision_id,
                parent_snapshot_hash=parent["snapshot_hash"],
                parent_blob_hash=parent["blob_hash"],
            )
            if existing.interpretation_hash != ihash:
                raise SoloRingError(
                    ErrorCode.VALIDATION_ERROR,
                    "a different spatial interpretation already exists for "
                    "this Production Revision; schema-1 interpretation is "
                    "immutable and correction requires a new Production "
                    "Revision or a future versioned contract",
                    status_code=409,
                )
            await conn.exec_driver_sql("COMMIT")
            return _read_row(existing, parent), False

        await conn.execute(
            text(
                "INSERT INTO production_revision_spatial_interpretations "
                "(production_revision_id, schema_version, x_mm, y_mm, z_mm, "
                "yaw_udeg, pitch_udeg, roll_udeg, interpretation_json, "
                f"interpretation_hash, created_at) VALUES "
                "(:rid, 1, :x, :y, :z, :yaw, :pitch, :roll, :ijs, :ih, "
                f"{DB_NOW_SQL})"
            ),
            {"rid": revision_id,
             "x": tr.translation_mm[0], "y": tr.translation_mm[1],
             "z": tr.translation_mm[2],
             "yaw": tr.rotation_udeg[0], "pitch": tr.rotation_udeg[1],
             "roll": tr.rotation_udeg[2],
             "ijs": ijson, "ih": ihash},
        )
        await conn.exec_driver_sql("COMMIT")
    return await get_interpretation(session, revision_id), True


async def get_interpretation(
    session: AsyncSession, revision_id: str,
) -> dict:
    """Verified read of the exact interpretation (frozen §4.4)."""
    async with session.bind.connect() as conn:
        parent = await _load_closed_revision(conn, revision_id)
        row = (
            await conn.execute(
                text(
                    "SELECT production_revision_id, schema_version, x_mm, "
                    "y_mm, z_mm, yaw_udeg, pitch_udeg, roll_udeg, "
                    "interpretation_json, interpretation_hash, created_at "
                    "FROM production_revision_spatial_interpretations "
                    "WHERE production_revision_id = :rid"
                ),
                {"rid": revision_id},
            )
        ).first()
        if row is None:
            raise not_found(
                ErrorCode.PRODUCTION_SPATIAL_INTERPRETATION_NOT_FOUND,
                f"no M13 schema-1 spatial interpretation exists for "
                f"production revision {revision_id!r}",
            )
        return _read_row(row, parent)


def _read_row(row, parent: dict) -> dict:
    canonical = verify_stored_interpretation(
        interpretation_json=row.interpretation_json,
        interpretation_hash=row.interpretation_hash,
        x_mm=row.x_mm, y_mm=row.y_mm, z_mm=row.z_mm,
        yaw_udeg=row.yaw_udeg, pitch_udeg=row.pitch_udeg,
        roll_udeg=row.roll_udeg,
        row_production_revision_id=row.production_revision_id,
        parent_snapshot_hash=parent["snapshot_hash"],
        parent_blob_hash=parent["blob_hash"],
    )
    return {
        "production_revision_id": row.production_revision_id,
        "production_revision_hash": canonical["production_revision_hash"],
        "retained_blob_hash": canonical["retained_blob_hash"],
        "schema_version": row.schema_version,
        "interpretation_hash": row.interpretation_hash,
        "coordinate_system": canonical["coordinate_system"],
        "origin_semantics": canonical["origin_semantics"],
        "realization_local_to_subject_local":
            canonical["realization_local_to_subject_local"],
        "created_at": row.created_at,
    }


def parse_public_interpretation_json(raw: str) -> dict:
    """Parse a stored interpretation JSON for external projection."""
    return _json.loads(raw)
