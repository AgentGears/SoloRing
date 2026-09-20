"""Current-readiness projection for shot vocal segment mappings (frozen
R5 §8.2; source review finding 3 + package-layout drift). Read-time
DIAGNOSIS ONLY, derived from the exact mapping VP versus the line
revision's current EXPLICIT selection; the mapping row is never mutated
by a later selection change.

Vocabulary: CURRENT — the mapping's VP IS the current explicit
selection; STALE — the mapping's VP is not the current selection
(including an UNSET selection): the working timing decision still names
a superseded (or unselected) performance. STALE never repairs, never
rewrites, never blocks — it reports.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from soloring.performance.models import (ShotVocalSegmentMapping,
                                         VocalPerformanceRevision,
                                         VocalPerformanceSelection)

CURRENT = "CURRENT"
STALE = "STALE"


async def project_mapping_readiness(
        session: AsyncSession,
        mapping: ShotVocalSegmentMapping) -> dict:
    """The current-readiness diagnosis for one mapping row."""
    vp = await session.get(
        VocalPerformanceRevision,
        mapping.vocal_performance_revision_id)
    selection = await session.get(
        VocalPerformanceSelection,
        vp.dialogue_line_revision_id) if vp is not None else None
    selected = (selection.selected_vocal_performance_revision_id
                if selection is not None else None)
    state = (CURRENT if selected == mapping.vocal_performance_revision_id
             else STALE)
    return {"readiness": state,
            "mapped_vocal_performance_revision_id":
            mapping.vocal_performance_revision_id,
            "selected_vocal_performance_revision_id": selected,
            "selection_state":
            ("UNSET" if selection is not None and selected is None
             else ("SELECTED" if selected is not None else "MISSING"))}


def stale_readiness(mapping: ShotVocalSegmentMapping,
                    selection: VocalPerformanceSelection | None) -> bool:
    """Boolean form of the same diagnosis (kept for direct row-level
    checks): True when the mapping's VP is not the current selection."""
    if selection is None:
        return True
    return (selection.selected_vocal_performance_revision_id !=
            mapping.vocal_performance_revision_id)
