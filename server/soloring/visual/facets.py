"""VisualFacet + VisualAnchor services (frozen plan §§11, 14–18, 25, 37–39).

Fenced BEGIN IMMEDIATE units with in-unit validation (the M6A lesson).
The M7 value authority is consumed exactly: anchors and value policies
persist the SERVER-DERIVED ``(feature_value_json, feature_value_hash)``
from M7 ``canonicalize_value`` — a client-supplied pair is never trusted
(§11).
"""

from __future__ import annotations

import contextlib
import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from soloring.continuity.entities import _translate_op_error
from soloring.continuity.values import canonicalize_value
from soloring.domain.ids import is_uuid, new_uuid
from soloring.domain.normalize import normalize_optional_creative
from soloring.errors import (
    ErrorCode,
    SoloRingError,
    internal_invariant,
    validation_error,
)

_FACET_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")

_FACET_COLUMNS = (
    "id, project_id, target_kind, entity_id, feature_id, facet_key, "
    "label, description, requirement, created_at, updated_at, deleted_at"
)


def _facet_not_found(facet_id: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.VISUAL_FACET_NOT_FOUND,
        f"VisualFacet {facet_id} not found (or not active).",
        status_code=404,
    )


def _target_invalid(message: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.VISUAL_FACET_TARGET_INVALID, message, status_code=409
    )


def _anchor_target_invalid(message: str) -> SoloRingError:
    return SoloRingError(
        ErrorCode.VISUAL_ANCHOR_TARGET_INVALID, message, status_code=409
    )


async def _facet_project(conn: AsyncConnection, facet_id: str) -> str:
    row = (
        await conn.execute(
            text(
                "SELECT project_id FROM visual_facets "
                "WHERE id = :fid AND deleted_at IS NULL"
            ),
            {"fid": facet_id},
        )
    ).first()
    if row is None:
        raise _facet_not_found(facet_id)
    return str(row.project_id)


async def _derive_feature_value(
    conn: AsyncConnection,
    project_id: str,
    feature_id: str,
    value: object,
) -> tuple[str, str]:
    """Server-side M7 canonicalization for one feature value (§11).

    Validates the feature is active, belongs to the same Project, and that
    ``value`` is legal under its frozen type domain; returns the exact
    server-derived ``(value_json, value_hash)``.
    """
    feature = (
        await conn.execute(
            text(
                "SELECT f.value_type, f.enum_values_json, "
                "ce.project_id AS owner_project, ce.deleted_at AS "
                "entity_deleted, f.deleted_at AS feature_deleted "
                "FROM continuity_features f "
                "JOIN creative_entities ce ON ce.id = f.entity_id "
                "WHERE f.id = :fid"
            ),
            {"fid": feature_id},
        )
    ).first()
    if feature is None or feature.feature_deleted is not None:
        raise _target_invalid(
            f"ContinuityFeature {feature_id} does not exist or is not "
            "active."
        )
    if feature.entity_deleted is not None:
        raise _target_invalid(
            f"ContinuityFeature {feature_id} belongs to a deleted Entity."
        )
    if feature.owner_project != project_id:
        raise _target_invalid(
            f"ContinuityFeature {feature_id} belongs to another Project."
        )
    enum_values = None
    if feature.value_type == "enum":
        import json as _json

        enum_values = _json.loads(feature.enum_values_json)
    # M7 canonicalize_value is the sole value authority (§11). Callers map
    # its INVALID_CONTINUITY_VALUE onto the frozen M8 surface codes (§68).
    return canonicalize_value(
        feature.value_type, value, enum_values=enum_values
    )


async def create_facet(session: AsyncSession, project_id: str, payload) -> str:
    if not is_uuid(project_id):
        raise SoloRingError(
            ErrorCode.PROJECT_NOT_FOUND,
            f"Project {project_id} not found.",
            status_code=404,
        )
    kind = payload.target_kind
    if kind not in ("entity", "feature"):
        raise validation_error("target_kind must be entity or feature.")
    if payload.requirement not in ("required", "optional"):
        raise validation_error("requirement must be required or optional.")
    if not _FACET_KEY_RE.match(payload.facet_key or ""):
        raise validation_error(
            f"facet_key {payload.facet_key!r} must match "
            "^[a-z0-9][a-z0-9._-]{0,127}$."
        )
    entity_id = payload.entity_id
    feature_id = payload.feature_id
    if kind == "entity":
        if entity_id is None or feature_id is not None:
            raise validation_error(
                "entity facet requires entity_id and no feature_id."
            )
        if not is_uuid(entity_id):
            raise SoloRingError(
                ErrorCode.ENTITY_NOT_FOUND,
                f"Entity {entity_id} not found.",
                status_code=404,
            )
    else:
        if feature_id is None or entity_id is not None:
            raise validation_error(
                "feature facet requires feature_id and no entity_id."
            )
        if not is_uuid(feature_id):
            raise _target_invalid(
                f"ContinuityFeature {feature_id} is not a valid target."
            )

    facet_id = new_uuid()
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            project = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM projects WHERE id = :pid "
                        "AND deleted_at IS NULL"
                    ),
                    {"pid": project_id},
                )
            ).first()
            if project is None:
                raise SoloRingError(
                    ErrorCode.PROJECT_NOT_FOUND,
                    f"Project {project_id} not found.",
                    status_code=404,
                )
            if kind == "entity":
                target = (
                    await conn.execute(
                        text(
                            "SELECT project_id FROM creative_entities "
                            "WHERE id = :eid AND deleted_at IS NULL"
                        ),
                        {"eid": entity_id},
                    )
                ).first()
                if target is None:
                    raise SoloRingError(
                        ErrorCode.ENTITY_NOT_FOUND,
                        f"Entity {entity_id} not found.",
                        status_code=404,
                    )
                if target.project_id != project_id:
                    raise _target_invalid(
                        f"Entity {entity_id} belongs to another Project."
                    )
            else:
                target = (
                    await conn.execute(
                        text(
                            "SELECT ce.project_id AS p, "
                            "ce.deleted_at AS e_del, f.deleted_at AS f_del "
                            "FROM continuity_features f "
                            "JOIN creative_entities ce ON ce.id = f.entity_id "
                            "WHERE f.id = :fid"
                        ),
                        {"fid": feature_id},
                    )
                ).first()
                if target is None or target.f_del is not None:
                    raise _target_invalid(
                        f"ContinuityFeature {feature_id} does not exist or "
                        "is not active."
                    )
                if target.e_del is not None:
                    raise _target_invalid(
                        f"ContinuityFeature {feature_id} belongs to a "
                        "deleted Entity."
                    )
                if target.p != project_id:
                    raise _target_invalid(
                        f"ContinuityFeature {feature_id} belongs to another "
                        "Project."
                    )
            existing = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM visual_facets WHERE "
                        f"{'entity_id' if kind == 'entity' else 'feature_id'}"
                        " = :tid AND facet_key = :k AND deleted_at IS NULL"
                    ),
                    {
                        "tid": entity_id if kind == "entity" else feature_id,
                        "k": payload.facet_key,
                    },
                )
            ).first()
            if existing is not None:
                raise SoloRingError(
                    ErrorCode.VISUAL_FACET_TARGET_INVALID,
                    f"An active VisualFacet with key {payload.facet_key!r} "
                    "already exists for this target.",
                    status_code=409,
                )
            await conn.execute(
                text(
                    "INSERT INTO visual_facets "
                    "(id, project_id, target_kind, entity_id, feature_id, "
                    " facet_key, label, description, requirement, "
                    " created_at, updated_at) "
                    "VALUES (:id, :pid, :kind, :eid, :fid, :key, :label, "
                    ":desc, :req, strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
                ),
                {
                    "id": facet_id,
                    "pid": project_id,
                    "kind": kind,
                    "eid": entity_id,
                    "fid": feature_id,
                    "key": payload.facet_key,
                    "label": payload.label,
                    "desc": normalize_optional_creative(payload.description),
                    "req": payload.requirement,
                },
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(exc, "visual facet creation") from exc
    return facet_id


async def list_facets(session: AsyncSession, project_id: str) -> list[dict]:
    if not is_uuid(project_id):
        raise SoloRingError(
            ErrorCode.PROJECT_NOT_FOUND,
            f"Project {project_id} not found.",
            status_code=404,
        )
    async with session.bind.connect() as conn:
        active = (
            await conn.execute(
                text(
                    "SELECT 1 FROM projects WHERE id = :pid "
                    "AND deleted_at IS NULL"
                ),
                {"pid": project_id},
            )
        ).first()
        if active is None:
            raise SoloRingError(
                ErrorCode.PROJECT_NOT_FOUND,
                f"Project {project_id} not found.",
                status_code=404,
            )
        rows = (
            await conn.execute(
                text(
                    f"SELECT {_FACET_COLUMNS} FROM visual_facets "
                    "WHERE project_id = :pid AND deleted_at IS NULL "
                    "ORDER BY facet_key"
                ),
                {"pid": project_id},
            )
        ).mappings().all()
        return [dict(r) for r in rows]


async def get_facet(session: AsyncSession, facet_id: str) -> dict:
    if not is_uuid(facet_id):
        raise _facet_not_found(facet_id)
    async with session.bind.connect() as conn:
        row = (
            await conn.execute(
                text(
                    f"SELECT {_FACET_COLUMNS} FROM visual_facets "
                    "WHERE id = :fid AND deleted_at IS NULL"
                ),
                {"fid": facet_id},
            )
        ).mappings().one_or_none()
    if row is None:
        raise _facet_not_found(facet_id)
    return dict(row)


async def patch_facet(session: AsyncSession, facet_id: str, patch) -> None:
    """Only label/description/requirement (§37); target identity is
    immutable and absent from the patch schema."""
    if not is_uuid(facet_id):
        raise _facet_not_found(facet_id)
    provided = patch.model_fields_set
    if not provided:
        await get_facet(session, facet_id)
        return
    if "requirement" in provided and patch.requirement not in (
        "required", "optional"
    ):
        raise validation_error("requirement must be required or optional.")

    updates: dict[str, object] = {}
    if "label" in provided:
        updates["label"] = patch.label
    if "description" in provided:
        updates["description"] = normalize_optional_creative(
            patch.description
        )
    if "requirement" in provided:
        updates["requirement"] = patch.requirement
    set_sql = ", ".join(f"{col} = :{col}" for col in updates)
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            rowcount = (
                await conn.execute(
                    text(
                        "UPDATE visual_facets SET "
                        f"{set_sql}, updated_at = "
                        "strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                        "WHERE id = :fid AND deleted_at IS NULL"
                    ),
                    {**updates, "fid": facet_id},
                )
            ).rowcount
            if rowcount != 1:
                raise _facet_not_found(facet_id)
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(exc, "visual facet patch") from exc


async def delete_facet(session: AsyncSession, facet_id: str) -> None:
    """Soft-delete with the two §38 guards: required facets and facets
    with active anchors are never deleted silently."""
    if not is_uuid(facet_id):
        raise _facet_not_found(facet_id)
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            row = (
                await conn.execute(
                    text(
                        "SELECT requirement, deleted_at FROM visual_facets "
                        "WHERE id = :fid"
                    ),
                    {"fid": facet_id},
                )
            ).first()
            if row is None:
                raise _facet_not_found(facet_id)
            if row.deleted_at is not None:
                await conn.exec_driver_sql("COMMIT")  # idempotent
                return
            if row.requirement == "required":
                raise SoloRingError(
                    ErrorCode.VISUAL_FACET_DELETE_BLOCKED,
                    "VisualFacet is required; change requirement to "
                    "optional before deletion.",
                    status_code=409,
                    details={"reason": "required"},
                )
            active_anchor = (
                await conn.execute(
                    text(
                        "SELECT 1 FROM visual_anchors "
                        "WHERE visual_facet_id = :fid "
                        "AND deleted_at IS NULL LIMIT 1"
                    ),
                    {"fid": facet_id},
                )
            ).first()
            if active_anchor is not None:
                raise SoloRingError(
                    ErrorCode.VISUAL_FACET_DELETE_BLOCKED,
                    "VisualFacet has active VisualAnchors; unapprove/delete "
                    "them first.",
                    status_code=409,
                    details={"reason": "active_anchors"},
                )
            await conn.execute(
                text(
                    "UPDATE visual_facets SET deleted_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'), updated_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :fid"
                ),
                {"fid": facet_id},
            )
            await conn.exec_driver_sql("COMMIT")
        except SoloRingError:
            raise
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise _translate_op_error(exc, "visual facet deletion") from exc


async def put_value_policies(
    session: AsyncSession, facet_id: str, payload
) -> list[dict]:
    """Atomic full-set replacement of feature-value policies (§16)."""
    if not is_uuid(facet_id):
        raise _facet_not_found(facet_id)

    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            facet = (
                await conn.execute(
                    text(
                        "SELECT id, project_id, target_kind, feature_id "
                        "FROM visual_facets WHERE id = :fid "
                        "AND deleted_at IS NULL"
                    ),
                    {"fid": facet_id},
                )
            ).first()
            if facet is None:
                raise _facet_not_found(facet_id)
            if facet.target_kind != "feature" or facet.feature_id is None:
                raise SoloRingError(
                    ErrorCode.VISUAL_FACET_VALUE_POLICY_INVALID,
                    "Value policies are only permitted for feature-targeted "
                    "VisualFacets.",
                    status_code=422,
                )
            derived: list[tuple[str, str, str]] = []
            seen_hashes: set[str] = set()
            for item in payload.policies:
                if item.policy not in ("required", "optional",
                                       "not_applicable"):
                    raise SoloRingError(
                        ErrorCode.VISUAL_FACET_VALUE_POLICY_INVALID,
                        f"policy must be required, optional, or "
                        f"not_applicable (got {item.policy!r}).",
                        status_code=422,
                    )
                try:
                    v_json, v_hash = await _derive_feature_value(
                        conn, facet.project_id, facet.feature_id, item.value
                    )
                except SoloRingError as exc:
                    if exc.code == ErrorCode.INVALID_CONTINUITY_VALUE:
                        raise SoloRingError(
                            ErrorCode.VISUAL_FACET_VALUE_POLICY_INVALID,
                            f"Value is not legal under the owning M7 "
                            f"Feature: {exc.message}",
                            status_code=422,
                        ) from exc
                    raise
                if v_hash in seen_hashes:
                    raise SoloRingError(
                        ErrorCode.VISUAL_FACET_VALUE_POLICY_INVALID,
                        "Duplicate value in proposed policy set.",
                        status_code=422,
                    )
                seen_hashes.add(v_hash)
                derived.append((v_hash, v_json, item.policy))
            await conn.execute(
                text(
                    "DELETE FROM visual_facet_value_policies "
                    "WHERE visual_facet_id = :fid"
                ),
                {"fid": facet_id},
            )
            for v_hash, v_json, policy in derived:
                await conn.execute(
                    text(
                        "INSERT INTO visual_facet_value_policies "
                        "(visual_facet_id, feature_value_hash, "
                        " feature_value_json, policy, created_at) VALUES "
                        "(:fid, :vh, :vj, :p, "
                        "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
                    ),
                    {"fid": facet_id, "vh": v_hash, "vj": v_json, "p": policy},
                )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(exc, "value policy replacement") from exc

    return await list_value_policies(session, facet_id)


async def list_value_policies(
    session: AsyncSession, facet_id: str
) -> list[dict]:
    async with session.bind.connect() as conn:
        await _facet_project(conn, facet_id)
        rows = (
            await conn.execute(
                text(
                    "SELECT feature_value_json, feature_value_hash, policy "
                    "FROM visual_facet_value_policies "
                    "WHERE visual_facet_id = :fid "
                    "ORDER BY feature_value_json"
                ),
                {"fid": facet_id},
            )
        ).mappings().all()
        return [dict(r) for r in rows]


async def create_anchor(
    session: AsyncSession, facet_id: str, payload
) -> str:
    """Create one state-specific VisualAnchor (§17). Binding is expressed
    semantically; the server derives and validates everything."""
    if not is_uuid(facet_id):
        raise _facet_not_found(facet_id)

    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            facet = (
                await conn.execute(
                    text(
                        "SELECT id, project_id, target_kind, entity_id, "
                        "feature_id FROM visual_facets WHERE id = :fid "
                        "AND deleted_at IS NULL"
                    ),
                    {"fid": facet_id},
                )
            ).first()
            if facet is None:
                raise _facet_not_found(facet_id)

            entity_revision_id = None
            feature_value_hash = None
            feature_value_json = None
            visual_context = None

            if facet.target_kind == "entity":
                er = payload.entity_revision_id
                if er is None or payload.value is not None or (
                    payload.visual_context_entity_revision_id is not None
                ):
                    raise _anchor_target_invalid(
                        "Entity-facet anchors require entity_revision_id "
                        "only (no value, no visual context)."
                    )
                if not is_uuid(er):
                    raise _anchor_target_invalid(
                        f"EntityRevision {er!r} is not a valid id."
                    )
                rev = (
                    await conn.execute(
                        text(
                            "SELECT er.id, ce.project_id AS p, "
                            "ce.id AS entity_id "
                            "FROM entity_revisions er "
                            "JOIN creative_entities ce "
                            "ON ce.id = er.entity_id "
                            "WHERE er.id = :rid"
                        ),
                        {"rid": er},
                    )
                ).first()
                if rev is None:
                    raise _anchor_target_invalid(
                        f"EntityRevision {er} does not exist."
                    )
                if rev.p != facet.project_id:
                    raise _anchor_target_invalid(
                        f"EntityRevision {er} belongs to another Project."
                    )
                # §13/§68: the revision must be OF THE FACET'S ENTITY —
                # a same-Project revision of a different Entity is a
                # wrong-EntityRevision target, not a legal binding.
                if rev.entity_id != facet.entity_id:
                    raise _anchor_target_invalid(
                        f"EntityRevision {er} does not belong to "
                        f"Entity {facet.entity_id} — the facet's own "
                        "target."
                    )
                entity_revision_id = er
            else:
                if payload.entity_revision_id is not None or (
                    payload.value is None
                ):
                    raise _anchor_target_invalid(
                        "Feature-facet anchors require the feature value "
                        "(and no entity_revision_id)."
                    )
                ctx = payload.visual_context_entity_revision_id
                if ctx is None:
                    raise _anchor_target_invalid(
                        "Feature-facet anchors require "
                        "visual_context_entity_revision_id (every feature "
                        "is entity-scoped under 0008)."
                    )
                if not is_uuid(ctx):
                    raise _anchor_target_invalid(
                        f"Visual-context EntityRevision {ctx!r} is not a "
                        "valid id."
                    )
                ctx_rev = (
                    await conn.execute(
                        text(
                            "SELECT ce.project_id AS p, ce.id AS entity_id "
                            "FROM entity_revisions er "
                            "JOIN creative_entities ce "
                            "ON ce.id = er.entity_id "
                            "WHERE er.id = :rid"
                        ),
                        {"rid": ctx},
                    )
                ).first()
                if ctx_rev is None:
                    raise _anchor_target_invalid(
                        f"Visual-context EntityRevision {ctx} does not "
                        "exist."
                    )
                if ctx_rev.p != facet.project_id:
                    raise _anchor_target_invalid(
                        f"Visual-context EntityRevision {ctx} belongs to "
                        "another Project."
                    )
                # §13/§68: the visual context must be a revision of the
                # Entity OWNING the ContinuityFeature — a same-Project
                # revision of any other Entity is a wrong visual-context
                # target.
                feature_owner = (
                    await conn.execute(
                        text(
                            "SELECT entity_id FROM continuity_features "
                            "WHERE id = :fid AND deleted_at IS NULL"
                        ),
                        {"fid": facet.feature_id},
                    )
                ).scalar_one_or_none()
                if feature_owner is None:
                    raise internal_invariant(
                        f"VisualFacet {facet_id} targets a missing "
                        "ContinuityFeature."
                    )
                if ctx_rev.entity_id != feature_owner:
                    raise _anchor_target_invalid(
                        f"Visual-context EntityRevision {ctx} does not "
                        f"belong to Entity {feature_owner}, the owner of "
                        "the facet's ContinuityFeature."
                    )
                try:
                    feature_value_json, feature_value_hash = (
                        await _derive_feature_value(
                            conn, facet.project_id, facet.feature_id,
                            payload.value,
                        )
                    )
                except SoloRingError as exc:
                    if exc.code == ErrorCode.INVALID_CONTINUITY_VALUE:
                        raise _anchor_target_invalid(
                            f"Value is not legal under the owning M7 "
                            f"Feature: {exc.message}"
                        ) from exc
                    raise
                visual_context = ctx

            # Active exact-state uniqueness (§18) — surface a stable
            # conflict instead of the raw partial-index error.
            dup_sql = (
                "SELECT 1 FROM visual_anchors WHERE visual_facet_id = :fid "
                "AND deleted_at IS NULL AND "
            )
            if facet.target_kind == "entity":
                dup_sql += "entity_revision_id = :er"
                dup_params = {"fid": facet_id, "er": entity_revision_id}
            else:
                dup_sql += (
                    "feature_value_hash = :vh AND "
                    "visual_context_entity_revision_id = :ctx"
                )
                dup_params = {
                    "fid": facet_id, "vh": feature_value_hash, "ctx": visual_context,
                }
            if (
                await conn.execute(text(dup_sql), dup_params)
            ).first() is not None:
                raise _anchor_target_invalid(
                    "An active VisualAnchor already exists for this exact "
                    "state binding."
                )

            anchor_id = new_uuid()
            await conn.execute(
                text(
                    "INSERT INTO visual_anchors "
                    "(id, visual_facet_id, entity_revision_id, "
                    " feature_value_hash, feature_value_json, "
                    " visual_context_entity_revision_id, created_at, "
                    " updated_at) VALUES (:id, :fid, :er, :vh, :vj, :ctx, "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'), "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'))"
                ),
                {
                    "id": anchor_id, "fid": facet_id, "er": entity_revision_id,
                    "vh": feature_value_hash, "vj": feature_value_json,
                    "ctx": visual_context,
                },
            )
            await conn.exec_driver_sql("COMMIT")
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            if isinstance(exc, SoloRingError):
                raise
            raise _translate_op_error(exc, "visual anchor creation") from exc
    return anchor_id


async def list_anchors(session: AsyncSession, facet_id: str) -> list[dict]:
    if not is_uuid(facet_id):
        raise _facet_not_found(facet_id)
    async with session.bind.connect() as conn:
        await _facet_project(conn, facet_id)
        rows = (
            await conn.execute(
                text(
                    "SELECT id, visual_facet_id, entity_revision_id, "
                    "feature_value_hash, feature_value_json, "
                    "visual_context_entity_revision_id, "
                    "approved_revision_id, created_at, updated_at "
                    "FROM visual_anchors WHERE visual_facet_id = :fid "
                    "AND deleted_at IS NULL ORDER BY created_at, id"
                ),
                {"fid": facet_id},
            )
        ).mappings().all()
        return [dict(r) for r in rows]


async def get_anchor(session: AsyncSession, anchor_id: str) -> dict:
    from .anchors import get_anchor_detail  # noqa: F401  (M8B)

    if not is_uuid(anchor_id):
        raise SoloRingError(
            ErrorCode.VISUAL_ANCHOR_NOT_FOUND,
            f"VisualAnchor {anchor_id} not found.",
            status_code=404,
        )
    async with session.bind.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT id, visual_facet_id, entity_revision_id, "
                    "feature_value_hash, feature_value_json, "
                    "visual_context_entity_revision_id, "
                    "approved_revision_id, created_at, updated_at "
                    "FROM visual_anchors WHERE id = :aid "
                    "AND deleted_at IS NULL"
                ),
                {"aid": anchor_id},
            )
        ).mappings().one_or_none()
    if row is None:
        raise SoloRingError(
            ErrorCode.VISUAL_ANCHOR_NOT_FOUND,
            f"VisualAnchor {anchor_id} not found.",
            status_code=404,
        )
    return dict(row)


async def delete_anchor(session: AsyncSession, anchor_id: str) -> None:
    """Soft-delete with the §39 guard: approved anchors must be
    unapproved first."""
    if not is_uuid(anchor_id):
        raise SoloRingError(
            ErrorCode.VISUAL_ANCHOR_NOT_FOUND,
            f"VisualAnchor {anchor_id} not found.",
            status_code=404,
        )
    async with session.bind.connect() as conn:
        try:
            await conn.exec_driver_sql("BEGIN IMMEDIATE")
            row = (
                await conn.execute(
                    text(
                        "SELECT deleted_at, approved_revision_id "
                        "FROM visual_anchors WHERE id = :aid"
                    ),
                    {"aid": anchor_id},
                )
            ).first()
            if row is None:
                raise SoloRingError(
                    ErrorCode.VISUAL_ANCHOR_NOT_FOUND,
                    f"VisualAnchor {anchor_id} not found.",
                    status_code=404,
                )
            if row.deleted_at is not None:
                await conn.exec_driver_sql("COMMIT")  # idempotent
                return
            if row.approved_revision_id is not None:
                raise SoloRingError(
                    ErrorCode.VISUAL_ANCHOR_DELETE_BLOCKED,
                    "VisualAnchor has an approved revision; unapprove "
                    "first.",
                    status_code=409,
                )
            await conn.execute(
                text(
                    "UPDATE visual_anchors SET deleted_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now'), updated_at = "
                    "strftime('%Y-%m-%dT%H:%M:%fZ','now') WHERE id = :aid"
                ),
                {"aid": anchor_id},
            )
            await conn.exec_driver_sql("COMMIT")
        except SoloRingError:
            raise
        except Exception as exc:
            with contextlib.suppress(Exception):
                await conn.exec_driver_sql("ROLLBACK")
            raise _translate_op_error(exc, "visual anchor deletion") from exc
