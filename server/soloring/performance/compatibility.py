"""Dialogue/vocal compatibility evaluator v1 + STALE readiness
(frozen R5 §8). The exact M15 four-verdict vocabulary; v1 produces no
COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION for vocal authority (audio
editing is new candidate production, never authority translation).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from soloring.errors import ErrorCode, SoloRingError, not_found
from soloring.performance.models import DialogueLineRevision

EVALUATOR_ID = "soloring.dialogue_vocal_compatibility"
EVALUATOR_VERSION = 1

COMPATIBLE_AS_IS = "COMPATIBLE_AS_IS"
COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION = (
    "COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION")
REQUIRES_REVIEW = "REQUIRES_REVIEW"
INCOMPATIBLE = "INCOMPATIBLE"


async def assess_vocal_against_line_revision(
        session: AsyncSession, *,
        vocal_performance_revision_id: str,
        target_revision_id: str) -> dict:
    from soloring.performance.vocal import (
        get_vocal_performance_revision)
    vp = await get_vocal_performance_revision(
        session, revision_id=vocal_performance_revision_id)
    target = await session.get(DialogueLineRevision, target_revision_id)
    if target is None:
        raise not_found(ErrorCode.DIALOGUE_LINE_REVISION_NOT_FOUND,
                        f"dialogue line revision {target_revision_id!r} "
                        "not found")
    source = await session.get(DialogueLineRevision,
                               vp.dialogue_line_revision_id)
    verdict = _verdict(source, target)
    return {"evaluator_id": EVALUATOR_ID,
            "evaluator_version": EVALUATOR_VERSION,
            "vocal_performance_revision_id": vp.id,
            "source_dialogue_line_revision_id": source.id,
            "target_dialogue_line_revision_id": target.id,
            "verdict": verdict}


def _verdict(source: DialogueLineRevision,
             target: DialogueLineRevision) -> str:
    if source.id == target.id:
        return COMPATIBLE_AS_IS
    same_triple = (
        source.speaker_subject_id == target.speaker_subject_id
        and source.wording == target.wording
        and source.language == target.language)
    if same_triple:
        return REQUIRES_REVIEW
    return INCOMPATIBLE
