"""M15 read-only assessment service surface (frozen R4 §17.1/§17.2).

Creation, verified detail reads, and cursor pagination over normalized
per-use children. Apply/tracking/discovery land in M15B/M15C; nothing
here mutates anything except the append-only assessment evidence
itself.
"""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.compatibility.canonical import verify_stored_assessment
from soloring.compatibility.evaluator import assess_revision_update
from soloring.errors import not_found
from soloring.errors import ErrorCode


async def create_assessment(
        session: AsyncSession, *, from_revision_id: str,
        to_revision_id: str) -> dict:
    return await assess_revision_update(
        session, from_revision_id=from_revision_id,
        to_revision_id=to_revision_id)


async def read_assessment(
        session: AsyncSession, assessment_id: str) -> dict:
    async with session.bind.connect() as conn:
        verified = await verify_stored_assessment(conn, assessment_id)
    parent = verified["parent"]
    uses = verified["uses"]
    counts = {v: 0 for v in (
        "COMPATIBLE_AS_IS",
        "COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION",
        "REQUIRES_REVIEW", "INCOMPATIBLE")}
    translator_count = 0
    for use in uses:
        counts[use["verdict"]] += 1
        if use["translator_id"] is not None:
            translator_count += 1
    return {
        "assessment_id": parent["id"],
        "report_hash": parent["report_hash"],
        "scope_hash": parent["scope_hash"],
        "project_id": parent["project_id"],
        "production_object_id": parent["production_object_id"],
        "from_revision_id": parent["from_revision_id"],
        "from_revision_hash": parent["from_revision_hash"],
        "to_revision_id": parent["to_revision_id"],
        "to_revision_hash": parent["to_revision_hash"],
        "evaluator_id": parent["evaluator_id"],
        "evaluator_version": parent["evaluator_version"],
        "overall_verdict": parent["overall_verdict"],
        "verdict_counts": counts,
        "translator_count": translator_count,
        "use_count": len(uses),
        "created_at": parent["created_at"],
    }


async def list_uses(
        session: AsyncSession, assessment_id: str, *, cursor: int = 0,
        limit: int = 50) -> dict:
    """Cursor pagination over the ordered, verified per-use trace."""
    if limit < 1 or limit > 200:
        limit = max(1, min(200, limit))
    async with session.bind.connect() as conn:
        await verify_stored_assessment(conn, assessment_id)
        rows = (await conn.execute(text(
            "SELECT position, composition_id, occurrence_id, "
            "composition_working_version, use_contract_hash, "
            "dimension_results_json, verdict, translator_id, "
            "translator_version, translator_output_hash "
            "FROM production_compatibility_uses "
            "WHERE assessment_id = :a AND position >= :c "
            "ORDER BY position LIMIT :l"),
            {"a": assessment_id, "c": cursor, "l": limit + 1})).fetchall()
    more = len(rows) > limit
    rows = rows[:limit]
    uses = [{
        "position": r.position,
        "composition_id": r.composition_id,
        "occurrence_id": r.occurrence_id,
        "composition_working_version": r.composition_working_version,
        "use_contract_hash": r.use_contract_hash,
        "dimensions": {
            d: json.loads(r.dimension_results_json)[d]["status"]
            for d in json.loads(r.dimension_results_json)},
        "verdict": r.verdict,
        "translator_id": r.translator_id,
        "translator_version": r.translator_version,
        "translator_output_hash": r.translator_output_hash,
    } for r in rows]
    return {"uses": uses, "next_cursor":
            rows[-1].position + 1 if rows and more else None}


async def assessment_or_404(
        session: AsyncSession, assessment_id: str) -> dict:
    try:
        return await read_assessment(session, assessment_id)
    except Exception:
        raise not_found(
            ErrorCode.PRODUCTION_REVISION_NOT_FOUND,
            f"compatibility assessment {assessment_id!r} not found")
