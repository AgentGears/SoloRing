"""M15 compatibility evaluator v1 (frozen R4 §6/§13).

One BEGIN IMMEDIATE assessment unit over relational/canonical inputs
only — no GPU/executor work. The working-state placement-consumer
projection (§6.5.1) is composed by CALLING the predecessor M13 pure
seam primitives in derive_candidate's exact prerequisite order; the
classifier in production_world/binding.py is never modified or
extracted, and the published-twin oracle in
tests/test_m15_placement_seam_probe.py constrains the projection to
predecessor semantics.
"""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from soloring.compatibility.canonical import (
    EVALUATOR_ID,
    EVALUATOR_VERSION,
    dimension_results_value,
    fold_summary,
    fold_verdict,
    report_root,
    scope_root,
    use_contract_value,
)
from soloring.compatibility.translation import (
    UnsupportedTranslation,
    frame_bridge_supported,
    frame_bridge_translate,
)
from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.domain.ids import new_uuid
from soloring.errors import (
    ErrorCode,
    SoloRingError,
    internal_invariant,
    not_found,
    validation_error,
)
from soloring.production.canonical import (
    RetainedBlobClosure,
    build_production_revision_snapshot,
)
from soloring.production_world.binding import (
    _entry_is_identity,
    _verify_interpretation_unused,
)
from soloring.production_world.canonical import verify_stored_interpretation
from soloring.spatial.targets import (
    classify_entity_a4_targets,
    load_world_revision_with_world,
)

CONFLICT_CODE = ErrorCode.PRODUCTION_COMPATIBILITY_CONFLICT \
    if hasattr(ErrorCode, "PRODUCTION_COMPATIBILITY_CONFLICT") \
    else "PRODUCTION_COMPATIBILITY_CONFLICT"


def _conflict(reason: str, **details) -> SoloRingError:
    return SoloRingError(
        CONFLICT_CODE,
        f"current compatibility coordinate conflict: {reason}",
        status_code=409,
        details={"reason": reason, **details},
    )


async def _load_verified_revision(conn: AsyncConnection, rid: str) -> dict:
    """§6.1 — the stored immutable revision agrees with its normalized
    retained_blob/v1 closure; disagreement is corruption, never a
    compatibility verdict."""
    row = (await conn.execute(text(
        "SELECT pr.id, pr.revision_number, pr.snapshot_json, "
        "pr.snapshot_hash, pr.production_object_id, po.project_id, "
        "(SELECT c.blob_hash FROM production_revision_closures c "
        " WHERE c.production_revision_id = pr.id "
        " AND c.contract_key = 'retained_blob' "
        " AND c.contract_version = 1) AS blob_hash, "
        "(SELECT c.size_bytes FROM production_revision_closures c "
        " WHERE c.production_revision_id = pr.id "
        " AND c.contract_key = 'retained_blob' "
        " AND c.contract_version = 1) AS blob_size, "
        "(SELECT c.media_type FROM production_revision_closures c "
        " WHERE c.production_revision_id = pr.id "
        " AND c.contract_key = 'retained_blob' "
        " AND c.contract_version = 1) AS media_type "
        "FROM production_revisions pr "
        "JOIN production_objects po ON po.id = pr.production_object_id "
        "WHERE pr.id = :r"),
        {"r": rid})).one_or_none()
    if row is None:
        raise not_found(
            ErrorCode.PRODUCTION_REVISION_NOT_FOUND,
            f"production revision {rid!r} not found")
    if row.blob_hash is None:
        raise internal_invariant(
            f"production revision {rid!r} lacks a retained_blob/v1 "
            "closure — historical/storage corruption")
    closure = RetainedBlobClosure(
        blob_hash=row.blob_hash, size_bytes=row.blob_size,
        media_type=row.media_type)
    snapshot = build_production_revision_snapshot(closure)
    if canonical_json_str(snapshot) != row.snapshot_json:
        raise internal_invariant(
            f"production revision {rid!r} snapshot_json disagrees with "
            "its normalized closure")
    import hashlib

    if hashlib.sha256(
            row.snapshot_json.encode()).hexdigest() != row.snapshot_hash:
        raise internal_invariant(
            f"production revision {rid!r} snapshot_hash disagrees with "
            "its stored bytes")
    return {
        "id": row.id, "revision_number": row.revision_number,
        "snapshot_hash": row.snapshot_hash,
        "production_object_id": row.production_object_id,
        "project_id": row.project_id, "blob_hash": row.blob_hash,
        "media_type": row.media_type,
    }


async def _interpretation(conn: AsyncConnection, rid: str,
                          revision: dict) -> tuple[dict | None, str | None]:
    """Verified canonical interpretation (or None) for one revision."""
    row = (await conn.execute(text(
        "SELECT interpretation_json, interpretation_hash, x_mm, y_mm, "
        "z_mm, yaw_udeg, pitch_udeg, roll_udeg FROM "
        "production_revision_spatial_interpretations "
        "WHERE production_revision_id = :r"),
        {"r": rid})).one_or_none()
    if row is None:
        return None, None
    canonical = verify_stored_interpretation(
        interpretation_json=row.interpretation_json,
        interpretation_hash=row.interpretation_hash,
        x_mm=row.x_mm, y_mm=row.y_mm, z_mm=row.z_mm,
        yaw_udeg=row.yaw_udeg, pitch_udeg=row.pitch_udeg,
        roll_udeg=row.roll_udeg,
        row_production_revision_id=rid,
        parent_snapshot_hash=revision["snapshot_hash"],
        parent_blob_hash=revision["blob_hash"])
    return canonical, row.interpretation_hash


async def _world_contexts(
        conn: AsyncConnection, *, subject: dict | None,
        pi_occurrence_id: str | None) -> list[dict]:
    """Applicable predecessor world contexts for one consumer.

    PI: worlds holding an ACTIVE PI track. CE: project worlds whose
    M10 classification returns at least one A4 candidate for the
    entity. Each context carries its uniquely-approved revision."""
    contexts: dict[str, dict] = {}
    if subject is not None and subject["kind"] == "creative_entity":
        worlds = (await conn.execute(text(
            "SELECT id FROM spatial_worlds "
            "WHERE project_id = :p AND deleted_at IS NULL"),
            {"p": subject["project_id"]})).fetchall()
        for world_row in worlds:
            approved = await _unique_approved_revision(
                conn, world_row.id)
            if approved is None:
                continue
            w = await load_world_revision_with_world(
                conn, spatial_world_revision_id=approved)
            candidates = await classify_entity_a4_targets(
                conn, world=w, entity_ids=[subject["id"]])
            if candidates.get(subject["id"]):
                contexts[world_row.id] = {
                    "world_id": world_row.id, "w": w,
                    "targets": candidates[subject["id"]]}
    else:
        tracks = (await conn.execute(text(
            "SELECT spatial_world_id, id FROM "
            "production_instance_spatial_tracks "
            "WHERE occurrence_id = :o AND deleted_at IS NULL "
            "ORDER BY id"),
            {"o": pi_occurrence_id})).fetchall()
        by_world: dict[str, list[dict]] = {}
        for track in tracks:
            by_world.setdefault(track.spatial_world_id, []).append(
                {"kind": "production_instance_track", "id": track.id})
        for world_id in by_world:
            approved = await _unique_approved_revision(conn, world_id)
            if approved is None:
                contexts[world_id] = {
                    "world_id": world_id, "w": None,
                    "targets": by_world[world_id], "unapproved": True}
                continue
            w = await load_world_revision_with_world(
                conn, spatial_world_revision_id=approved)
            contexts[world_id] = {
                "world_id": world_id, "w": w,
                "targets": by_world[world_id]}
    return list(contexts.values())


async def _unique_approved_revision(
        conn: AsyncConnection, world_id: str) -> str | None:
    rows = (await conn.execute(text(
        "SELECT approved_revision_id FROM spatial_world_states "
        "WHERE spatial_world_id = :w AND approved_revision_id IS NOT NULL"),
        {"w": world_id})).fetchall()
    if len(rows) != 1:
        return None
    return rows[0].approved_revision_id


async def resolve_placement_consumer(
        conn: AsyncConnection, *, working_row,
        subject: dict | None, revision: dict) -> dict:
    """§6.5.1 CLEAN_A6 / UNIQUE_A4 / UNRESOLVED projection.

    Composed from the predecessor primitives in derive_candidate's
    exact prerequisite order; UNRESOLVED is never coerced to A6 or
    resolved by incidental ordering."""
    if subject is None:
        # no authority subject → no A4 consumer in the predecessor rule
        return {"outcome": "CLEAN_A6"}

    contexts = await _world_contexts(
        conn, subject=subject, pi_occurrence_id=working_row.occurrence_id)
    if not contexts:
        return {"outcome": "CLEAN_A6"}
    if len(contexts) > 1:
        return {
            "outcome": "UNRESOLVED", "reason": "multi_world_context",
            "worlds": sorted(c["world_id"] for c in contexts)}
    context = contexts[0]
    if context.get("unapproved"):
        return {"outcome": "UNRESOLVED",
                "reason": "no_unique_approved_world_revision"}

    targets = context["targets"]
    if len(targets) != 1:
        return {"outcome": "UNRESOLVED", "reason": "multi_a4_target",
                "targets": targets}

    # derive_candidate's exact prerequisite order on the working row
    if not _entry_is_identity(working_row):
        return {"outcome": "UNRESOLVED",
                "reason": "BINDING_COMPOSITION_TRANSFORM_CONFLICT"}
    if revision["blob_hash"] is None:
        return {"outcome": "UNRESOLVED",
                "reason": "BINDING_SUBJECT_INVALID"}
    interp = await _verify_interpretation_unused(
        conn, working_row.production_revision_id,
        revision["snapshot_hash"], revision["blob_hash"])
    if interp is None:
        return {"outcome": "UNRESOLVED",
                "reason": "BINDING_SPATIAL_INTERPRETATION_REQUIRED"}
    w = context["w"]
    if w["project_id"] != revision["project_id"]:
        return {"outcome": "UNRESOLVED",
                "reason": "BINDING_PROJECT_MISMATCH"}
    return {
        "outcome": "UNIQUE_A4",
        "placement_contract": {
            "owner": "A4_SPATIAL",
            "spatial_world_id": context["world_id"],
            "spatial_world_revision_id": w["verified"]["id"],
            "spatial_world_revision_hash":
                w["verified"]["snapshot_hash"],
            "target_kind": targets[0]["kind"],
            "target_id": targets[0]["id"],
        },
    }


async def _feature_contracts(
        conn: AsyncConnection, composition_id: str,
        occurrence_id: str) -> list[dict]:
    features = (await conn.execute(text(
        "SELECT id, key, kind, value_type, name, enum_values_json, unit "
        "FROM production_instance_features "
        "WHERE composition_id = :c AND occurrence_id = :o "
        "AND deleted_at IS NULL ORDER BY key, id"),
        {"c": composition_id, "o": occurrence_id})).fetchall()
    if not features:
        return []
    ids = [f.id for f in features]
    ph = ", ".join(f":f{i}" for i in range(len(ids)))
    params = {f"f{i}": v for i, v in enumerate(ids)}
    transitions = (await conn.execute(text(
        "SELECT feature_id, id, anchor_type, anchor_id, boundary, "
        "operation, value_json, value_hash "
        f"FROM production_instance_feature_transitions "
        f"WHERE feature_id IN ({ph}) ORDER BY feature_id, id"),
        params)).fetchall()
    per_feature: dict[str, list[dict]] = {i: [] for i in ids}
    for t in transitions:
        per_feature[t.feature_id].append({
            "transition_id": t.id, "anchor_type": t.anchor_type,
            "anchor_id": t.anchor_id, "boundary": t.boundary,
            "operation": t.operation,
            "value_json": json.loads(t.value_json)
            if t.value_json is not None else None,
            "value_hash": t.value_hash})
    out = []
    for f in features:
        out.append({
            "feature_id": f.id, "key": f.key, "kind": f.kind,
            "value_type": f.value_type, "name": f.name,
            "enum_values": json.loads(f.enum_values_json)
            if f.enum_values_json is not None else None,
            "unit": f.unit,
            "active_transition_set_hash":
                canonical_hash(per_feature[f.id]),
        })
    return out


async def _track_contracts(
        conn: AsyncConnection, composition_id: str,
        occurrence_id: str) -> list[dict]:
    tracks = (await conn.execute(text(
        "SELECT id, spatial_world_id, requirement "
        "FROM production_instance_spatial_tracks "
        "WHERE composition_id = :c AND occurrence_id = :o "
        "AND deleted_at IS NULL ORDER BY id"),
        {"c": composition_id, "o": occurrence_id})).fetchall()
    if not tracks:
        return []
    ids = [t.id for t in tracks]
    ph = ", ".join(f":t{i}" for i in range(len(ids)))
    params = {f"t{i}": v for i, v in enumerate(ids)}
    transitions = (await conn.execute(text(
        "SELECT spatial_track_id, id, anchor_type, anchor_id, boundary, "
        "operation, x_mm, y_mm, z_mm, yaw_udeg, pitch_udeg, roll_udeg "
        "FROM production_instance_spatial_transitions "
        f"WHERE spatial_track_id IN ({ph}) AND deleted_at IS NULL "
        f"ORDER BY spatial_track_id, id"),
        params)).fetchall()
    per_track: dict[str, list[dict]] = {i: [] for i in ids}
    for t in transitions:
        per_track[t.spatial_track_id].append({
            "transition_id": t.id, "anchor_type": t.anchor_type,
            "anchor_id": t.anchor_id, "boundary": t.boundary,
            "operation": t.operation,
            "translation_mm": [t.x_mm, t.y_mm, t.z_mm]
            if t.x_mm is not None else None,
            "rotation_udeg": [t.yaw_udeg, t.pitch_udeg, t.roll_udeg]
            if t.yaw_udeg is not None else None})
    return [
        {"track_id": t.id, "spatial_world_id": t.spatial_world_id,
         "requirement": t.requirement,
         "active_transition_set_hash": canonical_hash(per_track[t.id])}
        for t in tracks
    ]


async def _adoption(conn: AsyncConnection, composition_id: str,
                    occurrence_id: str, project_id: str) -> dict | None:
    row = (await conn.execute(text(
        "SELECT a.subject_kind, a.creative_entity_id FROM "
        "composition_occurrence_authority_subjects a "
        "WHERE a.composition_id = :c AND a.occurrence_id = :o"),
        {"c": composition_id, "o": occurrence_id})).one_or_none()
    if row is None:
        return None
    if row.subject_kind == "production_instance":
        return {"kind": "production_instance", "id": occurrence_id}
    # creative-entity subject validity (the §10.1 predecessor checks)
    ent = (await conn.execute(text(
        "SELECT id, project_id, deleted_at FROM creative_entities "
        "WHERE id = :e"), {"e": row.creative_entity_id})).one_or_none()
    if ent is None or ent.deleted_at is not None:
        return {"kind": "creative_entity", "id": row.creative_entity_id,
                "invalid": "missing_or_deleted"}
    if ent.project_id != project_id:
        return {"kind": "creative_entity", "id": row.creative_entity_id,
                "invalid": "cross_project"}
    claims = (await conn.execute(text(
        "SELECT a.occurrence_id FROM "
        "composition_occurrence_authority_subjects a "
        "WHERE a.composition_id = :c AND a.creative_entity_id = :e "
        "AND NOT EXISTS ("
        "  SELECT 1 FROM composition_identity_operation_sources s "
        "  JOIN composition_identity_operations op "
        "  ON op.id = s.operation_id "
        "  WHERE op.composition_id = a.composition_id "
        "  AND s.occurrence_id = a.occurrence_id "
        "  AND s.terminates_identity = 1)"),
        {"c": composition_id, "e": row.creative_entity_id})).fetchall()
    if len(claims) > 1:
        return {"kind": "creative_entity", "id": row.creative_entity_id,
                "invalid": "overlapping_active_claim"}
    return {"kind": "creative_entity", "id": row.creative_entity_id,
            "project_id": ent.project_id}


def _evaluate_use(*, src: dict, tgt: dict, contract_value: dict,
                  src_interp: tuple, tgt_interp: tuple) -> tuple[dict, dict]:
    """§6.2-§6.6 dimension results + translator evidence for one use."""
    placement = contract_value["placement_contract"]
    evidence: dict = {
        "production_lineage": {
            "status": "SATISFIED",
            "evidence": {
                "production_object_id": src["production_object_id"],
                "source_revision_id": src["id"],
                "source_revision_hash": src["snapshot_hash"],
                "source_revision_number": src["revision_number"],
                "target_revision_id": tgt["id"],
                "target_revision_hash": tgt["snapshot_hash"],
                "target_revision_number": tgt["revision_number"]}},
        "retained_consumption": {
            "status": "SATISFIED" if src["blob_hash"] == tgt["blob_hash"]
            else "REVIEW_REQUIRED",
            "evidence": {
                "source_blob_hash": src["blob_hash"],
                "target_blob_hash": tgt["blob_hash"]}},
        "media_type": {
            "status": "SATISFIED"
            if src["media_type"] == tgt["media_type"]
            else "REVIEW_REQUIRED",
            "evidence": {
                "source_media_type": src["media_type"],
                "target_media_type": tgt["media_type"]}},
        "persistent_state_subject_identity": {
            "status": "SATISFIED",
            "evidence": {
                "occurrence_id": contract_value["occurrence_id"],
                "authority_subject": contract_value["authority_subject"],
                "active_feature_count": len(
                    contract_value["active_instance_feature_contracts"]),
                "active_track_count": len(
                    contract_value["active_instance_spatial_tracks"])}},
    }
    translator: dict | None = None
    if placement["owner"] == "A6_COMPOSITION":
        evidence["spatial_interpretation"] = {
            "status": "NOT_APPLICABLE",
            "evidence": {"placement_owner": "A6_COMPOSITION"}}
    else:
        src_canonical, src_hash = src_interp
        tgt_canonical, tgt_hash = tgt_interp
        if tgt_canonical is None:
            evidence["spatial_interpretation"] = {
                "status": "BLOCKED",
                "evidence": {
                    "placement_owner": "A4_SPATIAL",
                    "source_interpretation_hash": src_hash,
                    "target_interpretation_hash": None,
                    "reason": "target interpretation missing"}}
        elif src_hash == tgt_hash:
            evidence["spatial_interpretation"] = {
                "status": "SATISFIED",
                "evidence": {
                    "placement_owner": "A4_SPATIAL",
                    "source_interpretation_hash": src_hash,
                    "target_interpretation_hash": tgt_hash}}
        else:
            reason = frame_bridge_supported(src_canonical, tgt_canonical)
            if reason is None:
                translator = frame_bridge_translate(
                    source=src_canonical, target=tgt_canonical,
                    source_interpretation_hash=src_hash,
                    target_interpretation_hash=tgt_hash)
                evidence["spatial_interpretation"] = {
                    "status": "TRANSLATION_REQUIRED",
                    "evidence": {
                        "placement_owner": "A4_SPATIAL",
                        "source_interpretation_hash": src_hash,
                        "target_interpretation_hash": tgt_hash,
                        "translator_id": translator["translator_id"],
                        "translator_version":
                            translator["translator_version"]}}
            else:
                evidence["spatial_interpretation"] = {
                    "status": "REVIEW_REQUIRED",
                    "evidence": {
                        "placement_owner": "A4_SPATIAL",
                        "source_interpretation_hash": src_hash,
                        "target_interpretation_hash": tgt_hash,
                        "unsupported_reason": reason}}
    return evidence, translator


async def assess_revision_update(
        session: AsyncSession, *, from_revision_id: str,
        to_revision_id: str) -> dict:
    """§13.1 — one BEGIN IMMEDIATE assessment; NO_CURRENT_USES persists
    nothing; identical coordinates converge."""
    if from_revision_id == to_revision_id:
        raise validation_error(
            "source and target Production Revision are identical")
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            src = await _load_verified_revision(conn, from_revision_id)
            tgt = await _load_verified_revision(conn, to_revision_id)
            if src["project_id"] != tgt["project_id"]:
                raise validation_error(
                    "source and target Production Revisions belong to "
                    "different Projects")
            if src["production_object_id"] != tgt["production_object_id"]:
                raise SoloRingError(
                    ErrorCode.VALIDATION_ERROR,
                    "Production Revision from another Production Object "
                    "changes identity; use replace_as_new",
                    status_code=422,
                    details={"identity_change_required": True,
                             "allowed_operation": "replace_as_new"})

            uses_rows = (await conn.execute(text(
                "SELECT composition_id, occurrence_id, "
                "production_revision_id, display_name, "
                "visible, x_mm, y_mm, z_mm, yaw_udeg, pitch_udeg, "
                "roll_udeg FROM composition_working_occurrences "
                "WHERE production_revision_id = :r "
                "AND source_kind = 'production_revision' "
                "ORDER BY composition_id, occurrence_id"),
                {"r": from_revision_id})).fetchall()
            if not uses_rows:
                await conn.commit()
                return {"scope_status": "NO_CURRENT_USES",
                        "assessment_id": None,
                        "overall_verdict": None}

            comp_ids = sorted({r.composition_id for r in uses_rows})
            cph = ", ".join(f":c{i}" for i in range(len(comp_ids)))
            cparams = {f"c{i}": v for i, v in enumerate(comp_ids)}
            comps = {r.id: r for r in (await conn.execute(text(
                f"SELECT id, project_id, working_version FROM "
                f"compositions WHERE id IN ({cph})"),
                cparams)).fetchall()}
            for cid in comp_ids:
                if comps[cid].project_id != src["project_id"]:
                    raise internal_invariant(
                        f"working use in composition {cid!r} belongs to "
                        "another Project — row ownership mismatch")

            src_interp = await _interpretation(
                conn, src["id"], src)
            tgt_interp = await _interpretation(
                conn, tgt["id"], tgt)

            normalized: list[dict] = []
            for row in uses_rows:
                comp = comps[row.composition_id]
                subject = await _adoption(
                    conn, row.composition_id, row.occurrence_id,
                    src["project_id"])
                if subject is not None and subject.get("invalid"):
                    raise _conflict(
                        "placement_consumer_ambiguous",
                        composition_id=row.composition_id,
                        occurrence_id=row.occurrence_id,
                        issue="BINDING_SUBJECT_INVALID",
                        detail=subject["invalid"])
                resolution = await resolve_placement_consumer(
                    conn, working_row=row, subject=subject, revision=src)
                if resolution["outcome"] == "UNRESOLVED":
                    raise _conflict(
                        "placement_consumer_ambiguous",
                        composition_id=row.composition_id,
                        occurrence_id=row.occurrence_id,
                        issue=resolution["reason"])
                contract = {
                    "composition_id": row.composition_id,
                    "occurrence_id": row.occurrence_id,
                    "composition_working_version":
                        comp.working_version,
                    "working_spec": {
                        "display_name": row.display_name,
                        "source": {"kind": "production_revision",
                                   "revision_id": from_revision_id},
                        "visible": bool(row.visible),
                        "translation_mm": [row.x_mm, row.y_mm, row.z_mm],
                        "rotation_udeg": [row.yaw_udeg, row.pitch_udeg,
                                          row.roll_udeg]},
                    "authority_subject": subject,
                    "placement_contract":
                        resolution.get("placement_contract")
                        or {"owner": "A6_COMPOSITION"},
                    "active_instance_feature_contracts":
                        await _feature_contracts(
                            conn, row.composition_id,
                            row.occurrence_id),
                    "active_instance_spatial_tracks":
                        await _track_contracts(
                            conn, row.composition_id,
                            row.occurrence_id),
                    "source_revision": {
                        "id": src["id"],
                        "snapshot_hash": src["snapshot_hash"],
                        "blob_hash": src["blob_hash"],
                        "media_type": src["media_type"],
                        "spatial_interpretation_hash":
                            src_interp[1]},
                    "target_revision": {
                        "id": tgt["id"],
                        "snapshot_hash": tgt["snapshot_hash"],
                        "blob_hash": tgt["blob_hash"],
                        "media_type": tgt["media_type"],
                        "spatial_interpretation_hash":
                            tgt_interp[1]},
                }
                contract_value = use_contract_value(contract)
                evidence, translator = _evaluate_use(
                    src=src, tgt=tgt, contract_value=contract_value,
                    src_interp=src_interp, tgt_interp=tgt_interp)
                normalized.append({
                    "row": row,
                    "contract_value": contract_value,
                    "use_contract_hash":
                        canonical_hash(contract_value),
                    "dimensions": dimension_results_value(evidence),
                    "translator": translator,
                })

            for use in normalized:
                use["dimension_results_hash"] = canonical_hash(
                    use["dimensions"])
                use["verdict"] = fold_verdict(
                    {d: use["dimensions"][d]["status"]
                     for d in use["dimensions"]})
            summary = fold_summary([u["verdict"] for u in normalized])

            identity = {
                "from_revision_id": src["id"],
                "from_revision_hash": src["snapshot_hash"],
                "to_revision_id": tgt["id"],
                "to_revision_hash": tgt["snapshot_hash"]}
            root_uses = [{
                "composition_id": u["row"].composition_id,
                "occurrence_id": u["row"].occurrence_id,
                "verdict": u["verdict"],
                "dimension_results_hash": u["dimension_results_hash"],
                "use_contract_hash": u["use_contract_hash"],
                "translator_output_hash":
                    u["translator"]["output_hash"]
                    if u["translator"] else None}
                for u in normalized]
            scope = scope_root(root_uses)
            report = report_root(identity, root_uses, summary)

            existing = (await conn.execute(text(
                "SELECT id, report_hash FROM "
                "production_compatibility_assessments WHERE "
                "project_id = :p AND from_revision_id = :f "
                "AND to_revision_id = :t AND evaluator_id = :e "
                "AND evaluator_version = :v AND scope_hash = :s"),
                {"p": src["project_id"], "f": src["id"], "t": tgt["id"],
                 "e": EVALUATOR_ID, "v": EVALUATOR_VERSION,
                 "s": canonical_hash(scope)})).one_or_none()
            if existing is not None:
                if existing.report_hash != canonical_hash(report):
                    raise internal_invariant(
                        "identical assessment coordinate with a "
                        "different report — evaluator nondeterminism")
                await conn.commit()
                return _assessment_result(
                    existing.id, canonical_hash(report), summary,
                    normalized, converged=True)

            assessment_id = new_uuid()
            created_at = (await conn.execute(text(
                "SELECT " + _now_sql()))).scalar_one()
            await conn.execute(text(
                "INSERT INTO production_compatibility_assessments "
                "(id, project_id, production_object_id, from_revision_id, "
                "from_revision_hash, to_revision_id, to_revision_hash, "
                "schema_version, evaluator_id, evaluator_version, "
                "scope_json, scope_hash, report_json, report_hash, "
                "overall_verdict, created_at) VALUES "
                "(:id, :p, :o, :f, :fh, :t, :th, 1, :e, 1, :sj, :sh, "
                ":rj, :rh, :v, :n)"),
                {"id": assessment_id, "p": src["project_id"],
                 "o": src["production_object_id"], "f": src["id"],
                 "fh": src["snapshot_hash"], "t": tgt["id"],
                 "th": tgt["snapshot_hash"], "e": EVALUATOR_ID,
                 "sj": canonical_json_str(scope),
                 "sh": canonical_hash(scope),
                 "rj": canonical_json_str(report),
                 "rh": canonical_hash(report), "v": summary,
                 "n": created_at})
            for position, use in enumerate(normalized):
                translator = use["translator"]
                await conn.execute(text(
                    "INSERT INTO production_compatibility_uses "
                    "(assessment_id, position, composition_id, "
                    "occurrence_id, composition_working_version, "
                    "use_contract_json, use_contract_hash, "
                    "dimension_results_json, dimension_results_hash, "
                    "verdict, translator_id, translator_version, "
                    "translator_parameters_json, "
                    "translator_parameters_hash, translator_output_hash) "
                    "VALUES (:a, :pos, :c, :o, :wv, :uj, :uh, :dj, :dh, "
                    ":v, :ti, :tv, :tpj, :tph, :toh)"),
                    {"a": assessment_id, "pos": position,
                     "c": use["row"].composition_id,
                     "o": use["row"].occurrence_id,
                     "wv": use["contract_value"][
                         "composition_working_version"],
                     "uj": canonical_json_str(use["contract_value"]),
                     "uh": use["use_contract_hash"],
                     "dj": canonical_json_str(use["dimensions"]),
                     "dh": canonical_hash(use["dimensions"]),
                     "v": use["verdict"],
                     "ti": translator["translator_id"]
                     if translator else None,
                     "tv": translator["translator_version"]
                     if translator else None,
                     "tpj": canonical_json_str(
                         translator["parameters"]) if translator else None,
                     "tph": translator["parameters_hash"]
                     if translator else None,
                     "toh": translator["output_hash"]
                     if translator else None})
            await conn.commit()
            return _assessment_result(
                assessment_id, canonical_hash(report), summary,
                normalized, converged=False)
        except Exception:
            await conn.rollback()
            raise


def _now_sql() -> str:
    from soloring.db.timeutil import DB_NOW_SQL

    return DB_NOW_SQL


def _assessment_result(assessment_id: str, report_hash: str,
                       summary: str, normalized: list[dict],
                       *, converged: bool) -> dict:
    counts = {verdict: 0 for verdict in (
        "COMPATIBLE_AS_IS",
        "COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION",
        "REQUIRES_REVIEW", "INCOMPATIBLE")}
    for use in normalized:
        counts[use["verdict"]] += 1
    return {
        "scope_status": "ASSESSED",
        "assessment_id": assessment_id,
        "report_hash": report_hash,
        "overall_verdict": summary,
        "verdict_counts": counts,
        "converged": converged,
        "uses": [{
            "composition_id": u["row"].composition_id,
            "occurrence_id": u["row"].occurrence_id,
            "use_contract_hash": u["use_contract_hash"],
            "verdict": u["verdict"],
            "dimensions": {
                d: u["dimensions"][d]["status"]
                for d in u["dimensions"]},
            "translator_output_hash":
                u["translator"]["output_hash"]
                if u["translator"] else None,
        } for u in normalized],
    }
