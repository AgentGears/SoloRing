"""M17B Performance API routes (frozen R7 §12).

Partial cursors REJECT — this is a deliberate M17B tightening
relative to the published M17A dialogue-line pagination; M17B routes
must not weaken and must not backport the change into M17A during
this milestone.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.m17b_performance import (
    AdoptRequest, PerformanceCandidateCollection,
    PerformanceCandidateCreate, PerformanceCandidateRead,
    PerformanceRevisionCollection, PerformanceRevisionRead,
    RetargetAssessmentCreate, RetargetAssessmentRead,
    RetargetCandidateCreate, RetargetReviewCollection,
    RetargetReviewRead, ReviewCreate)
from soloring.errors import ErrorCode, SoloRingError
from soloring.performance import retarget as retarget_svc
from soloring.performance import revision as revision_svc
from soloring.performance.models import (PerformanceCandidate,
                                         PerformanceRevision)

router = APIRouter(tags=["performance-m17b"])


def _cursor(cursor_a: str | None, cursor_b: str | None,
            name_a: str, name_b: str) -> tuple[str, str] | None:
    """Partial cursors reject (frozen R7 §12)."""
    if (cursor_a is None) != (cursor_b is None):
        raise SoloRingError(
            ErrorCode.INVALID_CURSOR,
            f"pagination cursor requires BOTH {name_a} and {name_b}; "
            "a partial cursor rejects rather than degrading to an "
            "unbounded or first-page query", status_code=422)
    if cursor_a is None:
        return None
    return (cursor_a, cursor_b)


def _candidate_view(c: PerformanceCandidate) -> dict:
    return {"id": c.id, "project_id": c.project_id,
            "subject_id": c.subject_id,
            "performance_kind": c.performance_kind,
            "performance_profile_id": c.performance_profile_id,
            "temporal_start_ms": {"num": c.temporal_start_num,
                                  "den": c.temporal_start_den},
            "temporal_end_ms": {"num": c.temporal_end_num,
                                "den": c.temporal_end_den},
            "canonical_channel_payload_sha256":
                c.canonical_channel_payload_sha256,
            "canonical_channel_payload_blob_hash":
                c.canonical_channel_payload_blob_hash,
            "payload_schema_version": c.payload_schema_version,
            "source_kind": c.source_kind,
            "provenance_hash": c.provenance_hash,
            "created_at": c.created_at}


def _revision_view(r: PerformanceRevision) -> dict:
    return {"id": r.id, "project_id": r.project_id,
            "subject_id": r.subject_id,
            "performance_kind": r.performance_kind,
            "performance_profile_id": r.performance_profile_id,
            "temporal_start_ms": {"num": r.temporal_start_num,
                                  "den": r.temporal_start_den},
            "temporal_end_ms": {"num": r.temporal_end_num,
                                "den": r.temporal_end_den},
            "canonical_channel_payload_sha256":
                r.canonical_channel_payload_sha256,
            "canonical_channel_payload_blob_hash":
                r.canonical_channel_payload_blob_hash,
            "payload_schema_version": r.payload_schema_version,
            "source_kind": r.source_kind,
            "provenance_hash": r.provenance_hash,
            "adopted_candidate_id": r.adopted_candidate_id,
            "adoption_id": r.adoption_id, "adopted_by": r.adopted_by,
            "adopted_at": r.adopted_at}


def _assessment_view(a) -> RetargetAssessmentRead:
    return RetargetAssessmentRead(
        id=a.id, project_id=a.project_id,
        performance_revision_id=a.performance_revision_id,
        from_production_revision_id=a.from_production_revision_id,
        from_production_revision_hash=a.from_production_revision_hash,
        to_production_revision_id=a.to_production_revision_id,
        to_production_revision_hash=a.to_production_revision_hash,
        schema_version=a.schema_version, evaluator_id=a.evaluator_id,
        evaluator_version=a.evaluator_version, scope_hash=a.scope_hash,
        report_hash=a.report_hash, overall_verdict=a.overall_verdict,
        created_at=a.created_at,
        physical_revision_compatibility_only=True,
        subject_binding_assessed=False,
        executor_qualification_assessed=False)


@router.post("/creative-entities/{subject_id}/performance-candidates",
             response_model=PerformanceCandidateRead, status_code=201)
async def create_performance_candidate(
        subject_id: str, body: PerformanceCandidateCreate,
        request: Request,
        session: AsyncSession = Depends(get_session)):
    candidate = await revision_svc.create_performance_candidate(
        session, request.app.state.settings,
        subject_id=subject_id,
        performance_kind=body.performance_kind,
        performance_profile_id=body.performance_profile_id,
        temporal_start_num=body.temporal_start.num,
        temporal_start_den=body.temporal_start.den,
        temporal_end_num=body.temporal_end.num,
        temporal_end_den=body.temporal_end.den,
        channels=[ch.model_dump() for ch in body.channels],
        source_provenance=body.source_provenance.model_dump(
            exclude_unset=True))
    await session.commit()
    return PerformanceCandidateRead(**_candidate_view(candidate))


@router.get("/performance-candidates/{candidate_id}",
            response_model=PerformanceCandidateRead)
async def get_performance_candidate(
        candidate_id: str,
        session: AsyncSession = Depends(get_session)):
    c = await revision_svc.get_performance_candidate(
        session, candidate_id=candidate_id)
    return PerformanceCandidateRead(**_candidate_view(c))


@router.get("/creative-entities/{subject_id}/performance-candidates",
            response_model=PerformanceCandidateCollection)
async def list_performance_candidates(
        subject_id: str, limit: int = 50,
        cursor_created: str | None = None,
        cursor_id: str | None = None,
        session: AsyncSession = Depends(get_session)):
    cursor = _cursor(cursor_created, cursor_id, "cursor_created",
                     "cursor_id")
    limit = max(1, min(200, limit))
    stmt = select(PerformanceCandidate).where(
        PerformanceCandidate.subject_id == subject_id)
    if cursor is not None:
        stmt = stmt.where(or_(
            PerformanceCandidate.created_at > cursor[0],
            and_(PerformanceCandidate.created_at == cursor[0],
                 PerformanceCandidate.id > cursor[1])))
    stmt = stmt.order_by(PerformanceCandidate.created_at,
                         PerformanceCandidate.id).limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    return PerformanceCandidateCollection(
        candidates=[PerformanceCandidateRead(**_candidate_view(r))
                    for r in rows],
        next_cursor=(rows[-1].created_at, rows[-1].id)
        if rows and more else None)


@router.post("/performance-candidates/{candidate_id}/adopt",
             response_model=PerformanceRevisionRead, status_code=200)
async def adopt_performance_candidate(
        candidate_id: str, body: AdoptRequest,
        session: AsyncSession = Depends(get_session)):
    try:
        revision = await revision_svc.adopt_performance_candidate(
            session, candidate_id=candidate_id,
            adopted_by=body.adopted_by)
        await session.commit()
    except IntegrityError:
        # concurrent duplicate adoption converges through
        # UNIQUE(adopted_candidate_id) (frozen R7 §10): roll back,
        # re-run — the fresh transaction sees the committed winner
        await session.rollback()
        revision = await revision_svc.adopt_performance_candidate(
            session, candidate_id=candidate_id,
            adopted_by=body.adopted_by)
        await session.commit()
    return PerformanceRevisionRead(**_revision_view(revision))


@router.get("/performance-revisions/{revision_id}",
            response_model=PerformanceRevisionRead)
async def get_performance_revision(
        revision_id: str,
        session: AsyncSession = Depends(get_session)):
    r = await revision_svc.get_performance_revision(
        session, revision_id=revision_id)
    return PerformanceRevisionRead(**_revision_view(r))


@router.get("/creative-entities/{subject_id}/performance-revisions",
            response_model=PerformanceRevisionCollection)
async def list_performance_revisions(
        subject_id: str, limit: int = 50,
        cursor_adopted: str | None = None,
        cursor_id: str | None = None,
        session: AsyncSession = Depends(get_session)):
    cursor = _cursor(cursor_adopted, cursor_id, "cursor_adopted",
                     "cursor_id")
    limit = max(1, min(200, limit))
    stmt = select(PerformanceRevision).where(
        PerformanceRevision.subject_id == subject_id)
    if cursor is not None:
        stmt = stmt.where(or_(
            PerformanceRevision.adopted_at > cursor[0],
            and_(PerformanceRevision.adopted_at == cursor[0],
                 PerformanceRevision.id > cursor[1])))
    stmt = stmt.order_by(PerformanceRevision.adopted_at,
                         PerformanceRevision.id).limit(limit + 1)
    rows = (await session.execute(stmt)).scalars().fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    return PerformanceRevisionCollection(
        revisions=[PerformanceRevisionRead(**_revision_view(r))
                   for r in rows],
        next_cursor=(rows[-1].adopted_at, rows[-1].id)
        if rows and more else None)


@router.post("/performance-revisions/{revision_id}/"
             "retarget-assessments",
             response_model=RetargetAssessmentRead, status_code=201)
async def create_retarget_assessment(
        revision_id: str, body: RetargetAssessmentCreate,
        session: AsyncSession = Depends(get_session)):
    a = await retarget_svc.assess_physical_retarget(
        session, performance_revision_id=revision_id,
        from_production_revision_id=body.from_production_revision_id,
        to_production_revision_id=body.to_production_revision_id)
    await session.commit()
    return _assessment_view(a)


@router.get("/performance-retarget-assessments/{assessment_id}",
            response_model=RetargetAssessmentRead)
async def get_retarget_assessment(
        assessment_id: str,
        session: AsyncSession = Depends(get_session)):
    a = await retarget_svc.get_assessment(
        session, assessment_id=assessment_id)
    return _assessment_view(a)


@router.post("/performance-retarget-assessments/{assessment_id}/"
             "reviews",
             response_model=RetargetReviewRead, status_code=201)
async def create_retarget_review(
        assessment_id: str, body: ReviewCreate,
        session: AsyncSession = Depends(get_session)):
    review = await retarget_svc.create_review(
        session, assessment_id=assessment_id,
        decision=body.decision, reviewed_by=body.reviewed_by,
        rationale=body.rationale)
    await session.commit()
    return RetargetReviewRead(
        id=review.id, assessment_id=review.assessment_id,
        decision=review.decision, reviewed_by=review.reviewed_by,
        reviewed_at=review.reviewed_at, rationale=review.rationale)


@router.get("/performance-retarget-reviews/{review_id}",
            response_model=RetargetReviewRead)
async def get_retarget_review(
        review_id: str,
        session: AsyncSession = Depends(get_session)):
    review = await retarget_svc.get_review(session, review_id=review_id)
    return RetargetReviewRead(
        id=review.id, assessment_id=review.assessment_id,
        decision=review.decision, reviewed_by=review.reviewed_by,
        reviewed_at=review.reviewed_at, rationale=review.rationale)


@router.get("/performance-retarget-assessments/{assessment_id}/"
            "reviews",
            response_model=RetargetReviewCollection)
async def list_retarget_reviews(
        assessment_id: str, limit: int = 50,
        cursor_reviewed: str | None = None,
        cursor_id: str | None = None,
        session: AsyncSession = Depends(get_session)):
    cursor = _cursor(cursor_reviewed, cursor_id, "cursor_reviewed",
                     "cursor_id")
    reviews = await retarget_svc.list_reviews(
        session, assessment_id=assessment_id)
    if cursor is not None:
        reviews = [r for r in reviews
                   if (r.reviewed_at, r.id) > cursor]
    more = len(reviews) > limit
    reviews = reviews[:limit]
    return RetargetReviewCollection(
        reviews=[RetargetReviewRead(
            id=r.id, assessment_id=r.assessment_id,
            decision=r.decision, reviewed_by=r.reviewed_by,
            reviewed_at=r.reviewed_at, rationale=r.rationale)
            for r in reviews],
        next_cursor=(reviews[-1].reviewed_at, reviews[-1].id)
        if reviews and more else None)


@router.post("/performance-revisions/{revision_id}/"
             "retarget-candidates",
             response_model=PerformanceCandidateRead, status_code=201)
async def create_retarget_candidate(
        revision_id: str, body: RetargetCandidateCreate,
        request: Request,
        session: AsyncSession = Depends(get_session)):
    candidate = await retarget_svc.create_retarget_candidate(
        session, request.app.state.settings, revision_id=revision_id,
        assessment_id=body.assessment_id,
        accepted_review_id=body.accepted_review_id,
        producer_id=body.producer_id,
        producer_version=body.producer_version,
        source_identity=body.source_identity,
        parameters_sha256=body.parameters_sha256)
    await session.commit()
    return PerformanceCandidateRead(**_candidate_view(candidate))
