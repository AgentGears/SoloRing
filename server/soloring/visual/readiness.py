"""Combined M7 + M8 shot readiness (frozen plan §52) and the visual
readiness projection consumed by Shot capture/detail (§53).

ONE composed current-state interpretation: M7 semantic resolution runs
first on the caller's coherent read; if M7 is not ready, M8 projects
blocked honestly (§52.1) without partial resolution; only a semantically
ready state resolves visual facets (§52.2). The combined execution gate
(§52.3) requires BOTH ready flags.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncConnection

from soloring.errors import ErrorCode, SoloRingError
from soloring.visual.resolver import (
    VisualResolutionResult,
    resolve_visual_reference_pack_async,
)


def blocked_by_semantics(
    shot_id: str, m7_issues: list[dict]
) -> VisualResolutionResult:
    """§52.1: M7 not ready → visual false/NULL, M7 blockers surfaced
    honestly, no partial resolution."""
    return VisualResolutionResult(
        shot_id=shot_id,
        visual_continuity_ready=False,
        issues=tuple(m7_issues),
        facet_statuses=(),
        pack=None,
        visual_reference_pack_hash=None,
    )


async def resolve_visual_readiness(
    conn: AsyncConnection,
    shot_id: str,
    semantic_ready: bool,
    m7_issues: list[dict],
    resolved_deps,
    feature_states,
    *,
    blob_store=None,
) -> VisualResolutionResult:
    """The composed resolver entry used by capture + inspection (§44).

    ``blob_store`` is the physical-bytes authority (r2-gate B2): HTTP
    callers pass the running app's store; omission falls back to the
    process-level Settings singleton."""
    if not semantic_ready:
        return blocked_by_semantics(shot_id, m7_issues)
    return await resolve_visual_reference_pack_async(
        shot_id, (resolved_deps, feature_states), conn=conn,
        blob_store=blob_store,
    )


def visual_first_blocker(result: VisualResolutionResult) -> SoloRingError | None:
    """§53: the first canonical M8 blocker, with the full ordered set in
    details. Returns None when visually ready."""
    if result.visual_continuity_ready:
        return None
    if not result.issues:
        return None  # semantic blockers are raised by the M7 path
    first = result.issues[0]
    code = first["error_code"]
    if code == ErrorCode.VISUAL_REALIZATION_REQUIRED:
        return SoloRingError(
            code,
            "A required VisualFacet has no exact state-specific "
            "VisualAnchor for the current semantic state.",
            status_code=409,
            details={"issues": list(result.issues)},
        )
    if code == ErrorCode.VISUAL_ANCHOR_APPROVAL_REQUIRED:
        return SoloRingError(
            code,
            "A required exact VisualAnchor exists but has no approved "
            "revision.",
            status_code=409,
            details={"issues": list(result.issues)},
        )
    # Any other issue code on a not-ready result is impossible under legal
    # writes (corruption already raised as invariant inside the resolver).
    from soloring.errors import internal_invariant

    return internal_invariant(
        f"Visual resolution not ready with unraisable issue {code!r}."
    )
