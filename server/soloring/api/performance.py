"""M17A Performance Temporal + Dialogue/Vocal API (frozen R5 §10).

Production-concept routes only; no Blob filesystem paths, table names,
executor graphs, or model-native timing units leak through this
surface. Every mutating route is an append/adopt/select/put operation
on immutable-or-working state per the frozen plan.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.performance import (
    AdoptRequest,
    AlignmentCreate,
    AlignmentRead,
    CompatibilityRead,
    DialogueLineCollection,
    DialogueLineCreate,
    DialogueLineRead,
    DialogueLineRevisionCreate,
    DialogueLineRevisionRead,
    SelectionPut,
    SelectionRead,
    SegmentMappingPut,
    VocalCandidateCreate,
    VocalCandidateRead,
    VocalPerformanceRead,
)
from soloring.performance import alignment as alignment_svc
from soloring.performance import compatibility as compat_svc
from soloring.performance import dialogue as dialogue_svc
from soloring.performance import mapping as mapping_svc
from soloring.performance import vocal as vocal_svc

router = APIRouter(tags=["performance"])


@router.post("/projects/{project_id}/dialogue-lines",
             response_model=DialogueLineRead, status_code=201)
async def create_dialogue_line(project_id: str,
                               _body: DialogueLineCreate,
                               session: AsyncSession = Depends(get_session)):
    line = await dialogue_svc.create_dialogue_line(
        session, project_id=project_id)
    await session.commit()
    return DialogueLineRead(id=line.id, project_id=line.project_id,
                            created_at=line.created_at)


@router.get("/projects/{project_id}/dialogue-lines",
            response_model=DialogueLineCollection)
async def list_dialogue_lines(project_id: str,
                              cursor_created: str | None = None,
                              cursor_id: str | None = None,
                              limit: int = 50,
                              session: AsyncSession = Depends(get_session)):
    cursor = None
    if cursor_created is not None and cursor_id is not None:
        cursor = (cursor_created, cursor_id)
    result = await dialogue_svc.list_dialogue_lines(
        session, project_id=project_id, cursor=cursor, limit=limit)
    return DialogueLineCollection(
        lines=[DialogueLineRead(**l) for l in result["lines"]],
        next_cursor=result["next_cursor"])


@router.post("/dialogue-lines/{line_id}/revisions",
             response_model=DialogueLineRevisionRead, status_code=201)
async def create_line_revision(line_id: str,
                               body: DialogueLineRevisionCreate,
                               session: AsyncSession = Depends(get_session)):
    rev = await dialogue_svc.create_dialogue_line_revision(
        session, dialogue_line_id=line_id,
        speaker_subject_id=body.speaker_subject_id,
        wording=body.wording, language=body.language)
    await session.commit()
    return DialogueLineRevisionRead(
        id=rev.id, dialogue_line_id=rev.dialogue_line_id,
        revision_number=rev.revision_number,
        speaker_subject_id=rev.speaker_subject_id,
        language=rev.language, wording=rev.wording,
        spec_hash=rev.spec_hash, created_at=rev.created_at)


@router.get("/dialogue-lines/{line_id}/revisions",
            response_model=list[DialogueLineRevisionRead])
async def list_line_revisions(line_id: str,
                              session: AsyncSession = Depends(get_session)):
    rows = await dialogue_svc.list_dialogue_line_revisions(
        session, dialogue_line_id=line_id)
    for r in rows:
        r["dialogue_line_id"] = line_id
    return [DialogueLineRevisionRead(**r) for r in rows]


@router.post("/dialogue-line-revisions/{revision_id}/vocal-candidates",
             response_model=VocalCandidateRead, status_code=201)
async def create_vocal_candidate(revision_id: str,
                                 body: VocalCandidateCreate,
                                 request: Request,
                                 session: AsyncSession = Depends(get_session)):
    candidate = await vocal_svc.create_vocal_candidate(
        session, request.app.state.settings,
        dialogue_line_revision_id=revision_id,
        retained_audio_blob_hash=body.retained_audio_blob_hash,
        source_provenance=body.source_provenance.model_dump(
            exclude_none=True),
        trim_start_sample=body.trim_start_sample,
        trim_end_sample_exclusive=body.trim_end_sample_exclusive)
    await session.commit()
    return VocalCandidateRead(
        id=candidate.id,
        dialogue_line_revision_id=candidate.dialogue_line_revision_id,
        retained_audio_blob_hash=candidate.retained_audio_blob_hash,
        native_sample_rate_hz=candidate.native_sample_rate_hz,
        retained_sample_count=candidate.retained_sample_count,
        trim_start_sample=candidate.trim_start_sample,
        trim_end_sample_exclusive=candidate.trim_end_sample_exclusive,
        source_kind=candidate.source_kind,
        provenance_hash=candidate.provenance_hash,
        created_at=candidate.created_at)


@router.get("/dialogue-line-revisions/{revision_id}/vocal-candidates",
            response_model=list[VocalCandidateRead])
async def list_vocal_candidates(revision_id: str,
                                session: AsyncSession = Depends(get_session)):
    rows = await vocal_svc.list_vocal_candidates(
        session, dialogue_line_revision_id=revision_id)
    for r in rows:
        r["dialogue_line_revision_id"] = revision_id
    return [VocalCandidateRead(**r) for r in rows]


@router.post("/vocal-candidates/{candidate_id}/adopt",
             response_model=VocalPerformanceRead, status_code=200)
async def adopt_candidate(candidate_id: str, body: AdoptRequest,
                          session: AsyncSession = Depends(get_session)):
    from sqlalchemy.exc import IntegrityError
    try:
        vp = await vocal_svc.adopt_vocal_candidate(
            session, candidate_id=candidate_id, adopted_by=body.adopted_by)
        await session.commit()
    except IntegrityError:
        # the UNIQUE(adopted_candidate_id) race can surface at COMMIT
        # time (the winner commits between our SELECT and our write):
        # converge by rolling back and re-running — the fresh
        # transaction sees the committed winner and returns it (C03)
        await session.rollback()
        vp = await vocal_svc.adopt_vocal_candidate(
            session, candidate_id=candidate_id, adopted_by=body.adopted_by)
        await session.commit()
    return VocalPerformanceRead(
        id=vp.id, dialogue_line_revision_id=vp.dialogue_line_revision_id,
        revision_number=vp.revision_number,
        speaker_subject_id=vp.speaker_subject_id,
        retained_audio_blob_hash=vp.retained_audio_blob_hash,
        native_sample_rate_hz=vp.native_sample_rate_hz,
        retained_sample_count=vp.retained_sample_count,
        trim_start_sample=vp.trim_start_sample,
        trim_end_sample_exclusive=vp.trim_end_sample_exclusive,
        adopted_candidate_id=vp.adopted_candidate_id,
        adoption_id=vp.adoption_id, adopted_by=vp.adopted_by,
        adopted_at=vp.adopted_at)


@router.get("/dialogue-line-revisions/{revision_id}/vocal-selection",
            response_model=SelectionRead)
async def get_selection(revision_id: str,
                        session: AsyncSession = Depends(get_session)):
    return SelectionRead(**await vocal_svc.get_current_selection(
        session, dialogue_line_revision_id=revision_id))


@router.put("/dialogue-line-revisions/{revision_id}/vocal-selection",
            response_model=SelectionRead)
async def put_selection(revision_id: str, body: SelectionPut,
                        session: AsyncSession = Depends(get_session)):
    result = await vocal_svc.set_current_selection(
        session, dialogue_line_revision_id=revision_id,
        vocal_performance_revision_id=body.vocal_performance_revision_id,
        selected_by=body.selected_by)
    await session.commit()
    return SelectionRead(**result)


# the frozen first API surface carries no collection route for vocal
# performances (source review drift 2): VP reads go through the
# per-revision GET below, so the unfrozen listing route is absent


@router.get("/vocal-performance-revisions/{revision_id}",
            response_model=VocalPerformanceRead)
async def get_vocal_performance(revision_id: str,
                                session: AsyncSession = Depends(get_session)):
    vp = await vocal_svc.get_vocal_performance_revision(
        session, revision_id=revision_id)
    return VocalPerformanceRead(
        id=vp.id, dialogue_line_revision_id=vp.dialogue_line_revision_id,
        revision_number=vp.revision_number,
        speaker_subject_id=vp.speaker_subject_id,
        retained_audio_blob_hash=vp.retained_audio_blob_hash,
        native_sample_rate_hz=vp.native_sample_rate_hz,
        retained_sample_count=vp.retained_sample_count,
        trim_start_sample=vp.trim_start_sample,
        trim_end_sample_exclusive=vp.trim_end_sample_exclusive,
        adopted_candidate_id=vp.adopted_candidate_id,
        adoption_id=vp.adoption_id, adopted_by=vp.adopted_by,
        adopted_at=vp.adopted_at)


@router.put("/shots/{shot_id}/vocal-segments/{position}",
            status_code=200)
async def put_vocal_segment(shot_id: str, position: int,
                            body: SegmentMappingPut,
                            session: AsyncSession = Depends(get_session)):
    row = await mapping_svc.put_shot_vocal_segment_mapping(
        session, shot_id=shot_id, position=position,
        vocal_performance_revision_id=body.vocal_performance_revision_id,
        source_start_sample=body.source_start_sample,
        source_end_sample_exclusive=body.source_end_sample_exclusive,
        sample_rate_hz=body.sample_rate_hz,
        performance_origin_num=body.performance_origin_ms.num,
        performance_origin_den=body.performance_origin_ms.den,
        shot_anchor_num=body.shot_anchor_ms.num,
        shot_anchor_den=body.shot_anchor_ms.den)
    await session.commit()
    return {"shot_id": row.shot_id, "position": row.position,
            "mapping_hash": row.mapping_hash}


@router.delete("/shots/{shot_id}/vocal-segments/{position}",
               status_code=204)
async def delete_vocal_segment(shot_id: str, position: int,
                               session: AsyncSession = Depends(get_session)):
    await mapping_svc.delete_shot_vocal_segment_mapping(
        session, shot_id=shot_id, position=position)
    await session.commit()


@router.get("/shots/{shot_id}/vocal-segments")
async def list_vocal_segments(shot_id: str,
                              session: AsyncSession = Depends(get_session)):
    return await mapping_svc.list_shot_vocal_segment_mappings(
        session, shot_id=shot_id)


@router.post("/vocal-performance-revisions/{revision_id}/alignments",
             response_model=AlignmentRead, status_code=201)
async def create_alignment(revision_id: str, body: AlignmentCreate,
                           request: Request,
                           session: AsyncSession = Depends(get_session)):
    row = await alignment_svc.put_dialogue_alignment(
        session, request.app.state.settings,
        vocal_performance_revision_id=revision_id,
        analyzer_id=body.analyzer_id,
        analyzer_version=body.analyzer_version,
        model_identity=body.model_identity,
        runtime_identity=body.runtime_identity,
        parameters_sha256=body.parameters_sha256,
        alignment_document=body.alignment_document.model_dump(),
        derivation_run=body.derivation_run.model_dump())
    await session.commit()
    return AlignmentRead(
        id=row.id,
        vocal_performance_revision_id=row.vocal_performance_revision_id,
        analyzer_id=row.analyzer_id,
        analyzer_version=row.analyzer_version,
        model_identity=row.model_identity,
        runtime_identity=row.runtime_identity,
        parameters_sha256=row.parameters_sha256,
        retained_sha256=row.retained_sha256,
        derivation_run_hash=row.derivation_run_hash,
        derivation_run_identity=row.derivation_run_identity,
        created_at=row.created_at)


@router.get("/vocal-performance-revisions/{revision_id}/alignments",
            response_model=list[AlignmentRead])
async def list_alignments(revision_id: str,
                          session: AsyncSession = Depends(get_session)):
    rows = await alignment_svc.list_dialogue_alignments(
        session, vocal_performance_revision_id=revision_id)
    return [AlignmentRead(**r) for r in rows]


@router.post("/vocal-performance-revisions/{revision_id}/compatibility"
             "/dialogue-line-revisions/{target_revision_id}",
             response_model=CompatibilityRead)
async def assess_compatibility(revision_id: str, target_revision_id: str,
                               session: AsyncSession = Depends(get_session)):
    result = await compat_svc.assess_vocal_against_line_revision(
        session, vocal_performance_revision_id=revision_id,
        target_revision_id=target_revision_id)
    return CompatibilityRead(**result)
