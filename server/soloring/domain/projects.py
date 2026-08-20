"""ProjectService (plan §8).

CRUD + soft deletion. Soft-deleting a Project cascades to its active child
Shots only (already-deleted Shots keep their original timestamps). Historical
provenance (references, revisions, generations, assets, blobs) is never
modified. DELETE is idempotent.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.api.schemas.projects import ProjectCreate, ProjectPatch
from soloring.db.models import Project, Shot
from soloring.domain.ids import is_uuid, new_uuid
from soloring.domain.now import db_now
from soloring.domain.normalize import normalize_project_description, normalize_project_name
from soloring.errors import ErrorCode, not_found, validation_error


async def _get_active(session: AsyncSession, project_id: str) -> Project:
    if not is_uuid(project_id):
        raise not_found(ErrorCode.PROJECT_NOT_FOUND, f"Project {project_id} not found.")
    project = await session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise not_found(ErrorCode.PROJECT_NOT_FOUND, f"Project {project_id} not found.")
    return project


async def create_project(session: AsyncSession, data: ProjectCreate) -> Project:
    name = normalize_project_name(data.name)
    if not name:
        raise validation_error("Project name must not be empty.")
    project = Project(
        id=new_uuid(),
        name=name,
        description=normalize_project_description(data.description),
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return project


async def get_project(session: AsyncSession, project_id: str) -> Project:
    return await _get_active(session, project_id)


async def list_projects(session: AsyncSession) -> list[Project]:
    res = await session.execute(
        select(Project).where(Project.deleted_at.is_(None)).order_by(Project.created_at)
    )
    return list(res.scalars().all())


async def patch_project(session: AsyncSession, project_id: str, data: ProjectPatch) -> Project:
    project = await _get_active(session, project_id)
    provided = data.model_fields_set
    if "name" in provided:
        name = normalize_project_name(data.name)
        if not name:
            raise validation_error("Project name must not be empty.")
        project.name = name
    if "description" in provided:
        project.description = normalize_project_description(data.description)
    project.updated_at = await db_now(session)
    await session.commit()
    await session.refresh(project)
    return project


async def delete_project(session: AsyncSession, project_id: str) -> None:
    # DELETE idempotency applies to the persisted tombstone, not to identifiers
    # that never existed (plan §8.3, §44):
    #   malformed / well-formed-but-missing  -> entity-specific 404
    #   already soft-deleted                  -> no-op (204)
    if not is_uuid(project_id):
        raise not_found(ErrorCode.PROJECT_NOT_FOUND, f"Project {project_id} not found.")
    project = await session.get(Project, project_id)
    if project is None:
        raise not_found(ErrorCode.PROJECT_NOT_FOUND, f"Project {project_id} not found.")
    if project.deleted_at is not None:
        return  # already soft-deleted -> idempotent 204
    now = await db_now(session)
    project.deleted_at = now
    project.updated_at = now
    # Cascade to currently-active child Shots only (plan §8.2).
    shots = (
        await session.execute(
            select(Shot).where(
                Shot.project_id == project_id, Shot.deleted_at.is_(None)
            )
        )
    ).scalars().all()
    for shot in shots:
        shot.deleted_at = now
        shot.updated_at = now
    # M6 (plan §27): additionally soft-delete ACTIVE story-world rows —
    # CreativeEntities (plus Sequences/Scenes once M6B creates them). This
    # deliberately bypasses the ordinary ENTITY_IN_USE rejection: the Shots
    # holding the working dependencies are simultaneously leaving active
    # working state. Historical revisions and dependency snapshots remain.
    from soloring.continuity.models import CreativeEntity
    from soloring.narrative.models import Scene, Sequence

    entities = (
        await session.execute(
            select(CreativeEntity).where(
                CreativeEntity.project_id == project_id,
                CreativeEntity.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for entity in entities:
        entity.deleted_at = now
        entity.updated_at = now
    # M7A re-gate blocker 3: active Features leave working state WITH their
    # Entities (this cascade legitimately bypasses ENTITY_IN_USE — the
    # dependent Entities are simultaneously leaving active state).
    from sqlalchemy import text as _text

    await session.execute(
        _text(
            "UPDATE continuity_features SET deleted_at = :now, "
            "updated_at = :now WHERE deleted_at IS NULL AND entity_id IN "
            "(SELECT id FROM creative_entities WHERE project_id = :pid)"
        ),
        {"now": now, "pid": project_id},
    )
    # M7B §11: the Project cascade removes the entire working state, so
    # active FeatureTransitions of this Project's Features are tombstoned
    # with it (never physically deleted), leaving no active transitions
    # under tombstoned Features/anchors.
    await session.execute(
        _text(
            "UPDATE continuity_feature_transitions SET deleted_at = :now, "
            "updated_at = :now WHERE deleted_at IS NULL AND feature_id IN ("
            "SELECT id FROM continuity_features WHERE entity_id IN ("
            "SELECT id FROM creative_entities WHERE project_id = :pid))"
        ),
        {"now": now, "pid": project_id},
    )
    # M7D §13.5 (plan correction B): the cascade removes the ENTIRE
    # relation working state under the same fence and the same timestamp —
    # active RelationTransitions, then active Relations, then active
    # Predicates. Leaving Relations/Predicates active while their
    # Project's Entities are tombstoned would falsify the guard-chain
    # invariant (active Relation ⇒ active subject ⇒ active object ⇒
    # active Predicate) immediately after a legal Project deletion. The
    # ordinary in-use guards are bypassed here for the same reason as
    # above: the complete Project working state is leaving activity
    # together. Historical shot_revision_relation_states stay untouched.
    await session.execute(
        _text(
            "UPDATE continuity_relation_transitions SET deleted_at = :now, "
            "updated_at = :now WHERE deleted_at IS NULL AND relation_id IN ("
            "SELECT id FROM continuity_relations WHERE project_id = :pid)"
        ),
        {"now": now, "pid": project_id},
    )
    await session.execute(
        _text(
            "UPDATE continuity_relations SET deleted_at = :now "
            "WHERE deleted_at IS NULL AND project_id = :pid"
        ),
        {"now": now, "pid": project_id},
    )
    await session.execute(
        _text(
            "UPDATE continuity_predicates SET deleted_at = :now, "
            "updated_at = :now WHERE deleted_at IS NULL "
            "AND project_id = :pid"
        ),
        {"now": now, "pid": project_id},
    )
    sequences = (
        await session.execute(
            select(Sequence).where(
                Sequence.project_id == project_id,
                Sequence.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    for sequence in sequences:
        sequence.deleted_at = now
        sequence.updated_at = now
        scenes = (
            await session.execute(
                select(Scene).where(
                    Scene.sequence_id == sequence.id,
                    Scene.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        for scene in scenes:
            scene.deleted_at = now
            scene.updated_at = now
    # Scenes of already-deleted sequences keep their original timestamps
    # (matching the Shot policy); they were already inactive.
    await session.commit()
