"""Continuity endpoints (M6C §47, §63): working dependencies + historical
continuity provenance.

The historical endpoints traverse ONLY persisted history —
``shot_revisions`` and its immutable dependency rows — never current Story
World state (plan §63/M6-F8).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.deps import get_session
from soloring.api.schemas.continuity_features import (
    FeatureCreate,
    FeaturePatch,
    FeatureRead,
)
from soloring.api.schemas.continuity_transitions import (
    TransitionCreate,
    TransitionPatch,
    TransitionRead,
)
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
    feature_states: list[dict[str, Any]] = []
    transition_audit: list[dict[str, Any]] = []
    continuity_schema_version = None
    if rev["continuity_spec_json"] is not None:
        import json

        spec = json.loads(rev["continuity_spec_json"])
        continuity_schema_version = spec.get("schema_version")
        dependencies = list(spec.get("dependencies", []))
        # Rebuild the FULL canonical spec from the IMMUTABLE ROWS and
        # compare canonical bytes AND hash with what is persisted — the
        # consistency claim is literal: any provenance disagreement fails
        # loudly (M6C hardening; M7C §12).
        from soloring.continuity.snapshots import (
            ResolvedDependency,
            build_continuity_spec,
            build_continuity_spec_v2,
            historical_value_hash,
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
        rebuilt_deps = [
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
        ]

        # Feature states: the shot_revision_feature_states ROWS are the
        # authority (M7C §12). Their semantic fields are captured
        # duplicates — NEVER re-derived from today's ContinuityFeature,
        # transitions, or anchors. Per row, re-parse value_json and
        # re-canonicalize CAPTURED-ROW-ONLY (no live enum schema — the
        # freeze note), requiring the recomputed hash to match.
        frows = (
            await session.execute(
                text(
                    "SELECT entity_id, feature_id, feature_key, "
                    "feature_kind, value_type, unit, value_json, "
                    "value_hash, source_transition_id, "
                    "source_anchor_type, source_anchor_id, source_boundary "
                    "FROM shot_revision_feature_states "
                    "WHERE shot_revision_id = :rid"
                ),
                {"rid": revision_id},
            )
        ).mappings().all()

        class _CapturedFeatureState:
            """Row-shape adapter consumed by build_continuity_spec_v2."""

            def __init__(self, row):
                self.entity_id = row["entity_id"]
                self.feature_id = row["feature_id"]
                self.feature_key = row["feature_key"]
                self.feature_kind = row["feature_kind"]
                self.value_type = row["value_type"]
                self.unit = row["unit"]
                self.value_json = row["value_json"]
                self.value_hash = row["value_hash"]
                self.source_anchor_type = row["source_anchor_type"]
                self.source_anchor_id = row["source_anchor_id"]
                self.source_boundary = row["source_boundary"]

        for row in frows:
            if historical_value_hash(row["value_json"]) != row["value_hash"]:
                raise internal_invariant(
                    f"ShotRevision {revision_id} feature row "
                    f"{row['feature_id']} value bytes disagree with its "
                    "stored value_hash under captured-row-only "
                    "re-canonicalization."
                )
            transition_audit.append({
                "feature_id": row["feature_id"],
                "source_transition_id": row["source_transition_id"],
            })

        if continuity_schema_version == 2:
            rebuilt = build_continuity_spec_v2(
                rebuilt_deps, [_CapturedFeatureState(r) for r in frows]
            )
        else:
            rebuilt = build_continuity_spec(rebuilt_deps)
        if (
            canonical_json_str(rebuilt) != rev["continuity_spec_json"]
            or canonical_hash(rebuilt) != rev["continuity_spec_hash"]
        ):
            raise internal_invariant(
                f"ShotRevision {revision_id} immutable rows disagree with "
                "its canonical continuity spec."
            )
        feature_states = list(rebuilt.get("feature_states", []))

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
        "feature_states": feature_states,
        "source_transition_audit": transition_audit,
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


# --- ContinuityFeature surface (M7A §47) ------------------------------------------


@router.get(
    "/entities/{entity_id}/continuity-features",
    response_model=list[FeatureRead],
)
async def list_continuity_features(
    entity_id: str, session: AsyncSession = Depends(get_session)
) -> list[FeatureRead]:
    from soloring.continuity import features as feature_svc

    return [
        FeatureRead(**r)
        for r in await feature_svc.list_features(session, entity_id)
    ]


@router.post(
    "/entities/{entity_id}/continuity-features",
    response_model=FeatureRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_continuity_feature(
    entity_id: str,
    payload: FeatureCreate,
    session: AsyncSession = Depends(get_session),
) -> FeatureRead:
    from soloring.continuity import features as feature_svc

    fid = await feature_svc.create_feature(session, entity_id, payload)
    return FeatureRead(**await feature_svc.get_feature(session, fid))


@router.get("/continuity-features/{feature_id}", response_model=FeatureRead)
async def get_continuity_feature(
    feature_id: str, session: AsyncSession = Depends(get_session)
) -> FeatureRead:
    from soloring.continuity import features as feature_svc

    return FeatureRead(**await feature_svc.get_feature(session, feature_id))


@router.patch("/continuity-features/{feature_id}", response_model=FeatureRead)
async def patch_continuity_feature(
    feature_id: str,
    payload: FeaturePatch,
    session: AsyncSession = Depends(get_session),
) -> FeatureRead:
    from soloring.continuity import features as feature_svc

    await feature_svc.patch_feature(session, feature_id, payload)
    return FeatureRead(**await feature_svc.get_feature(session, feature_id))


@router.delete(
    "/continuity-features/{feature_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_continuity_feature(
    feature_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    from soloring.continuity import features as feature_svc

    await feature_svc.delete_feature(session, feature_id)


# --- FeatureTransition surface + continuity-state (M7B §2, §8) ----------------------


@router.get(
    "/continuity-features/{feature_id}/transitions",
    response_model=list[TransitionRead],
)
async def list_feature_transitions(
    feature_id: str, session: AsyncSession = Depends(get_session)
) -> list[TransitionRead]:
    from soloring.continuity import transitions as transition_svc

    return [
        TransitionRead(**r)
        for r in await transition_svc.list_transitions(session, feature_id)
    ]


@router.post(
    "/continuity-features/{feature_id}/transitions",
    response_model=TransitionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_feature_transition(
    feature_id: str,
    payload: TransitionCreate,
    session: AsyncSession = Depends(get_session),
) -> TransitionRead:
    from soloring.continuity import transitions as transition_svc

    tid = await transition_svc.create_transition(session, feature_id, payload)
    async with session.bind.connect() as conn:
        from sqlalchemy import text as _t

        row = (
            await conn.execute(
                _t(
                    "SELECT id, feature_id, anchor_type, anchor_id, boundary, "
                    "operation, value_json, value_hash, created_at, updated_at "
                    "FROM continuity_feature_transitions WHERE id = :tid"
                ),
                {"tid": tid},
            )
        ).mappings().one()
    return TransitionRead(**dict(row))


@router.patch(
    "/continuity-feature-transitions/{transition_id}",
    response_model=TransitionRead,
)
async def patch_feature_transition(
    transition_id: str,
    payload: TransitionPatch,
    session: AsyncSession = Depends(get_session),
) -> TransitionRead:
    from soloring.continuity import transitions as transition_svc

    await transition_svc.patch_transition(session, transition_id, payload)
    async with session.bind.connect() as conn:
        from sqlalchemy import text as _t

        row = (
            await conn.execute(
                _t(
                    "SELECT id, feature_id, anchor_type, anchor_id, boundary, "
                    "operation, value_json, value_hash, created_at, updated_at "
                    "FROM continuity_feature_transitions WHERE id = :tid"
                ),
                {"tid": transition_id},
            )
        ).mappings().one()
    return TransitionRead(**dict(row))


@router.delete(
    "/continuity-feature-transitions/{transition_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_feature_transition(
    transition_id: str, session: AsyncSession = Depends(get_session)
) -> None:
    from soloring.continuity import transitions as transition_svc

    await transition_svc.delete_transition(session, transition_id)


@router.get("/shots/{shot_id}/continuity-state")
async def get_shot_continuity_state(
    shot_id: str, session: AsyncSession = Depends(get_session)
) -> dict:
    """Current-state endpoint only (M7B §8). Historical endpoints never
    invoke this resolver."""
    from soloring.continuity.state import (
        narrative_context_required,
        readiness_projection,
        resolve_effective_feature_state,
    )
    from soloring.domain.ids import is_uuid
    from soloring.errors import ErrorCode, not_found

    if not is_uuid(shot_id):
        raise not_found(ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id} not found.")
    import contextlib as _cl

    async with session.bind.connect() as conn:
        # One explicit consistent read unit (the established pattern):
        # the complete M7 current state resolves from ONE WAL snapshot —
        # all-before or all-after a concurrent mutation, never a hybrid.
        await conn.exec_driver_sql("BEGIN")
        try:
            outcome = await resolve_effective_feature_state(conn, shot_id)
            await conn.commit()
        except Exception:
            with _cl.suppress(Exception):
                await conn.rollback()
            raise
    if not outcome.assigned and outcome.relevant_temporal_data:
        raise narrative_context_required(shot_id)
    readiness = readiness_projection(outcome)
    return {
        "shot_id": shot_id,
        "continuity_state_ready": readiness["continuity_state_ready"],
        "readiness_issues": readiness["readiness_issues"],
        "feature_states": [
            {
                "entity_id": s.entity_id,
                "feature_id": s.feature_id,
                "feature_key": s.feature_key,
                "feature_kind": s.feature_kind,
                "value_type": s.value_type,
                "unit": s.unit,
                "value": __import__("json").loads(s.value_json),
                "source_transition_id": s.source_transition_id,
                "source_anchor": {
                    "anchor_type": s.source_anchor_type,
                    "anchor_id": s.source_anchor_id,
                    "boundary": s.source_boundary,
                },
            }
            for s in outcome.states
        ],
    }
