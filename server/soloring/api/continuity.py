"""Continuity endpoints (M6C §47, §63): working dependencies + historical
continuity provenance.

The historical endpoints traverse ONLY persisted history —
``shot_revisions`` and its immutable dependency rows — never current Story
World state (plan §63/M6-F8).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.shots import SemanticDependencyWithEntity
from soloring.continuity import dependencies as dependency_svc

router = APIRouter(tags=["continuity"])


class SemanticDependencyAssignment(BaseModel):
    """Exactly the two client-expressible fields; positions are
    server-assigned and any extra field is rejected (M6C hardening)."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    role: str


class SemanticDependencyPut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dependencies: list[SemanticDependencyAssignment]


async def _get_shot_or_404(session: AsyncSession, shot_id: str) -> None:
    from soloring.errors import ErrorCode, not_found
    from soloring.domain.ids import is_uuid

    if not is_uuid(shot_id):
        raise not_found(ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id} not found.")
    row = (
        await session.execute(
            text("SELECT 1 FROM shots WHERE id = :s AND deleted_at IS NULL"),
            {"s": shot_id},
        )
    ).first()
    if row is None:
        raise not_found(ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id} not found.")


@router.put("/shots/{shot_id}/semantic-dependencies")
async def put_semantic_dependencies(
    shot_id: str,
    payload: SemanticDependencyPut,
    session: AsyncSession = Depends(get_session),
) -> dict:
    await dependency_svc.replace_semantic_dependencies(
        session, shot_id, [d.model_dump() for d in payload.dependencies]
    )
    return {"assigned": len(payload.dependencies)}


@router.get(
    "/shots/{shot_id}/semantic-dependencies",
    response_model=list[SemanticDependencyWithEntity],
)
async def get_semantic_dependencies(
    shot_id: str, session: AsyncSession = Depends(get_session)
) -> list[SemanticDependencyWithEntity]:
    await _get_shot_or_404(session, shot_id)
    rows = await dependency_svc.list_working_dependencies(session, shot_id)
    return [
        SemanticDependencyWithEntity(
            entity_id=r["entity_id"],
            entity_kind=r["entity_kind"],
            entity_name=r["entity_name"],
            role=r["role"],
            position=r["position"],
            resolved_revision_id=r["approved_revision_id"] or "",
            resolved_revision_number=r["revision_number"] or 0,
            resolved_revision_hash=r["spec_hash"] or "",
        )
        for r in rows
    ]


async def _revision_continuity(session: AsyncSession, revision_id: str) -> dict:
    """The historical continuity projection of one ShotRevision (§63).

    Legacy v1 revisions mean 'no semantic dependency snapshot' by definition
    (M6-F14): schema nulls and an empty dependency list — never a
    reconstruction from current Story World state.
    """
    from soloring.errors import ErrorCode, not_found
    from soloring.domain.ids import is_uuid

    if not is_uuid(revision_id):
        raise not_found(
            ErrorCode.SHOT_NOT_FOUND, f"ShotRevision {revision_id} not found."
        )
    rev = (
        await session.execute(
            text(
                "SELECT id, snapshot_hash, continuity_spec_json, "
                "continuity_spec_hash FROM shot_revisions WHERE id = :rid"
            ),
            {"rid": revision_id},
        )
    ).mappings().one_or_none()
    if rev is None:
        raise not_found(
            ErrorCode.SHOT_NOT_FOUND, f"ShotRevision {revision_id} not found."
        )

    dependencies: list[dict[str, Any]] = []
    continuity_schema_version = None
    if rev["continuity_spec_json"] is not None:
        import json

        spec = json.loads(rev["continuity_spec_json"])
        continuity_schema_version = spec.get("schema_version")
        dependencies = list(spec.get("dependencies", []))
        # Rebuild the FULL canonical spec from the immutable dependency rows
        # joined with their entities/revisions and compare canonical bytes
        # AND hash with what is persisted — the consistency claim is then
        # literal: any provenance disagreement fails loudly (M6C hardening).
        from soloring.continuity.snapshots import (
            ResolvedDependency,
            build_continuity_spec,
        )
        from soloring.domain.canonical import (
            canonical_hash,
            canonical_json_str,
        )
        from soloring.errors import internal_invariant

        rows = (
            await session.execute(
                text(
                    "SELECT sred.entity_id, sred.role, sred.position, "
                    "sred.source, ce.kind AS entity_kind, "
                    "er.id AS entity_revision_id, "
                    "er.revision_number AS entity_revision_number, "
                    "er.spec_hash AS entity_revision_hash "
                    "FROM shot_revision_entity_dependencies sred "
                    "JOIN creative_entities ce ON ce.id = sred.entity_id "
                    "JOIN entity_revisions er ON er.id = sred.entity_revision_id "
                    "WHERE sred.shot_revision_id = :rid"
                ),
                {"rid": revision_id},
            )
        ).mappings().all()
        rebuilt = build_continuity_spec([
            ResolvedDependency(
                entity_id=r["entity_id"],
                entity_kind=r["entity_kind"],
                entity_revision_id=r["entity_revision_id"],
                entity_revision_number=r["entity_revision_number"],
                entity_revision_hash=r["entity_revision_hash"],
                role=r["role"],
                position=r["position"],
                source=r["source"],
            )
            for r in rows
        ])
        if (
            canonical_json_str(rebuilt) != rev["continuity_spec_json"]
            or canonical_hash(rebuilt) != rev["continuity_spec_hash"]
        ):
            raise internal_invariant(
                f"ShotRevision {revision_id} dependency rows disagree with "
                "its canonical continuity spec."
            )

    import json as _json

    snapshot = None
    schema_version = None
    snap_row = (
        await session.execute(
            text("SELECT snapshot_json FROM shot_revisions WHERE id = :rid"),
            {"rid": revision_id},
        )
    ).scalar_one_or_none()
    if snap_row is not None:
        schema_version = _json.loads(snap_row).get("schema_version")

    return {
        "shot_revision_id": rev["id"],
        "snapshot_schema_version": schema_version,
        "snapshot_hash": rev["snapshot_hash"],
        "continuity_schema_version": continuity_schema_version,
        "continuity_spec_hash": rev["continuity_spec_hash"],
        "dependencies": dependencies,
    }


@router.get("/shot-revisions/{revision_id}/continuity")
async def shot_revision_continuity(
    revision_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    return await _revision_continuity(session, revision_id)


@router.get("/generations/{generation_id}/continuity")
async def generation_continuity(
    generation_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """Traverse Generation -> historical ShotRevision -> continuity graph.

    Never resolves current Entity approvals (M6-F8/§63)."""
    from soloring.errors import ErrorCode, not_found
    from soloring.domain.ids import is_uuid

    if not is_uuid(generation_id):
        raise not_found(
            ErrorCode.GENERATION_NOT_FOUND,
            f"Generation {generation_id} not found.",
        )
    revision_id = (
        await session.execute(
            text(
                "SELECT shot_revision_id FROM generations WHERE id = :gid"
            ),
            {"gid": generation_id},
        )
    ).scalar_one_or_none()
    if revision_id is None:
        raise not_found(
            ErrorCode.GENERATION_NOT_FOUND,
            f"Generation {generation_id} not found.",
        )
    projection = await _revision_continuity(session, revision_id)
    projection["generation_id"] = generation_id
    return projection
