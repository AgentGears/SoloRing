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
from soloring.production_world.binding import _entry_is_identity
from soloring.production_world.placement_consumer import (
    classify_placement_consumer_from_facts,
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


async def _load_world_contexts(
        conn: AsyncConnection, *, subject: dict | None,
        pi_occurrence_id: str | None) -> list[dict]:
    """I/O adapter (R5 S6.5.1): load applicable predecessor world
    contexts as classifier facts. PI: worlds holding an ACTIVE PI
    track. CE: project worlds whose M10 classification returns at
    least one A4 candidate. Contexts carry their uniquely-approved
    revision when one exists. No classification decision is made
    here."""
    targets_by_world: dict[str, list[dict]] = {}
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
                targets_by_world[world_row.id] = candidates[
                    subject["id"]]
    else:
        tracks = (await conn.execute(text(
            "SELECT spatial_world_id, id FROM "
            "production_instance_spatial_tracks "
            "WHERE occurrence_id = :o AND deleted_at IS NULL "
            "ORDER BY id"),
            {"o": pi_occurrence_id})).fetchall()
        for track in tracks:
            targets_by_world.setdefault(track.spatial_world_id, []).append(
                {"kind": "production_instance_track", "id": track.id})

    contexts: list[dict] = []
    for world_id in sorted(targets_by_world):
        approved = await _unique_approved_revision(conn, world_id)
        if approved is None:
            contexts.append({
                "world_id": world_id, "project_id": None,
                "approved_revision": None,
                "targets": targets_by_world[world_id]})
            continue
        w = await load_world_revision_with_world(
            conn, spatial_world_revision_id=approved)
        contexts.append({
            "world_id": world_id, "project_id": w["project_id"],
            "approved_revision": {
                "id": w["verified"]["id"],
                "snapshot_hash": w["verified"]["snapshot_hash"]},
            "targets": targets_by_world[world_id]})
    return contexts


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
        subject: dict | None, revision: dict,
        source_interpretation_hash: str | None) -> dict:
    """§6.5.1 projection through the SINGLE shared pure classifier.

    This is an I/O adapter: it loads facts and calls
    classify_placement_consumer_from_facts; no placement decision is
    encoded here (frozen R5 §6.5.1)."""
    from soloring.production_world.placement_consumer import (
        classify_placement_consumer_from_facts,
    )

    contexts = await _load_world_contexts(
        conn, subject=subject, pi_occurrence_id=working_row.occurrence_id)
    if subject is None:
        subject_fact = None
    else:
        invalid = subject.get("invalid")
        subject_fact = {
            "kind": subject["kind"], "id": subject["id"],
            "valid": not invalid,
            "invalid_detail": {"reason": invalid} if invalid else None}
    facts = {
        "occurrence_id": working_row.occurrence_id,
        "subject": subject_fact,
        "world_contexts": contexts,
        "transform_is_identity": _entry_is_identity(working_row),
        "revision": {
            "id": working_row.production_revision_id,
            "project_id": revision["project_id"],
            "closed": True,  # row verified by _load_verified_revision
            "interpretation_hash": source_interpretation_hash,
        },
    }
    return classify_placement_consumer_from_facts(facts)


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


def _semantic_projection(canonical: dict) -> tuple:
    """R5 §6.5.3 meaning-bearing schema-1 semantic projection."""
    transform = canonical["realization_local_to_subject_local"]
    return (canonical["schema_version"],
            tuple(transform["translation_mm"]),
            tuple(transform["rotation_udeg"]))


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
        elif _semantic_projection(src_canonical) == _semantic_projection(
                tgt_canonical):
            # R5 §6.5.3: exact schema-1 semantic value equality is the
            # predicate; parent-pinned hashes remain evidence pins only.
            evidence["spatial_interpretation"] = {
                "status": "SATISFIED",
                "evidence": {
                    "placement_owner": "A4_SPATIAL",
                    "source_interpretation_hash": src_hash,
                    "target_interpretation_hash": tgt_hash,
                    "semantic_equality": True}}
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


def _in_clause(values: list, prefix: str) -> tuple[str, dict]:
    marks = ", ".join(f":{prefix}{i}" for i in range(len(values)))
    params = {f"{prefix}{i}": v for i, v in enumerate(values)}
    return marks, params


async def _batched_subjects(
        conn, *, uses_rows, project_id: str) -> dict:
    """One adoption query + bounded CE validity/claim queries."""
    comp_ids = sorted({r.composition_id for r in uses_rows})
    marks, params = _in_clause(comp_ids, "c")
    rows = (await conn.execute(text(
        f"SELECT a.composition_id, a.occurrence_id, a.subject_kind, "
        f"a.creative_entity_id FROM "
        f"composition_occurrence_authority_subjects a "
        f"WHERE a.composition_id IN ({marks}) "
        f"ORDER BY a.composition_id, a.occurrence_id"),
        params)).fetchall()
    out: dict[tuple, dict | None] = {}
    ce_ids = sorted({r.creative_entity_id for r in rows
                     if r.subject_kind == "creative_entity"})
    ent_by_id = {}
    claims_by_ce: dict[str, list[str]] = {}
    if ce_ids:
        emarks, eparams = _in_clause(ce_ids, "e")
        for ent in (await conn.execute(text(
                f"SELECT id, project_id, deleted_at FROM "
                f"creative_entities WHERE id IN ({emarks})"),
                eparams)).fetchall():
            ent_by_id[ent.id] = ent
        for claim in (await conn.execute(text(
                f"SELECT a.creative_entity_id, a.occurrence_id FROM "
                f"composition_occurrence_authority_subjects a "
                f"WHERE a.composition_id IN ({marks}) "
                f"AND a.creative_entity_id IN ({emarks}) "
                f"AND NOT EXISTS ("
                f"  SELECT 1 FROM composition_identity_operation_sources s"
                f"  JOIN composition_identity_operations op "
                f"  ON op.id = s.operation_id "
                f"  WHERE op.composition_id = a.composition_id "
                f"  AND s.occurrence_id = a.occurrence_id "
                f"  AND s.terminates_identity = 1) "
                f"ORDER BY a.creative_entity_id, a.occurrence_id"),
                params | eparams)).fetchall():
            claims_by_ce.setdefault(
                claim.creative_entity_id, []).append(
                claim.occurrence_id)
    for r in rows:
        key = (r.composition_id, r.occurrence_id)
        if r.subject_kind == "production_instance":
            out[key] = {"kind": "production_instance",
                        "id": r.occurrence_id}
            continue
        ent = ent_by_id.get(r.creative_entity_id)
        if ent is None or ent.deleted_at is not None:
            out[key] = {"kind": "creative_entity",
                        "id": r.creative_entity_id,
                        "invalid": "missing_or_deleted"}
            continue
        if ent.project_id != project_id:
            out[key] = {"kind": "creative_entity",
                        "id": r.creative_entity_id,
                        "invalid": "cross_project"}
            continue
        if len(claims_by_ce.get(r.creative_entity_id, [])) > 1:
            out[key] = {"kind": "creative_entity",
                        "id": r.creative_entity_id,
                        "invalid": "overlapping_active_claim"}
            continue
        out[key] = {"kind": "creative_entity",
                    "id": r.creative_entity_id,
                    "project_id": ent.project_id}
    return out


async def _batched_feature_contracts(conn, uses_rows) -> dict:
    """One feature query + one transition query for ALL uses."""
    comp_ids = sorted({r.composition_id for r in uses_rows})
    marks, params = _in_clause(comp_ids, "c")
    feats = (await conn.execute(text(
        f"SELECT id, composition_id, occurrence_id, key, kind, "
        f"value_type, name, enum_values_json, unit FROM "
        f"production_instance_features "
        f"WHERE composition_id IN ({marks}) AND deleted_at IS NULL "
        f"ORDER BY composition_id, occurrence_id, key, id"),
        params)).fetchall()
    per_key: dict[tuple, list] = {}
    feat_ids = [f.id for f in feats]
    trans_by_feat: dict[str, list[dict]] = {}
    if feat_ids:
        tmarks, tparams = _in_clause(feat_ids, "f")
        for t in (await conn.execute(text(
                f"SELECT feature_id, id, anchor_type, anchor_id, "
                f"boundary, operation, value_json, value_hash FROM "
                f"production_instance_feature_transitions "
                f"WHERE feature_id IN ({tmarks}) "
                f"ORDER BY feature_id, id"),
                tparams)).fetchall():
            trans_by_feat.setdefault(t.feature_id, []).append({
                "transition_id": t.id,
                "anchor_type": t.anchor_type,
                "anchor_id": t.anchor_id,
                "boundary": t.boundary,
                "operation": t.operation,
                "value_json": json.loads(t.value_json)
                if t.value_json is not None else None,
                "value_hash": t.value_hash})
    for f in feats:
        per_key.setdefault(
            (f.composition_id, f.occurrence_id), []).append({
                "feature_id": f.id, "key": f.key, "kind": f.kind,
                "value_type": f.value_type, "name": f.name,
                "enum_values": json.loads(f.enum_values_json)
                if f.enum_values_json is not None else None,
                "unit": f.unit,
                "active_transition_set_hash": canonical_hash(
                    trans_by_feat.get(f.id, []))})
    return per_key


async def _batched_track_contracts(conn, uses_rows, *, project_id: str):
    """One track query + one transition query + bounded per-WORLD
    context loads (approved revision + verified world + CE
    classification per distinct world), never per occurrence."""
    comp_ids = sorted({r.composition_id for r in uses_rows})
    marks, params = _in_clause(comp_ids, "c")
    trks = (await conn.execute(text(
        f"SELECT id, composition_id, occurrence_id, spatial_world_id, "
        f"requirement FROM production_instance_spatial_tracks "
        f"WHERE composition_id IN ({marks}) AND deleted_at IS NULL "
        f"ORDER BY composition_id, occurrence_id, id"),
        params)).fetchall()
    track_ids = [t.id for t in trks]
    trans_by_track: dict[str, list[dict]] = {}
    if track_ids:
        tmarks, tparams = _in_clause(track_ids, "t")
        for t in (await conn.execute(text(
                f"SELECT spatial_track_id, id, anchor_type, anchor_id, "
                f"boundary, operation, x_mm, y_mm, z_mm, yaw_udeg, "
                f"pitch_udeg, roll_udeg FROM "
                f"production_instance_spatial_transitions "
                f"WHERE spatial_track_id IN ({tmarks}) "
                f"AND deleted_at IS NULL "
                f"ORDER BY spatial_track_id, id"),
                tparams)).fetchall():
            trans_by_track.setdefault(t.spatial_track_id, []).append({
                "transition_id": t.id,
                "anchor_type": t.anchor_type,
                "anchor_id": t.anchor_id,
                "boundary": t.boundary,
                "operation": t.operation,
                "translation_mm": [t.x_mm, t.y_mm, t.z_mm]
                if t.x_mm is not None else None,
                "rotation_udeg": [t.yaw_udeg, t.pitch_udeg, t.roll_udeg]
                if t.yaw_udeg is not None else None})
    per_key: dict[tuple, list] = {}
    targets_by_occ: dict[tuple, list[dict]] = {}
    for t in trks:
        key = (t.composition_id, t.occurrence_id)
        per_key.setdefault(key, []).append({
            "track_id": t.id,
            "spatial_world_id": t.spatial_world_id,
            "requirement": t.requirement,
            "active_transition_set_hash": canonical_hash(
                trans_by_track.get(t.id, []))})
        targets_by_occ.setdefault(key, {}).setdefault(
            t.spatial_world_id, []).append(
            {"kind": "production_instance_track", "id": t.id})

    # bounded world-context cache: one approved-revision query for all
    # distinct worlds, one verified load + CE classification per world
    world_ids = sorted({t.spatial_world_id for t in trks})
    context_cache: dict[str, dict | None] = {}
    if world_ids:
        wmarks, wparams = _in_clause(world_ids, "w")
        approved_by_world = {r.world_id: r.approved_revision_id
                             for r in (await conn.execute(text(
                                 f"SELECT spatial_world_id AS world_id, "
                                 f"approved_revision_id FROM "
                                 f"spatial_world_states "
                                 f"WHERE spatial_world_id IN ({wmarks}) "
                                 f"AND approved_revision_id IS NOT NULL"),
                                 wparams)).fetchall()}
        # worlds must have a UNIQUE approved revision to be a context
        counts: dict[str, int] = {}
        worlds_rows = (await conn.execute(text(
            f"SELECT id FROM spatial_worlds "
            f"WHERE id IN ({wmarks}) AND deleted_at IS NULL "
            f"AND project_id = :p"),
            wparams | {"p": project_id})).fetchall()
        valid_worlds = {r.id for r in worlds_rows}
        for w in world_ids:
            if w not in valid_worlds or approved_by_world.get(w) is None:
                context_cache[w] = None
                continue
            wr = await load_world_revision_with_world(
                conn, spatial_world_revision_id=approved_by_world[w])
            context_cache[w] = wr

    contexts_by_occ: dict[tuple, list[dict]] = {}
    for key, by_world in targets_by_occ.items():
        ctxs = []
        for wid, targets in by_world.items():
            wr = context_cache.get(wid)
            ctxs.append({
                "world_id": wid,
                "project_id": wr["project_id"] if wr else None,
                "approved_revision": {
                    "id": wr["verified"]["id"],
                    "snapshot_hash": wr["verified"]["snapshot_hash"]}
                if wr else None,
                "targets": targets})
        contexts_by_occ[key] = ctxs
    return per_key, contexts_by_occ


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

            # Frozen R6 S13.1 step 5 / S24: batched contract loading —
            # adoptions, features, tracks, and world contexts load in
            # bounded query classes, never one SELECT per occurrence.
            subjects = await _batched_subjects(
                conn, uses_rows=uses_rows, project_id=src["project_id"])
            features = await _batched_feature_contracts(conn, uses_rows)
            tracks, world_contexts = await _batched_track_contracts(
                conn, uses_rows, project_id=src["project_id"])

            normalized: list[dict] = []
            for row in uses_rows:
                comp = comps[row.composition_id]
                subject = subjects.get(
                    (row.composition_id, row.occurrence_id))
                subject_fact = None
                if subject is not None:
                    invalid = subject.get("invalid")
                    subject_fact = {
                        "kind": subject["kind"], "id": subject["id"],
                        "valid": not invalid,
                        "invalid_detail": {"reason": invalid}
                        if invalid else None}
                contexts = world_contexts.get(
                    (row.composition_id, row.occurrence_id), [])
                facts = {
                    "occurrence_id": row.occurrence_id,
                    "subject": subject_fact,
                    "world_contexts": contexts,
                    "transform_is_identity": _entry_is_identity(row),
                    "revision": {
                        "id": row.production_revision_id,
                        "project_id": src["project_id"],
                        "closed": True,
                        "interpretation_hash": src_interp[1],
                    },
                }
                resolution = classify_placement_consumer_from_facts(facts)
                if resolution["outcome"] == "UNRESOLVED":
                    detail = dict(resolution.get("detail") or {})
                    detail.pop("occurrence_id", None)
                    raise _conflict(
                        "placement_consumer_ambiguous",
                        composition_id=row.composition_id,
                        occurrence_id=row.occurrence_id,
                        issue=resolution["reason"], **detail)
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
                    "active_instance_feature_contracts": features.get(
                        (row.composition_id, row.occurrence_id), []),
                    "active_instance_spatial_tracks": tracks.get(
                        (row.composition_id, row.occurrence_id), []),
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
