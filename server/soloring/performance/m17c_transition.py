"""M17C-aware wrappers for the published M17B authority transitions.

The public M17B routes continue to own adoption/retarget entry points. These
wrappers preserve the predecessor behavior for generic candidates while adding
the optional PF-03 companion law when a dialogue-bound binding is present.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.performance import m17c_binding as binding_svc
from soloring.performance import retarget as retarget_svc
from soloring.performance import revision as revision_svc
from soloring.performance.m17c_models import PerformanceRevisionVocalBinding
from soloring.performance.models import PerformanceRevision


async def adopt_performance_candidate(
    session: AsyncSession,
    settings,
    *,
    candidate_id: str,
    adopted_by: str,
) -> PerformanceRevision:
    candidate = await revision_svc.get_performance_candidate(
        session, candidate_id=candidate_id)
    candidate_binding = await binding_svc.adoption_binding_precheck(
        session, settings, candidate)
    existing = (await session.execute(
        select(PerformanceRevision).where(
            PerformanceRevision.adopted_candidate_id == candidate.id)
    )).scalar_one_or_none()
    if existing is not None:
        # Preserve M17B winner-first historical semantics while adding the
        # M17C winner companion revalidation. Missing/divergent companion is
        # corruption and is never repaired by a replay.
        await revision_svc.verify_candidate_integrity(
            session, settings, candidate)
        revision_svc.revalidate_winner(existing, candidate)
        await binding_svc.converge_revision_binding(
            session, settings, candidate, existing, candidate_binding,
            allow_create=False)
        return existing

    revision = await revision_svc.adopt_performance_candidate(
        session, settings, candidate_id=candidate_id, adopted_by=adopted_by)
    await binding_svc.converge_revision_binding(
        session, settings, candidate, revision, candidate_binding,
        allow_create=True)
    return revision


async def create_retarget_candidate(
    session: AsyncSession,
    settings,
    *,
    revision_id: str,
    assessment_id: str,
    accepted_review_id: str,
    producer_id: str,
    producer_version: str,
    source_identity: str | None,
    parameters_sha256: str | None,
):
    source = await revision_svc.get_performance_revision(
        session, revision_id=revision_id)
    source_binding = await session.get(PerformanceRevisionVocalBinding,
                                       source.id)
    if source_binding is not None:
        # C05: corrupted binding/VP lineage refuses before a new retarget
        # candidate can become fresh evidence.
        await binding_svc.verify_revision_vocal_binding(
            session, settings, source, source_binding)
    candidate = await retarget_svc.create_retarget_candidate(
        session,
        settings,
        revision_id=revision_id,
        assessment_id=assessment_id,
        accepted_review_id=accepted_review_id,
        producer_id=producer_id,
        producer_version=producer_version,
        source_identity=source_identity,
        parameters_sha256=parameters_sha256,
    )
    await binding_svc.preserve_retarget_binding(
        session, settings, source_revision=source, candidate=candidate)
    return candidate
