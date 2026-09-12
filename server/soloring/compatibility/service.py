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
    result = await assess_revision_update(
        session, from_revision_id=from_revision_id,
        to_revision_id=to_revision_id)
    if result.get("assessment_id") is None:
        return result
    # Frozen R6 S9.2/S17.1: the advisory diagnostic block is a
    # RESPONSE-TIME projection of CURRENT state — never part of
    # scope_hash/report_hash/immutable identity, never replayed from
    # report_json. Convergent calls therefore report fresh diagnostics
    # over the same immutable assessment.
    from soloring.compatibility.impact import advisory_references

    async with session.bind.connect() as conn:
        advisory = await advisory_references(
            conn, production_revision_id=from_revision_id)
    result["advisory"] = advisory
    return result


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


async def impact_inventory(session, *, production_revision_id: str) -> dict:
    """M15B read-only affected-work inventory (frozen R6 S9)."""
    from soloring.compatibility.impact import (
        advisory_references, direct_working_uses)

    async with session.bind.connect() as conn:
        uses = await direct_working_uses(
            conn, production_revision_id=production_revision_id)
        advisory = await advisory_references(
            conn, production_revision_id=production_revision_id)
    return {"production_revision_id": production_revision_id,
            "use_count": len(uses), "uses": uses,
            "advisory": advisory}


async def read_tracking(session, *, composition_id: str,
                        occurrence_id: str) -> dict:
    from soloring.compatibility.impact import tracking_policy

    async with session.bind.connect() as conn:
        return await tracking_policy(
            conn, composition_id=composition_id,
            occurrence_id=occurrence_id)


async def put_tracking(session, *, composition_id: str,
                       occurrence_id: str, mode: str,
                       expected_policy_version: int) -> dict:
    from soloring.compatibility.impact import put_tracking_policy

    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            result = await put_tracking_policy(
                conn, composition_id=composition_id,
                occurrence_id=occurrence_id, mode=mode,
                expected_policy_version=expected_policy_version)
            await conn.commit()
            return result
        except Exception:
            await conn.rollback()
            raise


async def revision_updates(session, *, production_object_id: str) -> dict:
    from soloring.compatibility.impact import update_discovery

    async with session.bind.connect() as conn:
        return await update_discovery(
            conn, production_object_id=production_object_id)


async def apply_assessment(session, *, assessment_id: str,
                           selected_uses: list) -> dict:
    from soloring.compatibility.apply import apply_revision_update

    return await apply_revision_update(
        session, assessment_id=assessment_id,
        selected_uses=selected_uses)
