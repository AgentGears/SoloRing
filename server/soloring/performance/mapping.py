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
from soloring.performance.temporal import (PositionError,
                                           RationalError,
                                           canonical_rational,
                                           shot_ms,
                                           validate_mapping_position)
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
    # IR-04: the shared position-domain law runs BEFORE any ORM or
    # SQLite access; failures keep this service's established 4xx
    # vocabulary (an unbounded Python int would otherwise reach SQLite
    # and surface as a raw OverflowError)
    try:
        validate_mapping_position(position)
    except PositionError as exc:
        raise SoloRingError(ErrorCode.INVALID_SAMPLE_INTERVAL,
                            str(exc), status_code=422) from exc
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
    # selected VP for its own DialogueLineRevision. SR2-07 split: a
    # MISSING selection row is corruption (every DLR is created with
    # one — the same law as the M17A readiness/read paths); a LAWFUL
    # UNSET or different selection keeps the admission-shaped 409.
    sel = await session.get(VocalPerformanceSelection, rev.id)
    if sel is None:
        raise SoloRingError(
            ErrorCode.INTERNAL_INVARIANT_VIOLATION,
            f"DialogueLineRevision {rev.id!r} has no selection row — "
            "every revision is created with one; this is corruption, "
            "not a readiness state",
            status_code=500)
    if sel.selected_vocal_performance_revision_id != vp.id:
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
    # NOTE (frozen table design + mandatory E14): a Shot MAY carry
    # simultaneous vocal segments — overlapping speakers at different
    # positions are lawful; the second source review reversed the
    # previous overlap refusal. Remaining checks are the frozen
    # picture-intersection and current-selection working-readiness
    # laws only.
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
    # IR-04: the shared position-domain law on the DELETE path too —
    # stable 4xx BEFORE any storage access; 2^63-1 stays DB-safe and
    # the delete of an absent position stays an idempotent no-op.
    try:
        validate_mapping_position(position)
    except PositionError as exc:
        raise SoloRingError(ErrorCode.INVALID_SAMPLE_INTERVAL,
                            str(exc), status_code=422) from exc
    row = await session.get(ShotVocalSegmentMapping, (shot_id, position))
    if row is not None:
        await session.delete(row)
        await session.flush()


async def list_shot_vocal_segment_mappings(
        session: AsyncSession, *, shot_id: str) -> list[dict]:
    from soloring.performance.readiness import project_mapping_readiness
    rows = (await session.execute(
        select(ShotVocalSegmentMapping).where(
            ShotVocalSegmentMapping.shot_id == shot_id)
        .order_by(ShotVocalSegmentMapping.position))).scalars().all()
    out = []
    for r in rows:
        readiness = await project_mapping_readiness(session, r)
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
            "current_readiness": readiness,
            "created_at": r.created_at, "updated_at": r.updated_at})
    return out


# ---------------------------------------------------------------------------
# RR2-M17CC-01 (third first-pass review): the ONE shared, transport-
# neutral persisted structural law for a PRESENT ShotVocalSegmentMapping.
# The live capture/readiness path and the M17A recovery verifier consume
# the SAME document reconstruction so the two definitions cannot drift;
# each caller keeps its own transport and error vocabulary.
# ---------------------------------------------------------------------------

def vocal_mapping_canonical_document(
        *, vocal_performance_revision_id: str,
        source_start_sample: int,
        source_end_sample_exclusive: int,
        sample_rate_hz: int,
        performance_origin_num: int, performance_origin_den: int,
        shot_anchor_num: int, shot_anchor_den: int) -> dict:
    """The exact canonical vocal mapping document reconstructed from a
    stored row's OWN fields (the grammar the M17A PUT writes)."""
    return {
        "mapping_schema_version": 1,
        "vocal_performance_revision_id": vocal_performance_revision_id,
        "source_start_sample": source_start_sample,
        "source_end_sample_exclusive": source_end_sample_exclusive,
        "sample_rate_hz": sample_rate_hz,
        "performance_origin_ms": {
            "num": performance_origin_num,
            "den": performance_origin_den},
        "shot_anchor_ms": {"num": shot_anchor_num,
                           "den": shot_anchor_den},
    }


def verify_stored_vocal_mapping(
        *, mapping_schema_version, mapping_json: str, mapping_hash: str,
        vocal_performance_revision_id: str,
        source_start_sample: int,
        source_end_sample_exclusive: int,
        sample_rate_hz: int,
        performance_origin_num: int, performance_origin_den: int,
        shot_anchor_num: int, shot_anchor_den: int) -> None:
    """Fail closed (raising ValueError with a precise reason) unless a
    PRESENT vocal mapping row satisfies its complete persisted canonical
    law: mapping_schema_version == 1, the stored mapping_json IS EXACTLY
    the canonical serialized form (byte identity, per the frozen 11.4
    noncanonical-BYTES refusal — RR3-M17CC-01: decoding alone proves
    semantic equality, not canonical serialization; a pretty-printed,
    reordered, or duplicate-key form that decodes to the canonical
    document is NOT a serialization the canonical writer could emit),
    and mapping_hash IS that document's canonical digest. Never
    repairs, normalizes, reserializes-and-accepts, or substitutes the
    row. Parsing is used ONLY to differentiate diagnostics, never as
    the certification."""
    import json as _json

    canonical = vocal_mapping_canonical_document(
        vocal_performance_revision_id=vocal_performance_revision_id,
        source_start_sample=source_start_sample,
        source_end_sample_exclusive=source_end_sample_exclusive,
        sample_rate_hz=sample_rate_hz,
        performance_origin_num=performance_origin_num,
        performance_origin_den=performance_origin_den,
        shot_anchor_num=shot_anchor_num,
        shot_anchor_den=shot_anchor_den)
    if mapping_schema_version != 1:
        raise ValueError(
            "mapping_schema_version is not the frozen 1")
    # the CERTIFYING law: exact canonical serialized identity
    canonical_bytes = canonical_json_str(canonical)
    if mapping_json != canonical_bytes:
        # diagnostic-only parse: distinguish a semantic forgery from a
        # semantically identical but NONCANONICAL serialization
        try:
            doc = _json.loads(mapping_json)
        except (ValueError, TypeError) as exc:
            raise ValueError(
                f"mapping_json is not the canonical serialized form "
                f"and is not decodable JSON: {exc}") from exc
        if doc != canonical:
            raise ValueError(
                "mapping_json is not the canonical document over the "
                "row's own fields")
        raise ValueError(
            "mapping_json decodes to the canonical document but is "
            "not its canonical serialized form")
    if canonical_hash(canonical) != mapping_hash:
        raise ValueError(
            "mapping_hash is not the canonical digest of the row's "
            "own mapping document")
