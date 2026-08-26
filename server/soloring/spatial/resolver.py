"""M10D-2/3 — ONE complete current spatial resolver (M10D plan §§16-38).

Composes, on the caller's coherent connection and from exact M7 inputs:
applicable-world selection (frozen §22), exact Location-revision →
SpatialWorldState → approved immutable SpatialWorldRevision (verified
reader), fixed/Track placement authority, fixed EntityRevision
consistency, M10C random-access staging (reused, never duplicated),
current-duration plan revalidation, blocking t0 agreement, explicit
Shot/end handoff, arbitrary-precision axis-side enforcement, and the
canonical SpatialContinuityPack + spatial_continuity_hash.

Corruption raises INTERNAL_INVARIANT_VIOLATION immediately; issue rows
represent legitimate unresolved production state only, accumulated
prerequisite-aware (§35.1) and ordered by frozen precedence (§36).
"""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from soloring.domain.canonical import canonical_hash
from soloring.errors import ErrorCode, SoloRingError, internal_invariant
from soloring.spatial import schemas as S
from soloring.spatial.revisions import load_verified_world_revision
from soloring.spatial.staging import resolve_effective_staging

# frozen issue precedence ranks (§35)
RANK = {
    "world_selection": 1,
    "world_state": 2,
    "world_approval": 3,
    "placement": 4,
    "entity_revision": 5,
    "track_requirement": 6,
    "plan": 7,
    "blocking": 7,
    "axis": 8,
}


@dataclass(frozen=True)
class SpatialIssue:
    code: str
    layer: str
    message: str
    details: Mapping[str, object] = field(default_factory=dict)

    def order_key(self) -> tuple:
        d = dict(self.details)
        return (RANK[self.layer], str(d.get("entity_id", "")),
                str(d.get("spatial_world_id", "")),
                str(d.get("spatial_track_id", "")),
                str(d.get("spatial_axis_id", "")))


@dataclass(frozen=True)
class SpatialResolutionOutcome:
    shot_id: str
    ready: bool
    pack: dict | None
    spatial_continuity_hash: str | None
    issues: tuple[SpatialIssue, ...]
    selected_world: dict | None = None
    approved_world_revision: dict | None = None
    staging: object | None = None
    plan: dict | None = None
    plan_hash: str | None = None
    axis_status: dict | None = None


def _issue(code: ErrorCode | str, layer: str, message: str,
           **details) -> SpatialIssue:
    return SpatialIssue(code=str(code), layer=layer, message=message,
                        details=details)


def require_spatial_ready(outcome: SpatialResolutionOutcome) -> None:
    """Strict capture gate: raise the first blocker under frozen
    precedence, preserving the semantically reachable issue set."""
    if outcome.ready:
        return
    ordered = sorted(outcome.issues, key=lambda i: i.order_key())
    first = ordered[0]
    raise SoloRingError(
        first.code, first.message, status_code=409,
        details={"issues": [
            {"code": i.code, "layer": i.layer, "message": i.message,
             "details": dict(i.details)} for i in ordered]})


async def resolve_spatial_continuity(
    conn: AsyncConnection, *, shot_id: str,
    resolved_dependencies: Sequence,
) -> SpatialResolutionOutcome:
    """The ONE complete current resolver. ``resolved_dependencies`` are
    the exact M7 semantic values resolved in this same coherent read;
    the resolver never re-queries current EntityRevisions."""
    shot = (await conn.execute(text(
        "SELECT id, project_id, duration_ms, deleted_at FROM shots "
        "WHERE id = :s"), {"s": shot_id})).mappings().first()
    if shot is None or shot["deleted_at"] is not None:
        raise SoloRingError(ErrorCode.SHOT_NOT_FOUND,
                            f"Shot {shot_id} not found.", status_code=404)
    deps = {d.entity_id: d.entity_revision_id for d in resolved_dependencies}

    # ---- layer 1: applicable-world selection (frozen §22) ----------
    required_worlds = [dict(r) for r in (await conn.execute(text(
        "SELECT id, requirement, location_entity_id, project_id FROM "
        "spatial_worlds WHERE deleted_at IS NULL AND requirement = "
        "'required' AND location_entity_id IN (SELECT entity_id FROM "
        "shot_entity_dependencies WHERE shot_id = :s)"),
        {"s": shot_id})).mappings().all()] if deps else []

    plan_row = (await conn.execute(text(
        "SELECT plan_json, plan_hash FROM shot_spatial_plans "
        "WHERE shot_id = :s"), {"s": shot_id})).mappings().first()

    issues: list[SpatialIssue] = []

    if len(required_worlds) > 1:
        issues.append(_issue(
            ErrorCode.SPATIAL_CONTEXT_AMBIGUOUS, "world_selection",
            "More than one required SpatialWorld applies to this Shot.",
            spatial_world_id=required_worlds[0]["id"]))
        return _outcome(shot_id, issues)

    # current-duration revalidation of the STORED canonical plan (§11.1)
    parsed_plan = None
    parsed_hash = None
    if plan_row is not None:
        try:
            parsed_plan = S.parse_shot_plan(
                json.loads(plan_row["plan_json"]),
                duration_ms=shot["duration_ms"])
            parsed_hash = S.plan_hash(parsed_plan)
            # stored bytes/hash integrity (P0-2): the plan service
            # persists canonical bytes + their server-derived hash; any
            # disagreement is direct-DB corruption, never re-normalized
            from soloring.domain.canonical import (
                canonical_json_str as _cjs,
            )
            if _cjs(parsed_plan) != plan_row["plan_json"] or \
                    parsed_hash != plan_row["plan_hash"]:
                raise internal_invariant(
                    f"Stored ShotSpatialPlan for shot {shot_id}: "
                    "plan_json/plan_hash disagree with the re-canonicalized"
                    " value — persisted corruption.")
        except S.SchemaInvalid as exc:
            issues.append(_issue(
                ErrorCode.SPATIAL_SHOT_PLAN_INVALID, "plan",
                f"Stored ShotSpatialPlan is invalid in the current Shot "
                f"context: {exc.message}"))
            if not required_worlds:
                # optional selection derives from the unparseable plan —
                # no world can be selected; deeper layers are suppressed
                return _outcome(shot_id, issues)
            selected = required_worlds[0]
            # a required world still selects itself; continue evaluation
            return await _resolve_with_world(
                conn, shot_id, shot, deps, selected, None, None, issues)
        except Exception as exc:
            raise internal_invariant(
                f"Stored ShotSpatialPlan for shot {shot_id} is not "
                f"readable canonical authority: {exc}") from exc

    if required_worlds:
        selected = required_worlds[0]
        if plan_row is None:
            issues.append(_issue(
                ErrorCode.SPATIAL_SHOT_PLAN_REQUIRED, "world_selection",
                "A required SpatialWorld applies but this Shot has no "
                "ShotSpatialPlan.", spatial_world_id=selected["id"]))
            return await _resolve_with_world(
                conn, shot_id, shot, deps, selected, None, None, issues)
        if parsed_plan["spatial_world_id"] != selected["id"]:
            issues.append(_issue(
                ErrorCode.SPATIAL_SHOT_PLAN_INVALID, "world_selection",
                "The ShotSpatialPlan selects a world other than the one "
                "required SpatialWorld.", spatial_world_id=selected["id"]))
            return await _resolve_with_world(
                conn, shot_id, shot, deps, selected, None, None, issues)
    elif plan_row is not None and parsed_plan is not None:
        world = (await conn.execute(text(
            "SELECT id, requirement, location_entity_id, project_id, "
            "deleted_at FROM spatial_worlds WHERE id = :w"),
            {"w": parsed_plan["spatial_world_id"]})).mappings().first()
        if world is None or world["deleted_at"] is not None or \
                world["project_id"] != shot["project_id"]:
            issues.append(_issue(
                ErrorCode.SPATIAL_SHOT_PLAN_INVALID, "world_selection",
                "The ShotSpatialPlan selects a missing, deleted, or "
                "foreign-Project SpatialWorld."))
            return _outcome(shot_id, issues)
        if world["location_entity_id"] not in deps:
            issues.append(_issue(
                ErrorCode.SPATIAL_SHOT_PLAN_INVALID, "world_selection",
                "The selected world's Location Entity ceased to be a "
                "current semantic dependency.",
                spatial_world_id=world["id"]))
            return _outcome(shot_id, issues)
        selected = dict(world)
    else:
        # zero required worlds + no current plan (§18.6)
        return SpatialResolutionOutcome(
            shot_id=shot_id, ready=True, pack=None,
            spatial_continuity_hash=None, issues=())

    return await _resolve_with_world(
        conn, shot_id, shot, deps, selected, parsed_plan, parsed_hash,
        issues)


def _outcome(shot_id: str, issues: list[SpatialIssue],
             **kw) -> SpatialResolutionOutcome:
    ordered = tuple(sorted(issues, key=lambda i: i.order_key()))
    return SpatialResolutionOutcome(
        shot_id=shot_id, ready=not ordered, pack=None,
        spatial_continuity_hash=None, issues=ordered, **kw)


async def _resolve_with_world(conn, shot_id, shot, deps, selected,
                              parsed_plan, parsed_hash,
                              issues) -> SpatialResolutionOutcome:
    # ---- layer 2/3: exact state + approved revision (§19) ----------
    location_rev = deps.get(selected["location_entity_id"])
    if location_rev is None:
        # dependency-set race upstream of M7 coherence; not reachable via
        # the composed read, fail explicit rather than fabricate
        raise internal_invariant(
            "Selected world's Location Entity has no resolved semantic "
            "revision on this snapshot.")
    state = (await conn.execute(text(
        "SELECT id, approved_revision_id FROM spatial_world_states "
        "WHERE spatial_world_id = :w AND location_entity_revision_id = :r"),
        {"w": selected["id"], "r": location_rev})).mappings().first()
    if state is None:
        issues.append(_issue(
            ErrorCode.SPATIAL_WORLD_STATE_REQUIRED, "world_state",
            "No SpatialWorldState exists for the exact current Location "
            "EntityRevision.", spatial_world_id=selected["id"]))
        return _outcome(shot_id, issues, selected_world=selected,
                        plan=parsed_plan, plan_hash=parsed_hash)
    if state["approved_revision_id"] is None:
        issues.append(_issue(
            ErrorCode.SPATIAL_WORLD_APPROVAL_REQUIRED, "world_approval",
            "The exact SpatialWorldState has no approved "
            "SpatialWorldRevision.",
            spatial_world_id=selected["id"]))
        return _outcome(shot_id, issues, selected_world=selected,
                        plan=parsed_plan, plan_hash=parsed_hash)

    verified = await load_verified_world_revision(
        conn, spatial_world_state_id=state["id"],
        spatial_world_revision_id=state["approved_revision_id"])
    snapshot = verified["snapshot"]

    # ---- layer 4: placement authority (§21) ------------------------
    fixed_by_entity: dict[str, list[dict]] = {}
    for fr in snapshot["frames"]:
        if fr["bound_entity_id"] is not None:
            fixed_by_entity.setdefault(fr["bound_entity_id"], []).append(fr)
    conflicted_entities: set[str] = set()
    for eid, frames in fixed_by_entity.items():
        if len(frames) > 1:
            conflicted_entities.add(eid)
            issues.append(_issue(
                ErrorCode.SPATIAL_ENTITY_PLACEMENT_CONFLICT, "placement",
                "Entity has multiple fixed-frame placements in the "
                "approved world revision.", entity_id=eid,
                spatial_world_id=selected["id"]))

    # ---- M10C staging reuse (§23) ----------------------------------
    staging = await resolve_effective_staging(
        conn, shot_id=shot_id, spatial_world_id=selected["id"],
        resolved_entity_revisions=deps)
    # APPLICABLE Track authority (P0-1): a Track is a competing placement
    # authority for its Entity even when its current temporal state is
    # absent (winning clear, or no eligible transition) — states ∪ absent
    applicable_entities = (
        {s.entity_id for s in staging.states}
        | {a.entity_id for a in staging.absent}
    )
    for eid in sorted(applicable_entities & set(fixed_by_entity)):
        conflicted_entities.add(eid)
        issues.append(_issue(
            ErrorCode.SPATIAL_ENTITY_PLACEMENT_CONFLICT, "placement",
            "Entity has both a fixed-frame placement and an applicable "
            "SpatialTrack in the selected world.", entity_id=eid,
            spatial_world_id=selected["id"]))

    # ---- layer 5: fixed EntityRevision consistency (§22) -----------
    # (suppressed for placement-conflicted entities — §35.1)
    for eid, frames in sorted(fixed_by_entity.items()):
        if eid in conflicted_entities or eid not in deps:
            continue
        for fr in frames:
            if fr["bound_entity_revision_id"] != deps[eid]:
                issues.append(_issue(
                    ErrorCode.SPATIAL_ENTITY_REVISION_MISMATCH,
                    "entity_revision",
                    "Fixed-frame bound EntityRevision disagrees with the "
                    "exact semantic EntityRevision.", entity_id=eid,
                    spatial_world_id=selected["id"]))
                break

    # ---- layer 6: required track state (§24) -----------------------
    for a in staging.absent:
        if a.requirement == "required":
            issues.append(_issue(
                ErrorCode.SPATIAL_TRACK_STATE_REQUIRED,
                "track_requirement",
                "Required SpatialTrack has no effective set state at this "
                "Shot/start.", entity_id=a.entity_id,
                spatial_track_id=a.spatial_track_id, reason=a.reason))

    # ---- layers 7/8: plan, blocking, axis (§26-30) ------------------
    handoff_status = []
    if parsed_plan is not None:
        staged_by_track = {s.spatial_track_id: s for s in staging.states}
        for entry in parsed_plan["blocking"]:
            tid = entry["spatial_track_id"]
            st = staged_by_track.get(tid)
            if st is None:
                issues.append(_issue(
                    ErrorCode.SPATIAL_BLOCKING_STATE_MISMATCH, "blocking",
                    "Blocking entry references a Track with no effective "
                    "staged state at Shot/start.",
                    spatial_track_id=tid))
                continue
            t0 = entry["keyframes"][0]["transform"]
            eff = {"translation_mm": [st.x_mm, st.y_mm, st.z_mm],
                   "rotation_udeg": [st.yaw_udeg, st.pitch_udeg,
                                     st.roll_udeg]}
            if t0 != eff:
                issues.append(_issue(
                    ErrorCode.SPATIAL_BLOCKING_STATE_MISMATCH, "blocking",
                    "Blocking t0 transform does not exactly equal the "
                    "effective persistent staging transform.",
                    spatial_track_id=tid))

        # explicit Shot/end handoff (§25/§27) — one set-oriented query
        blocking_tracks = [b["spatial_track_id"]
                           for b in parsed_plan["blocking"]]
        if blocking_tracks:
            ph = ", ".join(f":t{i}" for i in range(len(blocking_tracks)))
            params = {f"t{i}": t for i, t in enumerate(blocking_tracks)}
            params["s"] = shot_id
            end_events = [dict(r) for r in (await conn.execute(text(
                f"SELECT spatial_track_id, operation, x_mm, y_mm, z_mm, "
                f"yaw_udeg, pitch_udeg, roll_udeg FROM "
                f"spatial_transitions WHERE deleted_at IS NULL AND "
                f"anchor_type = 'shot' AND anchor_id = :s AND boundary = "
                f"'end' AND spatial_track_id IN ({ph})"), params)
            ).mappings().all()]
            by_track: dict[str, list[dict]] = {}
            for ev in end_events:
                by_track.setdefault(ev["spatial_track_id"], []).append(ev)
            for tid, evs in by_track.items():
                if len(evs) > 1:
                    raise internal_invariant(
                        f"Multiple active Shot/end transitions for track "
                        f"{tid} despite uniqueness constraints.")
                ev = evs[0]
                if ev["operation"] != "set":
                    handoff_status.append(
                        {"spatial_track_id": tid, "status": "clear"})
                    continue
                if shot["duration_ms"] is None:
                    issues.append(_issue(
                        ErrorCode.SPATIAL_BLOCKING_STATE_MISMATCH,
                        "blocking",
                        "Shot/end set exists with blocking but the Shot "
                        "duration is NULL.", spatial_track_id=tid))
                    continue
                entry = next(b for b in parsed_plan["blocking"]
                             if b["spatial_track_id"] == tid)
                final = [k for k in entry["keyframes"]
                         if k["time_ms"] == shot["duration_ms"]]
                if not final:
                    issues.append(_issue(
                        ErrorCode.SPATIAL_BLOCKING_STATE_MISMATCH,
                        "blocking",
                        "Shot/end set with blocking requires a keyframe "
                        "exactly at Shot.duration_ms.",
                        spatial_track_id=tid))
                    continue
                tf = final[0]["transform"]
                if tf != {"translation_mm": [ev["x_mm"], ev["y_mm"],
                                             ev["z_mm"]],
                          "rotation_udeg": [ev["yaw_udeg"],
                                            ev["pitch_udeg"],
                                            ev["roll_udeg"]]}:
                    issues.append(_issue(
                        ErrorCode.SPATIAL_BLOCKING_STATE_MISMATCH,
                        "blocking",
                        "Final blocking keyframe transform does not "
                        "exactly equal the Shot/end transition.",
                        spatial_track_id=tid))
                    continue
                handoff_status.append(
                    {"spatial_track_id": tid, "status": "exact_match"})

    axis_status = None
    if parsed_plan is not None and \
            parsed_plan["axis_constraint"] is not None:
        axis = parsed_plan["axis_constraint"]
        snap_axes = {a["spatial_axis_id"]: a for a in snapshot["axes"]}
        snap_axis = snap_axes.get(axis["spatial_axis_id"])
        if snap_axis is None:
            issues.append(_issue(
                ErrorCode.SPATIAL_SHOT_PLAN_INVALID, "axis",
                "axis_constraint is absent from the exact approved "
                "SpatialWorldRevision.",
                spatial_axis_id=axis["spatial_axis_id"]))
        else:
            frames_by_id = {f["spatial_frame_id"]: f
                            for f in snapshot["frames"]}
            a_fr = frames_by_id[snap_axis["a_frame_id"]]
            b_fr = frames_by_id[snap_axis["b_frame_id"]]
            ax_, az_ = a_fr["transform"]["translation_mm"][0], \
                a_fr["transform"]["translation_mm"][2]
            bx_, bz_ = b_fr["transform"]["translation_mm"][0], \
                b_fr["transform"]["translation_mm"][2]
            if ax_ == bx_ and az_ == bz_:
                # coincident geometry inside VERIFIED immutable authority
                raise internal_invariant(
                    "Approved SpatialWorldRevision axis has coincident "
                    "X/Z endpoints — degenerate side evaluation is "
                    "corruption, not a readiness defect.")
            violating = []
            for kf in parsed_plan["camera"]["keyframes"]:
                cx_, cz_ = kf["transform"]["translation_mm"][0], \
                    kf["transform"]["translation_mm"][2]
                cross = ((bx_ - ax_) * (cz_ - az_) -
                         (bz_ - az_) * (cx_ - ax_))
                ok = cross > 0 if axis["camera_side"] == "positive" \
                    else cross < 0
                if not ok:
                    violating.append(kf["time_ms"])
            axis_status = {
                "spatial_axis_id": axis["spatial_axis_id"],
                "camera_side": axis["camera_side"],
                "violating_keyframe_times_ms": violating,
            }
            if violating:
                issues.append(_issue(
                    ErrorCode.SPATIAL_AXIS_CONSTRAINT_VIOLATION, "axis",
                    "Camera keyframe(s) violate the declared axis side.",
                    spatial_axis_id=axis["spatial_axis_id"],
                    times_ms=violating))

    ordered = tuple(sorted(issues, key=lambda i: i.order_key()))
    if ordered:
        return SpatialResolutionOutcome(
            shot_id=shot_id, ready=False, pack=None,
            spatial_continuity_hash=None, issues=ordered,
            selected_world=selected, approved_world_revision=verified,
            staging=staging, plan=parsed_plan, plan_hash=parsed_hash,
            axis_status=axis_status)

    # ---- ready: build the canonical pack (§32-34) ------------------
    pack = {
        "schema_version": 1,
        "spatial_world": {
            "spatial_world_id": selected["id"],
            "requirement": selected["requirement"],
            "spatial_world_state_id": state["id"],
            "spatial_world_revision_id": verified["id"],
            "spatial_world_revision_hash": verified["snapshot_hash"],
            "location_entity_id": selected["location_entity_id"],
            "location_entity_revision_id": location_rev,
            "world_snapshot": snapshot,
        },
        "staging": [
            {"spatial_track_id": s.spatial_track_id,
             "entity_id": s.entity_id,
             "entity_revision_id": s.entity_revision_id,
             "requirement": s.requirement,
             "transform": {
                 "translation_mm": [s.x_mm, s.y_mm, s.z_mm],
                 "rotation_udeg": [s.yaw_udeg, s.pitch_udeg,
                                   s.roll_udeg]},
             "source_transition": {
                 "spatial_transition_id": s.source_transition_id,
                 "anchor_type": s.source_anchor_type,
                 "anchor_id": s.source_anchor_id,
                 "boundary": s.source_boundary}}
            for s in staging.states],
        "shot_plan": parsed_plan,
    }
    canonical_pack = S.parse_continuity_pack(pack)
    return SpatialResolutionOutcome(
        shot_id=shot_id, ready=True, pack=canonical_pack,
        spatial_continuity_hash=canonical_hash(canonical_pack),
        issues=(), selected_world=selected,
        approved_world_revision=verified, staging=staging,
        plan=parsed_plan, plan_hash=parsed_hash, axis_status=axis_status)


__all__ = ["resolve_spatial_continuity", "require_spatial_ready",
           "SpatialResolutionOutcome", "SpatialIssue"]
