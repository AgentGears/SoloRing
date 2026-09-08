"""Production Instance spatial authority (frozen R3 §9 / §24.4).

M10-equivalent sparse persistent staging owned by one occurrence. The
requirement domain, Transform validation, anchor semantics, and winner
selection are reused from the M10 competence; the staging winner core is
the ONE shared spatial.staging.resolve_staging_winners_core (§9.1). No
interpolation authority, no implicit origin.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from soloring.continuity.transitions import _validate_anchor_in_ordering
from soloring.db.timeutil import DB_NOW_SQL
from soloring.domain.ids import new_uuid
from soloring.errors import (
    ErrorCode,
    SoloRingError,
    not_found,
    validation_error,
)
from soloring.narrative.order import load_narrative_ordering
from soloring.production_world.instance_state import (
    _occurrence_composition,
    _require_pi_subject,
)
from soloring.spatial.staging import resolve_staging_winners_core

NOW_SQL = DB_NOW_SQL


async def _load_world_active(conn, world_id: str) -> dict:
    row = (
        await conn.execute(
            text("SELECT id, project_id FROM spatial_worlds "
                 "WHERE id = :w AND deleted_at IS NULL"), {"w": world_id},
        )
    ).first()
    if row is None:
        raise not_found(ErrorCode.SPATIAL_WORLD_INVALID,
                        f"SpatialWorld {world_id!r} not found or deleted.")
    return {"id": row.id, "project_id": row.project_id}


async def create_track(session: AsyncSession, world_id: str, *,
                       occurrence_id: str, requirement: str) -> str:
    if requirement not in ("required", "optional"):
        raise validation_error("requirement must be 'required' or 'optional'")
    tid = new_uuid()
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        composition_id = await _occurrence_composition(conn, occurrence_id)
        world = await _load_world_active(conn, world_id)
        subj = await _require_pi_subject(conn, composition_id, occurrence_id)
        if subj["project_id"] != world["project_id"]:
            raise validation_error(
                "SpatialWorld belongs to another Project")
        taken = (
            await conn.execute(
                text(
                    "SELECT id FROM production_instance_spatial_tracks "
                    "WHERE spatial_world_id = :w AND occurrence_id = :oid "
                    "AND deleted_at IS NULL"
                ),
                {"w": world_id, "oid": occurrence_id},
            )
        ).first()
        if taken is not None:
            raise SoloRingError(
                ErrorCode.SPATIAL_TRACK_INVALID,
                "an active Production Instance track already exists for "
                "this occurrence in this SpatialWorld (one spatial winner "
                "per Production Instance per world)",
                status_code=409,
            )
        await conn.execute(
            text(
                "INSERT INTO production_instance_spatial_tracks "
                "(id, spatial_world_id, composition_id, occurrence_id, "
                f"requirement, created_at, updated_at) VALUES "
                f"(:id, :w, :cid, :oid, :req, {NOW_SQL}, {NOW_SQL})"
            ),
            {"id": tid, "w": world_id, "cid": composition_id,
             "oid": occurrence_id, "req": requirement},
        )
        await conn.exec_driver_sql("COMMIT")
    return tid


def _track_not_found(track_id: str) -> SoloRingError:
    return not_found(
        ErrorCode.PRODUCTION_INSTANCE_SPATIAL_TRACK_NOT_FOUND,
        f"Production Instance spatial track {track_id!r} not found.",
    )


async def _load_active_track(conn, track_id: str) -> dict:
    row = (
        await conn.execute(
            text(
                "SELECT id, spatial_world_id, composition_id, occurrence_id, "
                "requirement FROM production_instance_spatial_tracks "
                "WHERE id = :tid AND deleted_at IS NULL"
            ),
            {"tid": track_id},
        )
    ).first()
    if row is None:
        raise _track_not_found(track_id)
    return dict(row._mapping)


async def get_track(session: AsyncSession, track_id: str) -> dict:
    async with session.bind.connect() as conn:
        return await _load_active_track(conn, track_id)


async def list_tracks(session: AsyncSession, world_id: str) -> list[dict]:
    async with session.bind.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT id, spatial_world_id, composition_id, "
                    "occurrence_id, requirement FROM "
                    "production_instance_spatial_tracks "
                    "WHERE spatial_world_id = :w AND deleted_at IS NULL "
                    "ORDER BY occurrence_id"
                ),
                {"w": world_id},
            )
        ).mappings().all()
    return [dict(r) for r in rows]


async def patch_track(session: AsyncSession, track_id: str, *,
                      requirement: str | None = None) -> None:
    """The only schema-1 track mutation (frozen §24.4, mirroring M10):
    explicit requirement policy edit; identity fields are immutable."""
    if requirement is None:
        return
    if requirement not in ("required", "optional"):
        raise validation_error(
            "requirement must be 'required' or 'optional'")
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        track = await _load_active_track(conn, track_id)
        await _require_pi_subject(conn, track["composition_id"],
                                  track["occurrence_id"])
        await conn.execute(
            text(
                "UPDATE production_instance_spatial_tracks SET "
                f"requirement = :r, updated_at = {NOW_SQL} WHERE id = :t"
            ),
            {"r": requirement, "t": track_id},
        )
        await conn.exec_driver_sql("COMMIT")


async def delete_track(session: AsyncSession, track_id: str) -> None:
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        track = await _load_active_track(conn, track_id)
        await _require_pi_subject(conn, track["composition_id"],
                                  track["occurrence_id"])
        await conn.execute(
            text(
                "UPDATE production_instance_spatial_tracks "
                f"SET deleted_at = {NOW_SQL}, updated_at = {NOW_SQL} "
                "WHERE id = :tid"
            ),
            {"tid": track_id},
        )
        await conn.exec_driver_sql("COMMIT")


def _norm_transform_components(value: object) -> tuple[int, ...]:
    if not isinstance(value, dict) or set(value) != {
            "translation_mm", "rotation_udeg"}:
        raise validation_error(
            "transform must be exactly {translation_mm, rotation_udeg}")
    out: list[int] = []
    for key in ("translation_mm", "rotation_udeg"):
        vec = value[key]
        if not isinstance(vec, list) or len(vec) != 3:
            raise validation_error(f"transform.{key} must be 3 integers")
        for v in vec:
            if not isinstance(v, int) or isinstance(v, bool):
                raise validation_error(f"transform.{key} must be integers")
            out.append(v)
    return tuple(out)


async def create_spatial_transition(session: AsyncSession, track_id: str,
                                    payload) -> str:
    tid = new_uuid()
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        track = await _load_active_track(conn, track_id)
        subj = await _require_pi_subject(conn, track["composition_id"],
                                         track["occurrence_id"])
        world = await _load_world_active(conn, track["spatial_world_id"])
        if payload.boundary not in ("start", "end"):
            raise validation_error("boundary must be 'start' or 'end'")
        if payload.operation not in ("set", "clear"):
            raise validation_error("operation must be 'set' or 'clear'")
        if payload.operation == "clear":
            if payload.transform is not None:
                raise validation_error(
                    "clear requires transform to be omitted")
            six = (None,) * 6
        else:
            if payload.transform is None:
                raise validation_error("set requires a transform")
            six = _norm_transform_components(payload.transform)
        await _validate_anchor_in_ordering(
            conn, subj["project_id"], payload.anchor_type, payload.anchor_id)
        taken = (
            await conn.execute(
                text(
                    "SELECT 1 FROM production_instance_spatial_transitions "
                    "WHERE spatial_track_id = :tid AND anchor_type = :at "
                    "AND anchor_id = :aid AND boundary = :b "
                    "AND deleted_at IS NULL"
                ),
                {"tid": track_id, "at": payload.anchor_type,
                 "aid": payload.anchor_id, "b": payload.boundary},
            )
        ).first()
        if taken is not None:
            raise SoloRingError(
                ErrorCode.SPATIAL_TRANSITION_INVALID,
                "an active transition already occupies this narrative "
                "coordinate for this track",
                status_code=409,
            )
        # exact M10 canonicalization at authoring time (+180deg -> -180deg)
        from soloring.spatial.math import Transform

        stored = six
        if payload.operation == "set":
            tr = Transform(translation_mm=six[:3], rotation_udeg=six[3:])
            stored = tuple(tr.translation_mm) + tuple(tr.rotation_udeg)
        await conn.execute(
            text(
                "INSERT INTO production_instance_spatial_transitions "
                "(id, spatial_track_id, anchor_type, anchor_id, boundary, "
                "operation, x_mm, y_mm, z_mm, yaw_udeg, pitch_udeg, "
                f"roll_udeg, created_at, updated_at) VALUES "
                f"(:id, :tid, :at, :aid, :b, :op, :x, :y, :z, :yaw, "
                f":pitch, :roll, {NOW_SQL}, {NOW_SQL})"
            ),
            {"id": tid, "tid": track_id, "at": payload.anchor_type,
             "aid": payload.anchor_id, "b": payload.boundary,
             "op": payload.operation, "x": stored[0], "y": stored[1],
             "z": stored[2], "yaw": stored[3], "pitch": stored[4],
             "roll": stored[5]},
        )
        await conn.exec_driver_sql("COMMIT")
    return tid


_UNSET = object()


async def patch_spatial_transition(
    session: AsyncSession, transition_id: str, *,
    anchor_type=_UNSET, anchor_id=_UNSET, boundary=_UNSET,
    operation=_UNSET, transform=_UNSET,
) -> None:
    """PATCH one COMPLETE prospective transition (frozen §24.4, mirroring
    the M10 SpatialTransition PATCH discipline): omitted fields preserve;
    the aggregate must be one of the two legal forms; anchor/boundary
    changes revalidate the complete prospective coordinate."""
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        row = (
            await conn.execute(
                text(
                    "SELECT t.id, t.spatial_track_id, t.anchor_type, "
                    "t.anchor_id, t.boundary, t.operation, t.x_mm, t.y_mm,"
                    " t.z_mm, t.yaw_udeg, t.pitch_udeg, t.roll_udeg, "
                    "t.deleted_at, k.composition_id, k.occurrence_id FROM "
                    "production_instance_spatial_transitions t JOIN "
                    "production_instance_spatial_tracks k ON "
                    "k.id = t.spatial_track_id WHERE t.id = :tid"
                ),
                {"tid": transition_id},
            )
        ).first()
        if row is None:
            raise not_found(
                ErrorCode.PRODUCTION_INSTANCE_SPATIAL_TRACK_NOT_FOUND,
                f"Production Instance spatial transition {transition_id!r}"
                " not found.",
            )
        subj = await _require_pi_subject(conn, row.composition_id,
                                         row.occurrence_id)
        if row.deleted_at is not None:
            raise validation_error("cannot patch a deleted transition")
        p_at = row.anchor_type if anchor_type is _UNSET else anchor_type
        p_aid = row.anchor_id if anchor_id is _UNSET else anchor_id
        p_b = row.boundary if boundary is _UNSET else boundary
        p_op = row.operation if operation is _UNSET else operation
        if p_at not in ("sequence", "scene", "shot"):
            raise validation_error("anchor_type must be sequence|scene|shot")
        if p_b not in ("start", "end"):
            raise validation_error("boundary must be start|end")
        if p_op not in ("set", "clear"):
            raise validation_error("operation must be set|clear")
        await _validate_anchor_in_ordering(
            conn, subj["project_id"], p_at, p_aid)
        if p_op == "clear":
            if transform is not _UNSET and transform is not None:
                raise validation_error("clear requires no transform")
            six = (None,) * 6
        else:
            base = (row.x_mm, row.y_mm, row.z_mm, row.yaw_udeg,
                    row.pitch_udeg, row.roll_udeg)
            if transform is _UNSET:
                six = base
            else:
                if transform is None:
                    raise validation_error("set requires a transform")
                six = _norm_transform_components(transform)
        if (p_at, p_aid, p_b) != (row.anchor_type, row.anchor_id,
                                   row.boundary):
            taken = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM "
                        "production_instance_spatial_transitions WHERE "
                        "spatial_track_id = :t AND anchor_type = :at AND "
                        "anchor_id = :aid AND boundary = :b AND "
                        "deleted_at IS NULL AND id <> :ex"
                    ),
                    {"t": row.spatial_track_id, "at": p_at, "aid": p_aid,
                     "b": p_b, "ex": transition_id},
                )
            ).first()
            if taken is not None:
                raise SoloRingError(
                    ErrorCode.SPATIAL_TRANSITION_INVALID,
                    "the prospective coordinate is already occupied",
                    status_code=409,
                )
        # exact M10 canonicalization at authoring time
        stored = six
        if p_op == "set":
            from soloring.spatial.math import Transform

            tr = Transform(translation_mm=six[:3], rotation_udeg=six[3:])
            stored = tuple(tr.translation_mm) + tuple(tr.rotation_udeg)
        await conn.execute(
            text(
                "UPDATE production_instance_spatial_transitions SET "
                "anchor_type = :at, anchor_id = :aid, boundary = :b, "
                "operation = :op, x_mm = :x, y_mm = :y, z_mm = :z, "
                "yaw_udeg = :yaw, pitch_udeg = :pitch, roll_udeg = :roll, "
                f"updated_at = {NOW_SQL} WHERE id = :tid"
            ),
            {"at": p_at, "aid": p_aid, "b": p_b, "op": p_op,
             "x": stored[0], "y": stored[1], "z": stored[2],
             "yaw": stored[3], "pitch": stored[4], "roll": stored[5],
             "tid": transition_id},
        )
        await conn.exec_driver_sql("COMMIT")


async def delete_spatial_transition(session: AsyncSession,
                                    transition_id: str) -> None:
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        row = (
            await conn.execute(
                text(
                    "SELECT t.id, k.composition_id, k.occurrence_id FROM "
                    "production_instance_spatial_transitions t "
                    "JOIN production_instance_spatial_tracks k "
                    "ON k.id = t.spatial_track_id "
                    "WHERE t.id = :tid AND t.deleted_at IS NULL"
                ),
                {"tid": transition_id},
            )
        ).first()
        if row is None:
            raise not_found(
                ErrorCode.PRODUCTION_INSTANCE_SPATIAL_TRACK_NOT_FOUND,
                f"Production Instance spatial transition {transition_id!r} "
                "not found.",
            )
        await _require_pi_subject(conn, row.composition_id, row.occurrence_id)
        await conn.execute(
            text(
                "UPDATE production_instance_spatial_transitions "
                f"SET deleted_at = {NOW_SQL}, updated_at = {NOW_SQL} "
                "WHERE id = :tid"
            ),
            {"tid": transition_id},
        )
        await conn.exec_driver_sql("COMMIT")


async def resolve_pi_staging(
    conn: AsyncConnection, *, shot_id: str, spatial_world_id: str,
    subjects: list[tuple[str, str]],
) -> dict:
    """Effective PI staging at the target Shot/start on the caller's
    coherent snapshot, for the exact bound subject occurrence set (§9.3).

    Uses the ONE shared staging core; a required track with no effective
    set is surfaced via ``absent`` (the strict capture gate raises
    PRODUCTION_INSTANCE_TRACK_STATE_REQUIRED, §15).
    """
    shot = (
        await conn.execute(
            text("SELECT project_id, deleted_at, scene_id FROM shots "
                 "WHERE id = :sid"), {"sid": shot_id},
        )
    ).first()
    if shot is None or shot.deleted_at is not None:
        raise SoloRingError(ErrorCode.SHOT_NOT_FOUND,
                            f"Shot {shot_id} not found.", status_code=404)
    world = (
        await conn.execute(
            text("SELECT project_id FROM spatial_worlds WHERE id = :w "
                 "AND deleted_at IS NULL"), {"w": spatial_world_id},
        )
    ).first()
    if world is None:
        raise SoloRingError(
            ErrorCode.SPATIAL_WORLD_INVALID,
            f"SpatialWorld {spatial_world_id!r} not found or deleted.",
            status_code=404)
    if world.project_id != shot.project_id:
        raise validation_error("Requested SpatialWorld belongs to another "
                               "Project.")
    assigned = shot.scene_id is not None
    tracks: list[dict] = []
    transitions: list[dict] = []
    if subjects:
        o_ph = ", ".join(f":o{i}" for i in range(len(subjects)))
        o_params = {f"o{i}": occ for i, (_, occ) in enumerate(subjects)}
        tracks = [dict(r, owner_id=r["occurrence_id"], track_id=r["id"])
                  for r in (
            await conn.execute(text(
                f"SELECT id, occurrence_id, requirement FROM "
                f"production_instance_spatial_tracks "
                f"WHERE spatial_world_id = :w AND deleted_at IS NULL "
                f"AND occurrence_id IN ({o_ph})"),
                {"w": spatial_world_id, **o_params})
        ).mappings().all()]
        if tracks:
            t_ph = ", ".join(f":t{i}" for i in range(len(tracks)))
            t_params = {f"t{i}": t["id"] for i, t in enumerate(tracks)}
            transitions = [dict(r, track_id=r["spatial_track_id"])
                           for r in (
                await conn.execute(text(
                    f"SELECT id, spatial_track_id, anchor_type, anchor_id, "
                    f"boundary, operation, x_mm, y_mm, z_mm, yaw_udeg, "
                    f"pitch_udeg, roll_udeg FROM "
                    f"production_instance_spatial_transitions "
                    f"WHERE deleted_at IS NULL AND spatial_track_id IN "
                    f"({t_ph})"), t_params)
            ).mappings().all()]
    relevant = bool(transitions)
    if not assigned:
        return {"shot_id": shot_id, "spatial_world_id": spatial_world_id,
                "assigned": False,
                "relevant_transition_data": relevant,
                "states": [], "absent": []}
    ordering = await load_narrative_ordering(conn, shot.project_id)
    target_rank = ordering.shot_start_rank(shot_id)
    winners, absent = resolve_staging_winners_core(
        ordering=ordering, target_rank=target_rank,
        tracks=tracks, transitions=transitions)
    return {"shot_id": shot_id, "spatial_world_id": spatial_world_id,
            "assigned": True, "relevant_transition_data": relevant,
            "states": winners, "absent": absent}
