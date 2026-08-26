"""M10C-3 random-access effective temporal staging (M10C plan §8).

ONE temporal-staging subresolver. Given one explicitly requested
SpatialWorld, one target Shot, and the exact semantic EntityRevisions
already resolved on the caller's snapshot, it derives the effective
movable-Entity placements at Shot/start directly from explicit active
transitions ranked through the canonical M7 narrative ordering —
frozen §18 steps 1-10 + 12. It never replays prior Shots, never opens
its own session, and never re-resolves EntityRevisions. The fixed-frame
placement-conflict step (§18-11) needs the approved world revision and
is M10D composition, explicitly deferred.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from soloring.domain.canonical import canonical_json_bytes
from soloring.errors import ErrorCode, SoloRingError, internal_invariant
from soloring.narrative.order import load_narrative_ordering

_REQUIREMENTS = ("required", "optional")


@dataclass(frozen=True)
class EffectiveSpatialTrackState:
    spatial_track_id: str
    entity_id: str
    entity_revision_id: str
    requirement: str
    x_mm: int
    y_mm: int
    z_mm: int
    yaw_udeg: int
    pitch_udeg: int
    roll_udeg: int
    source_transition_id: str
    source_anchor_type: str
    source_anchor_id: str
    source_boundary: str

    def projection(self) -> dict:
        """One canonical capture-ready staging projection entry (§5.2)."""
        return {
            "spatial_track_id": self.spatial_track_id,
            "entity_id": self.entity_id,
            "entity_revision_id": self.entity_revision_id,
            "requirement": self.requirement,
            "transform": {
                "translation_mm": [self.x_mm, self.y_mm, self.z_mm],
                "rotation_udeg": [
                    self.yaw_udeg, self.pitch_udeg, self.roll_udeg],
            },
            "source_transition_id": self.source_transition_id,
            "source_anchor_type": self.source_anchor_type,
            "source_anchor_id": self.source_anchor_id,
            "source_boundary": self.source_boundary,
        }


@dataclass(frozen=True)
class AbsentSpatialTrack:
    """An applicable track with no effective set at the target (winning
    clear or no eligible transition). Not part of the canonical staging
    bytes — readiness inspection only (§9.2)."""
    spatial_track_id: str
    entity_id: str
    entity_revision_id: str
    requirement: str
    reason: str  # "clear" | "no_eligible_transition"


@dataclass(frozen=True)
class StagingResolutionOutcome:
    shot_id: str
    spatial_world_id: str
    assigned: bool
    relevant_transition_data: bool
    states: tuple[EffectiveSpatialTrackState, ...]
    absent: tuple[AbsentSpatialTrack, ...] = ()


def canonical_staging_bytes(
        states: tuple[EffectiveSpatialTrackState, ...]) -> bytes:
    """Canonical byte serialization of the sorted staging projection.

    States must already be in the frozen (entity_id, spatial_track_id)
    order; this function never re-sorts (callers prove order identity).
    Absent tracks never enter the bytes.
    """
    return canonical_json_bytes([s.projection() for s in states])


def require_track_states(outcome: StagingResolutionOutcome) -> None:
    """Strict-consumer readiness gate (§9.2): raise the frozen
    SPATIAL_TRACK_STATE_REQUIRED while any applicable required track has
    no effective set. Inspection projections surface the same condition
    structurally via ``outcome.absent`` instead."""
    missing = [a for a in outcome.absent if a.requirement == "required"]
    if missing:
        raise SoloRingError(
            ErrorCode.SPATIAL_TRACK_STATE_REQUIRED,
            "Required SpatialTrack(s) have no effective set state at this "
            "Shot/start: "
            + ", ".join(
                f"{a.entity_id}:{a.spatial_track_id}" for a in missing),
            status_code=409,
            details={"missing": [
                {"spatial_track_id": a.spatial_track_id,
                 "entity_id": a.entity_id} for a in missing]})


def _shot_not_found(shot_id: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id} not found.",
        status_code=404)


def narrative_context_required(shot_id: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.NARRATIVE_CONTEXT_REQUIRED,
        f"Shot {shot_id} has relevant temporal staging data but no "
        "resolvable narrative position (unassigned).",
        status_code=409,
        details={"shot_id": shot_id})


async def resolve_effective_staging(
    conn: AsyncConnection, *, shot_id: str, spatial_world_id: str,
    resolved_entity_revisions: Mapping[str, str],
) -> StagingResolutionOutcome:
    """Effective staging at target Shot/start on the caller's snapshot.

    ``resolved_entity_revisions`` maps dependent Entity ID → the exact
    semantic EntityRevision ID resolved inside this same coherent read;
    this resolver never queries current revisions itself (§8.3).
    """
    shot = (await conn.execute(text(
        "SELECT project_id, deleted_at, scene_id FROM shots "
        "WHERE id = :sid"), {"sid": shot_id})).first()
    if shot is None or shot.deleted_at is not None:
        raise _shot_not_found(shot_id)
    assigned = shot.scene_id is not None

    world = (await conn.execute(text(
        "SELECT project_id FROM spatial_worlds WHERE id = :w "
        "AND deleted_at IS NULL"), {"w": spatial_world_id})).first()
    if world is None:
        raise SoloRingError(
            ErrorCode.SPATIAL_WORLD_INVALID,
            f"SpatialWorld {spatial_world_id} not found or deleted.",
            status_code=404)
    if world.project_id != shot.project_id:
        raise SoloRingError(
            ErrorCode.SPATIAL_TRACK_INVALID,
            "Requested SpatialWorld belongs to another Project.",
            status_code=422)

    # dedupe identities, retaining exactly one supplied revision each
    revisions = dict(resolved_entity_revisions)
    dep_ids = tuple(revisions.keys())

    tracks: list[dict] = []
    transitions: list[dict] = []
    if dep_ids:
        e_ph = ", ".join(f":e{i}" for i in range(len(dep_ids)))
        e_params = {f"e{i}": e for i, e in enumerate(dep_ids)}
        tracks = [dict(r) for r in (await conn.execute(text(
            f"SELECT id, entity_id, requirement FROM spatial_tracks "
            f"WHERE spatial_world_id = :w AND deleted_at IS NULL "
            f"AND entity_id IN ({e_ph})"),
            {"w": spatial_world_id, **e_params})).mappings().all()]
        for t in tracks:
            if t["requirement"] not in _REQUIREMENTS:
                raise internal_invariant(
                    f"SpatialTrack {t['id']} carries requirement "
                    f"{t['requirement']!r} outside the frozen domain.")
        if tracks:
            t_ph = ", ".join(f":t{i}" for i in range(len(tracks)))
            t_params = {f"t{i}": t["id"] for i, t in enumerate(tracks)}
            transitions = [dict(r) for r in (await conn.execute(text(
                f"SELECT id, spatial_track_id, anchor_type, anchor_id, "
                f"boundary, operation, x_mm, y_mm, z_mm, yaw_udeg, "
                f"pitch_udeg, roll_udeg FROM spatial_transitions "
                f"WHERE deleted_at IS NULL AND spatial_track_id IN "
                f"({t_ph})"), t_params)).mappings().all()]

    relevant_transition_data = bool(transitions)

    if not assigned:
        if relevant_transition_data:
            # the frozen strict failure at the production semantic seam
            # (§8.5 step 6 / matrix 42): relevant temporal staging data
            # exists but the Shot has no narrative position. Inspection
            # wrappers (preview_staging) may catch and project this
            # condition structurally; the resolver itself fails closed.
            raise narrative_context_required(shot_id)
        # no relevant data: an unassigned Shot invents no blocker
        return StagingResolutionOutcome(
            shot_id=shot_id, spatial_world_id=spatial_world_id,
            assigned=False, relevant_transition_data=False,
            states=(), absent=())

    ordering = await load_narrative_ordering(conn, shot.project_id)
    try:
        target_rank = ordering.shot_start_rank(shot_id)
    except SoloRingError:
        raise internal_invariant(
            f"Assigned active shot {shot_id} missing from its Project's "
            "canonical ordering during staging resolution.")

    # rank every transition through the ordering; an anchor outside the
    # canonical stream is stored corruption (§8.7 discipline)
    by_track: dict[str, list] = {}
    for t in transitions:
        try:
            rank = ordering.rank_of(
                t["anchor_type"], t["anchor_id"], t["boundary"])
        except SoloRingError:
            raise internal_invariant(
                f"Active spatial transition {t['id']} anchored at "
                f"({t['anchor_type']}, {t['anchor_id']}, {t['boundary']}) "
                "is not present in the canonical ordering.")
        if rank <= target_rank:
            by_track.setdefault(t["spatial_track_id"], []).append((rank, t))

    track_by_id = {t["id"]: t for t in tracks}
    winners: list[EffectiveSpatialTrackState] = []
    absent: list[AbsentSpatialTrack] = []
    eligible_track_ids = set(by_track.keys())
    for tid, eligible in by_track.items():
        best_rank = max(r for r, _ in eligible)
        best = [t for r, t in eligible if r == best_rank]
        if len(best) != 1:
            raise internal_invariant(
                f"Ambiguous effective staging for track {tid}: "
                f"{len(best)} transitions share the winning rank — "
                "no ID/timestamp/UUID tie-breaking is permitted.")
        t = best[0]
        six = (t["x_mm"], t["y_mm"], t["z_mm"],
               t["yaw_udeg"], t["pitch_udeg"], t["roll_udeg"])
        track = track_by_id[tid]
        if t["operation"] == "clear":
            if any(v is not None for v in six):
                raise internal_invariant(
                    f"Stored clear transition {t['id']} carries non-NULL "
                    "transform columns.")
            absent.append(AbsentSpatialTrack(
                spatial_track_id=tid, entity_id=track["entity_id"],
                entity_revision_id=revisions[track["entity_id"]],
                requirement=track["requirement"], reason="clear"))
            continue  # canonical absence
        if t["operation"] != "set":
            raise internal_invariant(
                f"Stored transition {t['id']} has operation "
                f"{t['operation']!r} outside the set|clear domain.")
        if any(v is None for v in six):
            raise internal_invariant(
                f"Stored set transition {t['id']} has an incomplete "
                "transform.")
        winners.append(
            EffectiveSpatialTrackState(
                spatial_track_id=tid,
                entity_id=track["entity_id"],
                entity_revision_id=revisions[track["entity_id"]],
                requirement=track["requirement"],
                x_mm=six[0], y_mm=six[1], z_mm=six[2],
                yaw_udeg=six[3], pitch_udeg=six[4], roll_udeg=six[5],
                source_transition_id=t["id"],
                source_anchor_type=t["anchor_type"],
                source_anchor_id=t["anchor_id"],
                source_boundary=t["boundary"]))

    # applicable tracks with no eligible transition at all
    for t in tracks:
        if t["id"] not in eligible_track_ids:
            absent.append(AbsentSpatialTrack(
                spatial_track_id=t["id"], entity_id=t["entity_id"],
                entity_revision_id=revisions[t["entity_id"]],
                requirement=t["requirement"],
                reason="no_eligible_transition"))

    winners.sort(key=lambda s: (s.entity_id, s.spatial_track_id))
    absent.sort(key=lambda a: (a.entity_id, a.spatial_track_id))
    return StagingResolutionOutcome(
        shot_id=shot_id, spatial_world_id=spatial_world_id,
        assigned=True, relevant_transition_data=relevant_transition_data,
        states=tuple(winners), absent=tuple(absent))


async def preview_staging(session, *, spatial_world_id: str,
                          shot_id: str) -> dict:
    """The public staging-preview composition owner (M10C plan §10.3).

    ONE checked-out connection and ONE coherent read transaction for the
    whole composition: Shot verification → exact semantic dependency +
    EntityRevision resolution (continuity authority, fail-closed) →
    staging subresolver on the same connection → response projection.
    Never two sessions (§10.3 forbidden hybrid).
    """
    from soloring.continuity.snapshots import resolve_working_dependencies

    engine = session.bind
    async with engine.connect() as conn:
        await conn.exec_driver_sql("BEGIN")
        try:
            # Shot verification — this first read pins the snapshot
            shot = (await conn.execute(text(
                "SELECT project_id, deleted_at, scene_id, title FROM "
                "shots WHERE id = :sid"), {"sid": shot_id})).first()
            if shot is None or shot.deleted_at is not None:
                raise _shot_not_found(shot_id)
            # exact semantic inputs from the SAME snapshot; inherits the
            # semantic layer's fail-closed behavior for unresolvable rows
            deps = await resolve_working_dependencies(conn, shot_id)
            revisions = {d.entity_id: d.entity_revision_id for d in deps}
            narrative_blocked = False
            try:
                outcome = await resolve_effective_staging(
                    conn, shot_id=shot_id,
                    spatial_world_id=spatial_world_id,
                    resolved_entity_revisions=revisions)
            except SoloRingError as exc:
                if exc.code != ErrorCode.NARRATIVE_CONTEXT_REQUIRED:
                    raise  # invariant/corruption conditions propagate
                # the strict resolver raised the frozen condition; this
                # inspection projection surfaces it structurally (§10.4)
                outcome = None
                narrative_blocked = True
            if narrative_blocked:
                await conn.exec_driver_sql("COMMIT")
                return {
                    "shot_id": shot_id,
                    "spatial_world_id": spatial_world_id,
                    "assigned": False,
                    "relevant_transition_data": True,
                    "narrative_context_required": True,
                    "states": [],
                    "absent": [],
                }
            if revisions:
                n_ph = ", ".join(f":n{i}" for i in range(len(revisions)))
                n_params = {f"n{i}": e for i, e in
                            enumerate(revisions.keys())}
                names = {r["id"]: r["name"] for r in (
                    await conn.execute(text(
                        f"SELECT id, name FROM creative_entities "
                        f"WHERE id IN ({n_ph})"), n_params)
                ).mappings().all()}
            else:
                names = {}
            await conn.exec_driver_sql("COMMIT")
        except Exception:
            import contextlib
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise
    return {
        "shot_id": shot_id,
        "spatial_world_id": spatial_world_id,
        "assigned": outcome.assigned,
        "relevant_transition_data": outcome.relevant_transition_data,
        "narrative_context_required":
            (not outcome.assigned) and outcome.relevant_transition_data,
        "states": [
            {**s.projection(), "entity_name": names.get(s.entity_id)}
            for s in outcome.states],
        "absent": [
            {"spatial_track_id": a.spatial_track_id,
             "entity_id": a.entity_id,
             "entity_name": names.get(a.entity_id),
             "entity_revision_id": a.entity_revision_id,
             "requirement": a.requirement, "reason": a.reason}
            for a in outcome.absent],
    }


__all__ = ["resolve_effective_staging", "EffectiveSpatialTrackState",
           "AbsentSpatialTrack", "StagingResolutionOutcome",
           "canonical_staging_bytes", "require_track_states",
           "narrative_context_required", "preview_staging"]
