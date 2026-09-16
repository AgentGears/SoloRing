"""M16-C canonical intra-Shot capture pack (frozen R6 §8.2/§4.7/§4.8).

The pack is the top-level ``intra_shot`` block embedded in outer Shot
snapshot schema 7 and the immutable companion-parent value. It is built
ONLY from the B resolver's ready projection under the capture read
snapshot; captured target identities and semantic handoffs freeze
predecessor facts so history never consults current definitions.
"""

from __future__ import annotations

from soloring.continuity.intra_shot_canonical import (
    entity_feature_target_identity,
    entity_relation_target_identity,
    feature_handoff_value,
    production_instance_feature_target_identity,
    relation_handoff_value,
)
from soloring.domain.canonical import canonical_hash, canonical_json_str


def _captured_handoff(kind: str, target_id: str, shot_id: str,
                      terminal_state: dict) -> dict:
    """The canonical semantic handoff (R6 §4.8): transition row UUIDs are
    audit provenance and are NEVER embedded in the semantic block."""
    if kind == "entity_relation":
        return relation_handoff_value(
            relation_id=target_id, shot_id=shot_id,
            state="active" if terminal_state["active"] else "inactive")
    domain = kind
    if terminal_state.get("present"):
        return feature_handoff_value(
            domain=domain, target_kind=kind, target_id=target_id,
            shot_id=shot_id, operation="set", state=terminal_state)
    return feature_handoff_value(
        domain=domain, target_kind=kind, target_id=target_id,
        shot_id=shot_id, operation="clear",
        state={"present": False})


def build_intra_shot_pack(shot_id: str, duration_ms: int, events: list[dict],
                          target_identities: dict,
                          terminal_persistence: dict) -> dict:
    """Assemble the schema-1 intra_shot block from the resolver projection.

    ``events`` are the resolver's canonical public events (folded, ready);
    ``target_identities`` maps (kind, id) -> frozen identity; terminal
    events flagged in ``terminal_persistence`` (event id -> terminal
    state) carry the captured semantic handoff.
    """
    packed = []
    for event in events:
        key = (event["target"]["kind"], event["target"]["id"])
        entry = {
            "time_ms": event["time_ms"],
            "ordinal": event["ordinal"],
            "target": event["target"],
            "target_identity": target_identities[key],
            "before": event["before"],
            "after": event["after"],
            "persistence_mode": event["persistence_mode"],
            "handoff": None,
        }
        if event["id"] in terminal_persistence:
            entry["handoff"] = _captured_handoff(
                key[0], key[1], shot_id, terminal_persistence[event["id"]])
        packed.append(entry)
    return {
        "schema_version": 1,
        "duration_ms": duration_ms,
        "events": packed,
    }


def pack_from_projection(shot_id: str, projection: dict) -> dict | None:
    """The canonical pack from a READY resolver projection (None when
    event-free). One construction shared by capture and the working-hash
    seam so they can never diverge."""
    if not projection["events"]:
        return None
    terminal_persistence = {
        t["terminal_event_id"]: t["terminal_state"]
        for t in projection["terminal_targets"]
        if t["persistence_mode"] == "require_handoff"}
    transition_ids = {
        (h["target"]["kind"], h["target"]["id"]):
            h["existing"]["transition_id"]
        for h in projection["handoffs"] if h["existing"] is not None}
    pack = build_intra_shot_pack(
        shot_id=shot_id, duration_ms=projection["duration_ms"],
        events=projection["events"],
        target_identities=projection["target_identities"],
        terminal_persistence=terminal_persistence)
    return pack, transition_ids


def intra_shot_spec_bytes(pack: dict) -> tuple[str, str]:
    """Canonical companion-parent bytes/hash (exactly the block value)."""
    js = canonical_json_str(pack)
    return js, canonical_hash(pack)


def captured_child_row(pack_event: dict, *, position: int,
                       source_event_id: str | None,
                       source_proposal_id: str | None,
                       transition_id: str | None) -> dict:
    """One immutable companion-child row from a packed event (R6 §7.3).

    Semantic columns carry canonical bytes/hashes; source/transition ids
    are first-publication audit provenance only.
    """
    identity = pack_event["target_identity"]
    identity_json = canonical_json_str(identity)
    before_json = canonical_json_str(pack_event["before"])
    after_json = canonical_json_str(pack_event["after"])
    handoff = pack_event["handoff"]
    event = {
        "schema_version": 1,
        "time_ms": pack_event["time_ms"],
        "ordinal": pack_event["ordinal"],
        "target": pack_event["target"],
        "before": pack_event["before"],
        "after": pack_event["after"],
        "persistence_mode": pack_event["persistence_mode"],
    }
    event_json = canonical_json_str(event)
    return {
        "event_json": event_json,
        "event_hash": canonical_hash(event),
        "position": position,
        "source_event_id": source_event_id,
        "time_ms": pack_event["time_ms"],
        "ordinal": pack_event["ordinal"],
        "target_kind": pack_event["target"]["kind"],
        "captured_target_identity_json": identity_json,
        "captured_target_identity_hash": canonical_hash(identity),
        "captured_before_state_json": before_json,
        "captured_before_state_hash": canonical_hash(
            pack_event["before"]),
        "captured_after_state_json": after_json,
        "captured_after_state_hash": canonical_hash(pack_event["after"]),
        "persistence_mode": pack_event["persistence_mode"],
        "entity_feature_transition_id": (
            transition_id
            if pack_event["target"]["kind"] == "entity_feature"
            and handoff is not None else None),
        "entity_relation_transition_id": (
            transition_id
            if pack_event["target"]["kind"] == "entity_relation"
            and handoff is not None else None),
        "production_instance_feature_transition_id": (
            transition_id
            if pack_event["target"]["kind"]
            == "production_instance_feature"
            and handoff is not None else None),
        "captured_handoff_json": (
            canonical_json_str(handoff) if handoff is not None else None),
        "captured_handoff_hash": (
            canonical_hash(handoff) if handoff is not None else None),
        "source_proposal_id": source_proposal_id,
    }


def semantic_child_signature(row) -> tuple:
    """The semantic convergence key for one companion child: every
    captured semantic field. ``source_event_id``/``source_proposal_id``
    and transition UUIDs are deliberately excluded (R6 §14.4)."""
    return (
        row.position, row.time_ms, row.ordinal, row.target_kind,
        row.captured_target_identity_json,
        row.captured_target_identity_hash,
        row.captured_before_state_json, row.captured_before_state_hash,
        row.captured_after_state_json, row.captured_after_state_hash,
        row.persistence_mode, row.captured_handoff_json,
        row.captured_handoff_hash, row.event_json, row.event_hash,
    )


def expected_child_signature(child: dict) -> tuple:
    return (
        child["position"], child["time_ms"], child["ordinal"],
        child["target_kind"], child["captured_target_identity_json"],
        child["captured_target_identity_hash"],
        child["captured_before_state_json"],
        child["captured_before_state_hash"],
        child["captured_after_state_json"],
        child["captured_after_state_hash"], child["persistence_mode"],
        child["captured_handoff_json"], child["captured_handoff_hash"],
        child["event_json"], child["event_hash"],
    )
