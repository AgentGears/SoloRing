"""RelationTransition service (M7D plan §6).

Working relation state as transitions on narrative boundaries — the M7B
FeatureTransition matrix with ``state ∈ {active, inactive}`` replacing
operation+value (there ARE no value columns; `active` is presence,
`inactive` is canonical absence). Anchor validation is THE existing M7B
authority (``transitions._validate_anchor_in_ordering``), imported — never
re-implemented (APR-012). Every mutation is ONE fenced BEGIN IMMEDIATE
unit on one checked-out connection through monkeypatchable seams.
"""

from __future__ import annotations

import contextlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from soloring.continuity.entities import _translate_op_error
from soloring.continuity.transitions import (
    ANCHOR_TYPES,
    BOUNDARIES,
    _validate_anchor_in_ordering,
)
from soloring.domain.ids import is_uuid, new_uuid
from soloring.errors import ErrorCode, SoloRingError, validation_error

RELATION_STATES = ("active", "inactive")

_COLUMNS = (
    "id, relation_id, anchor_type, anchor_id, boundary, state, "
    "created_at, updated_at"
)


def _invalid_anchor(message: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.INVALID_CONTINUITY_ANCHOR, message, status_code=422
    )


def _conflict(message: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.CONTINUITY_TRANSITION_CONFLICT, message, status_code=409
    )


async def _load_active_relation(conn: AsyncConnection, relation_id: str) -> dict:
    """Active Relation + its Project (test seam; mirrors the M7B
    `_load_active_feature` seam)."""
    row = (
        await conn.execute(
            text(
                "SELECT r.id, r.project_id FROM continuity_relations r "
                "WHERE r.id = :rid AND r.deleted_at IS NULL "
                "AND EXISTS (SELECT 1 FROM projects p "
                "WHERE p.id = r.project_id AND p.deleted_at IS NULL)"
            ),
            {"rid": relation_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise SoloRingError(
            ErrorCode.CONTINUITY_RELATION_CONFLICT,
            f"ContinuityRelation {relation_id} not found (or not active).",
            status_code=409,
        )
    return dict(row)


async def _coordinate_taken(
    conn: AsyncConnection,
    relation_id: str,
    anchor_type: str,
    anchor_id: str,
    boundary: str,
    exclude_transition_id: str | None = None,
) -> bool:
    sql = (
        "SELECT 1 FROM continuity_relation_transitions "
        "WHERE relation_id = :rid AND anchor_type = :at AND anchor_id = :aid "
        "AND boundary = :b AND deleted_at IS NULL"
    )
    params = {
        "rid": relation_id, "at": anchor_type, "aid": anchor_id, "b": boundary,
    }
    if exclude_transition_id is not None:
        sql += " AND id <> :ex"
        params["ex"] = exclude_transition_id
    return (
        await conn.execute(text(sql), params)
    ).first() is not None


async def create_transition(
    session: AsyncSession, relation_id: str, payload
) -> str:
    """POST /continuity-relations/{id}/transitions (§6.2 create)."""
    if not is_uuid(relation_id):
        raise _conflict(f"ContinuityRelation {relation_id} not found.")
    anchor_type = payload.anchor_type
    anchor_id = payload.anchor_id
    boundary = payload.boundary
    state = payload.state

    if boundary not in BOUNDARIES:
        raise _invalid_anchor(f"boundary must be one of {BOUNDARIES}.")
    if state not in RELATION_STATES:
        raise validation_error(
            f"state must be one of {RELATION_STATES}."
        )

    transition_id = new_uuid()
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            relation = await _load_active_relation(conn, relation_id)
            await _validate_anchor_in_ordering(
                conn, relation["project_id"], anchor_type, anchor_id
            )
            if await _coordinate_taken(
                conn, relation_id, anchor_type, anchor_id, boundary
            ):
                raise _conflict(
                    f"An active transition already occupies "
                    f"({anchor_type}, {anchor_id}, {boundary}) for this "
                    "Relation."
                )
            await conn.execute(
                text(
                    "INSERT INTO continuity_relation_transitions "
                    "(id, relation_id, anchor_type, anchor_id, boundary, "
                    " state, created_at, updated_at) "
                    "VALUES (:id, :rid, :at, :aid, :b, :st, "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
                ),
                {
                    "id": transition_id, "rid": relation_id,
                    "at": anchor_type, "aid": anchor_id, "b": boundary,
                    "st": state,
                },
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(
                exc, "relation transition creation"
            ) from exc
    return transition_id


async def patch_transition(
    session: AsyncSession, transition_id: str, patch
) -> None:
    """PATCH with prospective-row semantics (§6.2). No value matrix:
    fields are anchor coordinates and state, omitted → preserve."""
    if not is_uuid(transition_id):
        raise _conflict(f"Relation transition {transition_id} not found.")
    provided = patch.model_fields_set

    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            current = (
                await conn.execute(
                    text(
                        f"SELECT {_COLUMNS} FROM "
                        "continuity_relation_transitions "
                        "WHERE id = :tid AND deleted_at IS NULL"
                    ),
                    {"tid": transition_id},
                )
            ).mappings().one_or_none()
            if current is None:
                raise _conflict(
                    f"Relation transition {transition_id} does not exist "
                    "or is not active."
                )
            current = dict(current)
            relation = await _load_active_relation(
                conn, current["relation_id"]
            )

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
            p_state = (
                patch.state if "state" in provided else current["state"]
            )

            if p_boundary not in BOUNDARIES:
                raise _invalid_anchor(
                    f"boundary must be one of {BOUNDARIES}."
                )
            if p_state not in RELATION_STATES:
                raise validation_error(
                    f"state must be one of {RELATION_STATES}."
                )

            anchor_moved = (
                p_anchor_type != current["anchor_type"]
                or p_anchor_id != current["anchor_id"]
                or p_boundary != current["boundary"]
            )
            if anchor_moved or p_state != current["state"]:
                await _validate_anchor_in_ordering(
                    conn, relation["project_id"], p_anchor_type, p_anchor_id
                )
                if await _coordinate_taken(
                    conn, current["relation_id"], p_anchor_type, p_anchor_id,
                    p_boundary, exclude_transition_id=transition_id,
                ):
                    raise _conflict(
                        "Another active transition occupies the target "
                        "coordinate."
                    )

            await conn.execute(
                text(
                    "UPDATE continuity_relation_transitions SET "
                    "anchor_type = :at, anchor_id = :aid, boundary = :b, "
                    "state = :st, updated_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                    "WHERE id = :tid AND deleted_at IS NULL"
                ),
                {
                    "at": p_anchor_type, "aid": p_anchor_id, "b": p_boundary,
                    "st": p_state, "tid": transition_id,
                },
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(
                exc, "relation transition patch"
            ) from exc


async def delete_transition(session: AsyncSession, transition_id: str) -> None:
    """Soft-delete; idempotent for tombstoned, conflict for never-existed
    (the frozen vocabulary has no transition NOT_FOUND code)."""
    if not is_uuid(transition_id):
        raise _conflict(f"Relation transition {transition_id} not found.")
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            row = (
                await conn.execute(
                    text(
                        "SELECT deleted_at FROM "
                        "continuity_relation_transitions WHERE id = :tid"
                    ),
                    {"tid": transition_id},
                )
            ).first()
            if row is None:
                raise _conflict(
                    f"Relation transition {transition_id} does not exist."
                )
            if row.deleted_at is not None:
                await conn.exec_driver_sql("COMMIT")  # idempotent 204
                return
            await conn.execute(
                text(
                    "UPDATE continuity_relation_transitions SET deleted_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'), updated_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :tid"
                ),
                {"tid": transition_id},
            )
            await conn.exec_driver_sql("COMMIT")
        except SoloRingError:
            raise
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise _translate_op_error(
                exc, "relation transition deletion"
            ) from exc


async def list_transitions(
    session: AsyncSession, relation_id: str
) -> list[dict]:
    if not is_uuid(relation_id):
        raise _conflict(f"ContinuityRelation {relation_id} not found.")
    async with session.bind.connect() as conn:
        await _load_active_relation(conn, relation_id)
        rows = (
            await conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM "
                    "continuity_relation_transitions "
                    "WHERE relation_id = :rid AND deleted_at IS NULL "
                    "ORDER BY created_at, id"
                ),
                {"rid": relation_id},
            )
        ).mappings().all()
        return [dict(r) for r in rows]
