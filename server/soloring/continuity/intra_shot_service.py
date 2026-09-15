"""M16-A authoritative intra-Shot event lifecycle foundation.

Every multi-row authority mutation takes ``BEGIN IMMEDIATE`` before its first
authoritative read. Prospective-set validation is whole-shot and set-oriented;
no event is committed if it would make a later before-state false or leave a
nonterminal ``require_handoff`` marker.
"""

from __future__ import annotations

import contextlib
import json

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from soloring.continuity.intra_shot_canonical import (
    MAX_ACTIVE_EVENTS_PER_SHOT,
    canonical_state,
    event_set_hash,
    event_storage,
    state_storage,
)
from soloring.db.timeutil import DB_NOW_SQL
from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.domain.ids import is_uuid, new_uuid
from soloring.domain.normalize import (
    normalize_optional_creative,
    normalize_required_text,
)
from soloring.errors import ErrorCode, SoloRingError, internal_invariant, not_found, validation_error

NOW_SQL = DB_NOW_SQL


def _domain(code: str, message: str, **details) -> SoloRingError:
    return SoloRingError(code, message, status_code=409, details=details)


def _target_id(row) -> str:
    if row.target_kind == "entity_feature":
        return row.entity_feature_id
    if row.target_kind == "entity_relation":
        return row.entity_relation_id
    if row.target_kind == "production_instance_feature":
        return row.production_instance_feature_id
    raise internal_invariant(f"stored M16 event has unknown target_kind {row.target_kind!r}")


def _target_fk_values(kind: str, target_id: str) -> dict:
    return {
        "entity_feature_id": target_id if kind == "entity_feature" else None,
        "entity_relation_id": target_id if kind == "entity_relation" else None,
        "production_instance_feature_id": (
            target_id if kind == "production_instance_feature" else None),
    }


async def _load_shot(conn: AsyncConnection, shot_id: str):
    if not isinstance(shot_id, str) or not is_uuid(shot_id):
        raise not_found(ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id!r} not found.")
    row = (await conn.execute(text(
        "SELECT id, project_id, scene_id, duration_ms, title, subject, action, "
        "environment, framing, camera_motion, lens, mood FROM shots "
        "WHERE id = :s AND deleted_at IS NULL"), {"s": shot_id})).first()
    if row is None:
        raise not_found(ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id!r} not found.")
    return row


async def _load_active_rows(conn: AsyncConnection, shot_id: str):
    return (await conn.execute(text(
        "SELECT id, shot_id, time_ms, ordinal, target_kind, entity_feature_id, "
        "entity_relation_id, production_instance_feature_id, "
        "before_state_json, before_state_hash, after_state_json, "
        "after_state_hash, persistence_mode, source_kind, source_proposal_id, "
        "event_json, event_hash, created_at, updated_at FROM "
        "shot_intra_shot_events WHERE shot_id = :s AND deleted_at IS NULL "
        "ORDER BY time_ms, ordinal"), {"s": shot_id})).fetchall()


def _params(prefix: str, values: list[str]):
    return ",".join(f":{prefix}{i}" for i in range(len(values))), {
        f"{prefix}{i}": v for i, v in enumerate(values)}


async def _target_context(conn: AsyncConnection, shot, drafts: list[dict]) -> tuple[dict, dict]:
    """Load all target metadata and exact Shot/start states set-oriented."""
    kinds: dict[str, list[str]] = {
        "entity_feature": [], "entity_relation": [],
        "production_instance_feature": []}
    for d in drafts:
        if d["target_id"] not in kinds[d["target_kind"]]:
            kinds[d["target_kind"]].append(d["target_id"])

    from soloring.continuity.snapshots import resolve_working_dependencies
    from soloring.continuity.state import (
        resolve_effective_feature_state,
        resolve_effective_relation_state,
    )

    resolved_deps = await resolve_working_dependencies(conn, shot.id)
    dep_ids = {d.entity_id for d in resolved_deps}
    metadata: dict[tuple[str, str], dict] = {}
    starts: dict[tuple[str, str], dict] = {}

    feature_outcome = await resolve_effective_feature_state(conn, shot.id)
    feature_states = {s.feature_id: {
        "present": True, "value": json.loads(s.value_json),
        "value_hash": s.value_hash} for s in feature_outcome.states}
    if kinds["entity_feature"]:
        ph, ps = _params("ef", kinds["entity_feature"])
        rows = (await conn.execute(text(
            "SELECT f.id, f.entity_id, f.key, f.kind, f.value_type, f.unit, "
            "f.enum_values_json, e.project_id FROM continuity_features f "
            "JOIN creative_entities e ON e.id = f.entity_id "
            f"WHERE f.deleted_at IS NULL AND f.id IN ({ph})"), ps)).mappings().all()
        by_id = {r["id"]: dict(r) for r in rows}
        for fid in kinds["entity_feature"]:
            f = by_id.get(fid)
            if (f is None or f["project_id"] != shot.project_id
                    or f["entity_id"] not in dep_ids):
                raise _domain(
                    ErrorCode.INTRA_SHOT_TARGET_INVALID,
                    "entity feature target is not an active Shot dependency",
                    target_kind="entity_feature", target_id=fid)
            if not feature_outcome.assigned and feature_outcome.relevant_temporal_data:
                raise _domain(
                    ErrorCode.INTRA_SHOT_TARGET_INVALID,
                    "entity feature Shot/start state is not resolvable without narrative context",
                    target_kind="entity_feature", target_id=fid)
            metadata[("entity_feature", fid)] = f
            starts[("entity_feature", fid)] = feature_states.get(fid, {"present": False})

    relation_outcome = await resolve_effective_relation_state(conn, shot.id)
    relation_active = {s.relation_id for s in relation_outcome.relation_states}
    if kinds["entity_relation"]:
        ph, ps = _params("er", kinds["entity_relation"])
        rows = (await conn.execute(text(
            "SELECT r.id, r.project_id, r.subject_entity_id, r.predicate_id, "
            "p.key AS predicate_key, r.object_entity_id FROM continuity_relations r "
            "JOIN continuity_predicates p ON p.id = r.predicate_id "
            f"WHERE r.deleted_at IS NULL AND p.deleted_at IS NULL AND r.id IN ({ph})"),
            ps)).mappings().all()
        by_id = {r["id"]: dict(r) for r in rows}
        for rid in kinds["entity_relation"]:
            r = by_id.get(rid)
            if (r is None or r["project_id"] != shot.project_id
                    or r["subject_entity_id"] not in dep_ids
                    or r["object_entity_id"] not in dep_ids):
                raise _domain(
                    ErrorCode.INTRA_SHOT_TARGET_INVALID,
                    "relation target requires both directional endpoint dependencies",
                    target_kind="entity_relation", target_id=rid)
            if not relation_outcome.assigned and relation_outcome.relevant_relation_data:
                raise _domain(
                    ErrorCode.INTRA_SHOT_TARGET_INVALID,
                    "relation Shot/start state is not resolvable without narrative context",
                    target_kind="entity_relation", target_id=rid)
            metadata[("entity_relation", rid)] = r
            starts[("entity_relation", rid)] = {"active": rid in relation_active}

    if kinds["production_instance_feature"]:
        ph, ps = _params("pf", kinds["production_instance_feature"])
        rows = (await conn.execute(text(
            "SELECT f.id, f.composition_id, f.occurrence_id, f.key, f.kind, "
            "f.value_type, f.unit, f.enum_values_json, "
            "a.subject_kind AS authority_subject_kind, bs.subject_kind AS binding_subject_kind, "
            "cr.composition_id AS binding_composition_id "
            "FROM production_instance_features f "
            "LEFT JOIN composition_occurrence_authority_subjects a "
            "ON a.composition_id = f.composition_id AND a.occurrence_id = f.occurrence_id "
            "LEFT JOIN shot_production_world_selections sel ON sel.shot_id = :sid "
            "LEFT JOIN composition_spatial_binding_subjects bs "
            "ON bs.binding_id = sel.binding_id AND bs.occurrence_id = f.occurrence_id "
            "LEFT JOIN composition_spatial_bindings b ON b.id = sel.binding_id "
            "LEFT JOIN composition_revisions cr ON cr.id = b.composition_revision_id "
            f"WHERE f.deleted_at IS NULL AND f.id IN ({ph})"),
            {"sid": shot.id, **ps})).mappings().all()
        by_id = {r["id"]: dict(r) for r in rows}

        from soloring.spatial.resolver import resolve_spatial_continuity
        from soloring.production_world.resolver import resolve_production_world

        spatial = await resolve_spatial_continuity(
            conn, shot_id=shot.id, resolved_dependencies=resolved_deps)
        if not spatial.ready:
            raise _domain(
                ErrorCode.INTRA_SHOT_TARGET_INVALID,
                "Production Instance target requires ready current Production World",
                reason="spatial_not_ready")
        world = await resolve_production_world(
            conn, shot_id=shot.id, resolved_dependencies=resolved_deps,
            m10_spatial_result=spatial)
        if not world.selected or not world.ready or world.pack is None:
            raise _domain(
                ErrorCode.INTRA_SHOT_TARGET_INVALID,
                "Production Instance target requires ready selected current Production World",
                reason="production_world_not_ready")
        pi_states = {s["feature_id"]: {
            "present": True, "value": s["value"], "value_hash": s["value_hash"]}
            for s in world.pack["instance_feature_states"]}
        for fid in kinds["production_instance_feature"]:
            f = by_id.get(fid)
            if (f is None or f["authority_subject_kind"] != "production_instance"
                    or f["binding_subject_kind"] != "production_instance"
                    or f["binding_composition_id"] != f["composition_id"]):
                raise _domain(
                    ErrorCode.INTRA_SHOT_TARGET_INVALID,
                    "Production Instance feature is not a selected production_instance subject",
                    target_kind="production_instance_feature", target_id=fid)
            metadata[("production_instance_feature", fid)] = f
            starts[("production_instance_feature", fid)] = pi_states.get(
                fid, {"present": False})

    return metadata, starts


def _draft_from_row(row) -> dict:
    try:
        before = json.loads(row.before_state_json)
        after = json.loads(row.after_state_json)
        event_doc = json.loads(row.event_json)
    except (ValueError, TypeError) as exc:
        raise internal_invariant(
            f"stored intra-Shot event {row.id} contains malformed JSON") from exc
    return {
        "id": row.id, "time_ms": row.time_ms, "ordinal": row.ordinal,
        "target_kind": row.target_kind, "target_id": _target_id(row),
        "before": before, "after": after,
        "persistence_mode": row.persistence_mode,
        "source_kind": row.source_kind,
        "source_proposal_id": row.source_proposal_id,
        "stored": row, "stored_event_doc": event_doc,
    }


async def validate_prospective_event_set(conn: AsyncConnection, shot,
                                         drafts: list[dict]) -> dict:
    if len(drafts) > MAX_ACTIVE_EVENTS_PER_SHOT:
        raise _domain(ErrorCode.INTRA_SHOT_EVENT_LIMIT_EXCEEDED,
                      "a Shot may contain at most 10,000 active intra-Shot events",
                      limit=MAX_ACTIVE_EVENTS_PER_SHOT)
    if not drafts:
        return {"events": [], "terminal_states": {}, "event_set_hash": None}
    duration = shot.duration_ms
    if type(duration) is not int or duration <= 0:
        raise _domain(ErrorCode.INTRA_SHOT_DURATION_REQUIRED,
                      "positive Shot duration is required while intra-Shot events exist",
                      shot_id=shot.id)

    seen: set[tuple[int, int]] = set()
    for d in drafts:
        t, o = d["time_ms"], d["ordinal"]
        if type(t) is not int or t < 1 or t >= duration:
            raise _domain(ErrorCode.INTRA_SHOT_TIME_OUT_OF_RANGE,
                          "event time must be strictly inside the Shot duration",
                          shot_id=shot.id, time_ms=t, duration_ms=duration)
        if type(o) is not int or o < 0:
            raise validation_error("ordinal must be a nonnegative plain integer")
        coordinate = (t, o)
        if coordinate in seen:
            raise _domain(ErrorCode.INTRA_SHOT_EVENT_COORDINATE_CONFLICT,
                          "two active events cannot share one (time_ms, ordinal) coordinate",
                          time_ms=t, ordinal=o)
        seen.add(coordinate)

    metadata, starts = await _target_context(conn, shot, drafts)
    normalized = []
    for d in drafts:
        key = (d["target_kind"], d["target_id"])
        meta = metadata[key]
        before, before_json, before_hash = state_storage(
            d["target_kind"], d["before"], meta)
        after, after_json, after_hash = state_storage(
            d["target_kind"], d["after"], meta)
        if before == after:
            raise validation_error("before and after must differ semantically")
        event, event_json, event_hash = event_storage(
            time_ms=d["time_ms"], ordinal=d["ordinal"],
            target={"kind": d["target_kind"], "id": d["target_id"]},
            before=before, after=after, persistence_mode=d["persistence_mode"])
        stored = d.get("stored")
        if stored is not None:
            exact = (
                stored.before_state_json == before_json
                and stored.before_state_hash == before_hash
                and stored.after_state_json == after_json
                and stored.after_state_hash == after_hash
                and stored.event_json == event_json
                and stored.event_hash == event_hash
                and d.get("stored_event_doc") == event)
            if not exact:
                raise internal_invariant(
                    f"stored intra-Shot event {stored.id} disagrees with canonical columns/hash")
        normalized.append({**d, "before": before, "after": after,
                           "before_json": before_json, "before_hash": before_hash,
                           "after_json": after_json, "after_hash": after_hash,
                           "event": event, "event_json": event_json,
                           "event_hash": event_hash})

    normalized.sort(key=lambda d: (d["time_ms"], d["ordinal"]))
    folded = {k: v for k, v in starts.items()}
    per_target: dict[tuple[str, str], list[dict]] = {}
    for d in normalized:
        key = (d["target_kind"], d["target_id"])
        expected = folded[key]
        if d["before"] != expected:
            raise _domain(
                ErrorCode.INTRA_SHOT_EVENT_BEFORE_STATE_MISMATCH,
                "event before-state does not equal the exact folded current state",
                event_id=d.get("id"), target={"kind": key[0], "id": key[1]},
                expected=expected, actual=d["before"])
        folded[key] = d["after"]
        per_target.setdefault(key, []).append(d)
    for key, target_events in per_target.items():
        for event in target_events[:-1]:
            if event["persistence_mode"] == "require_handoff":
                raise _domain(
                    ErrorCode.INTRA_SHOT_PERSISTENT_EVENT_NOT_TERMINAL,
                    "require_handoff is legal only on the terminal event for its exact target",
                    event_id=event.get("id"), target={"kind": key[0], "id": key[1]})
    semantic_events = [d["event"] for d in normalized]
    return {
        "events": normalized,
        "terminal_states": {
            f"{kind}:{target_id}": state
            for (kind, target_id), state in sorted(folded.items())},
        "event_set_hash": event_set_hash(
            shot_id=shot.id, duration_ms=duration, events=semantic_events),
    }


def _public_event(d: dict) -> dict:
    return {
        "id": d["id"],
        **d["event"],
        "event_hash": d["event_hash"],
        "source_kind": d["source_kind"],
        "source_proposal_id": d["source_proposal_id"],
    }


async def list_current(session: AsyncSession, shot_id: str, *, cursor: int = 0,
                       limit: int = 100) -> dict:
    if type(cursor) is not int or cursor < 0:
        raise validation_error("cursor must be a nonnegative integer")
    limit = max(1, min(500, limit))
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN")
        try:
            shot = await _load_shot(conn, shot_id)
            rows = await _load_active_rows(conn, shot_id)
            result = await validate_prospective_event_set(
                conn, shot, [_draft_from_row(r) for r in rows])
            page = result["events"][cursor:cursor + limit + 1]
            more = len(page) > limit
            page = page[:limit]
            await conn.commit()
            return {
                "shot_id": shot_id,
                "duration_ms": shot.duration_ms,
                "event_set_hash": result["event_set_hash"],
                "terminal_states": result["terminal_states"],
                "events": [_public_event(d) for d in page],
                "next_cursor": cursor + limit if more else None,
            }
        except Exception:
            with contextlib.suppress(Exception):
                await conn.rollback()
            raise


async def create_event(session: AsyncSession, shot_id: str, payload, *,
                       source_kind: str = "authored",
                       source_proposal_id: str | None = None) -> dict:
    body = (payload.model_dump(exclude_unset=True)
            if hasattr(payload, "model_dump") else dict(payload))
    eid = new_uuid()
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            shot = await _load_shot(conn, shot_id)
            rows = await _load_active_rows(conn, shot_id)
            if len(rows) >= MAX_ACTIVE_EVENTS_PER_SHOT:
                raise _domain(ErrorCode.INTRA_SHOT_EVENT_LIMIT_EXCEEDED,
                              "a Shot may contain at most 10,000 active intra-Shot events")
            target = body["target"]
            draft = {
                "id": eid, "time_ms": body["time_ms"], "ordinal": body["ordinal"],
                "target_kind": target["kind"], "target_id": target["id"],
                "before": body["before"], "after": body["after"],
                "persistence_mode": body["persistence_mode"],
                "source_kind": source_kind, "source_proposal_id": source_proposal_id,
            }
            result = await validate_prospective_event_set(
                conn, shot, [_draft_from_row(r) for r in rows] + [draft])
            d = next(e for e in result["events"] if e["id"] == eid)
            await conn.execute(text(
                "INSERT INTO shot_intra_shot_events "
                "(id, shot_id, time_ms, ordinal, target_kind, entity_feature_id, "
                "entity_relation_id, production_instance_feature_id, "
                "before_state_json, before_state_hash, after_state_json, "
                "after_state_hash, persistence_mode, source_kind, source_proposal_id, "
                "event_json, event_hash, created_at, updated_at) VALUES "
                f"(:id,:shot,:t,:o,:tk,:ef,:er,:pf,:bj,:bh,:aj,:ah,:pm,:sk,:sp,"
                f":ej,:eh,{NOW_SQL},{NOW_SQL})"), {
                    "id": eid, "shot": shot_id, "t": d["time_ms"], "o": d["ordinal"],
                    "tk": d["target_kind"], **{
                        "ef": _target_fk_values(d["target_kind"], d["target_id"])["entity_feature_id"],
                        "er": _target_fk_values(d["target_kind"], d["target_id"])["entity_relation_id"],
                        "pf": _target_fk_values(d["target_kind"], d["target_id"])["production_instance_feature_id"],
                    }, "bj": d["before_json"], "bh": d["before_hash"],
                    "aj": d["after_json"], "ah": d["after_hash"], "pm": d["persistence_mode"],
                    "sk": source_kind, "sp": source_proposal_id,
                    "ej": d["event_json"], "eh": d["event_hash"]})
            await conn.commit()
            return _public_event(d)
        except IntegrityError as exc:
            with contextlib.suppress(Exception):
                await conn.rollback()
            if "shot_intra_shot_events.shot_id" in str(exc) or "uq_sise_active_coordinate" in str(exc):
                raise _domain(ErrorCode.INTRA_SHOT_EVENT_COORDINATE_CONFLICT,
                              "intra-Shot event coordinate already occupied") from exc
            raise internal_invariant("unexpected M16 event integrity failure") from exc
        except Exception:
            with contextlib.suppress(Exception):
                await conn.rollback()
            raise


async def _event_row(conn: AsyncConnection, event_id: str):
    if not isinstance(event_id, str) or not is_uuid(event_id):
        raise not_found(ErrorCode.INTRA_SHOT_TARGET_INVALID,
                        f"intra-Shot event {event_id!r} not found")
    row = (await conn.execute(text(
        "SELECT id, shot_id, time_ms, ordinal, target_kind, entity_feature_id, "
        "entity_relation_id, production_instance_feature_id, before_state_json, "
        "before_state_hash, after_state_json, after_state_hash, persistence_mode, "
        "source_kind, source_proposal_id, event_json, event_hash, created_at, "
        "updated_at FROM shot_intra_shot_events WHERE id = :e AND deleted_at IS NULL"),
        {"e": event_id})).first()
    if row is None:
        raise not_found(ErrorCode.INTRA_SHOT_TARGET_INVALID,
                        f"intra-Shot event {event_id!r} not found")
    return row


async def patch_event(session: AsyncSession, event_id: str, payload) -> dict:
    body = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else dict(payload)
    if not body:
        raise validation_error("event PATCH requires at least one semantic field")
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            row = await _event_row(conn, event_id)
            shot = await _load_shot(conn, row.shot_id)
            rows = await _load_active_rows(conn, row.shot_id)
            drafts = [_draft_from_row(r) for r in rows]
            current = next(d for d in drafts if d["id"] == event_id)
            for field in ("time_ms", "ordinal", "before", "after", "persistence_mode"):
                if field in body:
                    current[field] = body[field]
            if current["source_kind"] == "proposal_adoption":
                current["source_kind"] = "authored"
                current["source_proposal_id"] = None
            current.pop("stored", None)
            current.pop("stored_event_doc", None)
            result = await validate_prospective_event_set(conn, shot, drafts)
            d = next(e for e in result["events"] if e["id"] == event_id)
            await conn.execute(text(
                "UPDATE shot_intra_shot_events SET time_ms=:t, ordinal=:o, "
                "before_state_json=:bj, before_state_hash=:bh, after_state_json=:aj, "
                "after_state_hash=:ah, persistence_mode=:pm, source_kind=:sk, "
                "source_proposal_id=:sp, event_json=:ej, event_hash=:eh, "
                f"updated_at={NOW_SQL} WHERE id=:id"), {
                    "t": d["time_ms"], "o": d["ordinal"], "bj": d["before_json"],
                    "bh": d["before_hash"], "aj": d["after_json"], "ah": d["after_hash"],
                    "pm": d["persistence_mode"], "sk": d["source_kind"],
                    "sp": d["source_proposal_id"], "ej": d["event_json"],
                    "eh": d["event_hash"], "id": event_id})
            await conn.commit()
            return _public_event(d)
        except IntegrityError as exc:
            with contextlib.suppress(Exception):
                await conn.rollback()
            raise _domain(ErrorCode.INTRA_SHOT_EVENT_COORDINATE_CONFLICT,
                          "intra-Shot event coordinate already occupied") from exc
        except Exception:
            with contextlib.suppress(Exception):
                await conn.rollback()
            raise


async def delete_event(session: AsyncSession, event_id: str) -> None:
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            row = await _event_row(conn, event_id)
            shot = await _load_shot(conn, row.shot_id)
            rows = await _load_active_rows(conn, row.shot_id)
            drafts = [_draft_from_row(r) for r in rows if r.id != event_id]
            await validate_prospective_event_set(conn, shot, drafts)
            await conn.execute(text(
                "UPDATE shot_intra_shot_events "
                f"SET deleted_at={NOW_SQL}, updated_at={NOW_SQL} WHERE id=:e"),
                {"e": event_id})
            await conn.commit()
        except Exception:
            with contextlib.suppress(Exception):
                await conn.rollback()
            raise


async def patch_shot_with_duration_fence(session: AsyncSession, shot_id: str,
                                         payload) -> None:
    """Apply a Shot PATCH containing duration under the M16 writer fence."""
    provided = set(payload.model_fields_set)
    if "duration_ms" not in provided:
        raise internal_invariant("duration-fence helper called without duration_ms")
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            shot = await _load_shot(conn, shot_id)
            max_time = (await conn.execute(text(
                "SELECT MAX(time_ms) FROM shot_intra_shot_events "
                "WHERE shot_id=:s AND deleted_at IS NULL"), {"s": shot_id})).scalar_one()
            duration = payload.duration_ms
            if max_time is not None and (
                    type(duration) is not int or duration <= 0 or duration <= max_time):
                code = (ErrorCode.INTRA_SHOT_DURATION_REQUIRED
                        if duration is None or duration == 0
                        else ErrorCode.INTRA_SHOT_TIME_OUT_OF_RANGE)
                raise _domain(
                    code,
                    "duration mutation would make an active intra-Shot event illegal",
                    shot_id=shot_id, duration_ms=duration, max_event_time_ms=max_time)
            values = {k: getattr(shot, k) for k in (
                "title", "subject", "action", "environment", "framing",
                "camera_motion", "lens", "mood", "duration_ms")}
            if "subject" in provided:
                subject = normalize_required_text(payload.subject)
                if not subject:
                    raise validation_error("Shot subject must not be empty.")
                values["subject"] = subject
            if "title" in provided:
                values["title"] = normalize_optional_creative(payload.title)
            for field in ("action", "environment", "framing", "camera_motion", "lens", "mood"):
                if field in provided:
                    values[field] = normalize_optional_creative(getattr(payload, field))
            values["duration_ms"] = duration
            await conn.execute(text(
                "UPDATE shots SET title=:title, subject=:subject, action=:action, "
                "environment=:environment, framing=:framing, camera_motion=:camera_motion, "
                "lens=:lens, mood=:mood, duration_ms=:duration_ms, "
                f"updated_at={NOW_SQL} WHERE id=:id"), {**values, "id": shot_id})
            await conn.commit()
        except Exception:
            with contextlib.suppress(Exception):
                await conn.rollback()
            raise
