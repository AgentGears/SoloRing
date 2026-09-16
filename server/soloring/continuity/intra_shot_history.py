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


def _start_states_from(features, relations, world):
    """Captured start states. The Production-World plane is referenced by
    hash in the companion row and embedded in the SNAPSHOT itself, so the
    re-fold consumes the snapshot's captured pack — same revision only."""
    starts: dict[tuple[str, str], dict] = {}
    for row in features:
        starts[("entity_feature", row[0])] = {
            "present": True, "value": json.loads(row[1]),
            "value_hash": row[2]}
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
                 revision_shot_id: str | None = None) -> dict | None:
    """parent: mapping rows (schema_version, duration_ms, spec_json,
    spec_hash); children: mapping rows over _CHILD_COLUMNS; starts/world:
    captured predecessor planes. Pure — performs no connection access."""
    if not parent:
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
    features = (await conn.execute(text(
        "SELECT feature_id, value_json, value_hash FROM "
        "shot_revision_feature_states WHERE shot_revision_id = :r"),
        {"r": revision_id})).fetchall()
    relations = (await conn.execute(text(
        "SELECT relation_id FROM shot_revision_relation_states "
        "WHERE shot_revision_id = :r"),
        {"r": revision_id})).fetchall()
    world = (snapshot or {}).get("production_world")
    starts, world = _start_states_from(features, relations, world)
    return _verify_core(parent, children, starts, world, revision_id,
                        snapshot, revision_shot_id=revision_shot_id)


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
    features = conn.execute(
        "SELECT feature_id, value_json, value_hash FROM "
        "shot_revision_feature_states WHERE shot_revision_id = ?",
        (revision_id,)).fetchall()
    relations = conn.execute(
        "SELECT relation_id FROM shot_revision_relation_states "
        "WHERE shot_revision_id = ?", (revision_id,)).fetchall()
    world = (snapshot or {}).get("production_world")
    starts, world = _start_states_from(features, relations, world)
    return _verify_core(parent, children, starts, world, revision_id,
                        snapshot, revision_shot_id=revision_shot_id)


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
