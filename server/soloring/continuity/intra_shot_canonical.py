"""Frozen M16 R6 canonical grammar and identity helpers.

This module is intentionally pure. Database services resolve live target metadata
first, then pass exact facts here. One canonical serializer/hash implementation
is reused from ``soloring.domain.canonical``.
"""

from __future__ import annotations

import json
from typing import Any

from soloring.continuity.values import canonicalize_value
from soloring.domain.canonical import canonical_hash, canonical_json_bytes, canonical_json_str
from soloring.domain.ids import is_uuid
from soloring.errors import validation_error

SAFE_INT_MAX = 9_007_199_254_740_991
MAX_ACTIVE_EVENTS_PER_SHOT = 10_000
MAX_PROPOSAL_CANONICAL_BYTES = 65_536
MAX_PROPOSAL_REVIEW_BATCH = 10_000
TARGET_KINDS = frozenset({
    "entity_feature", "entity_relation", "production_instance_feature"})
PERSISTENCE_MODES = frozenset({"transient", "require_handoff"})
PERSISTENCE_SUGGESTIONS = frozenset({"transient", "persist"})
PROPOSAL_DECISIONS = frozenset({
    "adopt_event_only", "adopt_persistence", "ignore"})
EVENT_DECISIONS = frozenset({"adopt_persistence", "decline_persistence"})


def require_plain_int(value: object, *, field: str, minimum: int = 0,
                      maximum: int = SAFE_INT_MAX) -> int:
    if type(value) is not int:  # bool is deliberately rejected
        raise validation_error(f"{field} must be a plain JSON integer")
    if value < minimum or value > maximum:
        raise validation_error(
            f"{field} must be between {minimum} and {maximum}")
    return value


def require_interior_time(time_ms: object, duration_ms: object) -> tuple[int, int]:
    """Return strict integer (time,duration) iff time is genuinely intra-Shot."""
    t = require_plain_int(time_ms, field="time_ms", minimum=1)
    duration = require_plain_int(duration_ms, field="duration_ms", minimum=1)
    if t >= duration:
        raise validation_error("time_ms must be strictly less than duration_ms")
    return t, duration


def require_hash(value: object, *, field: str) -> str:
    if (not isinstance(value, str) or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise validation_error(f"{field} must be 64 lowercase hex characters")
    return value


def target_value(kind: object, target_id: object) -> dict:
    if kind not in TARGET_KINDS:
        raise validation_error("unsupported intra-Shot target kind")
    if not isinstance(target_id, str) or not is_uuid(target_id):
        raise validation_error("target.id must be a UUID")
    return {"kind": kind, "id": target_id}


def _feature_state(raw: object, feature: dict) -> dict:
    if not isinstance(raw, dict) or type(raw.get("present")) is not bool:
        raise validation_error("feature state must contain literal boolean present")
    if raw["present"] is False:
        if set(raw) != {"present"}:
            raise validation_error("absent feature state is exactly {'present':false}")
        return {"present": False}
    if set(raw) != {"present", "value", "value_hash"}:
        raise validation_error(
            "present feature state requires exactly present,value,value_hash")
    enum_values = None
    if feature["value_type"] == "enum":
        enum_raw = feature.get("enum_values_json")
        enum_values = json.loads(enum_raw) if isinstance(enum_raw, str) else enum_raw
    try:
        value_json, value_hash = canonicalize_value(
            feature["value_type"], raw["value"], enum_values=enum_values)
    except Exception as exc:
        raise validation_error("feature state value is invalid for target schema") from exc
    supplied_hash = require_hash(raw["value_hash"], field="state.value_hash")
    if supplied_hash != value_hash:
        raise validation_error("state.value_hash disagrees with canonical value")
    return {
        "present": True,
        "value": json.loads(value_json),
        "value_hash": value_hash,
    }


def _relation_state(raw: object) -> dict:
    if (not isinstance(raw, dict) or set(raw) != {"active"}
            or type(raw.get("active")) is not bool):
        raise validation_error("relation state is exactly {'active':<boolean>}")
    return {"active": raw["active"]}


def canonical_state(kind: str, raw: object, target_metadata: dict) -> dict:
    if kind == "entity_relation":
        return _relation_state(raw)
    if kind in ("entity_feature", "production_instance_feature"):
        return _feature_state(raw, target_metadata)
    raise validation_error("unsupported intra-Shot target kind")


def state_storage(kind: str, raw: object, target_metadata: dict) -> tuple[dict, str, str]:
    value = canonical_state(kind, raw, target_metadata)
    return value, canonical_json_str(value), canonical_hash(value)


def event_value(*, time_ms: object, ordinal: object, target: dict,
                before: dict, after: dict, persistence_mode: object) -> dict:
    t = require_plain_int(time_ms, field="time_ms", minimum=1)
    o = require_plain_int(ordinal, field="ordinal", minimum=0)
    if not isinstance(target, dict) or set(target) != {"kind", "id"}:
        raise validation_error("target requires exactly kind and id")
    tv = target_value(target.get("kind"), target.get("id"))
    if persistence_mode not in PERSISTENCE_MODES:
        raise validation_error(
            "persistence_mode must be transient or require_handoff")
    if before == after:
        raise validation_error("before and after must differ semantically")
    return {
        "schema_version": 1,
        "time_ms": t,
        "ordinal": o,
        "target": tv,
        "before": before,
        "after": after,
        "persistence_mode": persistence_mode,
    }


def event_storage(**kwargs) -> tuple[dict, str, str]:
    value = event_value(**kwargs)
    return value, canonical_json_str(value), canonical_hash(value)


def event_set_value(*, shot_id: str, duration_ms: object,
                    events: list[dict]) -> dict:
    if not is_uuid(shot_id):
        raise validation_error("shot_id must be a UUID")
    duration = require_plain_int(duration_ms, field="duration_ms", minimum=1)
    return {
        "schema_version": 1,
        "shot_id": shot_id,
        "duration_ms": duration,
        "events": sorted(events, key=lambda e: (e["time_ms"], e["ordinal"])),
    }


def event_set_hash(*, shot_id: str, duration_ms: object,
                   events: list[dict]) -> str:
    return canonical_hash(event_set_value(
        shot_id=shot_id, duration_ms=duration_ms, events=events))


def entity_feature_target_identity(feature: dict) -> dict:
    return {
        "kind": "entity_feature",
        "feature_id": feature["id"],
        "entity_id": feature["entity_id"],
        "feature_key": feature["key"],
        "feature_kind": feature["kind"],
        "value_type": feature["value_type"],
        "unit": feature.get("unit"),
    }


def entity_relation_target_identity(relation: dict) -> dict:
    return {
        "kind": "entity_relation",
        "relation_id": relation["id"],
        "subject_entity_id": relation["subject_entity_id"],
        "predicate_id": relation["predicate_id"],
        "predicate_key": relation["predicate_key"],
        "object_entity_id": relation["object_entity_id"],
    }


def production_instance_feature_target_identity(feature: dict) -> dict:
    if feature.get("authority_subject_kind") != "production_instance":
        raise validation_error(
            "Production Instance target identity requires production_instance authority")
    return {
        "kind": "production_instance_feature",
        "feature_id": feature["id"],
        "composition_id": feature["composition_id"],
        "occurrence_id": feature["occurrence_id"],
        "authority_subject_kind": "production_instance",
        "feature_key": feature["key"],
        "feature_kind": feature["kind"],
        "value_type": feature["value_type"],
        "unit": feature.get("unit"),
    }


def feature_handoff_value(*, domain: str, target_kind: str, target_id: str,
                          shot_id: str, operation: str, state: dict) -> dict:
    if domain not in ("entity_feature", "production_instance_feature"):
        raise validation_error("feature handoff domain invalid")
    if target_kind != domain:
        raise validation_error("feature handoff target kind must equal domain")
    if operation not in ("set", "clear"):
        raise validation_error("feature handoff operation must be set or clear")
    if operation == "clear" and state != {"present": False}:
        raise validation_error("clear handoff requires canonical absence")
    if operation == "set" and not state.get("present"):
        raise validation_error("set handoff requires canonical presence")
    return {
        "domain": domain,
        "target": target_value(target_kind, target_id),
        "anchor": {"anchor_type": "shot", "anchor_id": shot_id,
                   "boundary": "end"},
        "operation": operation,
        "state": state,
    }


def relation_handoff_value(*, relation_id: str, shot_id: str, state: str) -> dict:
    if state not in ("active", "inactive"):
        raise validation_error("relation handoff state must be active or inactive")
    return {
        "domain": "entity_relation",
        "target": target_value("entity_relation", relation_id),
        "anchor": {"anchor_type": "shot", "anchor_id": shot_id,
                   "boundary": "end"},
        "state": state,
    }


def proposal_value(*, candidate_event: dict,
                   persistence_suggestion: object) -> dict:
    if persistence_suggestion not in PERSISTENCE_SUGGESTIONS:
        raise validation_error(
            "persistence_suggestion must be transient or persist")
    expected = {"time_ms", "ordinal", "target", "before", "after"}
    if not isinstance(candidate_event, dict) or set(candidate_event) != expected:
        raise validation_error("candidate_event has invalid Proposal Grammar v1 shape")
    # Candidate event omits persistence_mode but retains the exact event fields.
    target = candidate_event["target"]
    if not isinstance(target, dict) or set(target) != {"kind", "id"}:
        raise validation_error("candidate_event.target requires exactly kind and id")
    value = {
        "schema_version": 1,
        "candidate_event": {
            "time_ms": require_plain_int(candidate_event["time_ms"],
                                         field="candidate_event.time_ms", minimum=1),
            "ordinal": require_plain_int(candidate_event["ordinal"],
                                         field="candidate_event.ordinal"),
            "target": target_value(target["kind"], target["id"]),
            "before": candidate_event["before"],
            "after": candidate_event["after"],
        },
        "persistence_suggestion": persistence_suggestion,
    }
    raw = canonical_json_bytes(value)
    if len(raw) > MAX_PROPOSAL_CANONICAL_BYTES:
        raise validation_error("proposal canonical JSON exceeds 65,536 UTF-8 bytes")
    return value


def proposal_storage(**kwargs) -> tuple[dict, str, str]:
    value = proposal_value(**kwargs)
    return value, canonical_json_str(value), canonical_hash(value)


def event_review_basis_value(*, source_event_id: str, source_hash: str,
                             decision: str,
                             expected_event_set_hash: str,
                             expected_handoff: dict | None) -> dict:
    """R7 event-source basis: fenced by current M16 authority (source
    event + event-set hashes) — deliberately NO working-snapshot field,
    which §9.2 defines as unavailable exactly while the reviewed
    require_handoff state is unresolved."""
    if decision not in EVENT_DECISIONS:
        raise validation_error("invalid event review decision")
    if not is_uuid(source_event_id):
        raise validation_error("source event id must be UUID")
    require_hash(source_hash, field="source_hash")
    require_hash(expected_event_set_hash, field="expected_event_set_hash")
    if decision == "decline_persistence" and expected_handoff is not None:
        raise validation_error("decline_persistence requires expected_handoff null")
    return {
        "schema_version": 1,
        "source": {"kind": "event", "id": source_event_id,
                   "hash": source_hash},
        "decision": decision,
        "expected_event_set_hash": expected_event_set_hash,
        "expected_handoff": expected_handoff,
    }


def event_review_basis_hash(**kwargs) -> str:
    return canonical_hash(event_review_basis_value(**kwargs))


def proposal_batch_basis_value(*, shot_id: str, source_shot_revision_id: str,
                               source_shot_revision_hash: str,
                               expected_working_snapshot_hash: str | None,
                               expected_event_set_hash: str | None,
                               reviews: list[dict]) -> dict:
    if not is_uuid(shot_id) or not is_uuid(source_shot_revision_id):
        raise validation_error("batch shot/revision ids must be UUIDs")
    require_hash(source_shot_revision_hash, field="source_shot_revision_hash")
    if expected_working_snapshot_hash is not None:
        require_hash(expected_working_snapshot_hash,
                     field="expected_working_snapshot_hash")
    if expected_event_set_hash is not None:
        require_hash(expected_event_set_hash, field="expected_event_set_hash")
    if not reviews or len(reviews) > MAX_PROPOSAL_REVIEW_BATCH:
        raise validation_error("proposal review batch must contain 1..10,000 reviews")
    normalized = []
    seen = set()
    for review in reviews:
        if not isinstance(review, dict) or set(review) != {
                "proposal_id", "proposal_hash", "decision"}:
            raise validation_error("proposal batch review shape invalid")
        pid = review["proposal_id"]
        if not isinstance(pid, str) or not is_uuid(pid) or pid in seen:
            raise validation_error("proposal ids must be unique UUIDs")
        seen.add(pid)
        require_hash(review["proposal_hash"], field="proposal_hash")
        if review["decision"] not in PROPOSAL_DECISIONS:
            raise validation_error("invalid proposal review decision")
        normalized.append(dict(review))
    normalized.sort(key=lambda r: r["proposal_id"])
    return {
        "schema_version": 1,
        "shot_id": shot_id,
        "source_shot_revision_id": source_shot_revision_id,
        "source_shot_revision_hash": source_shot_revision_hash,
        "expected_working_snapshot_hash": expected_working_snapshot_hash,
        "expected_event_set_hash": expected_event_set_hash,
        "reviews": normalized,
    }


def proposal_batch_basis_hash(**kwargs) -> str:
    return canonical_hash(proposal_batch_basis_value(**kwargs))


def proposal_review_basis_hash(*, batch_basis_hash: str, proposal_id: str,
                               proposal_hash: str, decision: str) -> str:
    require_hash(batch_basis_hash, field="batch_basis_hash")
    if not is_uuid(proposal_id):
        raise validation_error("proposal_id must be UUID")
    require_hash(proposal_hash, field="proposal_hash")
    if decision not in PROPOSAL_DECISIONS:
        raise validation_error("invalid proposal review decision")
    return canonical_hash({
        "batch_basis_hash": batch_basis_hash,
        "proposal_id": proposal_id,
        "proposal_hash": proposal_hash,
        "decision": decision,
    })
