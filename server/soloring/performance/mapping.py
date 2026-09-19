"""Shot VocalSegmentMapping service (frozen R5 §4.6, §6, §9.5).
Current working Shot timing intent following the ShotSpatialPlan
precedent; M17C will capture the exact resolved mapping into schema 8.
Validation enforces the frozen rules; the two stricter checks
(picture intersection, current-selection binding) are M17A
working-readiness policy, not G8 authority invariants.
"""

from __future__ import annotations

from fractions import Fraction

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.domain.now import db_now
from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.domain.ids import new_uuid
from soloring.errors import ErrorCode, SoloRingError, not_found
from soloring.performance.models import (ShotVocalSegmentMapping,
                                         VocalPerformanceSelection)
from soloring.performance.temporal import (RationalError,
                                           canonical_rational, shot_ms)
from soloring.performance.vocal import get_vocal_performance_revision


async def put_shot_vocal_segment_mapping(
        session: AsyncSession, *, shot_id: str, position: int,
        vocal_performance_revision_id: str,
        source_start_sample: int, source_end_sample_exclusive: int,
        sample_rate_hz: int,
        performance_origin_num: int, performance_origin_den: int,
        shot_anchor_num: int, shot_anchor_den: int
        ) -> ShotVocalSegmentMapping:
    from soloring.domain.models import Shot
    if position < 0:
        raise SoloRingError(ErrorCode.INVALID_SAMPLE_INTERVAL,
                            "position must be >= 0", status_code=422)
    shot = await session.get(Shot, shot_id)
    if shot is None:
        raise not_found(ErrorCode.SHOT_NOT_FOUND,
                        f"shot {shot_id!r} not found")
    if shot.duration_ms is None or shot.duration_ms <= 0:
        raise SoloRingError(ErrorCode.SHOT_DURATION_REQUIRED,
                            "Shot.duration_ms must be present and > 0 "
                            "for vocal segment mapping",
                            status_code=422)
    vp = await get_vocal_performance_revision(
        session, revision_id=vocal_performance_revision_id)
    # project consistency
    from soloring.performance.models import DialogueLineRevision
    from soloring.performance.models import DialogueLine
    rev = await session.get(DialogueLineRevision,
                            vp.dialogue_line_revision_id)
    line = await session.get(DialogueLine, rev.dialogue_line_id)
    if line.project_id != shot.project_id:
        raise SoloRingError(ErrorCode.INVALID_SAMPLE_INTERVAL,
                            "Shot and VP resolve to different projects",
                            status_code=422)
    # M17A working-readiness: mapping may reference only the explicitly
    # selected VP for its own DialogueLineRevision
    sel = await session.get(VocalPerformanceSelection, rev.id)
    if sel is None or \
            sel.selected_vocal_performance_revision_id != vp.id:
        raise SoloRingError(
            ErrorCode.VOCAL_MAPPING_SELECTION_STALE,
            "the referenced VocalPerformanceRevision is not the "
            "explicit current selection for its DialogueLineRevision",
            status_code=409)
    # frozen validation block
    if not (0 <= source_start_sample
            and source_start_sample < source_end_sample_exclusive):
        raise SoloRingError(ErrorCode.INVALID_SAMPLE_INTERVAL,
                            f"sample interval [{source_start_sample}, "
                            f"{source_end_sample_exclusive}) invalid",
                            status_code=422)
    if source_end_sample_exclusive > vp.retained_sample_count:
        raise SoloRingError(
            ErrorCode.INVALID_SAMPLE_INTERVAL,
            f"end {source_end_sample_exclusive} exceeds retained "
            f"{vp.retained_sample_count} samples", status_code=422)
    if (source_start_sample < vp.trim_start_sample
            or source_end_sample_exclusive >
            vp.trim_end_sample_exclusive):
        raise SoloRingError(
            ErrorCode.MAPPING_OUTSIDE_TRIM,
            "segment must lie wholly inside the authoritative trim "
            f"[{vp.trim_start_sample}, {vp.trim_end_sample_exclusive})",
            status_code=422)
    if sample_rate_hz != vp.native_sample_rate_hz:
        raise SoloRingError(ErrorCode.SAMPLE_RATE_MISMATCH,
                            f"mapping rate {sample_rate_hz} != VP "
                            f"native {vp.native_sample_rate_hz}",
                            status_code=422)
    try:
        pnum, pden = canonical_rational(performance_origin_num,
                                        performance_origin_den)
        anum, aden = canonical_rational(shot_anchor_num, shot_anchor_den)
    except RationalError:
        raise
    # J/L-cut lawfulness: the segment must intersect the picture
    start_ms = shot_ms(source_start_sample, anchor_num=anum,
                       anchor_den=aden,
                       source_start_sample=source_start_sample,
                       sample_rate_hz=sample_rate_hz)
    end_ms = shot_ms(source_end_sample_exclusive, anchor_num=anum,
                     anchor_den=aden,
                     source_start_sample=source_start_sample,
                     sample_rate_hz=sample_rate_hz)
    if not (end_ms > 0 and start_ms < Fraction(shot.duration_ms)):
        raise SoloRingError(
            ErrorCode.MAPPING_NO_SHOT_OVERLAP,
            "mapped interval does not intersect the Shot picture "
            "interval (entirely before/after)", status_code=422)
    doc = {"mapping_schema_version": 1,
           "vocal_performance_revision_id": vp.id,
           "source_start_sample": source_start_sample,
           "source_end_sample_exclusive": source_end_sample_exclusive,
           "sample_rate_hz": sample_rate_hz,
           "performance_origin_ms": {"num": pnum, "den": pden},
           "shot_anchor_ms": {"num": anum, "den": aden}}
    mapping_json = canonical_json_str(doc)
    mapping_hash = canonical_hash(doc)
    existing = await session.get(ShotVocalSegmentMapping,
                                 (shot_id, position))
    if existing is None:
        row = ShotVocalSegmentMapping(
            shot_id=shot_id, position=position,
            vocal_performance_revision_id=vp.id,
            source_start_sample=source_start_sample,
            source_end_sample_exclusive=source_end_sample_exclusive,
            sample_rate_hz=sample_rate_hz,
            performance_origin_num=pnum, performance_origin_den=pden,
            shot_anchor_num=anum, shot_anchor_den=aden,
            mapping_schema_version=1,
            mapping_json=mapping_json, mapping_hash=mapping_hash,
            created_at=await db_now(session), updated_at=await db_now(session))
        session.add(row)
        await session.flush()
        return row
    for attr, value in (
            ("vocal_performance_revision_id", vp.id),
            ("source_start_sample", source_start_sample),
            ("source_end_sample_exclusive",
             source_end_sample_exclusive),
            ("sample_rate_hz", sample_rate_hz),
            ("performance_origin_num", pnum),
            ("performance_origin_den", pden),
            ("shot_anchor_num", anum),
            ("shot_anchor_den", aden),
            ("mapping_json", mapping_json),
            ("mapping_hash", mapping_hash)):
        setattr(existing, attr, value)
    existing.updated_at = await db_now(session)
    await session.flush()
    return existing


async def delete_shot_vocal_segment_mapping(
        session: AsyncSession, *, shot_id: str, position: int) -> None:
    row = await session.get(ShotVocalSegmentMapping, (shot_id, position))
    if row is not None:
        await session.delete(row)
        await session.flush()


async def list_shot_vocal_segment_mappings(
        session: AsyncSession, *, shot_id: str) -> list[dict]:
    rows = (await session.execute(
        select(ShotVocalSegmentMapping).where(
            ShotVocalSegmentMapping.shot_id == shot_id)
        .order_by(ShotVocalSegmentMapping.position))).scalars().all()
    out = []
    for r in rows:
        out.append({
            "shot_id": r.shot_id, "position": r.position,
            "vocal_performance_revision_id":
            r.vocal_performance_revision_id,
            "source_start_sample": r.source_start_sample,
            "source_end_sample_exclusive":
            r.source_end_sample_exclusive,
            "sample_rate_hz": r.sample_rate_hz,
            "performance_origin_ms": {"num": r.performance_origin_num,
                                      "den": r.performance_origin_den},
            "shot_anchor_ms": {"num": r.shot_anchor_num,
                               "den": r.shot_anchor_den},
            "mapping_hash": r.mapping_hash,
            "created_at": r.created_at, "updated_at": r.updated_at})
    return out
