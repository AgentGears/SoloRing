"""Immutable Composition↔Spatial binding (frozen M13 R3 §10-§12, §24.5).

The server independently derives the exact whole-C↔W candidate from
authoritative sources; the caller submits only the exact revision pair.
Publication re-reads every current-sensitive input under the writer fence
and converges identical publishers on one binding identity validated by
canonical bytes plus normalized children. Immutable binding integrity,
current binding readiness, and historical binding validity remain
distinct throughout.
"""

from __future__ import annotations

import json as _json
import re as _re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from soloring.composition.readiness import _verify_revision_invariants
from soloring.db.timeutil import DB_NOW_SQL
from soloring.domain.canonical import canonical_json_bytes, canonical_json_str
from soloring.domain.ids import new_uuid

_UUID_RE = _re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_HEX_RE = _re.compile(r"^[0-9a-f]{64}$")
from soloring.errors import (
    ErrorCode,
    SoloRingError,
    internal_invariant,
    not_found,
)
from soloring.production_world.canonical import (
    verify_stored_interpretation,
)
from soloring.spatial.targets import (
    classify_entity_a4_targets,
    load_world_revision_with_world,
)

# Frozen §12 — closed schema-1 readiness detail vocabulary.
ISSUE_CODES = (
    "BINDING_PROJECT_MISMATCH",
    "BINDING_SUBJECT_INVALID",
    "BINDING_SPATIAL_TARGET_CONFLICT",
    "BINDING_COMPOSITION_TRANSFORM_CONFLICT",
    "BINDING_SPATIAL_INTERPRETATION_REQUIRED",
    "BINDING_SPATIAL_INTERPRETATION_INVALID",
)
_ISSUE_ORDER = {code: i for i, code in enumerate(ISSUE_CODES)}

# Test-only race seam (frozen §11.3): an async callable executed after the
# prefence candidate derivation and before BEGIN IMMEDIATE. Production
# never sets it.
PREFENCE_SEAM = None


def binding_value(
    *, composition_revision_id: str, composition_revision_hash: str,
    spatial_world_revision_id: str, spatial_world_revision_hash: str,
    subjects: list[dict], entries: list[dict],
) -> dict:
    """Canonical schema-1 binding value (§11.1); inputs already ordered."""
    return {
        "schema_version": 1,
        "composition_revision": {
            "revision_id": composition_revision_id,
            "snapshot_hash": composition_revision_hash,
        },
        "spatial_world_revision": {
            "revision_id": spatial_world_revision_id,
            "snapshot_hash": spatial_world_revision_hash,
        },
        "subjects": subjects,
        "entries": entries,
    }


def binding_hash(value: dict) -> str:
    import hashlib

    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


async def _load_composition_revision(
    conn: AsyncConnection, revision_id: str,
) -> dict:
    row = (
        await conn.execute(
            text(
                "SELECT r.id, r.composition_id, r.snapshot_hash, "
                "c.project_id FROM composition_revisions r "
                "JOIN compositions c ON c.id = r.composition_id "
                "WHERE r.id = :rid"
            ),
            {"rid": revision_id},
        )
    ).first()
    if row is None:
        raise not_found(
            ErrorCode.COMPOSITION_REVISION_NOT_FOUND,
            f"composition revision {revision_id!r} not found",
        )
    await _verify_revision_invariants(conn, row.id, row.composition_id)
    return {"id": row.id, "composition_id": row.composition_id,
            "snapshot_hash": row.snapshot_hash,
            "project_id": row.project_id}


async def _verify_interpretation_unused(conn, production_revision_id: str,
                                        parent_snapshot_hash: str,
                                        parent_blob_hash: str) -> str:
    row = (
        await conn.execute(
            text(
                "SELECT production_revision_id, schema_version, x_mm, y_mm, "
                "z_mm, yaw_udeg, pitch_udeg, roll_udeg, "
                "interpretation_json, interpretation_hash FROM "
                "production_revision_spatial_interpretations "
                "WHERE production_revision_id = :rid"
            ),
            {"rid": production_revision_id},
        )
    ).first()
    if row is None:
        return None
    canonical = verify_stored_interpretation(
        interpretation_json=row.interpretation_json,
        interpretation_hash=row.interpretation_hash,
        x_mm=row.x_mm, y_mm=row.y_mm, z_mm=row.z_mm,
        yaw_udeg=row.yaw_udeg, pitch_udeg=row.pitch_udeg,
        roll_udeg=row.roll_udeg,
        row_production_revision_id=row.production_revision_id,
        parent_snapshot_hash=parent_snapshot_hash,
        parent_blob_hash=parent_blob_hash,
    )
    return canonical["realization_local_to_subject_local"]


def _entry_is_identity(row) -> bool:
    return (row.x_mm == 0 and row.y_mm == 0 and row.z_mm == 0
            and row.yaw_udeg == 0 and row.pitch_udeg == 0
            and row.roll_udeg == 0)


async def derive_candidate(conn, *, c: dict, w: dict) -> tuple[dict, list]:
    """Derive the exact whole-C↔W candidate (§10) — set-oriented.

    Returns (binding value, issues). Issues follow the frozen §12
    precedence; any stored corruption raises the invariant error instead
    of becoming a friendly issue.
    """
    issues: list[dict] = []

    def add(code: str, **kw) -> None:
        issues.append({"code": code, **kw})

    # revision integrity / project coherence (§10.1)
    if c["project_id"] != w["project_id"]:
        add("BINDING_PROJECT_MISMATCH",
            composition_project_id=c["project_id"],
            world_project_id=w["project_id"])
        return binding_value(
            composition_revision_id=c["id"],
            composition_revision_hash=c["snapshot_hash"],
            spatial_world_revision_id=w["verified"]["id"],
            spatial_world_revision_hash=w["verified"]["snapshot_hash"],
            subjects=[], entries=[]), issues

    # universe: direct production_revision occurrences present in exact C
    universe = (
        await conn.execute(
            text(
                "SELECT occurrence_id, production_revision_id, x_mm, y_mm, "
                "z_mm, yaw_udeg, pitch_udeg, roll_udeg FROM "
                "composition_revision_occurrences "
                "WHERE composition_revision_id = :rid "
                "AND source_kind = 'production_revision' "
                "ORDER BY occurrence_id"
            ),
            {"rid": c["id"]},
        )
    ).fetchall()
    by_occurrence = {r.occurrence_id: r for r in universe}
    occ_ids = list(by_occurrence)

    # subject adoptions for occurrences PRESENT in exact C (set-oriented)
    adoptions: dict[str, dict] = {}
    if occ_ids:
        ph = ", ".join(f":o{i}" for i in range(len(occ_ids)))
        params = {f"o{i}": o for i, o in enumerate(occ_ids)}
        rows = (
            await conn.execute(
                text(
                    "SELECT a.occurrence_id, a.subject_kind, "
                    "a.creative_entity_id FROM "
                    "composition_occurrence_authority_subjects a "
                    f"WHERE a.composition_id = :cid AND a.occurrence_id IN "
                    f"({ph}) ORDER BY a.occurrence_id"
                ),
                {"cid": c["composition_id"], **params},
            )
        ).fetchall()
        for r in rows:
            adoptions[r.occurrence_id] = {
                "subject_kind": r.subject_kind,
                "creative_entity_id": r.creative_entity_id,
            }

    # subject validity (§2.2/§10.1): PI subject id is the occurrence UUID;
    # CE subject same-Project + active-claim uniqueness inside the lineage
    invalid_occurrences: set[str] = set()
    ce_ids = sorted({a["creative_entity_id"] for a in adoptions.values()
                     if a["subject_kind"] == "creative_entity"})
    active_ce_ok: set[str] = set()
    if ce_ids:
        # set-oriented (§26.1 Q2-class): ONE entity query for ALL CE ids
        eph = ", ".join(f":e{i}" for i in range(len(ce_ids)))
        ent_rows = (await conn.execute(
            text(f"SELECT id, project_id, deleted_at FROM creative_entities"
                 f" WHERE id IN ({eph})"),
            {f"e{i}": v for i, v in enumerate(ce_ids)},
        )).fetchall()
        ent_by_id = {r.id: r for r in ent_rows}
        # ONE grouped query for every overlapping-active-claim CE at once
        dupes_rows = (await conn.execute(
            text(
                "SELECT a.creative_entity_id, a.occurrence_id FROM "
                "composition_occurrence_authority_subjects a "
                "WHERE a.composition_id = :cid AND a.occurrence_id IN ("
                + ",".join(f":o{i}" for i in range(len(occ_ids)))
                + ") AND a.creative_entity_id IN (" + eph + ") "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM composition_identity_operation_sources s"
                "  JOIN composition_identity_operations op "
                "  ON op.id = s.operation_id "
                "  WHERE op.composition_id = a.composition_id "
                "  AND s.occurrence_id = a.occurrence_id "
                "  AND s.terminates_identity = 1) "
                "ORDER BY a.creative_entity_id, a.occurrence_id"
            ),
            {"cid": c["composition_id"], **params,
             **{f"e{i}": v for i, v in enumerate(ce_ids)}},
        )).fetchall()
        claim_counts: dict[str, list[str]] = {}
        for d in dupes_rows:
            claim_counts.setdefault(d.creative_entity_id,
                                    []).append(d.occurrence_id)
        for eid in ce_ids:
            ent = ent_by_id.get(eid)
            if ent is None or ent.deleted_at is not None:
                add("BINDING_SUBJECT_INVALID", creative_entity_id=eid,
                    reason="missing_or_deleted")
                continue
            if ent.project_id != c["project_id"]:
                add("BINDING_PROJECT_MISMATCH", creative_entity_id=eid,
                    reason="cross_project_creative_entity")
                continue
            claimants = claim_counts.get(eid, [])
            if len(claimants) > 1:
                add("BINDING_SUBJECT_INVALID", creative_entity_id=eid,
                    reason="overlapping_active_claim",
                    occurrences=sorted(claimants))
                continue
            active_ce_ok.add(eid)
    for occ, a in adoptions.items():
        if a["subject_kind"] == "creative_entity" and (
                a["creative_entity_id"] not in active_ce_ok):
            invalid_occurrences.add(occ)

    # set-oriented Production Revision hash lookup for the whole universe
    pr_hash_map: dict[str, str] = {}
    if occ_ids:
        universe_prs = sorted({r.production_revision_id for r in universe})
        ph = ", ".join(f":p{i}" for i in range(len(universe_prs)))
        for r in (await conn.execute(
            text(f"SELECT id, snapshot_hash FROM production_revisions "
                 f"WHERE id IN ({ph})"),
            {f"p{i}": v for i, v in enumerate(universe_prs)},
        )).fetchall():
            pr_hash_map[r.id] = r.snapshot_hash

    subjects: list[dict] = []
    for occ in sorted(adoptions):
        if occ in invalid_occurrences:
            continue
        a = adoptions[occ]
        row = by_occurrence[occ]
        subjects.append({
            "occurrence_id": occ,
            "production_revision_id": row.production_revision_id,
            "production_revision_hash": pr_hash_map[
                row.production_revision_id],
            "authority_subject": {
                "kind": a["subject_kind"],
                "id": (a["creative_entity_id"]
                       if a["subject_kind"] == "creative_entity" else occ),
            },
        })

    # spatial-target derivation (§10.1): M10-owned classification
    ce_universe = sorted({s["authority_subject"]["id"] for s in subjects
                          if s["authority_subject"]["kind"] == "creative_entity"})
    ce_targets = await classify_entity_a4_targets(
        conn, world=w, entity_ids=ce_universe)
    pi_ids = sorted({s["occurrence_id"] for s in subjects
                     if s["authority_subject"]["kind"] == "production_instance"})
    pi_targets: dict[str, list[dict]] = {o: [] for o in pi_ids}
    if pi_ids:
        ph = ", ".join(f":o{i}" for i in range(len(pi_ids)))
        params = {f"o{i}": o for i, o in enumerate(pi_ids)}
        rows = (
            await conn.execute(
                text(
                    "SELECT id, occurrence_id FROM "
                    "production_instance_spatial_tracks "
                    f"WHERE spatial_world_id = :w AND deleted_at IS NULL "
                    f"AND occurrence_id IN ({ph}) ORDER BY id",
                ),
                {"w": w["world_id"], **params},
            )
        ).fetchall()
        for r in rows:
            pi_targets[r.occurrence_id].append(
                {"kind": "production_instance_track", "id": r.id})

    blocked_occurrences: set[str] = set()
    targets_by_occurrence: dict[str, list[dict]] = {}
    for s in subjects:
        occ = s["occurrence_id"]
        if s["authority_subject"]["kind"] == "creative_entity":
            targets = ce_targets[s["authority_subject"]["id"]]
        else:
            targets = pi_targets[occ]
        targets_by_occurrence[occ] = targets

    for s in sorted(subjects, key=lambda s: s["occurrence_id"]):
        occ = s["occurrence_id"]
        targets = targets_by_occurrence[occ]
        if len(targets) > 1:
            add("BINDING_SPATIAL_TARGET_CONFLICT", occurrence_id=occ,
                targets=targets)
            blocked_occurrences.add(occ)

    # per-authority-bound requirements for the unambiguous 1-target subset
    entries: list[dict] = []
    needed_prs = sorted({by_occurrence[occ].production_revision_id
                         for occ in targets_by_occurrence
                         if occ not in blocked_occurrences
                         and len(targets_by_occurrence[occ]) == 1})
    pr_hashes: dict[str, str] = {}
    pr_blobs: dict[str, str] = {}
    if needed_prs:
        # set-oriented (§26.1 Q3-class): ONE closure query for ALL needed PRs
        nph = ", ".join(f":n{i}" for i in range(len(needed_prs)))
        nparams = {f"n{i}": v for i, v in enumerate(needed_prs)}
        for row in (await conn.execute(
            text(
                "SELECT pr.id, pr.snapshot_hash, "
                "(SELECT c.blob_hash FROM production_revision_closures c"
                " WHERE c.production_revision_id = pr.id AND "
                "c.contract_key = 'retained_blob' AND "
                "c.contract_version = 1) AS blob_hash "
                f"FROM production_revisions pr WHERE pr.id IN ({nph})"
            ),
            nparams,
        )).fetchall():
            pr_hashes[row.id] = row.snapshot_hash
            pr_blobs[row.id] = row.blob_hash
        for prid in needed_prs:
            if prid not in pr_hashes:
                add("BINDING_SUBJECT_INVALID", production_revision_id=prid,
                    reason="missing_production_revision")
    # set-oriented (§26.1 Q3): ONE interpretation query for ALL needed
    # PRs; verification is in-memory per row (CPU only, no round trips)
    interp_map: dict[str, str] = {}
    closed_prs = [p for p in needed_prs
                  if p in pr_hashes and pr_hashes[p] is not None
                  and pr_blobs.get(p) is not None]
    if closed_prs:
        iph = ", ".join(f":i{i}" for i in range(len(closed_prs)))
        iparams = {f"i{i}": v for i, v in enumerate(closed_prs)}
        irows = (await conn.execute(
            text(
                "SELECT production_revision_id, interpretation_json, "
                "interpretation_hash, x_mm, y_mm, z_mm, yaw_udeg, "
                "pitch_udeg, roll_udeg FROM "
                "production_revision_spatial_interpretations "
                f"WHERE production_revision_id IN ({iph})"
            ),
            iparams,
        )).fetchall()
        for row in irows:
            verify_stored_interpretation(
                interpretation_json=row.interpretation_json,
                interpretation_hash=row.interpretation_hash,
                x_mm=row.x_mm, y_mm=row.y_mm, z_mm=row.z_mm,
                yaw_udeg=row.yaw_udeg, pitch_udeg=row.pitch_udeg,
                roll_udeg=row.roll_udeg,
                row_production_revision_id=row.production_revision_id,
                parent_snapshot_hash=pr_hashes[row.production_revision_id],
                parent_blob_hash=pr_blobs[row.production_revision_id],
            )
            interp_map[row.production_revision_id] = (
                row.interpretation_hash)
    for s in sorted(subjects, key=lambda s: s["occurrence_id"]):
        occ = s["occurrence_id"]
        if occ in blocked_occurrences:
            continue
        targets = targets_by_occurrence[occ]
        if len(targets) != 1:
            continue  # 0 candidates → composition-owned, no entry
        crow = by_occurrence[occ]
        if not _entry_is_identity(crow):
            add("BINDING_COMPOSITION_TRANSFORM_CONFLICT", occurrence_id=occ)
            blocked_occurrences.add(occ)
            continue
        prid = crow.production_revision_id
        if prid not in pr_hashes or pr_hashes[prid] is None:
            add("BINDING_SUBJECT_INVALID", occurrence_id=occ,
                reason="production_revision_not_closed")
            blocked_occurrences.add(occ)
            continue
        interp = interp_map.get(prid)
        if interp is None:
            add("BINDING_SPATIAL_INTERPRETATION_REQUIRED",
                occurrence_id=occ, production_revision_id=prid)
            blocked_occurrences.add(occ)
            continue
        target = targets[0]
        entries.append({
            "occurrence_id": occ,
            "production_revision_id": prid,
            "production_revision_hash": pr_hashes[prid],
            "authority_subject": dict(s["authority_subject"]),
            "placement": {"kind": target["kind"], "id": target["id"]},
            "spatial_interpretation_hash": interp_map[prid],
        })

    issues.sort(key=lambda i: _ISSUE_ORDER[i["code"]])
    return binding_value(
        composition_revision_id=c["id"],
        composition_revision_hash=c["snapshot_hash"],
        spatial_world_revision_id=w["verified"]["id"],
        spatial_world_revision_hash=w["verified"]["snapshot_hash"],
        subjects=subjects, entries=entries), issues


async def _interp_hash(conn, production_revision_id: str,
                       parent_snapshot_hash: str,
                       parent_blob_hash: str) -> str:
    row = (
        await conn.execute(
            text(
                "SELECT interpretation_json, interpretation_hash, x_mm, "
                "y_mm, z_mm, yaw_udeg, pitch_udeg, roll_udeg FROM "
                "production_revision_spatial_interpretations "
                "WHERE production_revision_id = :rid"
            ),
            {"rid": production_revision_id},
        )
    ).first()
    if row is None:
        raise internal_invariant(
            "authority-bound entry lost its interpretation during "
            "derivation")
    verify_stored_interpretation(
        interpretation_json=row.interpretation_json,
        interpretation_hash=row.interpretation_hash,
        x_mm=row.x_mm, y_mm=row.y_mm, z_mm=row.z_mm,
        yaw_udeg=row.yaw_udeg, pitch_udeg=row.pitch_udeg,
        roll_udeg=row.roll_udeg,
        row_production_revision_id=production_revision_id,
        parent_snapshot_hash=parent_snapshot_hash,
        parent_blob_hash=parent_blob_hash,
    )
    return row.interpretation_hash


async def binding_readiness(
    conn, *, composition_revision_id: str, spatial_world_revision_id: str,
) -> dict:
    """Preview (§11.2): ready/issues/proposed hash + ordered summaries."""
    c = await _load_composition_revision(conn, composition_revision_id)
    w = await load_world_revision_with_world(
        conn, spatial_world_revision_id=spatial_world_revision_id)
    value, issues = await derive_candidate(conn, c=c, w=w)
    return {
        "ready": not issues,
        "issues": issues,
        "proposed_binding_hash": binding_hash(value),
        "composition_revision_id": c["id"],
        "composition_revision_hash": c["snapshot_hash"],
        "spatial_world_revision_id": w["verified"]["id"],
        "spatial_world_revision_hash": w["verified"]["snapshot_hash"],
        "subject_summaries": [
            {"occurrence_id": s["occurrence_id"], **s["authority_subject"]}
            for s in value["subjects"]],
        "entry_summaries": [
            {"occurrence_id": e["occurrence_id"],
             "placement": e["placement"],
             "spatial_interpretation_hash": e["spatial_interpretation_hash"]}
            for e in value["entries"]],
        "_value": value,
    }


async def publish_binding(
    session: AsyncSession, *, composition_revision_id: str,
    spatial_world_revision_id: str,
) -> tuple[dict, bool]:
    """Compare-and-freeze publication (§11.3). Returns (read, created)."""
    async with session.bind.connect() as conn:
        # coherent prefence read + derivation outside the writer fence
        c = await _load_composition_revision(conn, composition_revision_id)
        w = await load_world_revision_with_world(
            conn, spatial_world_revision_id=spatial_world_revision_id)
        value, issues = await derive_candidate(conn, c=c, w=w)
        prefence_hash = binding_hash(value)

        # Test-only race seam (frozen §11.3): fires inside the exact
        # prefence-derivation → fence-acquisition window, before any
        # not-ready refusal, so an interleaved authority change (R6/R7/R8)
        # is always detected as a candidate-hash conflict.
        if PREFENCE_SEAM is not None:
            await PREFENCE_SEAM()

        # Frozen §11.3: the fence ALWAYS opens and the re-derived candidate
        # decides — a hash mismatch is a conflict even when the prefence
        # candidate was itself not ready (R8); a stable not-ready candidate
        # is refused only after the equality check.
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        # re-read EVERY current-sensitive input under the fence and
        # re-derive the exact candidate (no prefence subset reuse)
        c2 = await _load_composition_revision(conn, composition_revision_id)
        w2 = await load_world_revision_with_world(
            conn, spatial_world_revision_id=spatial_world_revision_id)
        value2, issues2 = await derive_candidate(conn, c=c2, w=w2)
        fence_hash = binding_hash(value2)
        # Frozen §11.3: candidate hash mismatch => binding conflict — this
        # check precedes any not-ready refusal so an interleaved authority
        # change (R6/R7/R8) is always reported as a conflict, even when it
        # also changed bindability.
        if fence_hash != prefence_hash:
            raise SoloRingError(
                ErrorCode.COMPOSITION_SPATIAL_BINDING_CONFLICT,
                "binding candidate changed between preview and fence; "
                "re-derive and retry",
                status_code=409)
        if issues2:
            raise SoloRingError(
                ErrorCode.COMPOSITION_SPATIAL_BINDING_NOT_READY,
                "binding candidate is not ready: "
                + "; ".join(i["code"] for i in issues2),
                status_code=409,
                details={"issues": issues2})

        existing = (
            await conn.execute(
                text(
                    "SELECT id, binding_json, binding_hash, created_at FROM "
                    "composition_spatial_bindings WHERE "
                    "composition_revision_id = :c AND "
                    "spatial_world_revision_id = :w AND binding_hash = :h"
                ),
                {"c": composition_revision_id, "w": spatial_world_revision_id,
                 "h": fence_hash},
            )
        ).first()
        if existing is not None:
            read = await _validate_stored_binding(conn, existing.id)
            await conn.exec_driver_sql("COMMIT")
            return read, False

        bid = new_uuid()
        await conn.execute(
            text(
                "INSERT INTO composition_spatial_bindings "
                "(id, composition_revision_id, composition_revision_hash, "
                "spatial_world_revision_id, spatial_world_revision_hash, "
                f"schema_version, binding_json, binding_hash, created_at) "
                f"VALUES (:id, :c, :ch, :w, :wh, 1, :js, :h, {DB_NOW_SQL})"
            ),
            {"id": bid, "c": value2["composition_revision"]["revision_id"],
             "ch": value2["composition_revision"]["snapshot_hash"],
             "w": value2["spatial_world_revision"]["revision_id"],
             "wh": value2["spatial_world_revision"]["snapshot_hash"],
             "js": canonical_json_str(value2), "h": fence_hash},
        )
        for position, s in enumerate(value2["subjects"]):
            await conn.execute(
                text(
                    "INSERT INTO composition_spatial_binding_subjects "
                    "(binding_id, position, occurrence_id, "
                    "production_revision_id, production_revision_hash, "
                    "subject_kind, subject_id, creative_entity_id) VALUES "
                    "(:b, :pos, :occ, :pr, :prh, :sk, :sid, :ce)"
                ),
                {"b": bid, "pos": position, "occ": s["occurrence_id"],
                 "pr": s["production_revision_id"],
                 "prh": s["production_revision_hash"],
                 "sk": s["authority_subject"]["kind"],
                 "sid": s["authority_subject"]["id"],
                 "ce": (s["authority_subject"]["id"]
                        if s["authority_subject"]["kind"] == "creative_entity"
                        else None)},
            )
        for position, e in enumerate(value2["entries"]):
            await conn.execute(
                text(
                    "INSERT INTO composition_spatial_binding_entries "
                    "(binding_id, position, occurrence_id, "
                    "production_revision_id, production_revision_hash, "
                    "subject_kind, subject_id, creative_entity_id, "
                    "placement_kind, spatial_frame_id, spatial_track_id, "
                    "production_instance_track_id, "
                    "spatial_interpretation_hash) VALUES "
                    "(:b, :pos, :occ, :pr, :prh, :sk, :sid, :ce, :pk, "
                    ":sf, :st, :pit, :ih)"
                ),
                {"b": bid, "pos": position, "occ": e["occurrence_id"],
                 "pr": e["production_revision_id"],
                 "prh": e["production_revision_hash"],
                 "sk": e["authority_subject"]["kind"],
                 "sid": e["authority_subject"]["id"],
                 "ce": (e["authority_subject"]["id"]
                        if e["authority_subject"]["kind"] == "creative_entity"
                        else None),
                 "pk": e["placement"]["kind"],
                 "sf": (e["placement"]["id"]
                        if e["placement"]["kind"] == "entity_fixed_frame"
                        else None),
                 "st": (e["placement"]["id"]
                        if e["placement"]["kind"] == "entity_track" else None),
                 "pit": (e["placement"]["id"]
                         if e["placement"]["kind"] == "production_instance_track"
                         else None),
                 "ih": e["spatial_interpretation_hash"]},
            )
        await conn.exec_driver_sql("COMMIT")
    read = await read_binding(session, bid)
    return read, True


async def _validate_stored_binding(conn, binding_id: str) -> dict:
    """Full immutable-integrity validation (§14.2 IMMUTABLE tier)."""
    parent = (
        await conn.execute(
            text(
                "SELECT id, composition_revision_id, "
                "composition_revision_hash, spatial_world_revision_id, "
                "spatial_world_revision_hash, schema_version, binding_json, "
                "binding_hash, created_at FROM composition_spatial_bindings "
                "WHERE id = :b"
            ),
            {"b": binding_id},
        )
    ).first()
    if parent is None:
        raise not_found(
            ErrorCode.COMPOSITION_SPATIAL_BINDING_NOT_FOUND,
            f"binding {binding_id!r} not found",
        )
    try:
        parsed = _json.loads(parent.binding_json)
    except ValueError as exc:
        raise internal_invariant(
            f"binding {binding_id} JSON is not parseable") from exc
    value = _parse_binding_value(parsed)
    if canonical_json_str(value) != parent.binding_json:
        raise internal_invariant(
            f"binding {binding_id} JSON is not the canonical encoding")
    if binding_hash(value) != parent.binding_hash:
        raise internal_invariant(
            f"binding {binding_id} hash disagrees with canonical bytes")
    if (value["composition_revision"]["revision_id"]
            != parent.composition_revision_id
            or value["composition_revision"]["snapshot_hash"]
            != parent.composition_revision_hash
            or value["spatial_world_revision"]["revision_id"]
            != parent.spatial_world_revision_id
            or value["spatial_world_revision"]["snapshot_hash"]
            != parent.spatial_world_revision_hash
            or parent.schema_version != 1):
        raise internal_invariant(
            f"binding {binding_id} parent columns disagree with its value")

    subject_rows = (
        await conn.execute(
            text(
                "SELECT position, occurrence_id, production_revision_id, "
                "production_revision_hash, subject_kind, subject_id, "
                "creative_entity_id FROM composition_spatial_binding_subjects"
                " WHERE binding_id = :b ORDER BY position"
            ),
            {"b": binding_id},
        )
    ).fetchall()
    if len(subject_rows) != len(value["subjects"]):
        raise internal_invariant(
            f"binding {binding_id} subject child count mismatch")
    for position, (row, s) in enumerate(zip(subject_rows,
                                            value["subjects"])):
        expected_ce = (s["authority_subject"]["id"]
                       if s["authority_subject"]["kind"] == "creative_entity"
                       else None)
        if (row.position != position  # contiguous zero-based
                or row.occurrence_id != s["occurrence_id"]
                or row.production_revision_id != s["production_revision_id"]
                or row.production_revision_hash != s["production_revision_hash"]
                or row.subject_kind != s["authority_subject"]["kind"]
                or row.subject_id != s["authority_subject"]["id"]
                or row.creative_entity_id != expected_ce):
            raise internal_invariant(
                f"binding {binding_id} subject projection mismatch")

    entry_rows = (
        await conn.execute(
            text(
                "SELECT position, occurrence_id, production_revision_id, "
                "production_revision_hash, subject_kind, subject_id, "
                "creative_entity_id, placement_kind, spatial_frame_id, "
                "spatial_track_id, production_instance_track_id, "
                "spatial_interpretation_hash FROM "
                "composition_spatial_binding_entries WHERE binding_id = :b "
                "ORDER BY position"
            ),
            {"b": binding_id},
        )
    ).fetchall()
    if len(entry_rows) != len(value["entries"]):
        raise internal_invariant(
            f"binding {binding_id} entry child count mismatch")
    for position, (row, e) in enumerate(zip(entry_rows, value["entries"])):
        expected_ce = (e["authority_subject"]["id"]
                       if e["authority_subject"]["kind"] == "creative_entity"
                       else None)
        col_for_kind = {
            "entity_fixed_frame": row.spatial_frame_id,
            "entity_track": row.spatial_track_id,
            "production_instance_track": row.production_instance_track_id,
        }
        others = [v for k, v in col_for_kind.items()
                  if k != e["placement"]["kind"]]
        if (row.occurrence_id != e["occurrence_id"]
                or row.production_revision_id != e["production_revision_id"]
                or row.production_revision_hash
                != e["production_revision_hash"]
                or row.subject_kind != e["authority_subject"]["kind"]
                or row.subject_id != e["authority_subject"]["id"]
                or row.creative_entity_id != expected_ce
                or row.placement_kind != e["placement"]["kind"]
                or col_for_kind[e["placement"]["kind"]] != e["placement"]["id"]
                or any(v is not None for v in others)
                or row.spatial_interpretation_hash
                != e["spatial_interpretation_hash"]
                or row.position != position):
            raise internal_invariant(
                f"binding {binding_id} entry projection mismatch")

    composition = (await conn.execute(
        text("SELECT composition_id FROM composition_revisions "
             "WHERE id = :r"),
        {"r": parent.composition_revision_id},
    )).first()
    if composition is None:
        raise internal_invariant(
            f"binding {parent.id} references a missing CompositionRevision")
    return _read_projection(parent, value, composition.composition_id)


def _parse_binding_value(parsed: object) -> dict:
    """Exact grammar gate over a parsed binding value (raises invariant)."""
    def bad(msg: str):
        return internal_invariant(f"binding value corrupt: {msg}")

    if not isinstance(parsed, dict) or set(parsed) != {
            "schema_version", "composition_revision",
            "spatial_world_revision", "subjects", "entries"}:
        raise bad("top-level keys")
    if parsed["schema_version"] != 1 or not isinstance(
            parsed["schema_version"], int):
        raise bad("schema_version")
    for key in ("composition_revision", "spatial_world_revision"):
        block = parsed[key]
        if (not isinstance(block, dict) or set(block) != {
                "revision_id", "snapshot_hash"}
                or not isinstance(block["revision_id"], str)):
            raise bad(key)
        if _HEX_RE.match(block["snapshot_hash"] or "") is None:
            raise bad(f"{key}.snapshot_hash")

    def is_uuid(v: object) -> bool:
        return isinstance(v, str) and _UUID_RE.match(v) is not None

    for lst, keys, is_entry in (
            (parsed["subjects"],
             {"occurrence_id", "production_revision_id",
              "production_revision_hash", "authority_subject"}, False),
            (parsed["entries"],
             {"occurrence_id", "production_revision_id",
              "production_revision_hash", "authority_subject", "placement",
              "spatial_interpretation_hash"}, True)):
        if not isinstance(lst, list):
            raise bad("subjects/entries must be lists")
        for item in lst:
            if not isinstance(item, dict) or set(item) != keys:
                raise bad("entry keys")
            if (not is_uuid(item["occurrence_id"])
                    or not is_uuid(item["production_revision_id"])
                    or not isinstance(item["production_revision_hash"], str)
                    or _HEX_RE.match(item["production_revision_hash"]) is None):
                raise bad("entry identity fields")
            subj = item["authority_subject"]
            if (not isinstance(subj, dict) or set(subj) != {"kind", "id"}
                    or subj["kind"] not in ("creative_entity",
                                            "production_instance")
                    or not is_uuid(subj["id"])):
                raise bad("authority_subject")
            if subj["kind"] == "production_instance" and subj[
                    "id"] != item["occurrence_id"]:
                raise bad("production_instance subject id")
            if is_entry:
                pl = item["placement"]
                if (not isinstance(pl, dict) or set(pl) != {"kind", "id"}
                        or pl["kind"] not in ("entity_fixed_frame",
                                              "entity_track",
                                              "production_instance_track")
                        or not is_uuid(pl["id"])):
                    raise bad("placement")
                if (not isinstance(item["spatial_interpretation_hash"], str)
                        or _HEX_RE.match(
                            item["spatial_interpretation_hash"]) is None):
                    raise bad("spatial_interpretation_hash")
    return parsed


def _read_projection(parent, value: dict, _composition_id: str) -> dict:
    return {
        "binding_id": parent.id,
        "composition_id": _composition_id,
        "binding_hash": parent.binding_hash,
        "schema_version": parent.schema_version,
        "composition_revision_id": parent.composition_revision_id,
        "composition_revision_hash": parent.composition_revision_hash,
        "spatial_world_revision_id": parent.spatial_world_revision_id,
        "spatial_world_revision_hash": parent.spatial_world_revision_hash,
        "subjects": value["subjects"],
        "entries": value["entries"],
        "created_at": parent.created_at,
    }


async def read_binding(session: AsyncSession, binding_id: str) -> dict:
    """Verified immutable binding reader (§20.2) — integrity only."""
    async with session.bind.connect() as conn:
        return await _validate_stored_binding(conn, binding_id)


async def binding_current_status(
    conn, *, composition_revision_id: str,
    spatial_world_revision_id: str, stored_value: dict,
) -> tuple[bool, list[dict]]:
    """Current readiness tier (§10.3/§14.2): candidate equality + the
    closed stale-detail vocabulary. Integrity must already be proven."""
    c = await _load_composition_revision(conn, composition_revision_id)
    w = await load_world_revision_with_world(
        conn, spatial_world_revision_id=spatial_world_revision_id)
    current, _ = await derive_candidate(conn, c=c, w=w)
    current_hash = binding_hash(current)
    if current_hash == binding_hash(stored_value):
        return True, []
    stale: list[dict] = []
    stored_subjects = {s["occurrence_id"]: s for s in stored_value["subjects"]}
    current_subjects = {s["occurrence_id"]: s
                        for s in current["subjects"]}
    if set(stored_subjects) != set(current_subjects):
        stale.append({
            "code": "BINDING_STALE_SUBJECT_SET_CHANGED",
            "before": sorted(stored_subjects),
            "current": sorted(current_subjects)})
    stored_entries = {e["occurrence_id"]: e for e in stored_value["entries"]}
    current_entries = {e["occurrence_id"]: e
                       for e in current["entries"]}
    if set(stored_entries) != set(current_entries):
        stale.append({
            "code": "BINDING_STALE_PLACEMENT_SET_CHANGED",
            "before": sorted(stored_entries),
            "current": sorted(current_entries)})
    for occ in sorted(set(stored_entries) & set(current_entries)):
        if (stored_entries[occ]["placement"]
                != current_entries[occ]["placement"]
                or stored_entries[occ]["spatial_interpretation_hash"]
                != current_entries[occ]["spatial_interpretation_hash"]):
            stale.append({
                "code": "BINDING_STALE_PLACEMENT_TARGET_CHANGED",
                "occurrence_id": occ,
                "before": stored_entries[occ]["placement"],
                "current": current_entries[occ]["placement"]})
    return False, stale
