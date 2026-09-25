"""M17C PF-03 dialogue-bound Performance API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.m17b_performance import PerformanceCandidateRead
from soloring.api.schemas.m17c_performance import (
    DialogueBoundPerformanceCandidateCreate,
    VocalBindingRead,
)
from soloring.performance import m17c_binding as m17c_svc
from soloring.performance.models import PerformanceCandidate

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
    session: AsyncSession = Depends(get_session),
):
    row = await m17c_svc.get_candidate_vocal_binding(
        session, candidate_id=candidate_id)
    return VocalBindingRead(**m17c_svc.binding_view(row))


@router.get(
    "/performance-revisions/{revision_id}/vocal-binding",
    response_model=VocalBindingRead,
)
async def get_revision_vocal_binding(
    revision_id: str,
    session: AsyncSession = Depends(get_session),
):
    row = await m17c_svc.get_revision_vocal_binding(
        session, revision_id=revision_id)
    return VocalBindingRead(**m17c_svc.binding_view(row))
