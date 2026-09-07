"""ONE current M13 production-world resolver (frozen M13 R3 §14).

Runs on the caller's already-coherent connection — never opens a second
database snapshot. M13 composes AFTER M10: the M10 result is consumed as
resolved input, never told which world to resolve. Strict capture raises
the first frozen blocker; inspection surfaces the deterministic
projection. Immutable binding integrity, current readiness, and
historical validity stay distinct.
"""

from __future__ import annotations

import json as _json
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from soloring.errors import (
    ErrorCode,
    SoloRingError,
    internal_invariant,
)
from soloring.production_world.binding import (
    _load_composition_revision,
    _validate_stored_binding,
    binding_current_status,
)
from soloring.production_world.instance_spatial import resolve_pi_staging
from soloring.production_world.instance_state import resolve_pi_feature_state


@dataclass(frozen=True)
class ProductionWorldOutcome:
    shot_id: str
    selected: bool
    ready: bool
    binding_id: str | None = None
    binding_hash: str | None = None
    binding_current_complete: bool | None = None
    stale_details: tuple = ()
    issues: tuple = ()
    pack: dict | None = None
    production_world_hash: str | None = None
    # §16.4: the semantic pack excludes the feature source_transition_id;
    # capture persists it as audit provenance from this parallel list in
    # the same canonical order.
    feature_source_transition_ids: tuple = ()


def _spatial_context_required(shot_id: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.PRODUCTION_WORLD_SPATIAL_CONTEXT_REQUIRED,
        f"Shot {shot_id} has a production-world selection but no resolved "
        "M10 spatial authority.", status_code=409)


def _revision_mismatch(shot_id: str, details: dict) -> SoloRingError:
    return SoloRingError(
        ErrorCode.PRODUCTION_WORLD_SPATIAL_REVISION_MISMATCH,
        f"Shot {shot_id}'s M10 authority resolved a different exact "
        "SpatialWorldRevision than the selected binding pins.",
        status_code=409, details=details)


def _entity_dependency_required(shot_id: str, missing: list) -> SoloRingError:
    return SoloRingError(
        ErrorCode.PRODUCTION_WORLD_ENTITY_DEPENDENCY_REQUIRED,
        f"Shot {shot_id}: every CreativeEntity authority subject in the "
        "selected binding must be an explicit semantic dependency.",
        status_code=409, details={"missing_entity_ids": missing})


def _stale_binding(details: dict) -> SoloRingError:
    return SoloRingError(
        ErrorCode.PRODUCTION_WORLD_BINDING_STALE,
        "the selected binding is no longer current-complete",
        status_code=409, details=details)


def _pi_track_state_required(missing: list) -> SoloRingError:
    return SoloRingError(
        ErrorCode.PRODUCTION_INSTANCE_TRACK_STATE_REQUIRED,
        "Required Production Instance track(s) have no effective set "
        "state at this Shot/start.",
        status_code=409,
        details={"missing": missing})


def _narrative_context_required(shot_id: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.NARRATIVE_CONTEXT_REQUIRED,
        f"Shot {shot_id} has relevant Production Instance temporal state "
        "but no resolvable narrative position (unassigned).",
        status_code=409)


def build_production_world_pack(
    *, binding_id: str, binding_hash: str, binding_value: dict,
    feature_states: list[dict], spatial_states: list[dict],
) -> dict:
    """Canonical schema-1 pack (§16.1); inputs already in §16.2 order."""
    return {
        "schema_version": 1,
        "binding": {
            "binding_id": binding_id,
            "binding_hash": binding_hash,
            "value": binding_value,
        },
        "instance_feature_states": feature_states,
        "instance_spatial_states": spatial_states,
    }


def production_world_hash(pack: dict) -> str:
    import hashlib

    from soloring.domain.canonical import canonical_json_bytes

    return hashlib.sha256(canonical_json_bytes(pack)).hexdigest()


async def resolve_production_world(
    conn: AsyncConnection, *, shot_id: str, resolved_dependencies,
    m10_spatial_result,
) -> ProductionWorldOutcome:
    """The ONE resolver (§14.1 steps 1-14) on the caller's snapshot."""
    # 1. read the exact Shot selection
    sel = (
        await conn.execute(
            text("SELECT binding_id FROM "
                 "shot_production_world_selections WHERE shot_id = :s"),
            {"s": shot_id},
        )
    ).first()
    # 2. no selection → M13 absent/ready
    if sel is None:
        return ProductionWorldOutcome(shot_id=shot_id, selected=False,
                                      ready=True)
    binding_id = sel.binding_id

    # 3. immutable binding integrity only (never current equality)
    stored = await _validate_stored_binding(conn, binding_id)

    # 4-5. current candidate equality + current-selectability
    stored_value = {
        "schema_version": 1,
        "composition_revision": {
            "revision_id": stored["composition_revision_id"],
            "snapshot_hash": stored["composition_revision_hash"]},
        "spatial_world_revision": {
            "revision_id": stored["spatial_world_revision_id"],
            "snapshot_hash": stored["spatial_world_revision_hash"]},
        "subjects": stored["subjects"], "entries": stored["entries"],
    }
    complete, stale_details = await binding_current_status(
        conn,
        composition_revision_id=stored["composition_revision_id"],
        spatial_world_revision_id=stored["spatial_world_revision_id"],
        stored_value=stored_value)
    issues: list[dict] = []
    if not complete:
        issues.append({"code": "PRODUCTION_WORLD_BINDING_STALE",
                       "stale_details": list(stale_details)})
    # liveness of every promoted authority-subject occurrence
    subject_occurrences = [s["occurrence_id"] for s in stored["subjects"]]
    terminated: set[str] = set()
    if subject_occurrences:
        ph = ",".join(f":o{i}" for i in range(len(subject_occurrences)))
        params = {f"o{i}": o for i, o in enumerate(subject_occurrences)}
        terminated = {
            r[0] for r in (await conn.execute(
                text(
                    "SELECT s.occurrence_id FROM "
                    "composition_identity_operation_sources s "
                    "JOIN composition_identity_operations op "
                    "ON op.id = s.operation_id "
                    "WHERE op.composition_id = :cid "
                    "AND s.terminates_identity = 1 AND s.occurrence_id "
                    f"IN ({ph})"),
                    {"cid": stored["composition_id"], **params},
            )).fetchall()}
        if terminated:
            issues.append({"code": "PRODUCTION_WORLD_BINDING_STALE",
                           "stale_details": [{
                               "code": "BINDING_STALE_BOUND_SUBJECT_TERMINATED",
                               "occurrences": sorted(terminated)}]})

    # 6. Project coherence
    shot_row = (
        await conn.execute(
            text("SELECT project_id FROM shots WHERE id = :s "
                 "AND deleted_at IS NULL"), {"s": shot_id},
        )
    ).first()
    if shot_row is None:
        raise SoloRingError(ErrorCode.SHOT_NOT_FOUND,
                            f"Shot {shot_id!r} not found.", status_code=404)
    comp = (
        await conn.execute(
            text("SELECT project_id FROM compositions WHERE id = :c"),
            {"c": stored["composition_id"]},
        )
    ).first()
    if comp is None or comp.project_id != shot_row.project_id:
        issues.append({"code": "PRODUCTION_WORLD_SELECTION_CONFLICT",
                       "reason": "binding_crosses_projects"})

    # 7. every CE subject is an explicit semantic dependency
    dep_entity_ids = {d.entity_id for d in resolved_dependencies}
    missing_ce = sorted({
        s["authority_subject"]["id"] for s in stored["subjects"]
        if s["authority_subject"]["kind"] == "creative_entity"
        and s["authority_subject"]["id"] not in dep_entity_ids})
    if missing_ce:
        issues.append({"code": "PRODUCTION_WORLD_ENTITY_DEPENDENCY_REQUIRED",
                       "missing_entity_ids": missing_ce})

    # 8-9. M10 agreement — the binding never overrides M10's resolution
    if m10_spatial_result is None or m10_spatial_result.pack is None:
        issues.append({"code": "PRODUCTION_WORLD_SPATIAL_CONTEXT_REQUIRED"})
    else:
        m10_world = m10_spatial_result.pack["spatial_world"]
        if (m10_world["spatial_world_revision_id"]
                != stored["spatial_world_revision_id"]
                or m10_world["spatial_world_revision_hash"]
                != stored["spatial_world_revision_hash"]):
            issues.append({
                "code": "PRODUCTION_WORLD_SPATIAL_REVISION_MISMATCH",
                "m10": {
                    "spatial_world_revision_id":
                        m10_world["spatial_world_revision_id"],
                    "spatial_world_revision_hash":
                        m10_world["spatial_world_revision_hash"]},
                "binding": {
                    "spatial_world_revision_id":
                        stored["spatial_world_revision_id"],
                    "spatial_world_revision_hash":
                        stored["spatial_world_revision_hash"]}})

    # 10-12. PI state + staging for the EXACT bound subject set only
    subjects = [(stored["composition_id"], s["occurrence_id"])
                for s in stored["subjects"]]
    pi_features = await resolve_pi_feature_state(
        conn, shot_id=shot_id, subjects=subjects)
    if not pi_features["assigned"] and pi_features[
            "relevant_temporal_data"]:
        issues.append({"code": "NARRATIVE_CONTEXT_REQUIRED"})
        feature_states: list[dict] = []
        spatial_states: list[dict] = []
        pi_staging = {"assigned": False}
    else:
        feature_states = _feature_pack_states(
            pi_features["states"], stored["composition_id"])
        world_row = (
            await conn.execute(
                text(
                    "SELECT st.spatial_world_id FROM "
                    "spatial_world_revisions r JOIN spatial_world_states st "
                    "ON st.id = r.spatial_world_state_id WHERE r.id = :r"),
                {"r": stored["spatial_world_revision_id"]},
            )
        ).first()
        if world_row is None:
            raise internal_invariant(
                "binding pins a SpatialWorldRevision with no owning state")
        pi_staging = await resolve_pi_staging(
            conn, shot_id=shot_id,
            spatial_world_id=world_row.spatial_world_id, subjects=subjects)
        spatial_states = _spatial_pack_states(
            pi_staging["states"], stored["composition_id"])
        missing_required = [a for a in pi_staging.get("absent", [])
                            if a["requirement"] == "required"]
        if missing_required:
            issues.append({
                "code": "PRODUCTION_INSTANCE_TRACK_STATE_REQUIRED",
                "missing": [{"occurrence_id": a["owner_id"],
                             "production_instance_track_id": a["track_id"]}
                            for a in missing_required]})

    ready = not issues
    pack = None
    pwhash = None
    audit_ids: tuple = ()
    if ready:
        pack = build_production_world_pack(
            binding_id=binding_id, binding_hash=stored["binding_hash"],
            binding_value=stored_value,
            feature_states=feature_states,
            spatial_states=spatial_states)
        pwhash = production_world_hash(pack)
        audit_ids = tuple(
            w["source_transition_id"] for w in sorted(
                pi_features["states"],
                key=lambda w: (w["owner_id"], w["feature_kind"],
                               w["feature_id"])))
    return ProductionWorldOutcome(
        shot_id=shot_id, selected=True, ready=ready,
        binding_id=binding_id, binding_hash=stored["binding_hash"],
        binding_current_complete=complete,
        stale_details=tuple(stale_details),
        issues=tuple(issues), pack=pack, production_world_hash=pwhash,
        feature_source_transition_ids=audit_ids)


def _feature_pack_states(states: list[dict],
                          composition_id: str) -> list[dict]:
    """§16.2 order + §16.1 shape; source_transition_id is audit-only and
    excluded from the semantic value exactly as M7 does (§16.4)."""
    ordered = sorted(states, key=lambda s: (s["owner_id"], s["feature_kind"],
                                            s["feature_id"]))
    return [
        {
            "composition_id": composition_id,
            "occurrence_id": s["owner_id"],
            "feature_id": s["feature_id"],
            "feature_key": s["feature_key"],
            "feature_kind": s["feature_kind"],
            "value_type": s["value_type"],
            "unit": s["unit"],
            "value": _json.loads(s["value_json"]),
            "value_hash": s["value_hash"],
            "source_anchor": {
                "anchor_type": s["source_anchor_type"],
                "anchor_id": s["source_anchor_id"],
                "boundary": s["source_boundary"],
            },
        }
        for s in ordered]


def _spatial_pack_states(states: list[dict],
                          composition_id: str) -> list[dict]:
    ordered = sorted(states, key=lambda s: (s["owner_id"], s["track_id"]))
    return [
        {
            "composition_id": composition_id,
            "occurrence_id": s["owner_id"],
            "production_instance_track_id": s["track_id"],
            "requirement": s["requirement"],
            "transform": {
                "translation_mm": [s["x_mm"], s["y_mm"], s["z_mm"]],
                "rotation_udeg": [s["yaw_udeg"], s["pitch_udeg"],
                                  s["roll_udeg"]],
            },
            "source_transition": {
                "transition_id": s["source_transition_id"],
                "anchor_type": s["source_anchor_type"],
                "anchor_id": s["source_anchor_id"],
                "boundary": s["source_boundary"],
            },
        }
        for s in ordered]


def require_production_world_ready(outcome: ProductionWorldOutcome) -> None:
    """Strict capture gate (§15): raise the first stable blocker in the
    frozen precedence; inspection surfaces the full ordered set instead."""
    if outcome.ready:
        return
    order = ("PRODUCTION_WORLD_BINDING_STALE",
             "PRODUCTION_WORLD_SPATIAL_CONTEXT_REQUIRED",
             "PRODUCTION_WORLD_SPATIAL_REVISION_MISMATCH",
             "PRODUCTION_WORLD_ENTITY_DEPENDENCY_REQUIRED",
             "NARRATIVE_CONTEXT_REQUIRED",
             "PRODUCTION_INSTANCE_TRACK_STATE_REQUIRED",
             "PRODUCTION_WORLD_SELECTION_CONFLICT")
    for code in order:
        for issue in outcome.issues:
            if issue["code"] != code:
                continue
            if code == "PRODUCTION_WORLD_BINDING_STALE":
                raise _stale_binding({
                    "stale_details": issue["stale_details"]})
            if code == "PRODUCTION_WORLD_SPATIAL_CONTEXT_REQUIRED":
                raise _spatial_context_required(outcome.shot_id)
            if code == "PRODUCTION_WORLD_SPATIAL_REVISION_MISMATCH":
                raise _revision_mismatch(outcome.shot_id, issue)
            if code == "PRODUCTION_WORLD_ENTITY_DEPENDENCY_REQUIRED":
                raise _entity_dependency_required(
                    outcome.shot_id, issue["missing_entity_ids"])
            if code == "NARRATIVE_CONTEXT_REQUIRED":
                raise _narrative_context_required(outcome.shot_id)
            if code == "PRODUCTION_INSTANCE_TRACK_STATE_REQUIRED":
                raise _pi_track_state_required(issue["missing"])
            if code == "PRODUCTION_WORLD_SELECTION_CONFLICT":
                raise SoloRingError(
                    ErrorCode.PRODUCTION_WORLD_SELECTION_CONFLICT,
                    "the selected binding belongs to another Project",
                    status_code=409)
    raise internal_invariant(
        f"production-world outcome for {outcome.shot_id} is not ready but "
        "no ordered blocker was found")
