"""M17B physical-retarget compatibility v1 (frozen R7 §11).

The evaluator answers ONLY the declared physical-revision-change
coordinate. COMPATIBLE_AS_IS means "no retarget translation is
required for this from→to pair" — it does not assert subject binding,
rig/channel support, or executor realizability.

M17B retargeting is physical-coordinate provenance, NOT semantic
Performance editing: a lawful retarget candidate copies the source
revision's semantic closure byte-for-byte and changes only production
provenance.
"""

from __future__ import annotations

import hashlib

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.domain.ids import new_uuid
from soloring.domain.now import db_now
from soloring.errors import ErrorCode, SoloRingError, not_found
from soloring.performance.models import (PerformanceCandidate,
                                         PerformanceRetargetAssessment,
                                         PerformanceRetargetReview,
                                         PerformanceRevision)
from soloring.performance.revision import (SOURCE_KINDS, _invalid,
                                           closure_matches)

EVALUATOR_ID = "soloring.performance_physical_retarget"
EVALUATOR_VERSION = 1

COMPATIBLE_AS_IS = "COMPATIBLE_AS_IS"
COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION = (
    "COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION")
REQUIRES_REVIEW = "REQUIRES_REVIEW"
INCOMPATIBLE = "INCOMPATIBLE"

_REASONS = {
    "SAME_EXACT_PHYSICAL_REVISION": COMPATIBLE_AS_IS,
    "SAME_PRODUCTION_OBJECT_DIFFERENT_REVISION": REQUIRES_REVIEW,
    "DIFFERENT_PRODUCTION_OBJECT": INCOMPATIBLE,
}

_SCOPE_KEYS = ("schema_version", "evaluator_id", "evaluator_version",
               "performance_revision_id", "subject_id",
               "performance_kind", "performance_profile_id",
               "performance_payload_sha256",
               "from_production_revision_id",
               "from_production_revision_hash",
               "from_production_object_id",
               "to_production_revision_id",
               "to_production_revision_hash",
               "to_production_object_id")
_REPORT_KEYS = ("schema_version", "evaluator_id", "evaluator_version",
                "scope_hash", "performance_revision_id",
                "from_production_revision_id",
                "to_production_revision_id", "verdict", "reason_code",
                "from_production_object_id",
                "to_production_object_id")


async def _load_physical(session: AsyncSession, revision_id: str,
                         project_id: str):
    from soloring.production.models import ProductionRevision
    pr = await session.get(ProductionRevision, revision_id)
    if pr is None:
        return None
    return pr


def _build_scope(*, performance: PerformanceRevision,
                 payload_sha: str, from_pr, to_pr) -> dict:
    return {
        "schema_version": 1,
        "evaluator_id": EVALUATOR_ID,
        "evaluator_version": EVALUATOR_VERSION,
        "performance_revision_id": performance.id,
        "subject_id": performance.subject_id,
        "performance_kind": performance.performance_kind,
        "performance_profile_id": performance.performance_profile_id,
        "performance_payload_sha256": payload_sha,
        "from_production_revision_id": from_pr.id,
        "from_production_revision_hash": from_pr.snapshot_hash,
        "from_production_object_id": str(from_pr.production_object_id),
        "to_production_revision_id": to_pr.id,
        "to_production_revision_hash": to_pr.snapshot_hash,
        "to_production_object_id": str(to_pr.production_object_id),
    }


def _evaluate(from_pr, to_pr) -> tuple[str, str]:
    if from_pr.id == to_pr.id:
        reason = "SAME_EXACT_PHYSICAL_REVISION"
    elif str(from_pr.production_object_id) == \
            str(to_pr.production_object_id):
        reason = "SAME_PRODUCTION_OBJECT_DIFFERENT_REVISION"
    else:
        reason = "DIFFERENT_PRODUCTION_OBJECT"
    return _REASONS[reason], reason


def _build_report(*, scope_hash: str, performance_id: str,
                  from_id: str, to_id: str, verdict: str,
                  reason: str, from_obj: str, to_obj: str) -> dict:
    return {
        "schema_version": 1,
        "evaluator_id": EVALUATOR_ID,
        "evaluator_version": EVALUATOR_VERSION,
        "scope_hash": scope_hash,
        "performance_revision_id": performance_id,
        "from_production_revision_id": from_id,
        "to_production_revision_id": to_id,
        "verdict": verdict,
        "reason_code": reason,
        "from_production_object_id": from_obj,
        "to_production_object_id": to_obj,
    }


async def assess_physical_retarget(
        session: AsyncSession, *, performance_revision_id: str,
        from_production_revision_id: str,
        to_production_revision_id: str
        ) -> PerformanceRetargetAssessment:
    """Frozen R7 §§11.1–11.3: deterministic evidence with sequential
    and concurrent convergence at one coordinate; differing report
    bytes at the same coordinate are invariant failure, never a
    competing row."""
    performance = await session.get(PerformanceRevision,
                                     performance_revision_id)
    if performance is None:
        raise not_found(ErrorCode.PERFORMANCE_REVISION_NOT_FOUND,
                        f"performance revision {performance_revision_id!r}"
                        " not found")
    from_pr = await _load_physical(session, from_production_revision_id,
                                   performance.project_id)
    if from_pr is None:
        raise not_found(ErrorCode.RETARGET_FROM_REVISION_NOT_FOUND,
                        f"from production revision "
                        f"{from_production_revision_id!r} not found")
    to_pr = await _load_physical(session, to_production_revision_id,
                                 performance.project_id)
    if to_pr is None:
        raise not_found(ErrorCode.RETARGET_TO_REVISION_NOT_FOUND,
                        f"to production revision "
                        f"{to_production_revision_id!r} not found")
    from soloring.domain.models import Project
    for label, pr in (("from", from_pr), ("to", to_pr)):
        project = await session.get(Project, performance.project_id)
        break
    # project agreement for both physical revisions
    from soloring.production.models import ProductionObject
    from_obj = await session.get(ProductionObject,
                                 from_pr.production_object_id)
    to_obj = await session.get(ProductionObject,
                               to_pr.production_object_id)
    if from_obj is None or to_obj is None or \
            from_obj.project_id != performance.project_id or \
            to_obj.project_id != performance.project_id:
        raise _invalid(ErrorCode.RETARGET_PROJECT_MISMATCH,
                       "physical revisions must belong to the "
                       "Performance's project")

    scope = _build_scope(
        performance=performance,
        payload_sha=performance.canonical_channel_payload_sha256,
        from_pr=from_pr, to_pr=to_pr)
    scope_json = canonical_json_str(scope)
    scope_hash = canonical_hash(scope)
    verdict, reason = _evaluate(from_pr, to_pr)
    report = _build_report(
        scope_hash=scope_hash, performance_id=performance.id,
        from_id=from_pr.id, to_id=to_pr.id, verdict=verdict,
        reason=reason, from_obj=str(from_pr.production_object_id),
        to_obj=str(to_pr.production_object_id))
    report_json = canonical_json_str(report)
    report_hash = canonical_hash(report)

    existing = (await session.execute(
        select(PerformanceRetargetAssessment).where(
            PerformanceRetargetAssessment.performance_revision_id ==
            performance.id,
            PerformanceRetargetAssessment.from_production_revision_id ==
            from_pr.id,
            PerformanceRetargetAssessment.to_production_revision_id ==
            to_pr.id,
            PerformanceRetargetAssessment.evaluator_id == EVALUATOR_ID,
            PerformanceRetargetAssessment.evaluator_version ==
            EVALUATOR_VERSION,
            PerformanceRetargetAssessment.scope_hash == scope_hash)
    )).scalar_one_or_none()
    if existing is not None:
        _assert_deterministic(existing, report_json, report_hash,
                              verdict)
        return existing

    row = PerformanceRetargetAssessment(
        id=new_uuid(), project_id=performance.project_id,
        performance_revision_id=performance.id,
        from_production_revision_id=from_pr.id,
        from_production_revision_hash=from_pr.snapshot_hash,
        to_production_revision_id=to_pr.id,
        to_production_revision_hash=to_pr.snapshot_hash,
        schema_version=1, evaluator_id=EVALUATOR_ID,
        evaluator_version=EVALUATOR_VERSION,
        scope_json=scope_json, scope_hash=scope_hash,
        report_json=report_json, report_hash=report_hash,
        overall_verdict=verdict, created_at=await db_now(session))
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        winner = (await session.execute(
            select(PerformanceRetargetAssessment).where(
                PerformanceRetargetAssessment.performance_revision_id
                == performance.id,
                PerformanceRetargetAssessment.
                from_production_revision_id == from_pr.id,
                PerformanceRetargetAssessment.to_production_revision_id
                == to_pr.id,
                PerformanceRetargetAssessment.evaluator_id ==
                EVALUATOR_ID,
                PerformanceRetargetAssessment.evaluator_version ==
                EVALUATOR_VERSION,
                PerformanceRetargetAssessment.scope_hash == scope_hash)
        )).scalar_one_or_none()
        if winner is None:
            raise
        _assert_deterministic(winner, report_json, report_hash, verdict)
        return winner
    return row


def _assert_deterministic(existing: PerformanceRetargetAssessment,
                          report_json: str, report_hash: str,
                          verdict: str) -> None:
    if existing.report_hash != report_hash or \
            existing.report_json != report_json or \
            existing.overall_verdict != verdict:
        raise SoloRingError(
            ErrorCode.RETARGET_ASSESSMENT_NONDETERMINISM,
            "the same retarget coordinate produced differing report "
            "bytes — evaluator nondeterminism or corruption; never "
            "overwritten", status_code=500)


async def get_assessment(session: AsyncSession, *, assessment_id: str
                         ) -> PerformanceRetargetAssessment:
    a = await session.get(PerformanceRetargetAssessment, assessment_id)
    if a is None:
        raise not_found(ErrorCode.RETARGET_ASSESSMENT_NOT_FOUND,
                        f"retarget assessment {assessment_id!r} "
                        "not found")
    return a


async def create_review(session: AsyncSession, *, assessment_id: str,
                        decision: str, reviewed_by: str,
                        rationale: str | None
                        ) -> PerformanceRetargetReview:
    """Frozen R7 §11.4: append-only review evidence; no latest-wins,
    no supersession."""
    await get_assessment(session, assessment_id=assessment_id)
    if decision not in ("ACCEPT_FOR_NEW_CANDIDATE", "REJECT"):
        raise _invalid(ErrorCode.PERFORMANCE_PAYLOAD_INVALID,
                       "decision must be ACCEPT_FOR_NEW_CANDIDATE or "
                       "REJECT")
    if not isinstance(reviewed_by, str) or not reviewed_by.strip() \
            or len(reviewed_by) > 255:
        raise _invalid(ErrorCode.PERFORMANCE_PAYLOAD_INVALID,
                       "reviewed_by must be nonempty (whitespace test) "
                       "<= 255 code points, persisted exactly")
    if rationale is not None and (not isinstance(rationale, str)
                                  or len(rationale) > 4096):
        raise _invalid(ErrorCode.PERFORMANCE_PAYLOAD_INVALID,
                       "rationale must be null or exact UTF-8 free "
                       "text <= 4096 code points")
    review = PerformanceRetargetReview(
        id=new_uuid(), assessment_id=assessment_id, decision=decision,
        reviewed_by=reviewed_by, reviewed_at=await db_now(session),
        rationale=rationale)
    session.add(review)
    await session.flush()
    return review


async def get_review(session: AsyncSession, *, review_id: str
                     ) -> PerformanceRetargetReview:
    r = await session.get(PerformanceRetargetReview, review_id)
    if r is None:
        raise not_found(ErrorCode.RETARGET_REVIEW_NOT_FOUND,
                        f"retarget review {review_id!r} not found")
    return r


async def list_reviews(session: AsyncSession, *, assessment_id: str
                       ) -> list[PerformanceRetargetReview]:
    await get_assessment(session, assessment_id=assessment_id)
    return list((await session.execute(
        select(PerformanceRetargetReview).where(
            PerformanceRetargetReview.assessment_id == assessment_id)
        .order_by(PerformanceRetargetReview.reviewed_at,
                  PerformanceRetargetReview.id))).scalars().all())


async def create_retarget_candidate(
        session: AsyncSession, settings, *, revision_id: str,
        assessment_id: str, accepted_review_id: str,
        producer_id: str, producer_version: str,
        source_identity: str | None,
        parameters_sha256: str | None) -> PerformanceCandidate:
    """Frozen R7 §11.5: physical-coordinate provenance only. The
    semantic closure is copied byte/scalar-exact from the source
    PerformanceRevision; only the production provenance becomes the
    server-constructed retarget envelope. The caller cannot supply
    replacement semantic bytes or forge the coordinate."""
    performance = await session.get(PerformanceRevision, revision_id)
    if performance is None:
        raise not_found(ErrorCode.PERFORMANCE_REVISION_NOT_FOUND,
                        f"performance revision {revision_id!r} "
                        "not found")
    assessment = await get_assessment(session,
                                      assessment_id=assessment_id)

    # coordinate equality chain (frozen §8.2 / §12.4)
    if assessment.performance_revision_id != performance.id:
        raise _invalid(
            ErrorCode.RETARGET_ASSESSMENT_COORDINATE_MISMATCH,
            "assessment belongs to a different PerformanceRevision")
    verdict = assessment.overall_verdict
    if verdict == COMPATIBLE_AS_IS:
        raise _invalid(
            ErrorCode.RETARGET_NOT_REQUIRED,
            "same-revision physical coordinate requires no retarget — "
            "assessment is valid evidence but retarget-candidate "
            "creation is a no-op rejection")
    if verdict == INCOMPATIBLE:
        raise _invalid(
            ErrorCode.RETARGET_INCOMPATIBLE,
            "INCOMPATIBLE assessment cannot seed a retarget candidate")
    if verdict != REQUIRES_REVIEW:
        raise SoloRingError(
            ErrorCode.INTERNAL_INVARIANT_VIOLATION,
            "evaluator v1 verdict outside its frozen law — "
            "corruption", status_code=500)

    review = await session.get(PerformanceRetargetReview,
                               accepted_review_id)
    if review is None:
        raise not_found(ErrorCode.RETARGET_REVIEW_NOT_FOUND,
                        f"retarget review {accepted_review_id!r} "
                        "not found")
    if review.assessment_id != assessment.id:
        raise _invalid(
            ErrorCode.RETARGET_REVIEW_ASSESSMENT_MISMATCH,
            "accepted review belongs to a different assessment — "
            "cross-assessment review replay rejects")
    if review.decision != "ACCEPT_FOR_NEW_CANDIDATE":
        raise _invalid(ErrorCode.RETARGET_REVIEW_REJECTED,
                       "retarget candidate requires an "
                       "ACCEPT_FOR_NEW_CANDIDATE review")

    # server constructs the exact retarget envelope — the caller
    # cannot forge source/from/to ids; the closed grammar (including
    # the five-key retarget object) is validated as a whole
    from soloring.performance.revision import build_provenance_envelope
    envelope = build_provenance_envelope({
        "schema_version": 1, "source_kind": "retargeted",
        "producer_id": producer_id,
        "producer_version": producer_version,
        "source_identity": source_identity,
        "parameters_sha256": parameters_sha256,
        "retarget": {
            "source_performance_revision_id": performance.id,
            "from_production_revision_id":
                assessment.from_production_revision_id,
            "to_production_revision_id":
                assessment.to_production_revision_id,
            "compatibility_assessment_id": assessment.id,
            "accepted_review_id": review.id,
        }})
    prov_json = canonical_json_str(envelope)
    prov_hash = canonical_hash(envelope)

    candidate = PerformanceCandidate(
        id=new_uuid(), project_id=performance.project_id,
        subject_id=performance.subject_id,
        performance_kind=performance.performance_kind,
        performance_profile_id=performance.performance_profile_id,
        temporal_start_num=performance.temporal_start_num,
        temporal_start_den=performance.temporal_start_den,
        temporal_end_num=performance.temporal_end_num,
        temporal_end_den=performance.temporal_end_den,
        canonical_channel_payload_blob_hash=(
            performance.canonical_channel_payload_blob_hash),
        canonical_channel_payload_sha256=(
            performance.canonical_channel_payload_sha256),
        payload_schema_version=performance.payload_schema_version,
        source_kind="retargeted",
        provenance_schema_version=1,
        provenance_json=prov_json, provenance_hash=prov_hash,
        created_at=await db_now(session))

    # the copied semantic closure must be byte/scalar-identical
    for f in ("project_id", "subject_id", "performance_kind",
              "performance_profile_id", "temporal_start_num",
              "temporal_start_den", "temporal_end_num",
              "temporal_end_den",
              "canonical_channel_payload_blob_hash",
              "canonical_channel_payload_sha256",
              "payload_schema_version"):
        if getattr(candidate, f) != getattr(performance, f):
            raise SoloRingError(
                ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                "retarget candidate semantic closure diverged from "
                "source — never created", status_code=500)

    session.add(candidate)
    await session.flush()
    return candidate
