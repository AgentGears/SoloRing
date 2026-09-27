"""M17C-B PF-02: Shot-local Performance working mappings and readiness.

Frozen R4 §8–§9 laws. ``ShotPerformanceSegmentMapping`` is mutable
Shot intent (last committed PUT wins, §20.2); readiness is a read-time
PROJECTION that is never persisted as authority (§9.1). Dialogue-bound
mappings store the exact interval/anchor mechanically induced from the
paired ``ShotVocalSegmentMapping`` through the immutable revision vocal
binding — no epsilon, tolerance, or floating comparison (§8.3).
"""

from __future__ import annotations

from fractions import Fraction

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.domain.now import db_now
from soloring.errors import ErrorCode, SoloRingError, not_found
from soloring.performance import revision as revision_svc
from soloring.performance.m17c_binding import (
    verify_revision_sync_classification,
)
from soloring.performance.m17c_models import (
    PerformanceRevisionVocalBinding,
    ShotPerformanceSegmentMapping,
)
from soloring.performance.models import (
    PerformanceRevision,
    ShotVocalSegmentMapping,
    VocalPerformanceSelection,
)
from soloring.performance.temporal import (RationalError,
                                           canonical_rational)

READY = "READY"
STALE_VOCAL_SELECTION = "STALE_VOCAL_SELECTION"
BLOCKED_BINDING_INTEGRITY = "BLOCKED_BINDING_INTEGRITY"
BLOCKED_TIMING_MISMATCH = "BLOCKED_TIMING_MISMATCH"
BLOCKED_SUBJECT_OR_PROJECT = "BLOCKED_SUBJECT_OR_PROJECT"
BLOCKED_CHANNEL_CONFLICT = "BLOCKED_CHANNEL_CONFLICT"
BLOCKED_SHOT_DEPENDENCY = "BLOCKED_SHOT_DEPENDENCY"


def _invalid(message: str) -> SoloRingError:
    return SoloRingError(ErrorCode.PERFORMANCE_SHOT_MAPPING_INVALID,
                         message, status_code=422)


def _mismatch(message: str) -> SoloRingError:
    return SoloRingError(ErrorCode.PERFORMANCE_VOCAL_MAPPING_MISMATCH,
                         message, status_code=422)


def _fraction(num: int, den: int) -> Fraction:
    return Fraction(num, den)


def _pr_domain(pr) -> tuple[Fraction, Fraction]:
    return (_fraction(pr.temporal_start_num, pr.temporal_start_den),
            _fraction(pr.temporal_end_num, pr.temporal_end_den))


def _stored_interval(row) -> tuple[Fraction, Fraction]:
    return (_fraction(row.performance_start_num,
                      row.performance_start_den),
            _fraction(row.performance_end_num, row.performance_end_den))


def _shot_interval(row) -> tuple[Fraction, Fraction]:
    """The mapping's Shot-relative picture interval: the anchor is the
    Shot time of performance_start, so the segment occupies
    [anchor, anchor + (end - start)) in Shot time (frozen §8.1)."""
    anchor = _fraction(row.shot_anchor_num, row.shot_anchor_den)
    start, end = _stored_interval(row)
    return anchor, anchor + (end - start)


def _induced_interval(binding, vocal_mapping) -> tuple[Fraction, Fraction]:
    """frozen §8.3 exact induction through the immutable binding."""
    origin = _fraction(binding.performance_origin_num,
                       binding.performance_origin_den)
    rate = binding.sample_rate_hz
    s0 = binding.source_start_sample
    p0 = origin + Fraction(
        (vocal_mapping.source_start_sample - s0) * 1000, rate)
    p1 = origin + Fraction(
        (vocal_mapping.source_end_sample_exclusive - s0) * 1000, rate)
    return p0, p1


async def _dependency_ids(session, shot_id: str) -> set[str]:
    from soloring.continuity.models import ShotEntityDependency
    rows = (await session.execute(
        select(ShotEntityDependency.entity_id).where(
            ShotEntityDependency.shot_id == shot_id))).scalars().all()
    return set(rows)


async def put_shot_performance_segment_mapping(
        session: AsyncSession, settings, *, shot_id: str, position: int,
        performance_revision_id: str,
        performance_start_num: int, performance_start_den: int,
        performance_end_num: int, performance_end_den: int,
        shot_anchor_num: int, shot_anchor_den: int,
        vocal_mapping_position: int | None) -> ShotPerformanceSegmentMapping:
    from soloring.domain.models import Shot
    if position < 0:
        raise _invalid("position must be >= 0")
    shot = await session.get(Shot, shot_id)
    if shot is None:
        raise not_found(ErrorCode.SHOT_NOT_FOUND,
                        f"shot {shot_id!r} not found")
    if shot.duration_ms is None or shot.duration_ms <= 0:
        raise SoloRingError(ErrorCode.SHOT_DURATION_REQUIRED,
                            "Shot.duration_ms must be present and > 0 for "
                            "performance segment mapping", status_code=422)
    pr = await session.get(PerformanceRevision, performance_revision_id)
    if pr is None:
        raise not_found(ErrorCode.PERFORMANCE_REVISION_NOT_FOUND,
                        f"performance revision {performance_revision_id!r} "
                        "not found")

    # The M17C-A pair verifier proves classification, both sides'
    # cardinality, and pair closure before the mode may be interpreted.
    classification = await verify_revision_sync_classification(
        session, pr)
    dialogue_bound = classification.sync_mode == "VOCAL_V1"

    try:
        sn, sd = canonical_rational(performance_start_num,
                                    performance_start_den)
        en, ed = canonical_rational(performance_end_num,
                                    performance_end_den)
        an, ad = canonical_rational(shot_anchor_num, shot_anchor_den)
    except RationalError:
        raise

    if dialogue_bound:
        if vocal_mapping_position is None:
            raise SoloRingError(
                ErrorCode.PERFORMANCE_VOCAL_MAPPING_REQUIRED,
                "a dialogue-bound PerformanceRevision requires "
                "vocal_mapping_position", status_code=422)
        binding = await session.get(PerformanceRevisionVocalBinding, pr.id)
        # verify_revision_sync_classification proved VOCAL_V1 cardinality
        vocal = await session.get(ShotVocalSegmentMapping,
                                  (shot_id, vocal_mapping_position))
        if vocal is None:
            raise _mismatch(
                f"paired ShotVocalSegmentMapping {shot_id!r}@"
                f"{vocal_mapping_position} does not exist on this Shot")
        if vocal.vocal_performance_revision_id != \
                binding.vocal_performance_revision_id:
            raise _mismatch(
                "paired vocal mapping names VocalPerformanceRevision "
                f"{vocal.vocal_performance_revision_id!r} != the "
                "immutable revision binding VP "
                f"{binding.vocal_performance_revision_id!r}")
        if vocal.sample_rate_hz != binding.sample_rate_hz:
            raise _mismatch(
                "paired vocal mapping rate != the immutable revision "
                "binding rate")
        if not (binding.source_start_sample
                <= vocal.source_start_sample
                and vocal.source_end_sample_exclusive
                <= binding.source_end_sample_exclusive):
            raise _mismatch(
                "paired vocal mapping source interval "
                f"[{vocal.source_start_sample}, "
                f"{vocal.source_end_sample_exclusive}) lies outside the "
                "immutable revision binding source interval "
                f"[{binding.source_start_sample}, "
                f"{binding.source_end_sample_exclusive})")
        # current selection is working-readiness policy at PUT (§8.3):
        # the paired vocal mapping must be CURRENT now
        vp_sel = await session.get(VocalPerformanceSelection,
                                   (await _vp_dlr_id(session, binding)))
        if vp_sel is None or \
                vp_sel.selected_vocal_performance_revision_id != \
                binding.vocal_performance_revision_id:
            raise SoloRingError(
                ErrorCode.PERFORMANCE_VOCAL_SELECTION_STALE,
                "the paired vocal mapping's VocalPerformanceRevision is "
                "not the current explicit selection for its "
                "DialogueLineRevision", status_code=409)
        # exact induction: supplied interval and anchor must equal the
        # mechanically induced values with NO tolerance (frozen §8.3)
        p0, p1 = _induced_interval(binding, vocal)
        if (Fraction(sn, sd) != p0 or Fraction(en, ed) != p1):
            raise _mismatch(
                f"supplied performance interval [{sn}/{sd}, {en}/{ed}) "
                f"!= the exact induced interval [{p0}, {p1}) — no "
                "tolerance is permitted")
        van = Fraction(vocal.shot_anchor_num, vocal.shot_anchor_den)
        if Fraction(an, ad) != van:
            raise _mismatch(
                f"supplied Shot anchor {an}/{ad} != the paired vocal "
                f"mapping anchor {van} — they must be exactly equal")
    else:
        if vocal_mapping_position is not None:
            raise _invalid(
                "a generic (non-dialogue-bound) PerformanceRevision "
                "must not carry vocal_mapping_position")

    # shared interval laws (frozen §8.2/§8.3)
    start = Fraction(sn, sd)
    end = Fraction(en, ed)
    if start >= end:
        raise _invalid("mapped performance interval is empty or inverted")
    domain = _pr_domain(pr)
    if not (domain[0] <= start and end <= domain[1]):
        raise _invalid(
            f"mapped interval [{sn}/{sd}, {en}/{ed}) lies outside the "
            f"immutable PerformanceRevision domain "
            f"[{domain[0]}, {domain[1]})")
    if pr.project_id != shot.project_id:
        raise _invalid(
            "Shot and PerformanceRevision resolve to different projects")
    # picture intersection (J/L-cut lawful when intersecting)
    shot_start, shot_end = (
        Fraction(an, ad), Fraction(an, ad) + (end - start))
    if not (shot_end > 0 and shot_start < Fraction(shot.duration_ms)):
        raise SoloRingError(
            ErrorCode.MAPPING_NO_SHOT_OVERLAP,
            "mapped interval does not intersect the Shot picture "
            "interval (entirely before/after)", status_code=422)

    doc = {"mapping_schema_version": 1,
           "performance_revision_id": pr.id,
           "performance_start_ms": {"num": sn, "den": sd},
           "performance_end_ms": {"num": en, "den": ed},
           "shot_anchor_ms": {"num": an, "den": ad},
           "vocal_mapping_position": vocal_mapping_position}
    mapping_json = canonical_json_str(doc)
    mapping_hash = canonical_hash(doc)
    existing = await session.get(ShotPerformanceSegmentMapping,
                                 (shot_id, position))
    if existing is None:
        row = ShotPerformanceSegmentMapping(
            shot_id=shot_id, position=position,
            performance_revision_id=pr.id,
            performance_start_num=sn, performance_start_den=sd,
            performance_end_num=en, performance_end_den=ed,
            shot_anchor_num=an, shot_anchor_den=ad,
            vocal_mapping_position=vocal_mapping_position,
            mapping_schema_version=1,
            mapping_json=mapping_json, mapping_hash=mapping_hash,
            created_at=await db_now(session),
            updated_at=await db_now(session))
        session.add(row)
        await session.flush()
        return row
    for attr, value in (
            ("performance_revision_id", pr.id),
            ("performance_start_num", sn),
            ("performance_start_den", sd),
            ("performance_end_num", en),
            ("performance_end_den", ed),
            ("shot_anchor_num", an),
            ("shot_anchor_den", ad),
            ("vocal_mapping_position", vocal_mapping_position),
            ("mapping_json", mapping_json),
            ("mapping_hash", mapping_hash)):
        setattr(existing, attr, value)
    existing.updated_at = await db_now(session)
    await session.flush()
    return existing


async def _vp_dlr_id(session, binding) -> str:
    from soloring.performance.models import VocalPerformanceRevision
    vp = await session.get(VocalPerformanceRevision,
                           binding.vocal_performance_revision_id)
    if vp is None:
        raise SoloRingError(
            ErrorCode.INTERNAL_INVARIANT_VIOLATION,
            "revision vocal binding names a missing VP — corruption",
            status_code=500)
    return vp.dialogue_line_revision_id


async def delete_shot_performance_segment_mapping(
        session: AsyncSession, *, shot_id: str, position: int) -> None:
    row = await session.get(ShotPerformanceSegmentMapping,
                            (shot_id, position))
    if row is not None:
        await session.delete(row)
        await session.flush()


def _row_view(row) -> dict:
    return {
        "shot_id": row.shot_id, "position": row.position,
        "performance_revision_id": row.performance_revision_id,
        "performance_start_ms": {"num": row.performance_start_num,
                                 "den": row.performance_start_den},
        "performance_end_ms": {"num": row.performance_end_num,
                               "den": row.performance_end_den},
        "shot_anchor_ms": {"num": row.shot_anchor_num,
                           "den": row.shot_anchor_den},
        "vocal_mapping_position": row.vocal_mapping_position,
        "mapping_hash": row.mapping_hash,
        "created_at": row.created_at, "updated_at": row.updated_at,
    }


async def project_shot_performance_readiness(
        session: AsyncSession, settings, *, shot_id: str) -> dict:
    """frozen §9.1: readiness is a projection, never persisted."""
    from soloring.domain.models import Shot
    shot = await session.get(Shot, shot_id)
    if shot is None:
        raise not_found(ErrorCode.SHOT_NOT_FOUND,
                        f"shot {shot_id!r} not found")
    rows = (await session.execute(
        select(ShotPerformanceSegmentMapping).where(
            ShotPerformanceSegmentMapping.shot_id == shot_id)
        .order_by(ShotPerformanceSegmentMapping.position))
    ).scalars().all()

    dependency_ids = await _dependency_ids(session, shot_id)
    segments = []
    states = []
    row_states = []
    for row in rows:
        state, diagnostics = await _project_one(
            session, settings, shot, row, dependency_ids)
        row_states.append([row, state, diagnostics])
        states.append(state)
    # channel conflict (frozen §8.5): same subject + overlapping shot
    # intervals + intersecting immutable channel_key sets
    for i in range(len(row_states)):
        row_i, state_i, _ = row_states[i]
        if state_i != READY:
            continue
        for j in range(i + 1, len(row_states)):
            row_j, state_j, _ = row_states[j]
            if state_j != READY:
                continue
            si0, si1 = _shot_interval(row_i)
            sj0, sj1 = _shot_interval(row_j)
            if not (si0 < sj1 and sj0 < si1):
                continue
            if await _pr_subject(session, row_i) != \
                    await _pr_subject(session, row_j):
                continue
            keys_i = await _pr_channel_keys(session, settings, row_i)
            keys_j = await _pr_channel_keys(session, settings, row_j)
            if not (keys_i & keys_j):
                continue
            for k in (i, j):
                row_states[k][1] = BLOCKED_CHANNEL_CONFLICT
                row_states[k][2] = {
                    "conflict_with_position":
                        row_states[j if k == i else i][0].position}
            states[i] = BLOCKED_CHANNEL_CONFLICT
            states[j] = BLOCKED_CHANNEL_CONFLICT
    for row, state, diagnostics in row_states:
        view = _row_view(row)
        view["readiness"] = state
        if diagnostics:
            view["readiness_diagnostics"] = diagnostics
        segments.append(view)
    return {"shot_id": shot_id,
            "ready": all(s == READY for s in states),
            "segments": segments}


async def _pr_subject(session, row) -> str:
    pr = await session.get(PerformanceRevision,
                            row.performance_revision_id)
    if pr is None:
        raise SoloRingError(
            ErrorCode.INTERNAL_INVARIANT_VIOLATION,
            f"mapping {row.shot_id}@{row.position} references a missing "
            "PerformanceRevision — corruption", status_code=500)
    return pr.subject_id


async def _pr_channel_keys(session, settings, row) -> set[str]:
    pr = await session.get(PerformanceRevision,
                            row.performance_revision_id)
    from soloring.performance.models import PerformanceCandidate
    candidate = await session.get(PerformanceCandidate,
                                  pr.adopted_candidate_id)
    doc = (await revision_svc.verify_candidate_integrity(
        session, settings, candidate))["payload_document"]
    return {ch["channel_key"] for ch in doc["channels"]}


async def _project_one(session, settings, shot, row, dependency_ids
                       ) -> tuple[str, dict | None]:
    pr = await session.get(PerformanceRevision,
                            row.performance_revision_id)
    # hard corruption of the PR closure fails closed (M17C-A contract)
    classification = await verify_revision_sync_classification(session, pr)
    diagnostics: dict | None = None

    if pr.project_id != shot.project_id:
        return (BLOCKED_SUBJECT_OR_PROJECT,
                {"reason": "PerformanceRevision belongs to another "
                           "project than the Shot"})
    if pr.subject_id not in dependency_ids:
        return (BLOCKED_SHOT_DEPENDENCY,
                {"reason": "the Performance subject is not a current "
                           "semantic dependency of this Shot"})

    if row.vocal_mapping_position is not None:
        binding = await session.get(PerformanceRevisionVocalBinding,
                                    pr.id)
        vocal = await session.get(ShotVocalSegmentMapping,
                                  (row.shot_id,
                                   row.vocal_mapping_position))
        if binding is None or vocal is None:
            return (BLOCKED_BINDING_INTEGRITY,
                    {"reason": "the paired vocal mapping or the "
                               "revision vocal binding is missing"})
        if vocal.vocal_performance_revision_id != \
                binding.vocal_performance_revision_id:
            return (BLOCKED_BINDING_INTEGRITY,
                    {"reason": "the paired vocal mapping names a "
                               "different VP than the immutable "
                               "revision binding"})
        vp_sel = await session.get(VocalPerformanceSelection,
                                   await _vp_dlr_id(session, binding))
        if vp_sel is None or \
                vp_sel.selected_vocal_performance_revision_id != \
                binding.vocal_performance_revision_id:
            return (STALE_VOCAL_SELECTION,
                    {"mapped_vocal_performance_revision_id":
                     binding.vocal_performance_revision_id,
                     "selected_vocal_performance_revision_id":
                     (vp_sel.selected_vocal_performance_revision_id
                      if vp_sel is not None else None)})
        # exact induced-interval equality against CURRENT state
        p0, p1 = _induced_interval(binding, vocal)
        s0, s1 = _stored_interval(row)
        if s0 != p0 or s1 != p1 or \
                Fraction(row.shot_anchor_num,
                         row.shot_anchor_den) != Fraction(
                    vocal.shot_anchor_num, vocal.shot_anchor_den):
            return (BLOCKED_TIMING_MISMATCH,
                    {"reason": "the stored interval/anchor no longer "
                               "equals the exact induced values "
                               "(paired vocal mapping changed)"})
    return READY, None


async def list_shot_performance_segment_mappings(
        session: AsyncSession, settings, *, shot_id: str) -> list[dict]:
    projection = await project_shot_performance_readiness(
        session, settings, shot_id=shot_id)
    return projection["segments"]
