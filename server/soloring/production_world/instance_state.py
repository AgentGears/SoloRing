"""Production Instance persistent state (frozen R3 §8 / §24.3).

M7-equivalent story-time state owned by one occurrence. The grammar,
canonicalization, anchor validation, and winner semantics are reused from
the M7/M10 competence (APR-105); only the subject identity differs. The
rank/winner/value-verification core is the ONE shared
continuity.state.resolve_feature_winners_core (§8.2) — there is no
parallel story clock.
"""

from __future__ import annotations

import json as _json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from soloring.continuity.features import _validate_semantics
from soloring.continuity.state import resolve_feature_winners_core
from soloring.continuity.transitions import _validate_anchor_in_ordering
from soloring.continuity.values import canonicalize_value
from soloring.db.timeutil import DB_NOW_SQL
from soloring.domain.ids import new_uuid
from soloring.errors import (
    ErrorCode,
    SoloRingError,
    not_found,
    validation_error,
)
from soloring.narrative.order import load_narrative_ordering

NOW_SQL = DB_NOW_SQL


async def _require_pi_subject(conn, composition_id: str,
                              occurrence_id: str) -> dict:
    """Active working occurrence + immutable production_instance adoption.

    An occurrence adopted as creative_entity is rejected here: its A2
    state remains exclusively on the existing M7 CreativeEntity path
    (frozen §5.3/§5.5 — no shadow PI state).
    """
    row = (
        await conn.execute(
            text(
                "SELECT c.project_id, "
                "(SELECT subject_kind FROM "
                "composition_occurrence_authority_subjects a "
                "WHERE a.composition_id = c.id AND a.occurrence_id = :oid) "
                "AS subject_kind, "
                "(SELECT CASE WHEN EXISTS (SELECT 1 FROM "
                "composition_working_occurrences w WHERE "
                "w.composition_id = c.id AND w.occurrence_id = :oid) "
                "AND NOT EXISTS (SELECT 1 FROM "
                "composition_identity_operation_sources s "
                "JOIN composition_identity_operations op "
                "ON op.id = s.operation_id "
                "WHERE op.composition_id = c.id AND s.occurrence_id = :oid "
                "AND s.terminates_identity = 1) THEN 1 ELSE 0 END) "
                "AS active_in_working "
                "FROM compositions c WHERE c.id = :cid"
            ),
            {"oid": occurrence_id, "cid": composition_id},
        )
    ).first()
    if row is None:
        raise not_found(
            ErrorCode.COMPOSITION_NOT_FOUND,
            f"composition {composition_id!r} not found",
        )
    if row.active_in_working != 1:
        raise validation_error(
            "Production Instance authoring requires an active occurrence "
            "currently in working membership")
    if row.subject_kind is None:
        raise validation_error(
            "Production Instance authoring requires an adopted "
            "production_instance subject")
    if row.subject_kind != "production_instance":
        raise validation_error(
            "occurrence is adopted as creative_entity; its state remains "
            "exclusively on the existing CreativeEntity authority and M13 "
            "may not create shadow Production Instance state")
    return {"project_id": row.project_id}


async def _occurrence_composition(conn, occurrence_id: str) -> str:
    """The occurrence UUID is globally unique; resolve its Composition."""
    row = (
        await conn.execute(
            text("SELECT composition_id FROM composition_occurrences "
                 "WHERE id = :oid"), {"oid": occurrence_id},
        )
    ).first()
    if row is None:
        raise not_found(
            ErrorCode.COMPOSITION_OCCURRENCE_NOT_FOUND,
            f"occurrence {occurrence_id!r} not found",
        )
    return row.composition_id


async def create_feature_for_occurrence(session: AsyncSession,
                                        occurrence_id: str, payload) -> str:
    async with session.bind.connect() as conn:
        cid = await _occurrence_composition(conn, occurrence_id)
    return await create_feature(session, cid, occurrence_id, payload)


async def list_features_for_occurrence(session: AsyncSession,
                                       occurrence_id: str) -> list[dict]:
    async with session.bind.connect() as conn:
        cid = await _occurrence_composition(conn, occurrence_id)
    return await list_features(session, cid, occurrence_id)


async def create_feature(session: AsyncSession, composition_id: str,
                         occurrence_id: str, payload) -> str:
    values = _validate_semantics(payload)
    fid = new_uuid()
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        await _require_pi_subject(conn, composition_id, occurrence_id)
        # Tombstone-inclusive: a deleted key is never recycled (§5.3).
        existing_key = (
            await conn.execute(
                text(
                    "SELECT id FROM production_instance_features "
                    "WHERE composition_id = :cid AND occurrence_id = :oid "
                    "AND key = :key"
                ),
                {"cid": composition_id, "oid": occurrence_id,
                 "key": values["key"]},
            )
        ).first()
        if existing_key is not None:
            raise SoloRingError(
                ErrorCode.CONTINUITY_FEATURE_KEY_CONFLICT,
                f"Production Instance already owns feature key "
                f"{values['key']!r} (keys are never recycled, including "
                "after deletion).",
                status_code=409,
            )
        if values["supersedes_feature_id"] is not None:
            pred = (
                await conn.execute(
                    text(
                        "SELECT id, composition_id, occurrence_id FROM "
                        "production_instance_features WHERE id = :pid"
                    ),
                    {"pid": values["supersedes_feature_id"]},
                )
            ).first()
            if (pred is None or pred.composition_id != composition_id
                    or pred.occurrence_id != occurrence_id):
                raise SoloRingError(
                    ErrorCode.CONTINUITY_FEATURE_SUPERSESSION_CONFLICT,
                    "supersedes_feature_id must reference a feature of the "
                    "same Production Instance.",
                    status_code=409,
                )
            claimed = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM production_instance_features "
                        "WHERE supersedes_feature_id = :pid"
                    ),
                    {"pid": values["supersedes_feature_id"]},
                )
            ).first()
            if claimed is not None:
                raise SoloRingError(
                    ErrorCode.CONTINUITY_FEATURE_SUPERSESSION_CONFLICT,
                    "predecessor already has a direct successor.",
                    status_code=409,
                )
        await conn.execute(
            text(
                "INSERT INTO production_instance_features "
                "(id, composition_id, occurrence_id, key, kind, value_type, "
                "name, description, enum_values_json, unit, "
                "supersedes_feature_id, created_at, updated_at) "
                f"VALUES (:id, :cid, :oid, :key, :kind, :vt, :name, :desc, "
                f":enum, :unit, :sup, {NOW_SQL}, {NOW_SQL})"
            ),
            {"id": fid, "cid": composition_id, "oid": occurrence_id,
             "key": values["key"], "kind": values["kind"],
             "vt": values["value_type"], "name": values["name"],
             "desc": values["description"],
             "enum": values["enum_values_json"], "unit": values["unit"],
             "sup": values["supersedes_feature_id"]},
        )
        await conn.exec_driver_sql("COMMIT")
    return fid


def _feature_not_found(feature_id: str) -> SoloRingError:
    return not_found(
        ErrorCode.PRODUCTION_INSTANCE_FEATURE_NOT_FOUND,
        f"Production Instance feature {feature_id!r} not found.",
    )


async def _load_active_feature(conn, feature_id: str) -> dict:
    row = (
        await conn.execute(
            text(
                "SELECT id, composition_id, occurrence_id, key, kind, "
                "value_type, name, description, enum_values_json, unit, "
                "supersedes_feature_id, created_at, updated_at FROM "
                "production_instance_features "
                "WHERE id = :fid AND deleted_at IS NULL"
            ),
            {"fid": feature_id},
        )
    ).first()
    if row is None:
        raise _feature_not_found(feature_id)
    return dict(row._mapping)


async def get_feature(session: AsyncSession, feature_id: str) -> dict:
    async with session.bind.connect() as conn:
        return await _load_active_feature(conn, feature_id)


async def list_features(session: AsyncSession, composition_id: str,
                        occurrence_id: str) -> list[dict]:
    async with session.bind.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT id, composition_id, occurrence_id, key, kind, "
                    "value_type, name, description, enum_values_json, unit, "
                    "supersedes_feature_id, created_at, updated_at FROM "
                    "production_instance_features WHERE composition_id = :cid "
                    "AND occurrence_id = :oid AND deleted_at IS NULL "
                    "ORDER BY key"
                ),
                {"cid": composition_id, "oid": occurrence_id},
            )
        ).mappings().all()
    return [dict(r) for r in rows]


async def patch_feature(session: AsyncSession, feature_id: str, payload) -> None:
    if payload.name is None and payload.description is None:
        raise validation_error(
            "nothing to patch: provide name and/or description")
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        feature = await _load_active_feature(conn, feature_id)
        # the owning occurrence must still be legally current (§7.3)
        await _require_pi_subject(conn, feature["composition_id"],
                                  feature["occurrence_id"])
        name = feature["name"] if payload.name is None else payload.name
        name = (name or "").strip()
        if not name:
            raise validation_error("Feature name must not be empty.")
        description = (feature["description"] if payload.description is None
                       else payload.description)
        await conn.execute(
            text(
                "UPDATE production_instance_features SET name = :name, "
                f"description = :desc, updated_at = {NOW_SQL} "
                "WHERE id = :fid"
            ),
            {"name": name, "desc": description, "fid": feature_id},
        )
        await conn.exec_driver_sql("COMMIT")


async def delete_feature(session: AsyncSession, feature_id: str) -> None:
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        feature = await _load_active_feature(conn, feature_id)
        await _require_pi_subject(conn, feature["composition_id"],
                                  feature["occurrence_id"])
        await conn.execute(
            text(
                "UPDATE production_instance_features "
                f"SET deleted_at = {NOW_SQL}, updated_at = {NOW_SQL} "
                "WHERE id = :fid"
            ),
            {"fid": feature_id},
        )
        await conn.exec_driver_sql("COMMIT")


async def create_transition(session: AsyncSession, feature_id: str,
                            payload) -> str:
    tid = new_uuid()
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        feature = await _load_active_feature(conn, feature_id)
        subj = await _require_pi_subject(conn, feature["composition_id"],
                                         feature["occurrence_id"])
        if payload.boundary not in ("start", "end"):
            raise validation_error("boundary must be 'start' or 'end'")
        if payload.operation not in ("set", "clear"):
            raise validation_error("operation must be 'set' or 'clear'")
        value_supplied = "value" in getattr(
            payload, "model_fields_set", {"value"}) and getattr(
            payload, "value", None) is not None
        value_explicit_null = "value" in getattr(
            payload, "model_fields_set", set()) and getattr(
            payload, "value", None) is None
        if payload.operation == "clear":
            if value_supplied or value_explicit_null:
                raise validation_error(
                    "clear requires value to be omitted entirely; "
                    "value:null is never accepted")
            value_json = value_hash = None
        else:
            if value_explicit_null:
                raise validation_error(
                    "value:null is never accepted; supply the set value")
            if not value_supplied:
                raise validation_error("set requires a value")
            enum_values = None
            if feature["value_type"] == "enum":
                enum_values = _json.loads(feature["enum_values_json"])
            value_json, value_hash = canonicalize_value(
                feature["value_type"], payload.value,
                enum_values=enum_values)
        await _validate_anchor_in_ordering(
            conn, subj["project_id"], payload.anchor_type, payload.anchor_id)
        taken = (
            await conn.execute(
                text(
                    "SELECT 1 FROM production_instance_feature_transitions "
                    "WHERE feature_id = :fid AND anchor_type = :at "
                    "AND anchor_id = :aid AND boundary = :b "
                    "AND deleted_at IS NULL"
                ),
                {"fid": feature_id, "at": payload.anchor_type,
                 "aid": payload.anchor_id, "b": payload.boundary},
            )
        ).first()
        if taken is not None:
            raise SoloRingError(
                ErrorCode.CONTINUITY_TRANSITION_CONFLICT,
                "an active transition already occupies this narrative "
                "coordinate for this feature",
                status_code=409,
            )
        await conn.execute(
            text(
                "INSERT INTO production_instance_feature_transitions "
                "(id, feature_id, anchor_type, anchor_id, boundary, "
                f"operation, value_json, value_hash, created_at, updated_at)"
                f" VALUES (:id, :fid, :at, :aid, :b, :op, :vj, :vh, "
                f"{NOW_SQL}, {NOW_SQL})"
            ),
            {"id": tid, "fid": feature_id, "at": payload.anchor_type,
             "aid": payload.anchor_id, "b": payload.boundary,
             "op": payload.operation, "vj": value_json, "vh": value_hash},
        )
        await conn.exec_driver_sql("COMMIT")
    return tid


_UNSET = object()


async def patch_transition(session: AsyncSession, transition_id: str, *,
                           anchor_type=_UNSET, anchor_id=_UNSET,
                           boundary=_UNSET, operation=_UNSET,
                           value=_UNSET) -> None:
    """PATCH one COMPLETE prospective transition (frozen §24.3, mirroring
    the M7/M10 PATCH discipline). Omitted fields preserve; the resulting
    aggregate must be one of the two legal forms (set = canonical value,
    clear = no value); anchor/boundary changes revalidate the complete
    prospective coordinate against the active-coordinate uniqueness."""
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        row = (
            await conn.execute(
                text(
                    "SELECT t.id, t.feature_id, t.anchor_type, t.anchor_id,"
                    " t.boundary, t.operation, t.value_json, t.value_hash,"
                    " t.deleted_at, f.composition_id, f.occurrence_id FROM "
                    "production_instance_feature_transitions t JOIN "
                    "production_instance_features f ON f.id = t.feature_id "
                    "WHERE t.id = :tid"
                ),
                {"tid": transition_id},
            )
        ).first()
        if row is None:
            raise not_found(
                ErrorCode.PRODUCTION_INSTANCE_FEATURE_NOT_FOUND,
                f"Production Instance feature transition {transition_id!r} "
                "not found.",
            )
        subj = await _require_pi_subject(conn, row.composition_id,
                                         row.occurrence_id)
        feature = await _load_active_feature(conn, row.feature_id)
        if row.deleted_at is not None:
            raise validation_error(
                "cannot patch a deleted transition")
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
            if value is not _UNSET:
                raise validation_error(
                    "clear requires value to be omitted entirely; "
                    "value:null is never accepted")
            v_json = v_hash = None
        else:
            if value is _UNSET:
                if row.operation != "set" or row.value_json is None:
                    # M7 rule: a clear→set transition requires an
                    # explicitly supplied value — there is nothing legal
                    # to preserve
                    raise validation_error(
                        "changing a clear transition to set requires an "
                        "explicit value")
                # preserve the stored value; re-verify it canonically
                value_obj = _json.loads(row.value_json)
            else:
                if value is None:
                    raise validation_error(
                        "value:null is never accepted; omit value or "
                        "supply the set value")
                value_obj = value
            enum_values = None
            if feature["value_type"] == "enum":
                enum_values = _json.loads(feature["enum_values_json"])
            v_json, v_hash = canonicalize_value(
                feature["value_type"], value_obj, enum_values=enum_values)
        if (p_at, p_aid, p_b) != (row.anchor_type, row.anchor_id,
                                   row.boundary):
            taken = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM "
                        "production_instance_feature_transitions "
                        "WHERE feature_id = :fid AND anchor_type = :at "
                        "AND anchor_id = :aid AND boundary = :b AND "
                        "deleted_at IS NULL AND id <> :ex"
                    ),
                    {"fid": row.feature_id, "at": p_at, "aid": p_aid,
                     "b": p_b, "ex": transition_id},
                )
            ).first()
            if taken is not None:
                raise SoloRingError(
                    ErrorCode.CONTINUITY_TRANSITION_CONFLICT,
                    "the prospective coordinate is already occupied",
                    status_code=409,
                )
        await conn.execute(
            text(
                "UPDATE production_instance_feature_transitions SET "
                "anchor_type = :at, anchor_id = :aid, boundary = :b, "
                f"operation = :op, value_json = :vj, value_hash = :vh, "
                f"updated_at = {NOW_SQL} WHERE id = :tid"
            ),
            {"at": p_at, "aid": p_aid, "b": p_b, "op": p_op,
             "vj": v_json, "vh": v_hash, "tid": transition_id},
        )
        await conn.exec_driver_sql("COMMIT")


async def delete_transition(session: AsyncSession, transition_id: str) -> None:
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        row = (
            await conn.execute(
                text(
                    "SELECT t.id, f.composition_id, f.occurrence_id FROM "
                    "production_instance_feature_transitions t "
                    "JOIN production_instance_features f "
                    "ON f.id = t.feature_id "
                    "WHERE t.id = :tid AND t.deleted_at IS NULL"
                ),
                {"tid": transition_id},
            )
        ).first()
        if row is None:
            raise not_found(
                ErrorCode.PRODUCTION_INSTANCE_FEATURE_NOT_FOUND,
                f"Production Instance feature transition {transition_id!r} "
                "not found.",
            )
        await _require_pi_subject(conn, row.composition_id, row.occurrence_id)
        await conn.execute(
            text(
                "UPDATE production_instance_feature_transitions "
                f"SET deleted_at = {NOW_SQL}, updated_at = {NOW_SQL} "
                "WHERE id = :tid"
            ),
            {"tid": transition_id},
        )
        await conn.exec_driver_sql("COMMIT")


async def resolve_pi_feature_state(
    conn: AsyncConnection, *, shot_id: str,
    subjects: list[tuple[str, str]],
) -> dict:
    """Effective PI Feature state at the target Shot for the exact bound
    subject occurrence set (§8.3), on the caller's coherent snapshot.

    Uses the ONE shared winner core. Unassigned Shots with relevant data
    surface the condition structurally (the strict capture gate raises
    NARRATIVE_CONTEXT_REQUIRED itself, §8.4).
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
    assigned = shot.scene_id is not None
    features: list[dict] = []
    transitions: list[dict] = []
    if subjects:
        o_ph = ", ".join(f":o{i}" for i in range(len(subjects)))
        o_params = {f"o{i}": occ for i, (_, occ) in enumerate(subjects)}
        features = [dict(r, owner_id=r["occurrence_id"]) for r in (
            await conn.execute(text(
                f"SELECT id, composition_id, occurrence_id, key, kind, "
                f"value_type, unit, enum_values_json FROM "
                f"production_instance_features WHERE deleted_at IS NULL "
                f"AND occurrence_id IN ({o_ph})"), o_params)
        ).mappings().all()]
        if features:
            f_ph = ", ".join(f":f{i}" for i in range(len(features)))
            f_params = {f"f{i}": f["id"] for i, f in enumerate(features)}
            transitions = [dict(r) for r in (
                await conn.execute(text(
                    f"SELECT id, feature_id, anchor_type, anchor_id, "
                    f"boundary, operation, value_json, value_hash FROM "
                    f"production_instance_feature_transitions "
                    f"WHERE deleted_at IS NULL AND feature_id IN ({f_ph})"),
                    f_params)
            ).mappings().all()]
    relevant = bool(transitions)
    if not assigned:
        return {"shot_id": shot_id, "assigned": False,
                "relevant_temporal_data": relevant, "states": []}
    ordering = await load_narrative_ordering(conn, shot.project_id)
    target_rank = ordering.shot_start_rank(shot_id)
    winners = resolve_feature_winners_core(
        ordering=ordering, target_rank=target_rank,
        features=features, transitions=transitions)
    return {"shot_id": shot_id, "assigned": True,
            "relevant_temporal_data": relevant, "states": winners}
