"""FeatureTransition service (M7B plan §2–§4, §11–§12).

Working Feature state as transitions on narrative boundaries. Every
mutation is ONE fenced BEGIN IMMEDIATE unit on one checked-out
connection: load active Feature → derive prospective row → validate typed
value (M7A canonicalizer, unchanged) → validate anchor (existence, active,
same Project, complete topology, present in the CANONICAL ORDERING via
``narrative.order.load_narrative_ordering`` — never re-implemented here) →
enforce the active semantic coordinate → write.

Clients submit ``value``; ``value_json``/``value_hash`` are never accepted.
Omitted ≠ null throughout (PATCH prospective-row matrix, plan §2).
"""

from __future__ import annotations

import contextlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from soloring.continuity.entities import _translate_op_error
from soloring.continuity.values import canonicalize_value
from soloring.domain.ids import is_uuid, new_uuid
from soloring.errors import ErrorCode, SoloRingError
from soloring.narrative.order import (
    ANCHOR_SCENE,
    ANCHOR_SEQUENCE,
    ANCHOR_SHOT,
    BOUNDARY_END,
    BOUNDARY_START,
    load_narrative_ordering,
)

ANCHOR_TYPES = (ANCHOR_SEQUENCE, ANCHOR_SCENE, ANCHOR_SHOT)
BOUNDARIES = (BOUNDARY_START, BOUNDARY_END)

_COLUMNS = (
    "id, feature_id, anchor_type, anchor_id, boundary, operation, "
    "value_json, value_hash, created_at, updated_at, deleted_at"
)


def _invalid_anchor(message: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.INVALID_CONTINUITY_ANCHOR, message, status_code=422
    )


def _conflict(message: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.CONTINUITY_TRANSITION_CONFLICT, message, status_code=409
    )


async def _load_active_feature(conn: AsyncConnection, feature_id: str) -> dict:
    """Active Feature + its Entity's authoritative Project (test seam)."""
    row = (
        await conn.execute(
            text(
                "SELECT f.id, f.entity_id, f.value_type, f.enum_values_json, "
                "ce.project_id AS project_id "
                "FROM continuity_features f "
                "JOIN creative_entities ce ON ce.id = f.entity_id "
                "WHERE f.id = :fid AND f.deleted_at IS NULL "
                "AND ce.deleted_at IS NULL"
            ),
            {"fid": feature_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise SoloRingError(
            ErrorCode.CONTINUITY_FEATURE_NOT_FOUND,
            f"ContinuityFeature {feature_id} not found (or its Entity is "
            "not active).",
            status_code=404,
        )
    return dict(row)


async def _validate_anchor_in_ordering(
    conn: AsyncConnection, project_id: str, anchor_type: str, anchor_id: str
) -> None:
    """Anchor must be active, same-Project, and PRESENT IN THE CANONICAL
    Project-local boundary stream — the only ordering authority."""
    import json as _json

    if anchor_type not in ANCHOR_TYPES:
        raise _invalid_anchor(
            f"anchor_type must be one of {ANCHOR_TYPES}."
        )
    if not is_uuid(anchor_id):
        raise _invalid_anchor(f"Invalid anchor_id {anchor_id!r}.")

    table = {"sequence": "sequences", "scene": "scenes", "shot": "shots"}[
        anchor_type
    ]
    owner_col = {"sequence": "project_id", "scene": None, "shot": "project_id"}[
        anchor_type
    ]

    if anchor_type == ANCHOR_SEQUENCE:
        row = (
            await conn.execute(
                text(
                    "SELECT project_id, deleted_at FROM sequences "
                    "WHERE id = :aid"
                ),
                {"aid": anchor_id},
            )
        ).first()
        if row is None or row.deleted_at is not None:
            raise _invalid_anchor(f"Sequence anchor {anchor_id} is missing or tombstoned.")
        if row.project_id != project_id:
            raise SoloRingError(
                ErrorCode.CONTINUITY_ANCHOR_PROJECT_MISMATCH,
                f"Sequence anchor {anchor_id} belongs to another Project.",
                status_code=409,
            )
    elif anchor_type == ANCHOR_SHOT:
        row = (
            await conn.execute(
                text(
                    "SELECT project_id, deleted_at, scene_id FROM shots "
                    "WHERE id = :aid"
                ),
                {"aid": anchor_id},
            )
        ).first()
        if row is None or row.deleted_at is not None:
            raise _invalid_anchor(f"Shot anchor {anchor_id} is missing or tombstoned.")
        if row.project_id != project_id:
            raise SoloRingError(
                ErrorCode.CONTINUITY_ANCHOR_PROJECT_MISMATCH,
                f"Shot anchor {anchor_id} belongs to another Project.",
                status_code=409,
            )
        if row.scene_id is None:
            raise _invalid_anchor(
                f"Shot anchor {anchor_id} is unassigned — it has no "
                "narrative boundary."
            )
    elif anchor_type == ANCHOR_SCENE:
        row = (
            await conn.execute(
                text(
                    "SELECT sc.deleted_at AS scene_deleted, "
                    "sq.project_id AS seq_project, "
                    "sq.deleted_at AS seq_deleted "
                    "FROM scenes sc "
                    "LEFT JOIN sequences sq ON sq.id = sc.sequence_id "
                    "WHERE sc.id = :aid"
                ),
                {"aid": anchor_id},
            )
        ).first()
        if row is None or row.scene_deleted is not None:
            raise _invalid_anchor(
                f"Scene anchor {anchor_id} is missing or tombstoned."
            )
        if row.seq_project is None or row.seq_deleted is not None:
            raise _invalid_anchor(
                f"Scene anchor {anchor_id} has no active parent Sequence."
            )
        if row.seq_project != project_id:
            raise SoloRingError(
                ErrorCode.CONTINUITY_ANCHOR_PROJECT_MISMATCH,
                f"Scene anchor {anchor_id} belongs to another Project.",
                status_code=409,
            )

    ordering = await load_narrative_ordering(conn, project_id)
    # Both boundaries of a present anchor exist by construction; checking
    # one is sufficient for presence.
    try:
        ordering.rank_of(anchor_type, anchor_id, BOUNDARY_START)
    except SoloRingError:
        raise _invalid_anchor(
            f"{anchor_type} anchor {anchor_id} is not present in the "
            "canonical narrative ordering of the Feature's Project."
        )


async def _canonicalize(
    feature: dict, operation: str, value: object
) -> tuple[str | None, str | None]:
    """Validate + canonicalize the value for a `set` operation.

    `clear` callers pass operation only; value must be omitted there."""
    if operation == "clear":
        return None, None
    if operation != "set":  # pragma: no cover - request schema guards
        raise _invalid_anchor(f"Unknown operation {operation!r}.")
    enum_values = None
    if feature["value_type"] == "enum":
        import json as _json

        enum_values = _json.loads(feature["enum_values_json"])
    return canonicalize_value(
        feature["value_type"], value, enum_values=enum_values
    )


async def _coordinate_taken(
    conn: AsyncConnection,
    feature_id: str,
    anchor_type: str,
    anchor_id: str,
    boundary: str,
    exclude_transition_id: str | None = None,
) -> bool:
    sql = (
        "SELECT 1 FROM continuity_feature_transitions "
        "WHERE feature_id = :fid AND anchor_type = :at AND anchor_id = :aid "
        "AND boundary = :b AND deleted_at IS NULL"
    )
    params = {
        "fid": feature_id, "at": anchor_type, "aid": anchor_id, "b": boundary,
    }
    if exclude_transition_id is not None:
        sql += " AND id <> :ex"
        params["ex"] = exclude_transition_id
    return (
        await conn.execute(text(sql), params)
    ).first() is not None


async def create_transition(
    session: AsyncSession, feature_id: str, payload
) -> str:
    """POST /continuity-features/{id}/transitions (plan §2 create)."""
    if not is_uuid(feature_id):
        raise SoloRingError(
            ErrorCode.CONTINUITY_FEATURE_NOT_FOUND,
            f"ContinuityFeature {feature_id} not found.",
            status_code=404,
        )
    anchor_type = payload.anchor_type
    anchor_id = payload.anchor_id
    boundary = payload.boundary
    operation = payload.operation

    if boundary not in BOUNDARIES:
        raise _invalid_anchor(f"boundary must be one of {BOUNDARIES}.")
    if "value" in payload.model_fields_set and payload.value is None:
        raise SoloRingError(
            ErrorCode.INVALID_CONTINUITY_VALUE,
            "value:null is never accepted; omit value entirely.",
            status_code=422,
        )
    if operation == "clear" and "value" in payload.model_fields_set:
        raise SoloRingError(
            ErrorCode.INVALID_CONTINUITY_VALUE,
            "clear requires value to be omitted.",
            status_code=422,
        )
    if operation == "set" and (
        "value" not in payload.model_fields_set
    ):
        raise SoloRingError(
            ErrorCode.INVALID_CONTINUITY_VALUE,
            "set requires a value.",
            status_code=422,
        )

    transition_id = new_uuid()
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            feature = await _load_active_feature(conn, feature_id)
            await _validate_anchor_in_ordering(
                conn, feature["project_id"], anchor_type, anchor_id
            )
            if await _coordinate_taken(
                conn, feature_id, anchor_type, anchor_id, boundary
            ):
                raise _conflict(
                    f"An active transition already occupies "
                    f"({anchor_type}, {anchor_id}, {boundary}) for this "
                    "Feature."
                )
            value_json, value_hash = await _canonicalize(
                feature, operation, payload.value
            )
            await conn.execute(
                text(
                    "INSERT INTO continuity_feature_transitions "
                    "(id, feature_id, anchor_type, anchor_id, boundary, "
                    " operation, value_json, value_hash, created_at, "
                    " updated_at) VALUES (:id, :fid, :at, :aid, :b, :op, "
                    ":vj, :vh, strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
                ),
                {
                    "id": transition_id, "fid": feature_id, "at": anchor_type,
                    "aid": anchor_id, "b": boundary, "op": operation,
                    "vj": value_json, "vh": value_hash,
                },
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(
                exc, "feature transition creation"
            ) from exc
    return transition_id


async def patch_transition(
    session: AsyncSession, transition_id: str, patch
) -> None:
    """PATCH with prospective-row semantics (plan §2 matrix)."""
    if not is_uuid(transition_id):
        raise _conflict(f"Transition {transition_id} not found.")
    provided = patch.model_fields_set

    if "value" in provided and patch.value is None:
        raise SoloRingError(
            ErrorCode.INVALID_CONTINUITY_VALUE,
            "value:null is never accepted.",
            status_code=422,
        )

    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            current = (
                await conn.execute(
                    text(
                        f"SELECT {_COLUMNS} FROM "
                        "continuity_feature_transitions "
                        "WHERE id = :tid AND deleted_at IS NULL"
                    ),
                    {"tid": transition_id},
                )
            ).mappings().one_or_none()
            if current is None:
                raise _conflict(
                    f"Transition {transition_id} does not exist or is not "
                    "active."
                )
            current = dict(current)
            feature = await _load_active_feature(conn, current["feature_id"])

            # Prospective row: current + explicitly supplied fields.
            p_anchor_type = (
                patch.anchor_type
                if "anchor_type" in provided else current["anchor_type"]
            )
            p_anchor_id = (
                patch.anchor_id
                if "anchor_id" in provided else current["anchor_id"]
            )
            p_boundary = (
                patch.boundary if "boundary" in provided else current["boundary"]
            )
            p_operation = (
                patch.operation
                if "operation" in provided else current["operation"]
            )

            if p_boundary not in BOUNDARIES:
                raise _invalid_anchor(
                    f"boundary must be one of {BOUNDARIES}."
                )

            # The binding value matrix (omitted ≠ null).
            current_op = current["operation"]
            if p_operation == "set":
                if "value" in provided:
                    p_value_json, p_value_hash = await _canonicalize(
                        feature, "set", patch.value
                    )
                else:
                    if current_op == "clear":
                        raise SoloRingError(
                            ErrorCode.INVALID_CONTINUITY_VALUE,
                            "clear → set requires a value (a clear row has "
                            "no value to inherit).",
                            status_code=422,
                        )
                    p_value_json = current["value_json"]
                    p_value_hash = current["value_hash"]
            else:  # prospective clear
                if "value" in provided:
                    raise SoloRingError(
                        ErrorCode.INVALID_CONTINUITY_VALUE,
                        "set → clear requires value to be omitted.",
                        status_code=422,
                    )
                p_value_json, p_value_hash = None, None

            anchor_moved = (
                p_anchor_type != current["anchor_type"]
                or p_anchor_id != current["anchor_id"]
                or p_boundary != current["boundary"]
            )
            if anchor_moved or p_operation != current_op:
                await _validate_anchor_in_ordering(
                    conn, feature["project_id"], p_anchor_type, p_anchor_id
                )
                if await _coordinate_taken(
                    conn, current["feature_id"], p_anchor_type, p_anchor_id,
                    p_boundary, exclude_transition_id=transition_id,
                ):
                    raise _conflict(
                        "Another active transition occupies the target "
                        "coordinate."
                    )

            await conn.execute(
                text(
                    "UPDATE continuity_feature_transitions SET "
                    "anchor_type = :at, anchor_id = :aid, boundary = :b, "
                    "operation = :op, value_json = :vj, value_hash = :vh, "
                    "updated_at = strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                    "WHERE id = :tid AND deleted_at IS NULL"
                ),
                {
                    "at": p_anchor_type, "aid": p_anchor_id, "b": p_boundary,
                    "op": p_operation, "vj": p_value_json,
                    "vh": p_value_hash, "tid": transition_id,
                },
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(
                exc, "feature transition patch"
            ) from exc


async def delete_transition(session: AsyncSession, transition_id: str) -> None:
    """Soft-delete; idempotent for already-tombstoned, conflict for
    never-existed (frozen vocabulary has no NOT_FOUND code)."""
    if not is_uuid(transition_id):
        raise _conflict(f"Transition {transition_id} not found.")
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            row = (
                await conn.execute(
                    text(
                        "SELECT deleted_at FROM "
                        "continuity_feature_transitions WHERE id = :tid"
                    ),
                    {"tid": transition_id},
                )
            ).first()
            if row is None:
                raise _conflict(
                    f"Transition {transition_id} does not exist."
                )
            if row.deleted_at is not None:
                await conn.exec_driver_sql("COMMIT")  # idempotent 204
                return
            await conn.execute(
                text(
                    "UPDATE continuity_feature_transitions SET deleted_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'), updated_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :tid"
                ),
                {"tid": transition_id},
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(
                exc, "feature transition deletion"
            ) from exc


async def list_transitions(
    session: AsyncSession, feature_id: str
) -> list[dict]:
    if not is_uuid(feature_id):
        raise SoloRingError(
            ErrorCode.CONTINUITY_FEATURE_NOT_FOUND,
            f"ContinuityFeature {feature_id} not found.",
            status_code=404,
        )
    async with session.bind.connect() as conn:
        await _load_active_feature(conn, feature_id)
        rows = (
            await conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM "
                    "continuity_feature_transitions "
                    "WHERE feature_id = :fid AND deleted_at IS NULL "
                    "ORDER BY created_at, id"
                ),
                {"fid": feature_id},
            )
        ).mappings().all()
        return [dict(r) for r in rows]
