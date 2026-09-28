"""M17C-aware wrappers for the published M17B authority transitions.

The M17C public transition routes preserve predecessor behavior for generic
candidates while adding the optional PF-03 companion law when dialogue-bound
binding authority is present.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.performance import m17c_binding as binding_svc
from soloring.performance import retarget as retarget_svc
from soloring.performance import revision as revision_svc
from soloring.performance.m17c_contract import corrupt
from soloring.performance.m17c_models import (
    PerformanceCandidateVocalBinding,
    PerformanceRevisionVocalBinding,
)
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
        # corruption and is never repaired by a replay. IR-03: the persisted
        # candidate is historical authority — corruption contract, never a
        # fresh-request 4xx.
        await revision_svc.verify_candidate_authority_historical(
            session, settings, candidate)
        revision_svc.revalidate_winner_historical(existing, candidate)
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

    # SR26-01: the immutable applicability discriminator is verified
    # first — a VOCAL_V1 revision whose companions have totally
    # disappeared refuses here instead of downgrading to generic M17B
    # retargeting. The XOR companion check is retained beneath it.
    await binding_svc.verify_revision_sync_classification(session, source)
    # IR-03: mode-independent SOURCE authority BEFORE any new evidence
    # is created — full historical candidate integrity, the source
    # revision's copied closure, and its adoption metadata. This proof
    # runs for NONE sources exactly as for VOCAL_V1; the underlying
    # retarget service must never copy fields from an unverified
    # source revision.
    await revision_svc.verify_revision_authority_historical(
        session, settings, source)
    candidate_binding = await session.get(
        PerformanceCandidateVocalBinding, source.adopted_candidate_id)
    source_binding = await session.get(
        PerformanceRevisionVocalBinding, source.id)
    if (candidate_binding is None) != (source_binding is None):
        raise corrupt(
            "adopted PerformanceRevision PF-03 companion closure is incomplete")
    if source_binding is not None:
        # Corrupted binding/VP lineage refuses before a new retarget candidate
        # can become fresh evidence.
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

    # Defend the same closure law across the complete transaction. PF-03 rows
    # are immutable through the public API, but a damaged database must still
    # fail closed if the source companion disappears between precheck and copy.
    if source_binding is not None:
        copied = await session.get(
            PerformanceCandidateVocalBinding, candidate.id)
        if copied is None:
            raise corrupt(
                "dialogue-bound retarget candidate is missing its PF-03 binding")
    return candidate
