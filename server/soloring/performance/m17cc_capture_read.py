"""M17C-C slice 2: the performance-plane coherent READ (frozen R4 11.1).

The ONE capture read seam resolves the complete performance plane on
the SAME pinned SQLite snapshot as every predecessor plane, and returns
it as a plain immutable-in-practice value — the mapping rows, the exact
referenced PerformanceRevision closure fields, the immutable revision
vocal bindings, the paired vocal mappings, and the current readiness
projection are ALL fixed in memory before the fenced persistence unit
begins. No second connection is opened (that would race); the M17C-B
session-based verifiers run through an ``AsyncSession`` bound to the
pinned connection in savepoint-join mode, so their reads see exactly
the pinned snapshot.

Slice-2 boundary: this module READS and SHAPES only. It never writes
companion rows (slice 3) and contains no execution/derived-input
production (M17C-D).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.performance.m17c_models import (
    PerformanceRevisionVocalBinding,
)
from soloring.performance.models import ShotVocalSegmentMapping

# the frozen R4 11.2 embedded segment key order is produced by dict
# literal below; canonical serialization is insertion-order stable, and
# build_capturable_snapshot asserts the complete grammar structurally.


async def resolve_performance_plane(conn, settings, shot_id: str):
    """Resolve the complete performance plane on the PINNED snapshot.

    Returns ``None`` when the Shot carries no working performance
    mappings (the capture emits the exact predecessor snapshot). When
    mappings exist, returns the complete capture value:

    ``{"ready": bool, "segments": [<embedded-shape dicts, position
    order>], "segment_readiness": [<projection states/diagnostics>]}``

    Impossible persisted history fails closed exactly as every other
    M17C-B authority read (500 INTERNAL_INVARIANT_VIOLATION through
    the shared seam); non-READY working states do NOT raise here —
    readiness is data the CAPTURE path gates on (frozen 11.2/11.4),
    so non-capture consumers of the one read stay unaffected.
    """
    n = (await conn.execute(text(
        "SELECT COUNT(*) FROM shot_performance_segment_mappings "
        "WHERE shot_id = :s"), {"s": shot_id})).scalar_one()
    if not n:
        return None

    from soloring.performance.m17c_shot_mapping import (
        project_shot_performance_readiness,
    )
    # the M17C-B verifiers are session-based; bind a short-lived
    # session to THIS pinned connection (savepoint join) so every read
    # sees the exact snapshot the outer BEGIN pinned — never a second
    # pooled connection
    async with AsyncSession(
            bind=conn, expire_on_commit=False,
            join_transaction_mode="create_savepoint") as pinned:
        projection = await project_shot_performance_readiness(
            pinned, settings, shot_id=shot_id)
        segments = []
        for seg in projection["segments"]:
            position = seg["position"]
            pr_id = seg["performance_revision_id"]
            pr = await _pr_row(pinned, pr_id)
            vocal = None
            if seg["vocal_mapping_position"] is not None:
                binding = await pinned.get(
                    PerformanceRevisionVocalBinding, pr_id)
                if binding is None:
                    # the seam verified classification/cardinality; a
                    # missing binding here is impossible persisted
                    # history, fail closed
                    from soloring.performance.m17c_shot_mapping import (
                        _corrupt,
                    )
                    raise _corrupt(
                        f"dialogue-bound revision {pr_id!r} lost its "
                        "PF-03 binding inside the capture read")
                paired = await pinned.get(ShotVocalSegmentMapping,
                                          (shot_id,
                                           seg["vocal_mapping_position"]))
                if paired is None:
                    from soloring.performance.m17c_shot_mapping import (
                        _corrupt,
                    )
                    raise _corrupt(
                        f"paired vocal mapping {shot_id!r}@"
                        f"{seg['vocal_mapping_position']} disappeared "
                        "inside the capture read")
                vocal = {
                    "vocal_performance_revision_id":
                        binding.vocal_performance_revision_id,
                    "vocal_binding_hash": binding.binding_hash,
                    "source_start_sample": paired.source_start_sample,
                    "source_end_sample_exclusive":
                        paired.source_end_sample_exclusive,
                    "sample_rate_hz": paired.sample_rate_hz,
                }
            segments.append({
                "position": position,
                "subject_id": pr["subject_id"],
                "performance_revision_id": pr_id,
                "performance_payload_sha256":
                    pr["canonical_channel_payload_sha256"],
                "performance_profile_id": pr["performance_profile_id"],
                "performance_kind": pr["performance_kind"],
                "performance_start_ms": seg["performance_start_ms"],
                "performance_end_ms": seg["performance_end_ms"],
                "shot_anchor_ms": seg["shot_anchor_ms"],
                "vocal": vocal,
            })
    ready = all(s["readiness"] == "READY" for s in projection["segments"])
    return {
        "ready": ready,
        "segments": segments,
        "segment_readiness": [
            {"position": s["position"], "readiness": s["readiness"],
             "readiness_diagnostics": s.get("readiness_diagnostics")}
            for s in projection["segments"]],
    }


async def _pr_row(pinned: AsyncSession, pr_id: str) -> dict:
    from soloring.performance.models import PerformanceRevision
    pr = await pinned.get(PerformanceRevision, pr_id)
    if pr is None:
        from soloring.performance.m17c_shot_mapping import _corrupt
        raise _corrupt(
            f"performance mapping references a missing "
            f"PerformanceRevision {pr_id!r} inside the capture read")
    return {
        "subject_id": pr.subject_id,
        "performance_kind": pr.performance_kind,
        "performance_profile_id": pr.performance_profile_id,
        "canonical_channel_payload_sha256":
            pr.canonical_channel_payload_sha256,
    }
