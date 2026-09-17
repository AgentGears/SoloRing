"""M16-D proposal ingestion + explicit consequence review/adoption.

Every multi-row authority operation takes BEGIN IMMEDIATE before its
first authoritative read; event + handoff + review share ONE atomic
transaction. The connection-scoped transition helpers never open,
commit, or roll back their own nested transaction. Review evidence
writes through the exact §7.5.1/§7.5.2 roots already certified by the
C recovery verifier.
"""

from __future__ import annotations

import contextlib
import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from soloring.continuity.intra_shot_canonical import (
    MAX_PROPOSAL_REVIEW_BATCH,
    PROPOSAL_DECISIONS,
    event_review_basis_hash,
    proposal_batch_basis_hash,
    proposal_review_basis_hash,
    proposal_storage,
)
from soloring.continuity.intra_shot_service import (
    _draft_from_row,
    _load_active_rows,
    _load_shot,
    validate_prospective_event_set,
)
from soloring.db.timeutil import DB_NOW_SQL
from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.domain.ids import new_uuid
from soloring.errors import ErrorCode, SoloRingError, validation_error

NOW_SQL = DB_NOW_SQL


def _conflict(code, message, **details) -> SoloRingError:
    return SoloRingError(code, message, status_code=409, details=details)


# --------------------------------------------------------------------------
# Connection-scoped owning-domain transition helpers (§13)
# --------------------------------------------------------------------------

async def _active_transition(conn: AsyncConnection, table: str, column: str,
                             target_id: str, shot_id: str):
    """Feature/PI transitions carry operation/value_json/value_hash;
    relation transitions carry state — per-domain column shapes."""
    if table == "continuity_relation_transitions":
        cols = "id, NULL AS operation, state, NULL AS value_json, "             "NULL AS value_hash"
    else:
        cols = "id, operation, NULL AS state, value_json, value_hash"
    return (await conn.execute(text(
        f"SELECT {cols} FROM "
        f"{table} WHERE {column} = :t AND anchor_type = 'shot' AND "
        f"anchor_id = :s AND boundary = 'end' AND deleted_at IS NULL"),
        {"t": target_id, "s": shot_id})).fetchall()


async def adopt_feature_transition(conn: AsyncConnection, *, feature_id: str,
                                   shot_id: str, operation: str,
                                   value_json: str | None,
                                   value_hash: str | None) -> str:
    """Create-or-exact-match convergence for an entity-feature Shot/end
    handoff INSIDE the caller's transaction. A different occupied value
    conflicts and is never overwritten."""
    rows = await _active_transition(
        conn, "continuity_feature_transitions", "feature_id", feature_id,
        shot_id)
    if rows:
        row = rows[0]
        if (row.operation != operation or row.value_json != value_json
                or row.value_hash != value_hash):
            raise _conflict(
                ErrorCode.INTRA_SHOT_HANDOFF_MISMATCH,
                "active Shot/end transition holds a different value",
                feature_id=feature_id)
        return row.id
    tid = new_uuid()
    await conn.execute(text(
        "INSERT INTO continuity_feature_transitions (id, feature_id, "
        "anchor_type, anchor_id, boundary, operation, value_json, "
        f"value_hash, created_at, updated_at) VALUES (:id, :f, 'shot', "
        f":s, 'end', :op, :vj, :vh, {NOW_SQL}, {NOW_SQL})"),
        {"id": tid, "f": feature_id, "s": shot_id, "op": operation,
         "vj": value_json, "vh": value_hash})
    return tid


async def adopt_pi_feature_transition(conn: AsyncConnection, *,
                                      feature_id: str, shot_id: str,
                                      operation: str,
                                      value_json: str | None,
                                      value_hash: str | None) -> str:
    rows = await _active_transition(
        conn, "production_instance_feature_transitions", "feature_id",
        feature_id, shot_id)
    if rows:
        row = rows[0]
        if (row.operation != operation or row.value_json != value_json
                or row.value_hash != value_hash):
            raise _conflict(
                ErrorCode.INTRA_SHOT_HANDOFF_MISMATCH,
                "active Production Instance Shot/end transition holds a "
                "different value", feature_id=feature_id)
        return row.id
    tid = new_uuid()
    await conn.execute(text(
        "INSERT INTO production_instance_feature_transitions (id, "
        "feature_id, anchor_type, anchor_id, boundary, operation, "
        f"value_json, value_hash, created_at, updated_at) VALUES (:id, "
        f":f, 'shot', :s, 'end', :op, :vj, :vh, {NOW_SQL}, {NOW_SQL})"),
        {"id": tid, "f": feature_id, "s": shot_id, "op": operation,
         "vj": value_json, "vh": value_hash})
    return tid


async def adopt_relation_transition(conn: AsyncConnection, *, relation_id: str,
                                    shot_id: str, state: str) -> str:
    rows = await _active_transition(
        conn, "continuity_relation_transitions", "relation_id", relation_id,
        shot_id)
    if rows:
        if rows[0].state != state:
            raise _conflict(
                ErrorCode.INTRA_SHOT_HANDOFF_MISMATCH,
                "active relation Shot/end transition holds a different "
                "state", relation_id=relation_id)
        return rows[0].id
    tid = new_uuid()
    await conn.execute(text(
        "INSERT INTO continuity_relation_transitions (id, relation_id, "
        f"anchor_type, anchor_id, boundary, state, created_at, "
        f"updated_at) VALUES (:id, :r, 'shot', :s, 'end', :st, "
        f"{NOW_SQL}, {NOW_SQL})"),
        {"id": tid, "r": relation_id, "s": shot_id, "st": state})
    return tid


async def _adopt_handoff(conn: AsyncConnection, *, kind: str,
                         target_id: str, shot_id: str,
                         terminal_state: dict) -> str:
    if kind == "entity_relation":
        return await adopt_relation_transition(
            conn, relation_id=target_id, shot_id=shot_id,
            state=("active" if terminal_state["active"] else "inactive"))
    operation = "set" if terminal_state.get("present") else "clear"
    value_json = (json.dumps(terminal_state["value"],
                             separators=(",", ":"), sort_keys=True,
                             ensure_ascii=False)
                  if operation == "set" else None)
    value_hash = terminal_state.get("value_hash") if operation == "set" \
        else None
    if kind == "entity_feature":
        return await adopt_feature_transition(
            conn, feature_id=target_id, shot_id=shot_id,
            operation=operation, value_json=value_json,
            value_hash=value_hash)
    return await adopt_pi_feature_transition(
        conn, feature_id=target_id, shot_id=shot_id, operation=operation,
        value_json=value_json, value_hash=value_hash)


# --------------------------------------------------------------------------
# Semantic evidence helpers
# --------------------------------------------------------------------------

def _handoff_semantic_hash(kind: str, target_id: str, shot_id: str,
                           terminal_state: dict) -> str:
    from soloring.continuity.intra_shot_canonical import (
        feature_handoff_value,
        relation_handoff_value,
    )

    if kind == "entity_relation":
        semantic = relation_handoff_value(
            relation_id=target_id, shot_id=shot_id,
            state=("active" if terminal_state["active"] else "inactive"))
    else:
        semantic = feature_handoff_value(
            domain=kind, target_kind=kind, target_id=target_id,
            shot_id=shot_id,
            operation=("set" if terminal_state.get("present") else "clear"),
            state=terminal_state)
    return canonical_hash(semantic)


async def _current_event_set(conn, shot) -> str | None:
    rows = await _load_active_rows(conn, shot.id)
    if not rows:
        return None
    from soloring.continuity.intra_shot_canonical import (
        event_set_hash as compute,
    )

    docs = [json.loads(r.event_json) for r in rows]
    return compute(shot_id=shot.id, duration_ms=shot.duration_ms,
                   events=docs)


async def _last_captured_hash(conn, shot_id: str) -> str | None:
    return (await conn.execute(text(
        "SELECT snapshot_hash FROM shot_revisions WHERE shot_id = :s "
        "ORDER BY revision_number DESC LIMIT 1"),
        {"s": shot_id})).scalar_one_or_none()


async def _working_pin(conn, shot, event_set: str | None) -> str:
    """The §7.5.1 working-hash commitment for DIRECT reviews: the last
    certified authority basis (the most recent ShotRevision hash); when
    no capture exists yet, the current event-set hash stands in as the
    pre-adoption authority pin (the M16-blocked working hash is by
    definition unavailable — that is what adoption fixes). The pin is
    recorded in the basis and verified by recovery from the record."""
    captured = await _last_captured_hash(conn, shot.id)
    if captured is not None:
        return captured
    if event_set is not None:
        return event_set
    from soloring.domain.canonical import canonical_hash as _h

    return _h({"pre_adoption_empty_basis": shot.id})


async def _review_result_still_valid(conn, op: dict,
                                     row_transition_ids=()) -> bool:
    """Exact-retry guard (frozen §12.4): every recorded result EVENT
    must still carry the committed hash, and every recorded result
    TRANSITION must still exist with the committed semantic value. A
    later edit or tombstone of either is drift, never false success."""
    result = op.get("result") or {}
    if not result:
        return True
    return await _result_entry_valid(conn, result, row_transition_ids)


async def _result_entry_valid(conn, result: dict,
                              row_transition_ids=()) -> bool:
    from soloring.continuity.intra_shot_canonical import (
        feature_handoff_value,
        relation_handoff_value,
    )
    from soloring.domain.canonical import canonical_hash as _h

    eid = result.get("event_id")
    if eid:
        row = (await conn.execute(text(
            "SELECT event_hash FROM shot_intra_shot_events "
            "WHERE id = :e AND deleted_at IS NULL"),
            {"e": eid})).first()
        if row is None or row.event_hash != result.get("event_hash"):
            return False
    tr = result.get("transition") or {}
    if not tr:
        return True
    kind = tr.get("kind")
    tid = tr.get("id") or (row_transition_ids[0]
                           if row_transition_ids else None)
    if not tid or not kind:
        return False
    if kind == "entity_relation":
        rows = (await conn.execute(text(
            "SELECT relation_id, anchor_id, anchor_type, boundary, "
            "state FROM continuity_relation_transitions WHERE id = :t "
            "AND deleted_at IS NULL"), {"t": tid})).fetchall()
        if not rows:
            return False  # tombstoned or deleted
        if (rows[0].anchor_type != "shot"
                or rows[0].boundary != "end"):
            return False  # re-anchored off the Shot/end boundary
        semantic = relation_handoff_value(
            relation_id=rows[0].relation_id, shot_id=rows[0].anchor_id,
            state=rows[0].state)
        return _h(semantic) == tr.get("semantic_hash")
    table = {
        "entity_feature": "continuity_feature_transitions",
        "production_instance_feature":
            "production_instance_feature_transitions",
    }.get(kind)
    if table is None:
        return False
    rows = (await conn.execute(text(
        f"SELECT feature_id, anchor_id, anchor_type, boundary, "
        f"operation, value_json, value_hash FROM {table} WHERE id = :t "
        f"AND deleted_at IS NULL"),
        {"t": tid})).fetchall()
    if not rows:
        return False  # tombstoned or deleted
    if (rows[0].anchor_type != "shot"
            or rows[0].boundary != "end"):
        return False  # re-anchored off the Shot/end boundary
    row = rows[0]
    if row.operation == "set":
        if row.value_json is None or row.value_hash is None:
            return False
        state = {"present": True, "value": json.loads(row.value_json),
                 "value_hash": row.value_hash}
    else:
        state = {"present": False}
    semantic = feature_handoff_value(
        domain=kind, target_kind=kind, target_id=row.feature_id,
        shot_id=row.anchor_id, operation=row.operation, state=state)
    return _h(semantic) == tr.get("semantic_hash")


async def _probe_review(conn, basis: str):
    return (await conn.execute(text(
        "SELECT id, operation_json, operation_hash FROM "
        "persistent_consequence_reviews WHERE review_basis_hash = :b"),
        {"b": basis})).first()


async def _probe_event_review(conn, *, event_id: str, source_hash: str,
                              decision: str):
    """Locate a direct event review by its IMMUTABLE source tuple —
    (source event, source hash, decision) is unique under
    uq_pcr_event_source_hash and depends on nothing about today's
    state (§12.4: current state never masks an exact retry)."""
    return (await conn.execute(text(
        "SELECT id, operation_json, operation_hash FROM "
        "persistent_consequence_reviews WHERE source_event_id = :e "
        "AND source_hash = :h AND decision = :d"),
        {"e": event_id, "h": source_hash, "d": decision})).first()


async def _row_transition_ids(conn, review_id) -> tuple:
    """The committed result-transition ids recorded on a review row."""
    row = (await conn.execute(text(
        "SELECT entity_feature_transition_id, "
        "entity_relation_transition_id, "
        "production_instance_feature_transition_id FROM "
        "persistent_consequence_reviews WHERE id = :r"),
        {"r": review_id})).first()
    if row is None:
        return ()
    return tuple(tid for tid in (row[0], row[1], row[2]) if tid)


def _basis_result(op: dict, *, review_id=None, operation_hash=None,
                  transition_ids=()) -> dict:
    out = {
        "idempotent": True,
        "review_id": review_id or op.get("review_id"),
        "operation_hash": operation_hash or op.get("operation_hash"),
        "review_basis_hash": op.get("review_basis_hash"),
        "batch_basis_hash": op.get("batch_basis_hash"),
        "decision": op.get("decision"),
        "result": op.get("result"),
        "results": op.get("results"),
        "source": op.get("source"),
    }
    # §12.4: the returned evidence carries the committed result
    # transition kind + id + semantic hash when one exists
    result = op.get("result") or {}
    tr = result.get("transition")
    if isinstance(tr, dict) and "id" not in tr:
        if len(transition_ids) == 1:
            merged = dict(tr)
            merged["id"] = transition_ids[0]
            merged_result = dict(result)
            merged_result["transition"] = merged
            out["result"] = merged_result
    return out


def _evidence_result(op: dict, *, review_id=None, operation_hash=None,
                     tids=()) -> dict:
    """Committed per-member batch evidence (§12.4): the recorded result
    with the transition id and the review/operation identities merged
    in, so an exact retry returns the complete committed evidence."""
    result = dict(op.get("result") or {})
    tr = result.get("transition")
    if isinstance(tr, dict) and "id" not in tr and tids:
        result["transition"] = {**tr, "id": tids[0]}
    if review_id is not None:
        result["review_id"] = review_id
    if operation_hash is not None:
        result["operation_hash"] = operation_hash
    return result


async def _insert_review(conn, *, review_id: str, shot_id: str,
                         source_kind: str, source_event_id, source_proposal_id,
                         source_hash: str, decision: str, basis: str,
                         result_event_id, ef_t, er_t, pf_t,
                         op: dict) -> None:
    from sqlalchemy.exc import IntegrityError

    op_json = canonical_json_str(op)
    try:
        await _insert_review_row(
            conn, review_id=review_id, shot_id=shot_id,
            source_kind=source_kind, source_event_id=source_event_id,
            source_proposal_id=source_proposal_id,
            source_hash=source_hash, decision=decision, basis=basis,
            result_event_id=result_event_id, ef_t=ef_t, er_t=er_t,
            pf_t=pf_t, op_json=op_json, op_hash=canonical_hash(op))
    except IntegrityError:
        # one immutable source hash cannot acquire competing decisive
        # reviews (the partial unique index) — the typed conflict
        raise _conflict(
            ErrorCode.INTRA_SHOT_REVIEW_CONFLICT,
            "this source hash already has a decisive review")


async def _insert_review_row(conn, *, review_id: str, shot_id: str,
                             source_kind: str, source_event_id,
                             source_proposal_id, source_hash: str,
                             decision: str, basis: str, result_event_id,
                             ef_t, er_t, pf_t, op_json: str,
                             op_hash: str) -> None:
    await conn.execute(text(
        "INSERT INTO persistent_consequence_reviews "
        "(id, shot_id, source_kind, source_event_id, "
        "source_proposal_id, source_hash, decision, review_basis_hash, "
        "result_event_id, entity_feature_transition_id, "
        "entity_relation_transition_id, "
        "production_instance_feature_transition_id, operation_json, "
        f"operation_hash, created_at) VALUES (:rid, :s, :sk, :se, :sp, "
        f":sh, :d, :bh, :re, :ef, :er, :pf, :oj, :oh, {NOW_SQL})"),
        {"rid": review_id, "s": shot_id, "sk": source_kind,
         "se": source_event_id, "sp": source_proposal_id,
         "sh": source_hash, "d": decision, "bh": basis,
         "re": result_event_id, "ef": ef_t, "er": er_t, "pf": pf_t,
         "oj": op_json, "oh": op_hash})


def _insert_event_sql(d: dict, event_id: str, shot_id: str,
                      source_kind: str, source_proposal_id):
    sql = (
        "INSERT INTO shot_intra_shot_events "
        "(id, shot_id, time_ms, ordinal, target_kind, entity_feature_id, "
        "entity_relation_id, production_instance_feature_id, "
        "before_state_json, before_state_hash, after_state_json, "
        "after_state_hash, persistence_mode, source_kind, "
        "source_proposal_id, event_json, event_hash, created_at, "
        f"updated_at) VALUES (:id,:shot,:t,:o,:tk,:ef,:er,:pf,:bj,:bh,"
        f":aj,:ah,:pm,:sk,:sp,:ej,:eh,{NOW_SQL},{NOW_SQL})")
    params = {"id": event_id, "shot": shot_id, "t": d["time_ms"],
              "o": d["ordinal"], "tk": d["target_kind"],
              "ef": d["target_id"] if d["target_kind"] == "entity_feature"
              else None,
              "er": d["target_id"] if d["target_kind"] == "entity_relation"
              else None,
              "pf": (d["target_id"]
                     if d["target_kind"] == "production_instance_feature"
                     else None),
              "bj": d["before_json"], "bh": d["before_hash"],
              "aj": d["after_json"], "ah": d["after_hash"],
              "pm": d["persistence_mode"], "sk": source_kind,
              "sp": source_proposal_id, "ej": d["event_json"],
              "eh": d["event_hash"]}
    return sql, params


# --------------------------------------------------------------------------
# Direct event adopt / decline (§12.1 / §12.2)
# --------------------------------------------------------------------------

async def adopt_event_persistence(session: AsyncSession, event_id: str, *,
                                  expected_event_hash: str,
                                  expected_event_set_hash: str
                                  ) -> dict:
    from soloring.continuity.intra_shot_service import _event_row

    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            row = await _event_row(conn, event_id)
            shot = await _load_shot(conn, row.shot_id)
            # §12.4: same tuple-first rule as decline — the committed
            # review is located from the immutable request source tuple
            # before any current-state gate, so unrelated event-set
            # evolution or a later capture cannot mask an exact retry;
            # current state only certifies recorded-result drift
            existing = await _probe_event_review(
                conn, event_id=event_id, source_hash=expected_event_hash,
                decision="adopt_persistence")
            if existing is not None:
                op = json.loads(existing.operation_json)
                if (op.get("expected_event_set_hash")
                        == expected_event_set_hash):
                    tids = await _row_transition_ids(conn, existing.id)
                    if not await _review_result_still_valid(
                            conn, op, row_transition_ids=tids):
                        raise _conflict(
                            ErrorCode.INTRA_SHOT_REVIEW_CONFLICT,
                            "recorded review result authority drifted")
                    await conn.commit()
                    return _basis_result(
                        op, review_id=existing.id,
                        operation_hash=existing.operation_hash,
                        transition_ids=tids)
                # different request evidence against the same source:
                # fall through to the gates, which conflict honestly
            if row.event_hash != expected_event_hash:
                raise _conflict(
                    ErrorCode.INTRA_SHOT_REVIEW_CONFLICT,
                    "source event hash drifted", event_id=event_id)
            if row.persistence_mode != "require_handoff":
                raise _conflict(
                    ErrorCode.INTRA_SHOT_REVIEW_CONFLICT,
                    "only a require_handoff event can adopt persistence",
                    event_id=event_id)
            ev = _draft_from_row(row)
            doc = ev["stored_event_doc"]
            semantic = _handoff_semantic_hash(
                doc["target"]["kind"], doc["target"]["id"], shot.id,
                doc["after"])
            eh = {
                "target": doc["target"],
                "anchor": {"anchor_type": "shot", "anchor_id": shot.id,
                           "boundary": "end"},
                "semantic_hash": semantic,
            }
            current_set = await _current_event_set(conn, shot)
            if current_set != expected_event_set_hash:
                raise _conflict(
                    ErrorCode.INTRA_SHOT_REVIEW_CONFLICT,
                    "event-set hash drifted")
            working_pin = await _working_pin(conn, shot, current_set)
            basis = event_review_basis_hash(
                source_event_id=event_id, source_hash=expected_event_hash,
                decision="adopt_persistence",
                expected_working_snapshot_hash=working_pin,
                expected_event_set_hash=expected_event_set_hash,
                expected_handoff=eh)
            if shot.scene_id is None:
                raise _conflict(
                    ErrorCode.INTRA_SHOT_HANDOFF_ANCHOR_REQUIRED,
                    "persistent adoption requires a narrative Shot/end "
                    "boundary")
            tid = await _adopt_handoff(
                conn, kind=doc["target"]["kind"],
                target_id=doc["target"]["id"], shot_id=shot.id,
                terminal_state=doc["after"])
            result = {
                "event_id": event_id,
                "event_hash": expected_event_hash,
                "transition": {"kind": doc["target"]["kind"],
                               "semantic_hash": semantic},
            }
            op = {
                "schema_version": 1,
                "source": {"kind": "event", "id": event_id,
                           "hash": expected_event_hash},
                "decision": "adopt_persistence",
                "expected_working_snapshot_hash": working_pin,
                "expected_event_set_hash": expected_event_set_hash,
                "expected_handoff": eh,
                "review_basis_hash": basis,
                "result": result,
            }
            review_id = new_uuid()
            kind = doc["target"]["kind"]
            await _insert_review(
                conn, review_id=review_id, shot_id=shot.id,
                source_kind="event", source_event_id=event_id,
                source_proposal_id=None, source_hash=expected_event_hash,
                decision="adopt_persistence", basis=basis,
                result_event_id=event_id,
                ef_t=tid if kind == "entity_feature" else None,
                er_t=tid if kind == "entity_relation" else None,
                pf_t=(tid if kind == "production_instance_feature"
                      else None), op=op)
            await conn.commit()
            return {
                "idempotent": False, "review_id": review_id,
                "transition_id": tid,
                "review_basis_hash": basis,
                "transition_semantic_hash": semantic,
                "result": result,
            }
        except Exception:
            with contextlib.suppress(Exception):
                await conn.rollback()
            raise


async def decline_event_persistence(session: AsyncSession, event_id: str, *,
                                    expected_event_hash: str,
                                    expected_event_set_hash: str) -> dict:
    from soloring.continuity.intra_shot_service import _event_row

    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            row = await _event_row(conn, event_id)
            shot = await _load_shot(conn, row.shot_id)
            # §12.4: the committed review is located from the immutable
            # REQUEST source tuple BEFORE the pre-decline row-shape
            # gates — the first successful decline flips this same UUID
            # to transient, and a LATER capture moves the working pin,
            # so neither today's row shape nor today's state may gate
            # the probe; current state is only consulted to verify the
            # recorded result authority for drift.
            existing = await _probe_event_review(
                conn, event_id=event_id, source_hash=expected_event_hash,
                decision="decline_persistence")
            if existing is not None:
                op = json.loads(existing.operation_json)
                if (op.get("expected_event_set_hash")
                        == expected_event_set_hash):
                    tids = await _row_transition_ids(conn, existing.id)
                    if not await _review_result_still_valid(
                            conn, op, row_transition_ids=tids):
                        raise _conflict(
                            ErrorCode.INTRA_SHOT_REVIEW_CONFLICT,
                            "recorded review result authority drifted")
                    await conn.commit()
                    return _basis_result(
                        op, review_id=existing.id,
                        operation_hash=existing.operation_hash,
                        transition_ids=tids)
                # different request evidence against the same source:
                # fall through to the gates, which conflict honestly
            if row.event_hash != expected_event_hash:
                raise _conflict(
                    ErrorCode.INTRA_SHOT_REVIEW_CONFLICT,
                    "source event hash drifted", event_id=event_id)
            if row.persistence_mode != "require_handoff":
                raise _conflict(
                    ErrorCode.INTRA_SHOT_REVIEW_CONFLICT,
                    "only an unreviewed require_handoff event can be "
                    "declined", event_id=event_id)
            current_set0 = await _current_event_set(conn, shot)
            working_pin = await _working_pin(conn, shot, current_set0)
            basis = event_review_basis_hash(
                source_event_id=event_id, source_hash=expected_event_hash,
                decision="decline_persistence",
                expected_working_snapshot_hash=working_pin,
                expected_event_set_hash=expected_event_set_hash,
                expected_handoff=None)
            current_set = await _current_event_set(conn, shot)
            if current_set != expected_event_set_hash:
                raise _conflict(
                    ErrorCode.INTRA_SHOT_REVIEW_CONFLICT,
                    "event-set hash drifted")
            # the decline PATCH must recompute the canonical event
            # document + hash (persistence_mode is semantic)
            rows = await _load_active_rows(conn, shot.id)
            drafts = []
            for r in rows:
                d = _draft_from_row(r)
                if d["id"] == event_id:
                    d["persistence_mode"] = "transient"
                    d.pop("stored", None)
                    d.pop("stored_event_doc", None)
                drafts.append(d)
            validated = await validate_prospective_event_set(
                conn, shot, drafts)
            d2 = next(d for d in validated["events"]
                      if d["id"] == event_id)
            await conn.execute(text(
                "UPDATE shot_intra_shot_events SET persistence_mode = "
                "'transient', event_json = :ej, event_hash = :eh, "
                f"updated_at={NOW_SQL} WHERE id = :e"),
                {"ej": d2["event_json"], "eh": d2["event_hash"],
                 "e": event_id})
            fresh = d2["event_hash"]
            result = {"event_id": event_id, "event_hash": fresh}
            op = {
                "schema_version": 1,
                "source": {"kind": "event", "id": event_id,
                           "hash": expected_event_hash},
                "decision": "decline_persistence",
                "expected_working_snapshot_hash": working_pin,
                "expected_event_set_hash": expected_event_set_hash,
                "expected_handoff": None,
                "review_basis_hash": basis,
                "result": result,
            }
            review_id = new_uuid()
            await _insert_review(
                conn, review_id=review_id, shot_id=shot.id,
                source_kind="event", source_event_id=event_id,
                source_proposal_id=None, source_hash=expected_event_hash,
                decision="decline_persistence", basis=basis,
                result_event_id=event_id, ef_t=None, er_t=None, pf_t=None,
                op=op)
            await conn.commit()
            return {"idempotent": False, "review_id": review_id,
                    "resulting_event_hash": fresh,
                    "review_basis_hash": basis, "result": result}
        except Exception:
            with contextlib.suppress(Exception):
                await conn.rollback()
            raise


# --------------------------------------------------------------------------
# Proposal ingestion (§11.1)
# --------------------------------------------------------------------------

async def ingest_proposal(session: AsyncSession, shot_id: str, payload) -> dict:
    body = (payload.model_dump(exclude_unset=True)
            if hasattr(payload, "model_dump") else dict(payload))
    pid = new_uuid()
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            shot = await _load_shot(conn, shot_id)
            source_kind = body["source_kind"]
            source_rev = body["source_shot_revision_id"]
            source_hash = body["source_shot_revision_hash"]
            row = (await conn.execute(text(
                "SELECT snapshot_hash FROM shot_revisions "
                "WHERE id = :r"), {"r": source_rev})).first()
            if row is None or row.snapshot_hash != source_hash:
                raise _conflict(
                    ErrorCode.INTRA_SHOT_PROPOSAL_STALE,
                    "source ShotRevision pin mismatch",
                    source_shot_revision_id=source_rev)
            snap = json.loads((await conn.execute(text(
                "SELECT snapshot_json FROM shot_revisions WHERE id = :r"),
                {"r": source_rev})).scalar_one())
            gen_id = take_id = None
            if source_kind == "generation":
                gen_id = body.get("source_generation_id")
                if not gen_id:
                    raise validation_error(
                        "generation proposals require "
                        "source_generation_id")
                g = (await conn.execute(text(
                    "SELECT shot_id, shot_revision_id FROM generations "
                    "WHERE id = :g"), {"g": gen_id})).first()
                if g is None or g.shot_id != shot_id \
                        or g.shot_revision_id != source_rev:
                    raise _conflict(
                        ErrorCode.INTRA_SHOT_PROPOSAL_STALE,
                        "Generation lineage mismatch")
            elif source_kind == "take":
                gen_id = body.get("source_generation_id")
                take_id = body.get("source_take_id")
                if not gen_id or not take_id:
                    raise validation_error(
                        "take proposals require source_generation_id "
                        "and source_take_id")
                t = (await conn.execute(text(
                    "SELECT g.shot_id, g.shot_revision_id, "
                    "g.id AS gen_id FROM takes t JOIN generations g ON "
                    "g.id = t.generation_id WHERE t.id = :t"),
                    {"t": take_id})).first()
                if (t is None or t.shot_id != shot_id
                        or t.shot_revision_id != source_rev
                        or t.gen_id != gen_id):
                    raise _conflict(
                        ErrorCode.INTRA_SHOT_PROPOSAL_STALE,
                        "Take lineage mismatch")
            elif source_kind == "imported":
                if body.get("source_generation_id") or body.get(
                        "source_take_id"):
                    raise validation_error(
                        "imported proposals carry no Generation/Take ids")
            else:
                raise validation_error("unknown proposal source kind")
            proposer = body["proposer_kind"]
            analyzer_id = analyzer_version = analyzer_hash = None
            if proposer == "analyzer":
                analyzer_id = body.get("analyzer_id")
                analyzer_version = body.get("analyzer_version")
                analyzer_hash = body.get("analyzer_parameters_hash")
                if not analyzer_id or not analyzer_version \
                        or not analyzer_hash:
                    raise validation_error(
                        "analyzer proposals require exact id/version/"
                        "parameter hash")
            value, pj, ph = proposal_storage(
                candidate_event=body["candidate_event"],
                persistence_suggestion=body["persistence_suggestion"])
            duration = snap.get("intent", {}).get("duration_ms")
            t = body["candidate_event"]["time_ms"]
            if not isinstance(duration, int) or not 1 <= t < duration:
                raise _conflict(
                    ErrorCode.INTRA_SHOT_PROPOSAL_STALE,
                    "proposal time is not interior to the captured "
                    "source duration")
            await conn.execute(text(
                "INSERT INTO shot_intra_shot_event_proposals "
                "(id, shot_id, source_kind, source_shot_revision_id, "
                "source_shot_revision_hash, source_generation_id, "
                "source_take_id, proposer_kind, analyzer_id, "
                "analyzer_version, analyzer_parameters_hash, "
                "proposal_json, proposal_hash, created_at) VALUES (:id, "
                f":s, :sk, :r, :h, :g, :t, :pk, :ai, :av, :ah, :pj, "
                f":ph, {NOW_SQL})"),
                {"id": pid, "s": shot_id, "sk": source_kind,
                 "r": source_rev, "h": source_hash, "g": gen_id,
                 "t": take_id, "pk": proposer, "ai": analyzer_id,
                 "av": analyzer_version, "ah": analyzer_hash,
                 "pj": pj, "ph": ph})
            await conn.commit()
            return {"id": pid, "proposal_hash": ph,
                    "source_shot_revision_id": source_rev}
        except Exception:
            with contextlib.suppress(Exception):
                await conn.rollback()
            raise


async def list_proposals(session: AsyncSession, shot_id: str, *,
                         cursor: int = 0, limit: int = 100) -> dict:
    if type(cursor) is not int or cursor < 0:
        raise validation_error("cursor must be a nonnegative integer")
    limit = max(1, min(500, limit))
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN")
        try:
            await _load_shot(conn, shot_id)
            rows = (await conn.execute(text(
                "SELECT id, source_kind, source_shot_revision_id, "
                "source_shot_revision_hash, source_generation_id, "
                "source_take_id, proposer_kind, analyzer_id, "
                "analyzer_version, analyzer_parameters_hash, "
                "proposal_json, proposal_hash, created_at FROM "
                "shot_intra_shot_event_proposals WHERE shot_id = :s "
                "ORDER BY created_at, id LIMIT :lim OFFSET :cur"),
                {"s": shot_id, "lim": limit + 1, "cur": cursor})).fetchall()
            more = len(rows) > limit
            rows = rows[:limit]
            out = []
            for r in rows:
                doc = json.loads(r.proposal_json)
                review = (await conn.execute(text(
                    "SELECT decision FROM "
                    "persistent_consequence_reviews WHERE "
                    "source_proposal_id = :p"), {"p": r.id})).first()
                out.append({
                    "id": r.id, "source_kind": r.source_kind,
                    "source_shot_revision_id": r.source_shot_revision_id,
                    "source_shot_revision_hash":
                        r.source_shot_revision_hash,
                    "source_generation_id": r.source_generation_id,
                    "source_take_id": r.source_take_id,
                    "proposer_kind": r.proposer_kind,
                    "analyzer_id": r.analyzer_id,
                    "analyzer_version": r.analyzer_version,
                    "analyzer_parameters_hash":
                        r.analyzer_parameters_hash,
                    "candidate_event": doc["candidate_event"],
                    "persistence_suggestion":
                        doc["persistence_suggestion"],
                    "proposal_hash": r.proposal_hash,
                    "created_at": r.created_at,
                    "review_decision": review.decision if review else None,
                })
            await conn.commit()
            return {"shot_id": shot_id, "proposals": out,
                    "next_cursor": cursor + limit if more else None}
        except Exception:
            with contextlib.suppress(Exception):
                await conn.rollback()
            raise


# --------------------------------------------------------------------------
# Proposal review — single is a one-item batch (§12.3)
# --------------------------------------------------------------------------

async def _proposal_shot(session: AsyncSession, proposal_id: str) -> str:
    """Resolve a proposal's Shot for the single-review convenience route."""
    from soloring.errors import not_found

    if not isinstance(proposal_id, str) or not proposal_id:
        raise not_found(ErrorCode.INTRA_SHOT_TARGET_INVALID,
                        "proposal id required")
    from sqlalchemy import text as _text

    async with session.bind.connect() as conn:
        row = (await conn.execute(_text(
            "SELECT shot_id FROM shot_intra_shot_event_proposals "
            "WHERE id = :p"), {"p": proposal_id})).first()
    if row is None:
        raise not_found(ErrorCode.INTRA_SHOT_TARGET_INVALID,
                        f"proposal {proposal_id!r} not found")
    return row.shot_id


async def review_proposals(session: AsyncSession, shot_id: str,
                           reviews: list[dict]) -> dict:
    if not reviews or len(reviews) > MAX_PROPOSAL_REVIEW_BATCH:
        raise validation_error(
            "proposal review batch must contain 1..10,000 reviews")
    for r in reviews:
        if r.get("decision") not in PROPOSAL_DECISIONS:
            raise validation_error("invalid proposal review decision")
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            shot = await _load_shot(conn, shot_id)
            authority = [r for r in reviews if r["decision"] != "ignore"]
            # one source ShotRevision per ATOMIC batch. §7.5.2 gives the
            # batch object a single source coordinate pair, and the
            # certified C-recovery source-coherence invariant requires it
            # to equal EVERY member proposal's own pinned source — a
            # stale proposal (ignored or not) is reviewed in its own
            # batch, never mixed into a current-authority batch.
            pins: set[tuple[str, str]] = set()
            specs = []
            for r in reviews:
                row = (await conn.execute(text(
                    "SELECT shot_id, source_shot_revision_id, "
                    "source_shot_revision_hash, proposal_json, "
                    "proposal_hash FROM "
                    "shot_intra_shot_event_proposals WHERE id = :p"),
                    {"p": r["proposal_id"]})).first()
                if row is None or row.shot_id != shot_id:
                    raise _conflict(
                        ErrorCode.INTRA_SHOT_PROPOSAL_STALE,
                        "proposal missing or foreign",
                        proposal_id=r["proposal_id"])
                if row.proposal_hash != r["expected_proposal_hash"]:
                    raise _conflict(
                        ErrorCode.INTRA_SHOT_PROPOSAL_STALE,
                        "proposal hash drifted",
                        proposal_id=r["proposal_id"])
                pins.add((row.source_shot_revision_id,
                          row.source_shot_revision_hash))
                specs.append((r, row))
            if len(pins) != 1:
                raise _conflict(
                    ErrorCode.INTRA_SHOT_PROPOSAL_STALE,
                    "proposals in one atomic batch must share one source "
                    "ShotRevision; review a stale proposal separately")
            source_rev, source_hash = next(iter(pins))
            # §12.3 batch-retry convergence FIRST: if every member
            # already has a committed review sharing ONE batch basis
            # and the recorded results are still valid, return the
            # exact committed evidence — a later working-state change
            # must not mask an idempotent retry
            committed = []
            for r in reviews:
                row = (await conn.execute(text(
                    "SELECT id, operation_json, operation_hash FROM "
                    "persistent_consequence_reviews WHERE "
                    "source_proposal_id = :p AND source_hash = :h AND "
                    "decision = :d"),
                    {"p": r["proposal_id"],
                     "h": r["expected_proposal_hash"],
                     "d": r["decision"]})).first()
                committed.append(row)
            if any(c is not None for c in committed) and not all(
                    c is not None for c in committed):
                # §12.4: a committed batch missing persisted member rows
                # is invariant corruption — the retry must conflict,
                # never repair the batch by recreating the missing rows
                # through the per-member path
                partial_incoming = {
                    (r["proposal_id"], r["expected_proposal_hash"],
                     r["decision"]) for r in reviews}
                for c in committed:
                    if c is None:
                        continue
                    c_op = json.loads(c.operation_json)
                    c_recorded = (c_op.get("batch_basis") or {}
                                  ).get("reviews") or []
                    c_recorded_set = {
                        (x["proposal_id"], x["proposal_hash"],
                         x["decision"]) for x in c_recorded}
                    if partial_incoming <= c_recorded_set:
                        raise _conflict(
                            ErrorCode.INTRA_SHOT_REVIEW_CONFLICT,
                            "a committed batch is missing persisted "
                            "review rows — corruption, not a retry")
            if all(c is not None for c in committed):
                ops = [json.loads(c.operation_json) for c in committed]
                bases = {op.get("batch_basis_hash") for op in ops}
                if len(bases) == 1:
                    # §12.4 completeness: the recorded batch doc names
                    # the ENTIRE committed member set under this basis.
                    # A strict subset of a committed batch is corruption,
                    # never a retry; a superset is simply a different
                    # batch and falls through to normal processing.
                    recorded = (ops[0].get("batch_basis") or {}
                                ).get("reviews") or []
                    recorded_set = {
                        (x["proposal_id"], x["proposal_hash"],
                         x["decision"]) for x in recorded}
                    incoming_set = {
                        (r["proposal_id"], r["expected_proposal_hash"],
                         r["decision"]) for r in reviews}
                    if incoming_set < recorded_set:
                        raise _conflict(
                            ErrorCode.INTRA_SHOT_REVIEW_CONFLICT,
                            "a strict subset of a committed batch is "
                            "corruption, not a retry")
                    if incoming_set == recorded_set:
                        for pid, phash, dec in recorded_set:
                            member = (await conn.execute(text(
                                "SELECT 1 FROM "
                                "persistent_consequence_reviews WHERE "
                                "source_proposal_id = :p AND "
                                "source_hash = :h AND decision = :d"),
                                {"p": pid, "h": phash,
                                 "d": dec})).first()
                            if member is None:
                                raise _conflict(
                                    ErrorCode.INTRA_SHOT_REVIEW_CONFLICT,
                                    "a recorded batch member is no "
                                    "longer committed")
                        results = {}
                        for c, op in zip(committed, ops):
                            tids = await _row_transition_ids(conn, c.id)
                            if not await _review_result_still_valid(
                                    conn, op, row_transition_ids=tids):
                                raise _conflict(
                                    ErrorCode.INTRA_SHOT_REVIEW_CONFLICT,
                                    "recorded review result authority "
                                    "drifted")
                            results[op["source"]["id"]] = _evidence_result(
                                op, review_id=c.id,
                                operation_hash=c.operation_hash,
                                tids=tids)
                        await conn.commit()
                        first = ops[0]
                        return {
                            "idempotent": True,
                            "batch_basis_hash":
                                first.get("batch_basis_hash"),
                            "results": results,
                            "source": first.get("source"),
                        }
            # §12.3: the source-basis equality check runs ONCE at
            # transaction start, before any mutation. NULL current
            # working hash (M16-blocked) is stale for authority.
            working = None
            if authority:
                recorded = (await conn.execute(text(
                    "SELECT snapshot_hash FROM shot_revisions "
                    "WHERE id = :r"), {"r": source_rev})).scalar_one()
                from soloring.domain.shots import read_shot_detail

                detail = await read_shot_detail(
                    session.bind, shot_id)
                working = detail[4]
                if working is None or working != recorded:
                    raise _conflict(
                        ErrorCode.INTRA_SHOT_PROPOSAL_STALE,
                        "current working hash does not equal the shared "
                        "source basis")
            batch_reviews = [{
                "proposal_id": r["proposal_id"],
                "proposal_hash": r["expected_proposal_hash"],
                "decision": r["decision"],
            } for r in reviews]
            # the event set over existing events only; None when the
            # Shot has no active events (§7.5.2 allows the None basis)
            existing_rows = await _load_active_rows(conn, shot_id)
            event_set = None
            if existing_rows:
                current = await validate_prospective_event_set(
                    conn, shot, [_draft_from_row(r) for r in
                                 existing_rows])
                event_set = current["event_set_hash"]
            batch_basis = proposal_batch_basis_hash(
                shot_id=shot_id, source_shot_revision_id=source_rev,
                source_shot_revision_hash=source_hash,
                expected_working_snapshot_hash=working,
                expected_event_set_hash=event_set,
                reviews=batch_reviews)
            batch_doc = {
                "shot_id": shot_id,
                "source_shot_revision_id": source_rev,
                "source_shot_revision_hash": source_hash,
                # §7.5.2 nullable basis values are recorded as JSON null,
                # byte-verbatim with the hashed basis inputs — C recovery
                # recomputes the batch root from this doc, and "" is not
                # a legal hash in the frozen grammar
                "expected_working_snapshot_hash": working,
                "expected_event_set_hash": event_set,
                "reviews": batch_reviews,
            }
            new_drafts = []
            plan = []
            for r, row in specs:
                candidate = json.loads(row.proposal_json)[
                    "candidate_event"]
                decision = r["decision"]
                basis = proposal_review_basis_hash(
                    batch_basis_hash=batch_basis,
                    proposal_id=r["proposal_id"],
                    proposal_hash=r["expected_proposal_hash"],
                    decision=decision)
                retry = await _probe_review(conn, basis)
                if retry is not None:
                    op = json.loads(retry.operation_json)
                    tids = await _row_transition_ids(conn, retry.id)
                    if not await _review_result_still_valid(
                            conn, op, row_transition_ids=tids):
                        raise _conflict(
                            ErrorCode.INTRA_SHOT_REVIEW_CONFLICT,
                            "recorded review result authority drifted")
                    plan.append((r, row, basis, None, {
                        "op": op, "review_id": retry.id,
                        "operation_hash": retry.operation_hash,
                        "tids": tids}))
                    continue
                if decision == "ignore":
                    plan.append((r, row, basis, None, None))
                    continue
                eid = new_uuid()
                persistence = ("require_handoff"
                               if decision == "adopt_persistence"
                               else "transient")
                draft = {
                    "id": eid, "time_ms": candidate["time_ms"],
                    "ordinal": candidate["ordinal"],
                    "target_kind": candidate["target"]["kind"],
                    "target_id": candidate["target"]["id"],
                    "before": candidate["before"],
                    "after": candidate["after"],
                    "persistence_mode": persistence,
                    "source_kind": "proposal_adoption",
                    "source_proposal_id": r["proposal_id"],
                }
                new_drafts.append(draft)
                plan.append((r, row, basis, draft, None))
            # the full prospective event set (existing + every selected
            # adopted candidate) validates TOGETHER before any insert
            merged = await validate_prospective_event_set(
                conn, shot,
                [_draft_from_row(r) for r in existing_rows] + new_drafts)
            merged_by_id = {d["id"]: d for d in merged["events"]}
            results = {}
            review_ids = []
            first_source = None
            for r, row, basis, draft, existing in plan:
                if existing is not None:
                    if first_source is None:
                        first_source = existing["op"].get("source")
                    results[r["proposal_id"]] = _evidence_result(
                        existing["op"],
                        review_id=existing["review_id"],
                        operation_hash=existing["operation_hash"],
                        tids=existing["tids"])
                    continue
                decision = r["decision"]
                tid = None
                semantic = None
                eh = None
                if decision == "adopt_persistence":
                    if shot.scene_id is None:
                        raise _conflict(
                            ErrorCode.INTRA_SHOT_HANDOFF_ANCHOR_REQUIRED,
                            "persistent adoption requires a narrative "
                            "Shot/end boundary")
                    semantic = _handoff_semantic_hash(
                        draft["target_kind"], draft["target_id"],
                        shot_id, draft["after"])
                    eh = {
                        "target": {"kind": draft["target_kind"],
                                   "id": draft["target_id"]},
                        "anchor": {"anchor_type": "shot",
                                   "anchor_id": shot_id,
                                   "boundary": "end"},
                        "semantic_hash": semantic,
                    }
                normalized = merged_by_id.get(draft["id"]) if draft \
                    else None
                result = {}
                if draft is not None:
                    sql, params = _insert_event_sql(
                        normalized, draft["id"], shot_id,
                        "proposal_adoption", r["proposal_id"])
                    await conn.execute(text(sql), params)
                    result = {
                        "event_id": draft["id"],
                        "event_hash": normalized["event_hash"],
                    }
                    if decision == "adopt_persistence":
                        tid = await _adopt_handoff(
                            conn, kind=draft["target_kind"],
                            target_id=draft["target_id"], shot_id=shot_id,
                            terminal_state=draft["after"])
                        result["transition"] = {
                            "kind": draft["target_kind"],
                            "semantic_hash": semantic}
                op = {
                    "schema_version": 1,
                    "source": {"kind": "proposal",
                               "id": r["proposal_id"],
                               "hash": r["expected_proposal_hash"]},
                    "decision": decision,
                    "expected_working_snapshot_hash": working,
                    "expected_event_set_hash": event_set,
                    "expected_handoff": eh,
                    "review_basis_hash": basis,
                    "batch_basis_hash": batch_basis,
                    "batch_basis": batch_doc,
                    "result": result,
                }
                kind = draft["target_kind"] if draft else None
                review_id = new_uuid()
                await _insert_review(
                    conn, review_id=review_id, shot_id=shot_id,
                    source_kind="proposal", source_event_id=None,
                    source_proposal_id=r["proposal_id"],
                    source_hash=r["expected_proposal_hash"],
                    decision=decision, basis=basis,
                    result_event_id=result.get("event_id"),
                    ef_t=tid if kind == "entity_feature" and tid else None,
                    er_t=(tid if kind == "entity_relation" and tid
                          else None),
                    pf_t=(tid if kind == "production_instance_feature"
                          and tid else None), op=op)
                review_ids.append(review_id)
                results[r["proposal_id"]] = result
            await conn.commit()
            if not review_ids:
                # every member converged as an exact per-member retry
                return {
                    "idempotent": True,
                    "batch_basis_hash": batch_basis,
                    "results": results,
                    "source": first_source,
                }
            return {
                "idempotent": False,
                "batch_basis_hash": batch_basis,
                "review_ids": review_ids,
                "results": results,
                "event_set_hash": event_set,
            }
        except Exception:
            with contextlib.suppress(Exception):
                await conn.rollback()
            raise
