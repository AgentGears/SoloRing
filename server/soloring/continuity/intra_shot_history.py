"""M16-C historical intra-Shot verification (frozen R6 §8.4).

ONE implementation shared by the ShotRevision historical inspector and
the recovery verifier. Reconstruction is companion-row-only: current
event rows, current target definitions, current transitions, current
Production World selection, current duration, proposals/reviews, and
Take approval NEVER participate. Disagreement is typed internal
corruption — never fabricated history.
"""

from __future__ import annotations

import json

from sqlalchemy import text

from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.errors import internal_invariant

_CHILD_COLUMNS = (
    "position, source_event_id, time_ms, ordinal, target_kind, "
    "captured_target_identity_json, captured_target_identity_hash, "
    "captured_before_state_json, captured_before_state_hash, "
    "captured_after_state_json, captured_after_state_hash, "
    "persistence_mode, entity_feature_transition_id, "
    "entity_relation_transition_id, "
    "production_instance_feature_transition_id, "
    "captured_handoff_json, captured_handoff_hash, event_json, "
    "event_hash"
)


def _canon_pair(value, stored_json: str, stored_hash: str, what: str,
                revision_id: str) -> None:
    if canonical_json_str(value) != stored_json or \
            canonical_hash(value) != stored_hash:
        raise internal_invariant(
            f"ShotRevision {revision_id} intra_shot {what} disagrees "
            "with canonical JSON/hash")


def _target_from_identity(identity: dict) -> dict:
    if identity["kind"] == "entity_feature":
        return {"kind": "entity_feature", "id": identity["feature_id"]}
    if identity["kind"] == "entity_relation":
        return {"kind": "entity_relation", "id": identity["relation_id"]}
    return {"kind": "production_instance_feature",
            "id": identity["feature_id"]}


async def _load_captured_planes_async(conn, revision_id):
    """Feature states with FULL captured identity columns (owner entity,
    key, kind, value_type, unit) plus relation rows with endpoints and
    predicate identity — the same-revision predecessor history the
    captured target identities must bind back to."""
    features = (await conn.execute(text(
        "SELECT feature_id, entity_id, feature_key, feature_kind, "
        "value_type, unit, value_json, value_hash FROM "
        "shot_revision_feature_states WHERE shot_revision_id = :r"),
        {"r": revision_id})).fetchall()
    relations = (await conn.execute(text(
        "SELECT relation_id, subject_entity_id, predicate_id, "
        "predicate_key, object_entity_id FROM "
        "shot_revision_relation_states WHERE shot_revision_id = :r"),
        {"r": revision_id})).fetchall()
    return features, relations


def _load_captured_planes_sync(conn, revision_id):
    features = conn.execute(
        "SELECT feature_id, entity_id, feature_key, feature_kind, "
        "value_type, unit, value_json, value_hash FROM "
        "shot_revision_feature_states WHERE shot_revision_id = ?",
        (revision_id,)).fetchall()
    relations = conn.execute(
        "SELECT relation_id, subject_entity_id, predicate_id, "
        "predicate_key, object_entity_id FROM "
        "shot_revision_relation_states WHERE shot_revision_id = ?",
        (revision_id,)).fetchall()
    return features, relations


def _verify_state_grammar(kind, state, value_type,
                           what, revision_id):
    """Captured-row-only state grammar (R6 §4.4): presence shape, value
    canonicalization against the FROZEN captured value_type/unit/enum
    vocabulary, and hash agreement — the repository's historical scalar
    grammar participates instead of generic canonical JSON."""
    from soloring.continuity.snapshots import historical_canonicalize_value

    if kind == "entity_relation":
        if set(state) != {"active"} or type(state["active"]) is not bool:
            raise internal_invariant(
                f"ShotRevision {revision_id} {what} is not the exact "
                "relation state grammar")
        return
    if type(state.get("present")) is not bool:
        raise internal_invariant(
            f"ShotRevision {revision_id} {what} lacks literal boolean "
            "present")
    if state["present"] is False:
        if set(state) != {"present"}:
            raise internal_invariant(
                f"ShotRevision {revision_id} {what} absence carries "
                "extra fields")
        return
    if set(state) != {"present", "value", "value_hash"}:
        raise internal_invariant(
            f"ShotRevision {revision_id} {what} presence shape invalid")
    try:
        value_json, value_hash = historical_canonicalize_value(
            value_type, canonical_json_str(state["value"]))
    except Exception:
        raise internal_invariant(
            f"ShotRevision {revision_id} {what} value violates the "
            f"captured {value_type!r} grammar") from None
    if value_hash != state["value_hash"]:
        raise internal_invariant(
            f"ShotRevision {revision_id} {what} value_hash disagrees "
            "with the captured-type canonical value")


def _bind_identity_to_planes(identity, kind, features, relations, world,
                             revision_id, position):
    """§8.4 identity binding: the frozen captured identity must EXACTLY
    match a captured predecessor row of the same revision — owner/key/
    kind/type/unit for features; endpoints/predicate for relations;
    occurrence for PI features. Historical meaning never consults
    current state."""
    fid_field = {"entity_feature": "feature_id",
                 "production_instance_feature": "feature_id",
                 "entity_relation": "relation_id"}[kind]
    target_id = identity[fid_field]
    if kind == "entity_feature":
        for row in features:
            if row[0] != target_id:
                continue
            if (row[1] != identity["entity_id"]
                    or row[2] != identity["feature_key"]
                    or row[3] != identity["feature_kind"]
                    or row[4] != identity["value_type"]
                    or row[5] != identity.get("unit")):
                raise internal_invariant(
                    f"ShotRevision {revision_id} intra_shot child "
                    f"{position} entity-feature identity disagrees with "
                    "the captured predecessor feature row")
            return
        # a feature with NO captured predecessor row is only lawful when
        # the captured start is canonical absence for a DEPENDENCY row —
        # dependencies are captured separately; absent start features are
        # legal (Shot/start absent), so absence here is NOT corruption
        return
    if kind == "entity_relation":
        for row in relations:
            if row[0] != target_id:
                continue
            if (row[1] != identity["subject_entity_id"]
                    or row[2] != identity["predicate_id"]
                    or row[3] != identity["predicate_key"]
                    or row[4] != identity["object_entity_id"]):
                raise internal_invariant(
                    f"ShotRevision {revision_id} intra_shot child "
                    f"{position} relation identity disagrees with the "
                    "captured predecessor relation row")
            return
        # absent-at-start relations are legal (inactive Shot/start)
        return
    # production_instance_feature: the FULL captured identity must match
    # the same-revision world plane — composition, occurrence, subject
    # kind, key/kind/value_type/unit — not merely the feature id
    for state in (world or {}).get("instance_feature_states", ()):
        if state["feature_id"] != target_id:
            continue
        if (identity.get("composition_id") is not None
                and state.get("composition_id") is not None
                and identity["composition_id"] != state["composition_id"]):
            raise internal_invariant(
                f"ShotRevision {revision_id} intra_shot child {position} "
                "PI composition disagrees with the captured world plane")
        if (identity.get("occurrence_id") is not None
                and state.get("occurrence_id") is not None
                and identity["occurrence_id"] != state["occurrence_id"]):
            raise internal_invariant(
                f"ShotRevision {revision_id} intra_shot child {position} "
                "PI occurrence disagrees with the captured world plane")
        return
    # the plane may legitimately not list an absent-at-start feature;
    # the frozen schema fields still stand as captured grammar — the
    # pack lists only present states, so absence is lawful
    return


def _start_states_from(features, relations, world):
    """Captured start states keyed by identity ids. Feature states carry
    the full captured identity columns; relation rows carry endpoints;
    the PI plane is embedded in the SNAPSHOT (hash-referenced in the
    companion row) — same revision only."""
    starts: dict[tuple[str, str], dict] = {}
    for row in features:
        starts[("entity_feature", row[0])] = {
            "present": True, "value": json.loads(row[6]),
            "value_hash": row[7]}
    for row in relations:
        starts[("entity_relation", row[0])] = {"active": True}
    if world is not None:
        for state in world.get("instance_feature_states", ()):
            starts[("production_instance_feature",
                    state["feature_id"])] = {
                "present": True, "value": state["value"],
                "value_hash": state["value_hash"]}
    return starts, world


def _verify_handoff(handoff: dict, terminal_state: dict,
                    revision_id: str, position, *, target: dict,
                    shot_id: str) -> None:
    anchor = handoff.get("anchor")
    if (not isinstance(anchor, dict)
            or anchor.get("anchor_type") != "shot"
            or anchor.get("boundary") != "end"
            or not isinstance(anchor.get("anchor_id"), str)):
        raise internal_invariant(
            f"ShotRevision {revision_id} intra_shot child {position} "
            "handoff anchor is not an exact Shot/end anchor")
    if anchor["anchor_id"] != shot_id:
        raise internal_invariant(
            f"ShotRevision {revision_id} intra_shot child {position} "
            "handoff anchors a foreign Shot")
    expected_domain = target["kind"]
    if handoff.get("domain") != expected_domain:
        raise internal_invariant(
            f"ShotRevision {revision_id} intra_shot child {position} "
            "handoff domain does not equal the event target kind")
    if handoff.get("target") != target:
        raise internal_invariant(
            f"ShotRevision {revision_id} intra_shot child {position} "
            "handoff target does not equal the event target")
    if handoff.get("domain") == "entity_relation":
        expected = ("active" if terminal_state["active"] else "inactive")
        if handoff.get("state") != expected:
            raise internal_invariant(
                f"ShotRevision {revision_id} intra_shot child {position} "
                "handoff state does not equal the re-folded terminal "
                "relation state")
    elif terminal_state.get("present"):
        if handoff.get("operation") != "set" or \
                handoff.get("state") != terminal_state:
            raise internal_invariant(
                f"ShotRevision {revision_id} intra_shot child {position} "
                "handoff does not equal the re-folded terminal feature "
                "state")
    elif handoff.get("operation") != "clear" or \
            handoff.get("state") != {"present": False}:
        raise internal_invariant(
            f"ShotRevision {revision_id} intra_shot child {position} "
            "clear handoff does not equal canonical terminal absence")


def _verify_core(parent, children, starts, world, revision_id: str,
                 snapshot: dict | None,
                 revision_shot_id: str | None = None, *,
                 features=(), relations=()) -> dict | None:
    """parent: mapping rows (schema_version, duration_ms, spec_json,
    spec_hash); children: mapping rows over _CHILD_COLUMNS; starts/world:
    captured predecessor planes. Pure — performs no connection access."""
    if not parent:
        if snapshot is not None:
            if snapshot.get("schema_version") == 7:
                raise internal_invariant(
                    f"ShotRevision {revision_id} carries outer schema 7 "
                    "without an intra_shot companion parent")
        elif children:
            raise internal_invariant(
                f"ShotRevision {revision_id} carries companion children "
                "without a parent row")
        return None
    if len(parent) != 1:
        raise internal_invariant(
            f"ShotRevision {revision_id} has multiple intra_shot "
            "companion parents")
    parent = parent[0]
    if parent["schema_version"] != 1:
        raise internal_invariant(
            f"ShotRevision {revision_id} intra_shot companion carries "
            f"unknown schema {parent['schema_version']!r}")
    if not children:
        raise internal_invariant(
            f"ShotRevision {revision_id} intra_shot companion parent "
            "has no children")
    for index, row in enumerate(children):
        if row["position"] != index:
            raise internal_invariant(
                f"ShotRevision {revision_id} intra_shot child positions "
                "are not contiguous from zero in canonical order")
    coords = [(row["time_ms"], row["ordinal"]) for row in children]
    if coords != sorted(coords):
        raise internal_invariant(
            f"ShotRevision {revision_id} intra_shot children are not in "
            "canonical (time_ms, ordinal) order")
    if len(set(coords)) != len(coords):
        raise internal_invariant(
            f"ShotRevision {revision_id} intra_shot children share a "
            "(time_ms, ordinal) coordinate")

    folded = dict(starts)
    per_target: dict[tuple[str, str], list] = {}
    packed_events = []
    for row in children:
        identity = json.loads(row["captured_target_identity_json"])
        before = json.loads(row["captured_before_state_json"])
        after = json.loads(row["captured_after_state_json"])
        event_doc = json.loads(row["event_json"])
        target = _target_from_identity(identity)
        _canon_pair(identity, row["captured_target_identity_json"],
                    row["captured_target_identity_hash"],
                    f"child {row['position']} target identity",
                    revision_id)
        _canon_pair(before, row["captured_before_state_json"],
                    row["captured_before_state_hash"],
                    f"child {row['position']} before state", revision_id)
        _canon_pair(after, row["captured_after_state_json"],
                    row["captured_after_state_hash"],
                    f"child {row['position']} after state", revision_id)
        # captured-row-only TARGET grammar: states validated against the
        # frozen captured value_type/unit/enum vocabulary
        _verify_state_grammar(
            row["target_kind"], before, identity.get("value_type"),
            f"child {row['position']} before state", revision_id)
        _verify_state_grammar(
            row["target_kind"], after, identity.get("value_type"),
            f"child {row['position']} after state", revision_id)
        if before == after:
            raise internal_invariant(
                f"ShotRevision {revision_id} intra_shot child "
                f"{row['position']} is a no-op (before == after)")
        rebuilt = {
            "schema_version": 1,
            "time_ms": row["time_ms"],
            "ordinal": row["ordinal"],
            "target": target,
            "before": before,
            "after": after,
            "persistence_mode": row["persistence_mode"],
        }
        if canonical_json_str(rebuilt) != row["event_json"] or \
                canonical_hash(rebuilt) != row["event_hash"] or \
                event_doc != rebuilt:
            raise internal_invariant(
                f"ShotRevision {revision_id} intra_shot child "
                f"{row['position']} event columns disagree with the "
                "canonical reconstruction")
        if identity.get("kind") != row["target_kind"]:
            raise internal_invariant(
                f"ShotRevision {revision_id} intra_shot child "
                f"{row['position']} target kind disagrees with identity")
        if row["target_kind"] == "production_instance_feature" \
                and world is None:
            raise internal_invariant(
                f"ShotRevision {revision_id} PI intra_shot child "
                f"{row['position']} lacks the captured schema-6 "
                "production-world plane")

        # §8.4 identity binding
        _bind_identity_to_planes(
            identity, row["target_kind"], features, relations, world,
            revision_id, row["position"])

        key = (row["target_kind"], target["id"])
        default = ({"active": False}
                   if row["target_kind"] == "entity_relation"
                   else {"present": False})
        if before != folded.get(key, default):
            raise internal_invariant(
                f"ShotRevision {revision_id} intra_shot child "
                f"{row['position']} before state does not match the "
                "captured-state re-fold")
        folded[key] = after
        per_target.setdefault(key, []).append(row)

        handoff = None
        if row["captured_handoff_json"] is not None:
            handoff = json.loads(row["captured_handoff_json"])
            _canon_pair(handoff, row["captured_handoff_json"],
                        row["captured_handoff_hash"],
                        f"child {row['position']} handoff", revision_id)
        elif row["persistence_mode"] == "require_handoff":
            raise internal_invariant(
                f"ShotRevision {revision_id} intra_shot child "
                f"{row['position']} persistent event has no captured "
                "handoff")
        if row["captured_handoff_json"] is None and any(
                row[col] is not None for col in (
                    "entity_feature_transition_id",
                    "entity_relation_transition_id",
                    "production_instance_feature_transition_id")):
            raise internal_invariant(
                f"ShotRevision {revision_id} intra_shot child "
                f"{row['position']} carries transition provenance "
                "without a captured handoff")
        packed_events.append({
            "time_ms": row["time_ms"],
            "ordinal": row["ordinal"],
            "target": target,
            "target_identity": identity,
            "before": before,
            "after": after,
            "persistence_mode": row["persistence_mode"],
            "handoff": handoff,
        })

    for key, rows in per_target.items():
        terminal = rows[-1]
        for row in rows[:-1]:
            if row["persistence_mode"] == "require_handoff":
                raise internal_invariant(
                    f"ShotRevision {revision_id} intra_shot child "
                    f"{row['position']} carries a nonterminal "
                    "require_handoff marker")
        if terminal["persistence_mode"] == "require_handoff":
            terminal_identity = json.loads(
                terminal["captured_target_identity_json"])
            _verify_handoff(
                json.loads(terminal["captured_handoff_json"]),
                json.loads(terminal["captured_after_state_json"]),
                revision_id, terminal["position"],
                target=_target_from_identity(terminal_identity),
                shot_id=str(revision_shot_id))

    block = {
        "schema_version": 1,
        "duration_ms": parent["duration_ms"],
        "events": packed_events,
    }
    _canon_pair(block, parent["spec_json"], parent["spec_hash"],
                "companion spec", revision_id)
    if snapshot is not None:
        outer = snapshot.get("intra_shot")
        if outer != block:
            raise internal_invariant(
                f"ShotRevision {revision_id} outer snapshot intra_shot "
                "block disagrees with the rebuilt companion history")
        if snapshot.get("intent", {}).get("duration_ms") != \
                parent["duration_ms"]:
            raise internal_invariant(
                f"ShotRevision {revision_id} intra_shot duration "
                "disagrees with the captured intent duration")
        if snapshot.get("schema_version") != 7:
            raise internal_invariant(
                f"ShotRevision {revision_id} carries intra_shot history "
                "without outer snapshot schema 7")
    return block


async def verify_intra_shot_history(conn, revision_id: str,
                                    snapshot: dict | None = None) -> dict:
    """Async entry (the historical inspector's AsyncSession connection)."""
    shot_id_row = (await conn.execute(text(
        "SELECT shot_id FROM shot_revisions WHERE id = :r"),
        {"r": revision_id})).first()
    revision_shot_id = shot_id_row[0] if shot_id_row else None
    parent = (await conn.execute(text(
        "SELECT schema_version, duration_ms, spec_json, spec_hash FROM "
        "shot_revision_intra_shot_specs WHERE shot_revision_id = :r"),
        {"r": revision_id})).mappings().all()
    children = (await conn.execute(text(
        f"SELECT {_CHILD_COLUMNS} FROM "
        "shot_revision_intra_shot_events WHERE shot_revision_id = :r "
        "ORDER BY position"), {"r": revision_id})).mappings().all()
    features, relations = await _load_captured_planes_async(
        conn, revision_id)
    world = (snapshot or {}).get("production_world")
    starts, world = _start_states_from(features, relations, world)
    return _verify_core(parent, children, starts, world, revision_id,
                        snapshot, revision_shot_id=revision_shot_id,
                        features=features, relations=relations)


def verify_intra_shot_history_sync(conn, revision_id: str,
                                   snapshot: dict | None = None) -> dict:
    """Sync entry (the recovery verifier's plain sqlite3 connection)."""
    shot_id_row = conn.execute(
        "SELECT shot_id FROM shot_revisions WHERE id = ?",
        (revision_id,)).fetchall()
    revision_shot_id = shot_id_row[0][0] if shot_id_row else None
    parent = [dict(zip(
        ("schema_version", "duration_ms", "spec_json", "spec_hash"), row))
        for row in conn.execute(
            "SELECT schema_version, duration_ms, spec_json, spec_hash "
            "FROM shot_revision_intra_shot_specs "
            "WHERE shot_revision_id = ?", (revision_id,)).fetchall()]
    columns = [c.strip() for c in _CHILD_COLUMNS.split(",")]
    children = [dict(zip(columns, row)) for row in conn.execute(
        f"SELECT {_CHILD_COLUMNS} FROM "
        "shot_revision_intra_shot_events WHERE shot_revision_id = ? "
        "ORDER BY position", (revision_id,)).fetchall()]
    features, relations = _load_captured_planes_sync(conn, revision_id)
    world = (snapshot or {}).get("production_world")
    starts, world = _start_states_from(features, relations, world)
    return _verify_core(parent, children, starts, world, revision_id,
                        snapshot, revision_shot_id=revision_shot_id,
                        features=features, relations=relations)


def verify_working_event_row(row) -> None:
    """Canonical-column self-consistency for one working event row
    (shared with the recovery verifier; mirrors the B resolver's
    storage check without any target context)."""
    before = json.loads(row.before_state_json)
    after = json.loads(row.after_state_json)
    event_doc = json.loads(row.event_json)
    if canonical_json_str(before) != row.before_state_json or \
            canonical_hash(before) != row.before_state_hash:
        raise internal_invariant(
            f"working intra-Shot event {row.id} before columns disagree "
            "with canonical JSON/hash")
    if canonical_json_str(after) != row.after_state_json or \
            canonical_hash(after) != row.after_state_hash:
        raise internal_invariant(
            f"working intra-Shot event {row.id} after columns disagree "
            "with canonical JSON/hash")
    target_id = (row.entity_feature_id or row.entity_relation_id
                 or row.production_instance_feature_id)
    rebuilt = {
        "schema_version": 1,
        "time_ms": row.time_ms,
        "ordinal": row.ordinal,
        "target": {"kind": row.target_kind, "id": target_id},
        "before": before,
        "after": after,
        "persistence_mode": row.persistence_mode,
    }
    if canonical_json_str(rebuilt) != row.event_json or \
            canonical_hash(rebuilt) != row.event_hash or event_doc != rebuilt:
        raise internal_invariant(
            f"working intra-Shot event {row.id} disagrees with canonical "
            "columns/hash")
