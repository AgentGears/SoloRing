"""Scene service + Shot narrative membership (M6 §33–§34, §39, §41).

Same fencing discipline as sequences/entities: every mutation is ONE
BEGIN IMMEDIATE unit whose active-verification is atomic with the write,
through monkeypatchable seams (``_verify_active_scene``).

Shot membership (§39) is full-set replacement inside one write unit:

    validate proposed complete set (unique ids, active Shots, same Project,
    no Shot silently stolen from another Scene)
    ↓
    members omitted from the set -> scene_id/scene_position = NULL
    ↓
    retained members shift into a temporary intra-scene position range
    ↓
    proposed members assigned scene_position 0..N-1

``shot_number`` is NEVER touched (plan §36); narrative order comes only
from scene_position (never timestamps, plan §37).
"""

from __future__ import annotations

import contextlib

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from soloring.continuity.entities import _translate_op_error
from soloring.domain.ids import is_uuid, new_uuid
from soloring.domain.normalize import normalize_optional_creative
from soloring.errors import ErrorCode, SoloRingError, not_found
from soloring.narrative.ordering import (
    compact_active,
    list_ordered,
    next_position,
    order_invalid,
    reorder_full_set,
)
from soloring.narrative.sequences import sequence_not_found

_COLUMNS = "id, sequence_id, title, description, position, created_at, updated_at"


def scene_not_found(scene_id: str) -> SoloRingError:
    return not_found(
        ErrorCode.SCENE_NOT_FOUND, f"Scene {scene_id} not found."
    )


async def _verify_active_sequence_conn(
    conn: AsyncConnection, sequence_id: str
) -> None:
    row = (
        await conn.execute(
            text(
                "SELECT 1 FROM sequences WHERE id = :sid AND deleted_at IS NULL"
            ),
            {"sid": sequence_id},
        )
    ).first()
    if row is None:
        raise sequence_not_found(sequence_id)


async def _verify_active_scene(conn: AsyncConnection, scene_id: str) -> dict:
    """Active-scene check INSIDE a held BEGIN IMMEDIATE unit (test seam)."""
    row = (
        await conn.execute(
            text(
                "SELECT id, sequence_id, "
                "(SELECT project_id FROM sequences WHERE id = "
                "scenes.sequence_id) AS project_id "
                "FROM scenes WHERE id = :cid AND deleted_at IS NULL"
            ),
            {"cid": scene_id},
        )
    ).mappings().one_or_none()
    if row is None:
        raise scene_not_found(scene_id)
    return dict(row)


async def create_scene(
    session: AsyncSession, sequence_id: str, title: str | None,
    description: str | None,
) -> str:
    if not is_uuid(sequence_id):
        raise sequence_not_found(sequence_id)
    scene_id = new_uuid()
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await _verify_active_sequence_conn(conn, sequence_id)
            position = await next_position(conn, "scenes", "sequence_id", sequence_id)
            await conn.execute(
                text(
                    "INSERT INTO scenes (id, sequence_id, title, description, "
                    "position, created_at, updated_at) "
                    "VALUES (:id, :sid, :title, :desc, :pos, "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
                ),
                {
                    "id": scene_id,
                    "sid": sequence_id,
                    "title": normalize_optional_creative(title),
                    "desc": normalize_optional_creative(description),
                    "pos": position,
                },
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(exc, "scene creation") from exc
    return scene_id


async def list_scenes(session: AsyncSession, sequence_id: str) -> list[dict]:
    if not is_uuid(sequence_id):
        raise sequence_not_found(sequence_id)
    async with session.bind.connect() as conn:
        await _verify_active_sequence_conn(conn, sequence_id)
        return await list_ordered(
            conn, "scenes", "sequence_id", sequence_id, _COLUMNS
        )


async def get_scene(session: AsyncSession, scene_id: str) -> dict:
    if not is_uuid(scene_id):
        raise scene_not_found(scene_id)
    async with session.bind.connect() as conn:
        row = (
            await conn.execute(
                text(
                    f"SELECT {_COLUMNS} FROM scenes "
                    "WHERE id = :cid AND deleted_at IS NULL"
                ),
                {"cid": scene_id},
            )
        ).mappings().one_or_none()
    if row is None:
        raise scene_not_found(scene_id)
    return dict(row)


async def patch_scene(session: AsyncSession, scene_id: str, patch) -> None:
    """Partial PATCH (M6B re-gate): omitted fields are preserved; explicit
    nulls clear nullable values; ``{}`` mutates nothing."""
    if not is_uuid(scene_id):
        raise scene_not_found(scene_id)
    provided = patch.model_fields_set
    if not provided:
        await get_scene(session, scene_id)  # active check only
        return

    updates: dict[str, object] = {}
    if "title" in provided:
        updates["title"] = normalize_optional_creative(patch.title)
    if "description" in provided:
        updates["description"] = normalize_optional_creative(patch.description)
    set_sql = ", ".join(f"{col} = :{col}" for col in updates)
    params = {**updates, "cid": scene_id}
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await _verify_active_scene(conn, scene_id)
            rowcount = (
                await conn.execute(
                    text(
                        "UPDATE scenes SET "
                        f"{set_sql}, updated_at = "
                        "strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                        "WHERE id = :cid AND deleted_at IS NULL"
                    ),
                    params,
                )
            ).rowcount
            if rowcount != 1:
                await conn.exec_driver_sql("ROLLBACK")
                raise scene_not_found(scene_id)
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(exc, "scene patch") from exc


async def delete_scene(session: AsyncSession, scene_id: str) -> None:
    """Soft-delete; SCENE_IN_USE while an ACTIVE Shot is assigned (§41).

    Idempotent for already-deleted Scenes (Project/Shot/Entity policy).
    """
    if not is_uuid(scene_id):
        raise scene_not_found(scene_id)
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            row = (
                await conn.execute(
                    text(
                        "SELECT sequence_id, deleted_at FROM scenes "
                        "WHERE id = :cid"
                    ),
                    {"cid": scene_id},
                )
            ).first()
            if row is None:
                await conn.exec_driver_sql("ROLLBACK")
                raise scene_not_found(scene_id)
            if row.deleted_at is not None:
                await conn.exec_driver_sql("COMMIT")  # idempotent no-op
                return
            in_use = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM shots WHERE scene_id = :cid "
                        "AND deleted_at IS NULL LIMIT 1"
                    ),
                    {"cid": scene_id},
                )
            ).first()
            if in_use is not None:
                await conn.exec_driver_sql("ROLLBACK")
                raise SoloRingError(
                    ErrorCode.SCENE_IN_USE,
                    f"Scene {scene_id} still has assigned active Shots.",
                    status_code=409,
                )
            # M7B §11: scene-anchored active transitions block deletion.
            anchored = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM continuity_feature_transitions "
                        "WHERE anchor_type = 'scene' AND anchor_id = :cid "
                        "AND deleted_at IS NULL LIMIT 1"
                    ),
                    {"cid": scene_id},
                )
            ).first()
            if anchored is not None:
                await conn.exec_driver_sql("ROLLBACK")
                raise SoloRingError(
                    ErrorCode.CONTINUITY_ANCHOR_IN_USE,
                    f"Scene {scene_id} anchors an active Feature transition.",
                    status_code=409,
                )
            # M7D §13.5: the same guard for Relation transitions.
            anchored_relation = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM continuity_relation_transitions "
                        "WHERE anchor_type = 'scene' AND anchor_id = :cid "
                        "AND deleted_at IS NULL LIMIT 1"
                    ),
                    {"cid": scene_id},
                )
            ).first()
            if anchored_relation is not None:
                await conn.exec_driver_sql("ROLLBACK")
                raise SoloRingError(
                    ErrorCode.CONTINUITY_ANCHOR_IN_USE,
                    f"Scene {scene_id} anchors an active Relation "
                    "transition.",
                    status_code=409,
                )
            await conn.execute(
                text(
                    "UPDATE scenes SET deleted_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'), updated_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :cid"
                ),
                {"cid": scene_id},
            )
            # Active siblings compact to 0..N-1; the tombstone keeps its
            # coordinates forever (M6B re-gate).
            await compact_active(conn, "scenes", "sequence_id", row.sequence_id)
            await conn.exec_driver_sql("COMMIT")
        except SoloRingError:
            raise
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise _translate_op_error(exc, "scene deletion") from exc


async def reorder_scenes(
    session: AsyncSession, sequence_id: str, ordered_ids: list[str]
) -> None:
    if not is_uuid(sequence_id):
        raise sequence_not_found(sequence_id)
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            await _verify_active_sequence_conn(conn, sequence_id)
            await reorder_full_set(
                conn, "scenes", "sequence_id", sequence_id, ordered_ids
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(exc, "scene reorder") from exc


async def assign_scene_shots(
    session: AsyncSession, scene_id: str, ordered_shot_ids: list[str]
) -> None:
    """Full-set Shot membership/order replacement (plan §39, M6B-2)."""
    if not is_uuid(scene_id):
        raise scene_not_found(scene_id)
    if len(set(ordered_shot_ids)) != len(ordered_shot_ids):
        raise order_invalid("Duplicate shot ids in membership request.")
    for shot_id in ordered_shot_ids:
        if not is_uuid(shot_id):
            raise order_invalid(f"Invalid shot id {shot_id!r}.")

    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            scene = await _verify_active_scene(conn, scene_id)

            if ordered_shot_ids:
                placeholders = ", ".join(
                    f":s{i}" for i in range(len(ordered_shot_ids))
                )
                params = {
                    f"s{i}": sid for i, sid in enumerate(ordered_shot_ids)
                }
                rows = (
                    await conn.execute(
                        text(
                            f"SELECT id, project_id, scene_id, deleted_at "
                            f"FROM shots WHERE id IN ({placeholders})"
                        ),
                        params,
                    )
                ).mappings().all()
                by_id = {r["id"]: dict(r) for r in rows}
                for shot_id in ordered_shot_ids:
                    shot = by_id.get(shot_id)
                    if shot is None or shot["deleted_at"] is not None:
                        raise order_invalid(
                            f"Shot {shot_id} does not exist or is deleted."
                        )
                    if shot["project_id"] != scene["project_id"]:
                        raise order_invalid(
                            f"Shot {shot_id} belongs to another Project."
                        )
                    if (
                        shot["scene_id"] is not None
                        and shot["scene_id"] != scene_id
                    ):
                        raise order_invalid(
                            f"Shot {shot_id} is assigned to another Scene."
                        )

            # M7B §11: unassigning an active Shot that anchors an active
            # Feature transition is forbidden (reorder is legal — identity
            # survives; unassignment destroys the narrative boundary).
            if ordered_shot_ids:
                removed = (
                    await conn.execute(
                        text(
                            "SELECT sh.id FROM shots sh WHERE sh.scene_id = :cid "
                            "AND sh.deleted_at IS NULL AND sh.id NOT IN "
                            f"({placeholders}) AND EXISTS ("
                            "SELECT 1 FROM continuity_feature_transitions t "
                            "WHERE t.anchor_type = 'shot' AND t.anchor_id = sh.id "
                            "AND t.deleted_at IS NULL) LIMIT 1"
                        ),
                        {"cid": scene_id, **params},
                    )
                ).first()
            else:
                removed = (
                    await conn.execute(
                        text(
                            "SELECT sh.id FROM shots sh WHERE sh.scene_id = :cid "
                            "AND sh.deleted_at IS NULL AND EXISTS ("
                            "SELECT 1 FROM continuity_feature_transitions t "
                            "WHERE t.anchor_type = 'shot' AND t.anchor_id = sh.id "
                            "AND t.deleted_at IS NULL) LIMIT 1"
                        ),
                        {"cid": scene_id},
                    )
                ).first()
            if removed is not None:
                await conn.exec_driver_sql("ROLLBACK")
                raise SoloRingError(
                    ErrorCode.CONTINUITY_ANCHOR_IN_USE,
                    f"Shot {removed.id} anchors an active Feature "
                    "transition and cannot be unassigned.",
                    status_code=409,
                )

            # M7D §13.5: the same unassign guard for Relation transitions
            # (mirrors the feature form in both full-set branches).
            if ordered_shot_ids:
                removed_rel = (
                    await conn.execute(
                        text(
                            "SELECT sh.id FROM shots sh WHERE sh.scene_id = :cid "
                            "AND sh.deleted_at IS NULL AND sh.id NOT IN "
                            f"({placeholders}) AND EXISTS ("
                            "SELECT 1 FROM continuity_relation_transitions t "
                            "WHERE t.anchor_type = 'shot' AND t.anchor_id = sh.id "
                            "AND t.deleted_at IS NULL) LIMIT 1"
                        ),
                        {"cid": scene_id, **params},
                    )
                ).first()
            else:
                removed_rel = (
                    await conn.execute(
                        text(
                            "SELECT sh.id FROM shots sh WHERE sh.scene_id = :cid "
                            "AND sh.deleted_at IS NULL AND EXISTS ("
                            "SELECT 1 FROM continuity_relation_transitions t "
                            "WHERE t.anchor_type = 'shot' AND t.anchor_id = sh.id "
                            "AND t.deleted_at IS NULL) LIMIT 1"
                        ),
                        {"cid": scene_id},
                    )
                ).first()
            if removed_rel is not None:
                await conn.exec_driver_sql("ROLLBACK")
                raise SoloRingError(
                    ErrorCode.CONTINUITY_ANCHOR_IN_USE,
                    f"Shot {removed_rel.id} anchors an active Relation "
                    "transition and cannot be unassigned.",
                    status_code=409,
                )

            # Full-set semantics over ACTIVE members: omitted ACTIVE members
            # unassign. A soft-deleted Shot's narrative coordinates are
            # immutable history — never rewritten by this operation (M6B
            # re-gate).
            if ordered_shot_ids:
                placeholders = ", ".join(
                    f":s{i}" for i in range(len(ordered_shot_ids))
                )
                params = {
                    f"s{i}": sid for i, sid in enumerate(ordered_shot_ids)
                }
                await conn.execute(
                    text(
                        "UPDATE shots SET scene_id = NULL, scene_position = "
                        "NULL WHERE scene_id = :cid AND deleted_at IS NULL "
                        f"AND id NOT IN ({placeholders})"
                    ),
                    {"cid": scene_id, **params},
                )
            else:
                await conn.execute(
                    text(
                        "UPDATE shots SET scene_id = NULL, scene_position = "
                        "NULL WHERE scene_id = :cid AND deleted_at IS NULL"
                    ),
                    {"cid": scene_id},
                )

            # Temporary intra-scene range for ACTIVE retained members only:
            # strictly above every final position, so no intermediate
            # (scene_id, scene_position) duplicate exists under the
            # active-only partial unique index.
            current_max = (
                await conn.execute(
                    text(
                        "SELECT COALESCE(MAX(scene_position), -1) FROM shots "
                        "WHERE scene_id = :cid AND deleted_at IS NULL"
                    ),
                    {"cid": scene_id},
                )
            ).scalar()
            offset = current_max + len(ordered_shot_ids) + 1
            await conn.execute(
                text(
                    "UPDATE shots SET scene_position = scene_position + "
                    ":offset WHERE scene_id = :cid AND deleted_at IS NULL"
                ),
                {"offset": offset, "cid": scene_id},
            )
            for index, shot_id in enumerate(ordered_shot_ids):
                await conn.execute(
                    text(
                        "UPDATE shots SET scene_id = :cid, scene_position = "
                        ":pos WHERE id = :sid"
                    ),
                    {"cid": scene_id, "pos": index, "sid": shot_id},
                )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(exc, "scene shot assignment") from exc
