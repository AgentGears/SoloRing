"""M17C PF-03 dialogue-bound Performance API.

The two M17B authority-transition paths are intentionally shadowed by this
router once M17C is enabled. Generic candidates retain the exact M17B behavior;
dialogue-bound candidates additionally revalidate/copy their immutable PF-03
companion. The router is included before the published M17B router so these two
path+method pairs are the active handlers.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.m17b_performance import (
    AdoptRequest,
    PerformanceCandidateRead,
    PerformanceRevisionRead,
    RetargetCandidateCreate,
)
from soloring.api.schemas.m17c_performance import (
    DialogueBoundPerformanceCandidateCreate,
    PerformanceSegmentPut,
    PerformanceSegmentRead,
    VocalBindingRead,
)
from soloring.performance import m17c_binding as m17c_svc
from soloring.performance import m17c_shot_mapping as shot_mapping_svc
from soloring.performance import m17c_transition as transition_svc
from soloring.performance.models import PerformanceCandidate, PerformanceRevision

router = APIRouter(tags=["performance-m17c"])


def _candidate_view(c: PerformanceCandidate) -> dict:
    return {
        "id": c.id,
        "project_id": c.project_id,
        "subject_id": c.subject_id,
        "performance_kind": c.performance_kind,
        "performance_profile_id": c.performance_profile_id,
        "temporal_start_ms": {
            "num": c.temporal_start_num,
            "den": c.temporal_start_den,
        },
        "temporal_end_ms": {
            "num": c.temporal_end_num,
            "den": c.temporal_end_den,
        },
        "canonical_channel_payload_sha256":
            c.canonical_channel_payload_sha256,
        "canonical_channel_payload_blob_hash":
            c.canonical_channel_payload_blob_hash,
        "payload_schema_version": c.payload_schema_version,
        "source_kind": c.source_kind,
        "provenance_hash": c.provenance_hash,
        "created_at": c.created_at,
    }


def _revision_view(r: PerformanceRevision) -> dict:
    return {
        "id": r.id,
        "project_id": r.project_id,
        "subject_id": r.subject_id,
        "performance_kind": r.performance_kind,
        "performance_profile_id": r.performance_profile_id,
        "temporal_start_ms": {
            "num": r.temporal_start_num,
            "den": r.temporal_start_den,
        },
        "temporal_end_ms": {
            "num": r.temporal_end_num,
            "den": r.temporal_end_den,
        },
        "canonical_channel_payload_sha256":
            r.canonical_channel_payload_sha256,
        "canonical_channel_payload_blob_hash":
            r.canonical_channel_payload_blob_hash,
        "payload_schema_version": r.payload_schema_version,
        "source_kind": r.source_kind,
        "provenance_hash": r.provenance_hash,
        "adopted_candidate_id": r.adopted_candidate_id,
        "adoption_id": r.adoption_id,
        "adopted_by": r.adopted_by,
        "adopted_at": r.adopted_at,
    }


async def _create(
    session: AsyncSession,
    settings,
    *,
    subject_id: str,
    body: DialogueBoundPerformanceCandidateCreate,
):
    return await m17c_svc.create_dialogue_bound_performance_candidate(
        session,
        settings,
        subject_id=subject_id,
        performance_kind=body.performance_kind,
        performance_profile_id=body.performance_profile_id,
        temporal_start_num=body.temporal_domain.start.num,
        temporal_start_den=body.temporal_domain.start.den,
        temporal_end_num=body.temporal_domain.end.num,
        temporal_end_den=body.temporal_domain.end.den,
        channels=[ch.model_dump() for ch in body.channels],
        source_provenance={
            **body.source_provenance.model_dump(),
            "retarget": None,
        },
        vocal_binding=body.vocal_binding.model_dump(),
    )


@router.post(
    "/performance-candidates/{candidate_id}/adopt",
    response_model=PerformanceRevisionRead,
    status_code=200,
)
async def adopt_performance_candidate(
    candidate_id: str,
    body: AdoptRequest,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    try:
        revision = await transition_svc.adopt_performance_candidate(
            session,
            request.app.state.settings,
            candidate_id=candidate_id,
            adopted_by=body.adopted_by,
        )
        await session.commit()
    except IntegrityError:
        await session.rollback()
        revision = await transition_svc.adopt_performance_candidate(
            session,
            request.app.state.settings,
            candidate_id=candidate_id,
            adopted_by=body.adopted_by,
        )
        await session.commit()
    return PerformanceRevisionRead(**_revision_view(revision))


@router.post(
    "/performance-revisions/{revision_id}/retarget-candidates",
    response_model=PerformanceCandidateRead,
    status_code=201,
)
async def create_retarget_candidate(
    revision_id: str,
    body: RetargetCandidateCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    candidate = await transition_svc.create_retarget_candidate(
        session,
        request.app.state.settings,
        revision_id=revision_id,
        assessment_id=body.assessment_id,
        accepted_review_id=body.accepted_review_id,
        producer_id=body.producer_id,
        producer_version=body.producer_version,
        source_identity=body.source_identity,
        parameters_sha256=body.parameters_sha256,
    )
    await session.commit()
    return PerformanceCandidateRead(**_candidate_view(candidate))


@router.post(
    "/creative-entities/{subject_id}/dialogue-bound-performance-candidates",
    response_model=PerformanceCandidateRead,
    status_code=201,
)
async def create_dialogue_bound_performance_candidate(
    subject_id: str,
    body: DialogueBoundPerformanceCandidateCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    try:
        candidate, _ = await _create(
            session,
            request.app.state.settings,
            subject_id=subject_id,
            body=body,
        )
        await session.commit()
    except IntegrityError:
        # Preserve M17B's content-addressed Blob collision convergence:
        # rollback + rerun still creates this request's distinct candidate
        # and its immutable synchronization companion atomically.
        await session.rollback()
        candidate, _ = await _create(
            session,
            request.app.state.settings,
            subject_id=subject_id,
            body=body,
        )
        await session.commit()
    return PerformanceCandidateRead(**_candidate_view(candidate))


@router.get(
    "/performance-candidates/{candidate_id}/vocal-binding",
    response_model=VocalBindingRead,
)
async def get_candidate_vocal_binding(
    candidate_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    # SR26-03: authoritative reads verify the PF-03 classification,
    # canonical binding bytes/hash, parent/companion closure, and exact
    # immutable identity before representing the binding as authority.
    # Damaged PF-03 closure fails closed as corruption (500), not 404.
    row = await m17c_svc.read_candidate_vocal_binding(
        session, request.app.state.settings, candidate_id=candidate_id)
    return VocalBindingRead(**m17c_svc.binding_view(row))


@router.get(
    "/performance-revisions/{revision_id}/vocal-binding",
    response_model=VocalBindingRead,
)
async def get_revision_vocal_binding(
    revision_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    row = await m17c_svc.read_revision_vocal_binding(
        session, request.app.state.settings, revision_id=revision_id)
    return VocalBindingRead(**m17c_svc.binding_view(row))


@router.put(
    "/shots/{shot_id}/performance-segments/{position}",
    status_code=200,
)
async def put_performance_segment(
    shot_id: str,
    position: int,
    body: PerformanceSegmentPut,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """M17C-B frozen R4 §8: mutable Shot working intent. For
    dialogue-bound PerformanceRevisions the supplied interval/anchor
    must equal the exact induced values (no tolerance)."""
    row = await shot_mapping_svc.put_shot_performance_segment_mapping(
        session, request.app.state.settings,
        shot_id=shot_id, position=position,
        performance_revision_id=body.performance_revision_id,
        performance_start_num=body.performance_start_ms.num,
        performance_start_den=body.performance_start_ms.den,
        performance_end_num=body.performance_end_ms.num,
        performance_end_den=body.performance_end_ms.den,
        shot_anchor_num=body.shot_anchor_ms.num,
        shot_anchor_den=body.shot_anchor_ms.den,
        vocal_mapping_position=body.vocal_mapping_position)
    await session.commit()
    return {"shot_id": row.shot_id, "position": row.position,
            "mapping_hash": row.mapping_hash}


@router.delete(
    "/shots/{shot_id}/performance-segments/{position}",
    status_code=204,
)
async def delete_performance_segment(
    shot_id: str,
    position: int,
    session: AsyncSession = Depends(get_session),
):
    await shot_mapping_svc.delete_shot_performance_segment_mapping(
        session, shot_id=shot_id, position=position)
    await session.commit()


@router.get(
    "/shots/{shot_id}/performance-segments",
    response_model=list[PerformanceSegmentRead],
)
async def list_performance_segments(
    shot_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    return await shot_mapping_svc.list_shot_performance_segment_mappings(
        session, request.app.state.settings, shot_id=shot_id)


@router.get("/shots/{shot_id}/performance-readiness")
async def get_performance_readiness(
    shot_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    """frozen R4 §9: readiness is a read-time projection; STALE never
    mutates authority or historical state."""
    return await shot_mapping_svc.project_shot_performance_readiness(
        session, request.app.state.settings, shot_id=shot_id)
