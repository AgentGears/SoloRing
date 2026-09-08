"""Subject-adoption service (frozen R3 §7).

Adoption is explicit, append-only, one-way, and bound to the stable M12
occurrence identity. The whole precondition set runs under one
BEGIN IMMEDIATE fence; concurrent same-CreativeEntity adoption attempts
cannot both commit. No PATCH/DELETE/rebind exists.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.db.timeutil import DB_NOW_SQL
from soloring.errors import ErrorCode, not_found, validation_error
from soloring.composition.service import (
    EditConflict,
    _require_composition,
    _terminated_ids,
)

_SUBJECT_KINDS = ("creative_entity", "production_instance")

# One active occurrence per (composition lineage, CreativeEntity): rows
# attached to terminated occurrences are historical provenance and do not
# occupy the active-claim slot (frozen §2.2/§7.1).
_ACTIVE_CE_CLAIM_SQL = (
    "SELECT a.occurrence_id "
    "FROM composition_occurrence_authority_subjects a "
    "WHERE a.composition_id = :cid AND a.creative_entity_id = :eid "
    "AND a.occurrence_id <> :oid "
    "AND NOT EXISTS ("
    "  SELECT 1 FROM composition_identity_operation_sources s "
    "  JOIN composition_identity_operations op ON op.id = s.operation_id "
    "  WHERE op.composition_id = a.composition_id "
    "  AND s.occurrence_id = a.occurrence_id "
    "  AND s.terminates_identity = 1) "
    "LIMIT 1"
)


async def adopt_subject(
    session: AsyncSession, composition_id: str, occurrence_id: str, *,
    kind: object, creative_entity_id: object = None,
) -> tuple[dict, bool]:
    """Adopt one durable authority subject. Returns (read, created_flag)."""
    if kind not in _SUBJECT_KINDS:
        raise validation_error(
            "kind must be 'creative_entity' or 'production_instance'")
    if kind == "production_instance":
        if creative_entity_id is not None:
            raise validation_error(
                "production_instance adoption takes no creative_entity_id; "
                "the subject id is exactly the occurrence UUID")
    else:
        if not isinstance(creative_entity_id, str) or not creative_entity_id:
            raise validation_error(
                "creative_entity adoption requires an exact "
                "creative_entity_id")

    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        # (1) Composition exists and Project is active.
        comp = await _require_composition(conn, composition_id)

        # (2) occurrence belongs to that Composition lineage.
        occ = (
            await conn.execute(
                text("SELECT id FROM composition_occurrences "
                     "WHERE id = :oid AND composition_id = :cid"),
                {"oid": occurrence_id, "cid": composition_id},
            )
        ).first()
        if occ is None:
            raise not_found(
                ErrorCode.COMPOSITION_OCCURRENCE_NOT_FOUND,
                f"occurrence {occurrence_id!r} not found in composition "
                f"{composition_id!r}",
            )

        # (3) active and currently in working membership.
        working = (
            await conn.execute(
                text("SELECT source_kind, production_revision_id "
                     "FROM composition_working_occurrences "
                     "WHERE composition_id = :cid AND occurrence_id = :oid"),
                {"cid": composition_id, "oid": occurrence_id},
            )
        ).first()
        terminated = await _terminated_ids(
            conn, composition_id, [occurrence_id])
        if occurrence_id in terminated or working is None:
            raise validation_error(
                "subject adoption requires an active occurrence currently "
                "in working membership")
        # (4) current working source is exactly production_revision.
        if (working.source_kind != "production_revision"
                or working.production_revision_id is None):
            raise validation_error(
                "subject adoption requires the current working source to be "
                "exactly 'production_revision'")

        # (5) the selected Production Revision belongs to the same Project.
        prow = (
            await conn.execute(
                text(
                    "SELECT po.project_id FROM production_revisions pr "
                    "JOIN production_objects po "
                    "ON po.id = pr.production_object_id "
                    "WHERE pr.id = :rid"
                ),
                {"rid": working.production_revision_id},
            )
        ).first()
        if prow is None or prow.project_id != comp["project_id"]:
            raise validation_error(
                "the occurrence's Production Revision does not belong to "
                "the Composition's Project")

        # (6) no adoption row already exists (identical retry converges).
        existing = (
            await conn.execute(
                text(
                    "SELECT subject_kind, creative_entity_id, created_at "
                    "FROM composition_occurrence_authority_subjects "
                    "WHERE composition_id = :cid AND occurrence_id = :oid"
                ),
                {"cid": composition_id, "oid": occurrence_id},
            )
        ).first()
        if existing is not None:
            if (existing.subject_kind == kind
                    and existing.creative_entity_id == creative_entity_id):
                await conn.exec_driver_sql("COMMIT")
                return _read(composition_id, occurrence_id, existing), False
            raise EditConflict(
                "subject_adoption_conflict",
                "an immutable subject adoption already exists for this "
                "occurrence; schema-1 adoption is never rebound in place "
                "(correction requires identity evolution)",
            )

        # (7) CreativeEntity existence / same Project / active-claim slot.
        if kind == "creative_entity":
            ent = (
                await conn.execute(
                    text(
                        "SELECT id, project_id, deleted_at "
                        "FROM creative_entities WHERE id = :eid"
                    ),
                    {"eid": creative_entity_id},
                )
            ).first()
            if ent is None or ent.deleted_at is not None:
                raise validation_error(
                    "creative entity not found or deleted")
            if ent.project_id != comp["project_id"]:
                raise validation_error(
                    "creative entity belongs to another Project")
            clash = (
                await conn.execute(
                    text(_ACTIVE_CE_CLAIM_SQL),
                    {"cid": composition_id, "eid": creative_entity_id,
                     "oid": occurrence_id},
                )
            ).first()
            if clash is not None:
                raise EditConflict(
                    "creative_entity_claim_conflict",
                    "another active occurrence in this Composition already "
                    "claims that CreativeEntity; terminated historical "
                    "claims do not block",
                    details={"active_claim_occurrence_id": clash.occurrence_id},
                )

        # (8) production_instance subject id is exactly the occurrence UUID.
        await conn.execute(
            text(
                "INSERT INTO composition_occurrence_authority_subjects "
                "(composition_id, occurrence_id, subject_kind, "
                "creative_entity_id, created_at) VALUES "
                f"(:cid, :oid, :kind, :eid, {DB_NOW_SQL})"
            ),
            {"cid": composition_id, "oid": occurrence_id, "kind": kind,
             "eid": creative_entity_id if kind == "creative_entity" else None},
        )
        await conn.exec_driver_sql("COMMIT")
    row = (
        await _get_row(session, composition_id, occurrence_id)
    )
    return row, True


async def _get_row(session: AsyncSession, composition_id: str,
                   occurrence_id: str) -> dict | None:
    async with session.bind.connect() as conn:
        occ = (
            await conn.execute(
                text("SELECT id FROM composition_occurrences "
                     "WHERE id = :oid AND composition_id = :cid"),
                {"oid": occurrence_id, "cid": composition_id},
            )
        ).first()
        if occ is None:
            raise not_found(
                ErrorCode.COMPOSITION_OCCURRENCE_NOT_FOUND,
                f"occurrence {occurrence_id!r} not found in composition "
                f"{composition_id!r}",
            )
        row = (
            await conn.execute(
                text(
                    "SELECT subject_kind, creative_entity_id, created_at "
                    "FROM composition_occurrence_authority_subjects "
                    "WHERE composition_id = :cid AND occurrence_id = :oid"
                ),
                {"cid": composition_id, "oid": occurrence_id},
            )
        ).first()
        if row is None:
            return None
        return _read(composition_id, occurrence_id, row)


async def get_subject(
    session: AsyncSession, composition_id: str, occurrence_id: str,
) -> dict:
    """Effective subject state; no row means COMPOSITION-LOCAL (§2.2)."""
    row = await _get_row(session, composition_id, occurrence_id)
    if row is None:
        return {
            "composition_id": composition_id,
            "occurrence_id": occurrence_id,
            "subject_kind": "composition_local",
            "subject_id": None,
            "creative_entity_id": None,
            "created_at": None,
        }
    return row


def _read(composition_id: str, occurrence_id: str, row) -> dict:
    subject_id = (row.creative_entity_id
                  if row.subject_kind == "creative_entity" else occurrence_id)
    return {
        "composition_id": composition_id,
        "occurrence_id": occurrence_id,
        "subject_kind": row.subject_kind,
        "subject_id": subject_id,
        "creative_entity_id": row.creative_entity_id,
        "created_at": row.created_at,
    }
