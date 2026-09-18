"""M16-B shared read-only intra-Shot resolver (frozen R6 §5/§9/§10.1).

The resolver is THE single current-state M16 authority projection consumed
by Shot detail/readiness, the dedicated intra-Shot read, and (in M16-C)
capture. It performs no writes, creates or adopts no transitions, and
never redefines predecessor ``continuity_state_ready``: handoff handling
here is COMPARISON ONLY (adoption is the M16-D slice).

Loading is set-oriented — one query per fact class regardless of the
number of active events (the frozen §5.4 bound is <=20 SQL statements
for 1..10,000 events). Structural authoring violations cannot exist
through M16 APIs; the read path still fails closed by reporting them as
deterministic ``intra_shot_issues``. Genuine storage corruption (stored
canonical columns disagreeing with rebuilt canonical values) raises the
typed internal invariant instead of fabricating readiness.
"""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from soloring.continuity.intra_shot_canonical import (
    MAX_ACTIVE_EVENTS_PER_SHOT,
    event_set_hash,
    event_storage,
    state_storage,
)
from soloring.continuity.intra_shot_service import (
    _draft_from_row,
    _load_shot,
    _params,
)
from soloring.continuity.values import canonicalize_value
from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.errors import ErrorCode, internal_invariant

_ISSUE_ORDER = (
    ErrorCode.INTRA_SHOT_DURATION_REQUIRED,
    ErrorCode.INTRA_SHOT_TIME_OUT_OF_RANGE,
    ErrorCode.INTRA_SHOT_EVENT_COORDINATE_CONFLICT,
    ErrorCode.INTRA_SHOT_EVENT_BEFORE_STATE_MISMATCH,
    ErrorCode.INTRA_SHOT_TARGET_INVALID,
    ErrorCode.INTRA_SHOT_PERSISTENT_EVENT_NOT_TERMINAL,
    ErrorCode.INTRA_SHOT_HANDOFF_ANCHOR_REQUIRED,
    ErrorCode.INTRA_SHOT_HANDOFF_REQUIRED,
    ErrorCode.INTRA_SHOT_HANDOFF_MISMATCH,
)


def _issue(code: ErrorCode, message: str, **details) -> dict:
    # ErrorCode members are plain string attributes
    return {"code": getattr(code, "value", code),
            "message": message, "details": details}


def _code_rank(code: str) -> int:
    for i, member in enumerate(_ISSUE_ORDER):
        if code == getattr(member, "value", member):
            return i
    return len(_ISSUE_ORDER)


async def _load_active_rows_bounded(conn: AsyncConnection, shot_id: str):
    """Bounded active-event load: at most one row over the frozen
    structural ceiling, so corrupt storage can never force unbounded
    materialization through the read path."""
    return (await conn.execute(text(
        "SELECT id, shot_id, time_ms, ordinal, target_kind, "
        "entity_feature_id, entity_relation_id, "
        "production_instance_feature_id, before_state_json, "
        "before_state_hash, after_state_json, after_state_hash, "
        "persistence_mode, source_kind, source_proposal_id, "
        "event_json, event_hash, created_at, updated_at FROM "
        "shot_intra_shot_events WHERE shot_id = :s AND deleted_at IS NULL "
        "ORDER BY time_ms, ordinal "
        "LIMIT :cap"), {"s": shot_id,
                        "cap": MAX_ACTIVE_EVENTS_PER_SHOT + 1})).fetchall()


def _verify_stored_consistency(d: dict) -> None:
    """R6 §5.2 step 4: every duplicated stored event/state field is
    rebuilt and verified against its canonical JSON/hash BEFORE any
    current target-context validation. This is storage self-consistency
    only — it never consults the live schema, so an event whose target
    is no longer a valid current dependency/Production World member can
    still be proven internally consistent (and stay visible) while
    folding/hash/terminalization fail closed. Disagreement is internal
    corruption: typed invariant, never fabricated output."""
    stored = d["stored"]
    before, after = d["before"], d["after"]

    if canonical_json_str(before) != stored.before_state_json or             canonical_hash(before) != stored.before_state_hash:
        raise internal_invariant(
            f"stored intra-Shot event {stored.id} before-state columns "
            "disagree with canonical JSON/hash")
    if canonical_json_str(after) != stored.after_state_json or             canonical_hash(after) != stored.after_state_hash:
        raise internal_invariant(
            f"stored intra-Shot event {stored.id} after-state columns "
            "disagree with canonical JSON/hash")

    event = {
        "schema_version": 1,
        "time_ms": stored.time_ms,
        "ordinal": stored.ordinal,
        "target": {"kind": d["target_kind"], "id": d["target_id"]},
        "before": before,
        "after": after,
        "persistence_mode": stored.persistence_mode,
    }
    if canonical_json_str(event) != stored.event_json or             canonical_hash(event) != stored.event_hash:
        raise internal_invariant(
            f"stored intra-Shot event {stored.id} disagrees with "
            "canonical columns/hash")
    if d["stored_event_doc"] != event:
        raise internal_invariant(
            f"stored intra-Shot event {stored.id} canonical event JSON "
            "disagrees with the reconstructed semantic event")


def _stored_public(d: dict) -> dict:
    """An unresolved-target active event keeps its STORED canonical
    identity (id, canonical event bytes/hash, provenance) in the
    authoritative events list; the resolver refuses to fold, terminalize,
    or hash an unresolved target — it never hides the row."""
    return {
        "id": d["id"],
        **d["stored_event_doc"],
        "event_hash": d["stored"].event_hash,
        "source_kind": d["source_kind"],
        "source_proposal_id": d["source_proposal_id"],
    }


def _event_free(duration_ms) -> dict:
    return {
        "intra_shot_ready": True,
        "intra_shot_issues": [],
        "duration_ms": duration_ms,
        "events": [],
        "terminal_targets": [],
        "handoffs": [],
        "event_set_hash": None,
        "target_identities": {},
    }


async def _transition_rows(conn: AsyncConnection, table: str,
                           column: str, ids: list[str], shot_id: str):
    # relation transitions carry `state`; feature transitions carry
    # operation/value columns — each domain selects its exact vocabulary
    if table == "continuity_relation_transitions":
        cols = (f"id, {column} AS target_id, NULL AS operation, state, "
                "NULL AS value_json, NULL AS value_hash")
    else:
        cols = (f"id, {column} AS target_id, operation, NULL AS state, "
                "value_json, value_hash")
    ph, params = _params("t", ids)
    return (await conn.execute(text(
        f"SELECT {cols} FROM "
        f"{table} WHERE anchor_type = 'shot' AND anchor_id = :sid "
        f"AND boundary = 'end' AND deleted_at IS NULL "
        f"AND {column} IN ({ph})"),
        {"sid": shot_id, **params})).fetchall()


def _feature_handoff_matches(row, terminal_state: dict, meta: dict) -> bool:
    """Exact set|clear + canonical value/hash equality (R6 §1.5/§6.1)."""
    if terminal_state.get("present"):
        if row.operation != "set" or row.value_hash is None:
            return False
        if row.value_hash != terminal_state.get("value_hash"):
            return False
        enum_raw = meta.get("enum_values_json")
        enum_values = None
        if meta.get("value_type") == "enum":
            enum_values = (json.loads(enum_raw)
                           if isinstance(enum_raw, str) else enum_raw)
        value_json, value_hash = canonicalize_value(
            meta["value_type"], terminal_state["value"],
            enum_values=enum_values)
        return row.value_json == value_json and row.value_hash == value_hash
    return row.operation == "clear" and row.value_json is None


def _relation_handoff_matches(row, terminal_state: dict) -> bool:
    expected = "active" if terminal_state["active"] else "inactive"
    return row.state == expected


async def resolve_intra_shot(conn: AsyncConnection, shot, *,
                             resolved_deps, feature_outcome,
                             relation_outcome,
                             production_world_outcome) -> dict:
    """Project the current M16 authority for one Shot from resolved facts.

    ``resolved_deps``/``feature_outcome``/``relation_outcome`` are the
    predecessor resolutions for the SAME read snapshot (the Shot-detail
    read unit already holds them); ``production_world_outcome`` may be
    None when no Production-World plane is selected — Production Instance
    targets then fail closed as TARGET_INVALID.
    """
    rows = await _load_active_rows_bounded(conn, shot.id)
    if not rows:
        return _event_free(shot.duration_ms)

    issues: list[dict] = []
    drafts_all = [_draft_from_row(r) for r in rows]
    for d in drafts_all:
        _verify_stored_consistency(d)
    if len(rows) > MAX_ACTIVE_EVENTS_PER_SHOT:
        # structural validity ceiling (frozen R6 §5.4): overflow storage
        # is fail-closed — never folded, never hashed, never ready. The
        # bounded load observes at most ceiling+1 rows; the count below
        # is the observed lower bound, not the exact active total.
        return {
            "intra_shot_ready": False,
            "intra_shot_issues": [_issue(
                ErrorCode.INTRA_SHOT_EVENT_LIMIT_EXCEEDED,
                "active intra-Shot events exceed the structural ceiling",
                observed_active_event_count=len(rows),
                limit=MAX_ACTIVE_EVENTS_PER_SHOT)],
            "duration_ms": shot.duration_ms,
            "events": [_stored_public(d) for d in drafts_all],
            "terminal_targets": [],
            "handoffs": [],
            "event_set_hash": None,
            "target_identities": {},
        }
    duration = shot.duration_ms
    duration_ok = type(duration) is int and duration > 0
    if not duration_ok:
        issues.append(_issue(
            ErrorCode.INTRA_SHOT_DURATION_REQUIRED,
            "positive Shot duration is required while intra-Shot "
            "events exist", shot_id=shot.id))

    drafts = drafts_all

    seen: set[tuple[int, int]] = set()
    for d in drafts:
        coordinate = (d["time_ms"], d["ordinal"])
        if coordinate in seen:
            issues.append(_issue(
                ErrorCode.INTRA_SHOT_EVENT_COORDINATE_CONFLICT,
                "two active events share one (time_ms, ordinal) "
                "coordinate", time_ms=d["time_ms"], ordinal=d["ordinal"]))
        seen.add(coordinate)
        if duration_ok and not (1 <= d["time_ms"] < duration):
            issues.append(_issue(
                ErrorCode.INTRA_SHOT_TIME_OUT_OF_RANGE,
                "event time is not strictly inside the Shot duration",
                time_ms=d["time_ms"], duration_ms=duration))

    kinds: dict[str, list[str]] = {
        "entity_feature": [], "entity_relation": [],
        "production_instance_feature": []}
    for d in drafts:
        if d["target_id"] not in kinds[d["target_kind"]]:
            kinds[d["target_kind"]].append(d["target_id"])

    dep_ids = {d.entity_id for d in resolved_deps}
    metadata: dict[tuple[str, str], dict] = {}
    starts: dict[tuple[str, str], dict] = {}
    identities: dict[tuple[str, str], dict] = {}

    from soloring.continuity.intra_shot_canonical import (
        entity_feature_target_identity,
        entity_relation_target_identity,
        production_instance_feature_target_identity,
    )

    if kinds["entity_feature"]:
        ph, ps = _params("ef", kinds["entity_feature"])
        mrows = (await conn.execute(text(
            "SELECT f.id, f.entity_id, f.key, f.kind, f.value_type, "
            "f.unit, f.enum_values_json, e.project_id FROM "
            "continuity_features f JOIN creative_entities e "
            "ON e.id = f.entity_id "
            f"WHERE f.deleted_at IS NULL AND f.id IN ({ph})"),
            ps)).mappings().all()
        by_id = {r["id"]: dict(r) for r in mrows}
        feature_states = {s.feature_id: {
            "present": True, "value": json.loads(s.value_json),
            "value_hash": s.value_hash} for s in feature_outcome.states}
        for fid in kinds["entity_feature"]:
            f = by_id.get(fid)
            if (f is None or f["project_id"] != shot.project_id
                    or f["entity_id"] not in dep_ids):
                issues.append(_issue(
                    ErrorCode.INTRA_SHOT_TARGET_INVALID,
                    "entity feature target is not an active Shot "
                    "dependency", target_kind="entity_feature",
                    target_id=fid))
                continue
            if not feature_outcome.assigned and \
                    feature_outcome.relevant_temporal_data:
                issues.append(_issue(
                    ErrorCode.INTRA_SHOT_TARGET_INVALID,
                    "entity feature Shot/start state is not resolvable "
                    "without narrative context",
                    target_kind="entity_feature", target_id=fid,
                    reason="start_state_unresolvable"))
                continue
            metadata[("entity_feature", fid)] = f
            identities[("entity_feature", fid)] =                 entity_feature_target_identity(f)
            starts[("entity_feature", fid)] = feature_states.get(
                fid, {"present": False})

    if kinds["entity_relation"]:
        ph, ps = _params("er", kinds["entity_relation"])
        mrows = (await conn.execute(text(
            "SELECT r.id, r.project_id, r.subject_entity_id, "
            "r.predicate_id, p.key AS predicate_key, r.object_entity_id "
            "FROM continuity_relations r JOIN continuity_predicates p "
            "ON p.id = r.predicate_id "
            f"WHERE r.deleted_at IS NULL AND p.deleted_at IS NULL "
            f"AND r.id IN ({ph})"), ps)).mappings().all()
        by_id = {r["id"]: dict(r) for r in mrows}
        relation_active = {s.relation_id
                           for s in relation_outcome.relation_states}
        for rid in kinds["entity_relation"]:
            r = by_id.get(rid)
            if (r is None or r["project_id"] != shot.project_id
                    or r["subject_entity_id"] not in dep_ids
                    or r["object_entity_id"] not in dep_ids):
                issues.append(_issue(
                    ErrorCode.INTRA_SHOT_TARGET_INVALID,
                    "relation target requires both directional endpoint "
                    "dependencies", target_kind="entity_relation",
                    target_id=rid))
                continue
            if not relation_outcome.assigned and \
                    relation_outcome.relevant_relation_data:
                issues.append(_issue(
                    ErrorCode.INTRA_SHOT_TARGET_INVALID,
                    "relation Shot/start state is not resolvable without "
                    "narrative context", target_kind="entity_relation",
                    target_id=rid, reason="start_state_unresolvable"))
                continue
            metadata[("entity_relation", rid)] = r
            identities[("entity_relation", rid)] =                 entity_relation_target_identity(r)
            starts[("entity_relation", rid)] = {
                "active": rid in relation_active}

    if kinds["production_instance_feature"]:
        ph, ps = _params("pf", kinds["production_instance_feature"])
        mrows = (await conn.execute(text(
            "SELECT f.id, f.composition_id, f.occurrence_id, f.key, "
            "f.kind, f.value_type, f.unit, f.enum_values_json, "
            "a.subject_kind AS authority_subject_kind, "
            "bs.subject_kind AS binding_subject_kind, "
            "cr.composition_id AS binding_composition_id "
            "FROM production_instance_features f "
            "LEFT JOIN composition_occurrence_authority_subjects a "
            "ON a.composition_id = f.composition_id "
            "AND a.occurrence_id = f.occurrence_id "
            "LEFT JOIN shot_production_world_selections sel "
            "ON sel.shot_id = :sid "
            "LEFT JOIN composition_spatial_binding_subjects bs "
            "ON bs.binding_id = sel.binding_id "
            "AND bs.occurrence_id = f.occurrence_id "
            "LEFT JOIN composition_spatial_bindings b "
            "ON b.id = sel.binding_id "
            "LEFT JOIN composition_revisions cr "
            "ON cr.id = b.composition_revision_id "
            f"WHERE f.deleted_at IS NULL AND f.id IN ({ph})"),
            {"sid": shot.id, **ps})).mappings().all()
        by_id = {r["id"]: dict(r) for r in mrows}
        if (production_world_outcome is None
                or not production_world_outcome.selected
                or not production_world_outcome.ready
                or production_world_outcome.pack is None):
            for fid in kinds["production_instance_feature"]:
                issues.append(_issue(
                    ErrorCode.INTRA_SHOT_TARGET_INVALID,
                    "Production Instance target requires a ready selected "
                    "current Production World",
                    target_kind="production_instance_feature",
                    target_id=fid, reason="production_world_not_ready"))
        else:
            pi_states = {s["feature_id"]: {
                "present": True, "value": s["value"],
                "value_hash": s["value_hash"]}
                for s in production_world_outcome.pack[
                    "instance_feature_states"]}
            for fid in kinds["production_instance_feature"]:
                f = by_id.get(fid)
                if (f is None
                        or f["authority_subject_kind"] != "production_instance"
                        or f["binding_subject_kind"] != "production_instance"
                        or f["binding_composition_id"] != f["composition_id"]):
                    issues.append(_issue(
                        ErrorCode.INTRA_SHOT_TARGET_INVALID,
                        "Production Instance feature is not a selected "
                        "production_instance subject",
                        target_kind="production_instance_feature",
                        target_id=fid))
                    continue
                metadata[("production_instance_feature", fid)] = f
                identities[("production_instance_feature", fid)] =                     production_instance_feature_target_identity(f)
                starts[("production_instance_feature", fid)] = pi_states.get(
                    fid, {"present": False})

    # Canonical rebuild of every stored event; disagreement between the
    # stored canonical columns and the rebuilt values is corruption.
    normalized = []
    unresolved: list[dict] = []
    structural = False
    for d in drafts:
        key = (d["target_kind"], d["target_id"])
        meta = metadata.get(key)
        if meta is None:
            structural = True
            unresolved.append(d)
            continue
        try:
            before, before_json, before_hash = state_storage(
                d["target_kind"], d["before"], meta)
            after, after_json, after_hash = state_storage(
                d["target_kind"], d["after"], meta)
            event, event_json, event_hash = event_storage(
                time_ms=d["time_ms"], ordinal=d["ordinal"],
                target={"kind": d["target_kind"], "id": d["target_id"]},
                before=before, after=after,
                persistence_mode=d["persistence_mode"])
        except Exception:
            issues.append(_issue(
                ErrorCode.INTRA_SHOT_TARGET_INVALID,
                "stored event state is not canonical under the live "
                "target schema", target_kind=d["target_kind"],
                target_id=d["target_id"], event_id=d.get("id"),
                reason="state_not_canonical_under_live_schema"))
            structural = True
            unresolved.append(d)
            continue
        stored = d.get("stored")
        if stored is not None and not (
                stored.before_state_json == before_json
                and stored.before_state_hash == before_hash
                and stored.after_state_json == after_json
                and stored.after_state_hash == after_hash
                and stored.event_json == event_json
                and stored.event_hash == event_hash):
            from soloring.errors import internal_invariant

            raise internal_invariant(
                f"stored intra-Shot event {stored.id} disagrees with "
                "canonical columns/hash")
        normalized.append({**d, "before": before, "after": after,
                           "event": event, "event_json": event_json,
                           "event_hash": event_hash})

    normalized.sort(key=lambda d: (d["time_ms"], d["ordinal"]))
    folded = dict(starts)
    per_target: dict[tuple[str, str], list[dict]] = {}
    for d in normalized:
        key = (d["target_kind"], d["target_id"])
        expected = folded.get(key)
        if expected is not None and d["before"] != expected:
            issues.append(_issue(
                ErrorCode.INTRA_SHOT_EVENT_BEFORE_STATE_MISMATCH,
                "event before-state does not equal the exact folded "
                "current state", event_id=d.get("id"),
                target={"kind": key[0], "id": key[1]},
                time_ms=d["time_ms"], ordinal=d["ordinal"],
                expected=expected, actual=d["before"]))
        folded[key] = d["after"]
        per_target.setdefault(key, []).append(d)

    terminal_targets = []
    persistent_terminals: list[tuple[tuple[str, str], dict]] = []
    for key in sorted(per_target):
        target_events = per_target[key]
        terminal = target_events[-1]
        for event in target_events[:-1]:
            if event["persistence_mode"] == "require_handoff":
                issues.append(_issue(
                    ErrorCode.INTRA_SHOT_PERSISTENT_EVENT_NOT_TERMINAL,
                    "require_handoff is legal only on the terminal event "
                    "for its exact target", event_id=event.get("id"),
                    target={"kind": key[0], "id": key[1]},
                    time_ms=event["time_ms"], ordinal=event["ordinal"]))
        terminal_targets.append({
            "target": {"kind": key[0], "id": key[1]},
            "terminal_event_id": terminal.get("id"),
            "time_ms": terminal["time_ms"],
            "ordinal": terminal["ordinal"],
            "terminal_state": terminal["after"],
            "persistence_mode": terminal["persistence_mode"],
        })
        if terminal["persistence_mode"] == "require_handoff":
            persistent_terminals.append((key, terminal))

    handoffs = []
    if persistent_terminals:
        if shot.scene_id is None:
            for key, terminal in persistent_terminals:
                issues.append(_issue(
                    ErrorCode.INTRA_SHOT_HANDOFF_ANCHOR_REQUIRED,
                    "persistent intra-Shot event requires a narrative "
                    "Shot/end boundary", event_id=terminal.get("id"),
                    target={"kind": key[0], "id": key[1]}))
                handoffs.append({
                    "target": {"kind": key[0], "id": key[1]},
                    "required_state": terminal["after"],
                    "existing": None, "matched": False,
                    "reason": "anchor_required"})
        else:
            ef_ids = [tid for (kind, tid), t in persistent_terminals
                      if kind == "entity_feature"]
            er_ids = [tid for (kind, tid), t in persistent_terminals
                      if kind == "entity_relation"]
            pf_ids = [tid for (kind, tid), t in persistent_terminals
                      if kind == "production_instance_feature"]
            transitions: dict[tuple[str, str], list] = {}
            if ef_ids:
                for row in await _transition_rows(
                        conn, "continuity_feature_transitions",
                        "feature_id", ef_ids, shot.id):
                    transitions.setdefault(
                        ("entity_feature", row.target_id), []).append(row)
            if er_ids:
                for row in await _transition_rows(
                        conn, "continuity_relation_transitions",
                        "relation_id", er_ids, shot.id):
                    transitions.setdefault(
                        ("entity_relation", row.target_id), []).append(row)
            if pf_ids:
                for row in await _transition_rows(
                        conn, "production_instance_feature_transitions",
                        "feature_id", pf_ids, shot.id):
                    transitions.setdefault(
                        ("production_instance_feature",
                         row.target_id), []).append(row)
            for key, terminal in persistent_terminals:
                rows_for_target = transitions.get(key, [])
                if not rows_for_target:
                    issues.append(_issue(
                        ErrorCode.INTRA_SHOT_HANDOFF_REQUIRED,
                        "persistent intra-Shot event has no owning-domain "
                        "Shot/end handoff", event_id=terminal.get("id"),
                        target={"kind": key[0], "id": key[1]}))
                    handoffs.append({
                        "target": {"kind": key[0], "id": key[1]},
                        "required_state": terminal["after"],
                        "existing": None, "matched": False,
                        "reason": "missing"})
                    continue
                matched_row = None
                for row in rows_for_target:
                    if key[0] == "entity_relation":
                        ok = _relation_handoff_matches(row, terminal["after"])
                    else:
                        ok = _feature_handoff_matches(
                            row, terminal["after"], metadata[key])
                    if ok:
                        matched_row = row
                        break
                if matched_row is None:
                    issues.append(_issue(
                        ErrorCode.INTRA_SHOT_HANDOFF_MISMATCH,
                        "active Shot/end transition does not equal the "
                        "terminal event state",
                        event_id=terminal.get("id"),
                        target={"kind": key[0], "id": key[1]}))
                    handoffs.append({
                        "target": {"kind": key[0], "id": key[1]},
                        "required_state": terminal["after"],
                        "existing": {
                            "transition_id": rows_for_target[0].id,
                            "operation": rows_for_target[0].operation,
                            "state": rows_for_target[0].state,
                        },
                        "matched": False, "reason": "mismatch"})
                else:
                    handoffs.append({
                        "target": {"kind": key[0], "id": key[1]},
                        "required_state": terminal["after"],
                        "existing": {
                            "transition_id": matched_row.id,
                            "operation": matched_row.operation,
                            "state": matched_row.state,
                        },
                        "matched": True, "reason": "exact"})

    _structural_codes = {
        getattr(ErrorCode.INTRA_SHOT_EVENT_COORDINATE_CONFLICT,
                "value", ErrorCode.INTRA_SHOT_EVENT_COORDINATE_CONFLICT),
        getattr(ErrorCode.INTRA_SHOT_TIME_OUT_OF_RANGE,
                "value", ErrorCode.INTRA_SHOT_TIME_OUT_OF_RANGE),
    }
    set_hash = None
    if duration_ok and not structural and not any(
            i["code"] in _structural_codes
            for i in issues):
        set_hash = event_set_hash(
            shot_id=shot.id, duration_ms=duration,
            events=[d["event"] for d in normalized])

    issues.sort(key=lambda i: (
        _code_rank(i["code"]),
        json.dumps(i.get("details", {}).get("target") or {},
                   sort_keys=True),
        i.get("details", {}).get("time_ms") is None,
        i.get("details", {}).get("time_ms") or 0,
        i.get("details", {}).get("ordinal") or 0))

    from soloring.continuity.intra_shot_service import _public_event

    public_events = [_public_event(d) for d in normalized]
    public_events.extend(_stored_public(d) for d in unresolved)
    public_events.sort(key=lambda e: (e["time_ms"], e["ordinal"]))

    return {
        "intra_shot_ready": not issues,
        "intra_shot_issues": issues,
        "duration_ms": duration,
        "events": public_events,
        "terminal_targets": terminal_targets,
        "handoffs": handoffs,
        "event_set_hash": set_hash,
        "target_identities": identities,
    }


async def resolve_intra_shot_read(session: AsyncSession, shot_id: str) -> dict:
    """Standalone read: one snapshot, predecessor facts resolved lazily."""
    from soloring.continuity.snapshots import resolve_working_dependencies
    from soloring.continuity.state import (
        resolve_effective_feature_state,
        resolve_effective_relation_state,
    )

    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN")
        try:
            shot = await _load_shot(conn, shot_id)
            rows = await _load_active_rows_bounded(conn, shot_id)
            pi_present = any(
                r.target_kind == "production_instance_feature"
                for r in rows)
            resolved_deps = await resolve_working_dependencies(conn, shot.id)
            feature_outcome = await resolve_effective_feature_state(
                conn, shot.id)
            relation_outcome = await resolve_effective_relation_state(
                conn, shot.id)
            world_outcome = None
            if pi_present:
                from soloring.spatial.resolver import resolve_spatial_continuity
                from soloring.production_world.resolver import (
                    resolve_production_world,
                )

                spatial = await resolve_spatial_continuity(
                    conn, shot_id=shot.id,
                    resolved_dependencies=resolved_deps)
                if spatial.ready:
                    world_outcome = await resolve_production_world(
                        conn, shot_id=shot.id,
                        resolved_dependencies=resolved_deps,
                        m10_spatial_result=spatial)
            projection = await resolve_intra_shot(
                conn, shot,
                resolved_deps=resolved_deps,
                feature_outcome=feature_outcome,
                relation_outcome=relation_outcome,
                production_world_outcome=world_outcome)
            await conn.commit()
            projection.pop("target_identities", None)
            return projection
        except Exception:
            import contextlib

            with contextlib.suppress(Exception):
                await conn.rollback()
            raise
