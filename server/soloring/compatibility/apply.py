"""M15C fenced apply (frozen R6 §14/§17.3) — the ONLY ordinary path
that mutates composition_working_occurrences.production_revision_id.
"""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from soloring.compatibility.canonical import (
    dimension_results_value,
    fold_verdict,
    operation_root,
    use_contract_value,
    verify_stored_assessment,
)
from soloring.compatibility.evaluator import (
    _batched_feature_contracts,
    _batched_subjects,
    _batched_track_contracts,
    _evaluate_use,
    _interpretation,
    _load_verified_revision,
)
from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.domain.ids import new_uuid
from soloring.errors import (
    ErrorCode,
    SoloRingError,
    internal_invariant,
    validation_error,
)

BLOCKED_CODE = ErrorCode.PRODUCTION_UPDATE_BLOCKED
CONFLICT_CODE = ErrorCode.PRODUCTION_COMPATIBILITY_CONFLICT


def _conflict(reason: str, **details) -> SoloRingError:
    return SoloRingError(
        CONFLICT_CODE,
        f"current compatibility coordinate conflict: {reason}",
        status_code=409,
        details={"reason": reason, **details})


def _blocked(reason: str, **details) -> SoloRingError:
    return SoloRingError(
        BLOCKED_CODE,
        f"the stored/recomputed domain verdict forbids apply: {reason}",
        status_code=409,
        details={"reason": reason, **details})


def _working_spec(row, revision_id: str) -> dict:
    return {
        "display_name": row.display_name,
        "source": {"kind": "production_revision",
                   "revision_id": revision_id},
        "visible": bool(row.visible),
        "translation_mm": [row.x_mm, row.y_mm, row.z_mm],
        "rotation_udeg": [row.yaw_udeg, row.pitch_udeg, row.roll_udeg],
    }


def _now_sql() -> str:
    from soloring.db.timeutil import DB_NOW_SQL

    return DB_NOW_SQL


async def _committed_operations(conn, assessment_id: str):
    return (await conn.execute(text(
        "SELECT id, operation_hash, operation_json FROM "
        "production_update_operations WHERE assessment_id = :a"),
        {"a": assessment_id})).fetchall()


def _find_committed(candidates, selected_uses, uses):
    """A committed operation matches an exact retry iff its items
    cover the exact selection coordinates, review decisions, and
    stored use hashes pinned at assessment time (frozen R6 §14.2
    basis: assessment id/hash + selected coordinates + expected use
    hashes + review decisions)."""
    # items of a committed operation for THIS assessment were built
    # from this assessment's stored uses, so coordinate+review
    # equality with matching cardinality is the exact-retry match
    want = {(s["composition_id"], s["occurrence_id"]):
            bool(s.get("review_accept")) for s in selected_uses}
    for cand in candidates:
        doc = json.loads(cand.operation_json)
        if len(doc["items"]) != len(want):
            continue
        got = {(i["composition_id"], i["occurrence_id"]):
               i["review_accepted"] for i in doc["items"]}
        if got == want:
            return cand
    return None


async def apply_revision_update(
        session: AsyncSession, *, assessment_id: str,
        selected_uses: list[dict]) -> dict:
    """Fenced selected-use apply (frozen R6 §14.1-§14.3)."""
    if not isinstance(selected_uses, list) or not selected_uses:
        raise validation_error("selected uses must be a non-empty list")
    async with session.bind.connect() as conn:
        await conn.exec_driver_sql("BEGIN IMMEDIATE")
        try:
            # 1. verify assessment identity + exact report hash
            verified = await verify_stored_assessment(conn, assessment_id)
            parent = dict(verified["parent"])
            parent["assessment_id"] = parent["id"]
            uses = {u["occurrence_id"]: u for u in verified["uses"]}
            # 2. exact revisions still exist and match
            src = await _load_verified_revision(
                conn, parent["from_revision_id"])
            tgt = await _load_verified_revision(
                conn, parent["to_revision_id"])
            if (src["snapshot_hash"] != parent["from_revision_hash"]
                    or tgt["snapshot_hash"] != parent["to_revision_hash"]):
                raise _conflict("target_changed_impossible")

            # 3. selection belongs to THIS assessment; 4. group keys
            selected_keys = []
            by_selection = {}
            for sel in selected_uses:
                key = (sel["composition_id"], sel["occurrence_id"])
                stored = uses.get(sel["occurrence_id"])
                if (stored is None
                        or stored["composition_id"] != sel["composition_id"]):
                    raise validation_error(
                        f"selected use {key} does not belong to "
                        f"assessment {assessment_id!r}")
                if key in by_selection:
                    raise validation_error(f"duplicate selected use {key}")
                selected_keys.append(key)
                by_selection[key] = (sel, stored)

            # 5. per-composition expected versions consistent
            expected_versions = {}
            for (cid, _), (sel, _) in by_selection.items():
                want = sel.get("expected_working_version")
                if want is not None and cid in expected_versions and (
                        expected_versions[cid] != want):
                    raise validation_error(
                        f"inconsistent expected working versions for "
                        f"composition {cid!r}")
                if want is not None:
                    expected_versions[cid] = want

            # frozen R6 §14.2 — idempotency probe BEFORE the fresh-path
            # state checks: a committed operation for the exact retry
            # basis is returned only after proving every selected
            # working row is on the recorded target revision.
            committed = _find_committed(
                await _committed_operations(conn, assessment_id),
                selected_uses, uses)
            if committed is not None:
                cdoc = json.loads(committed.operation_json)
                for sel in selected_uses:
                    row_source = (await conn.execute(text(
                        "SELECT production_revision_id FROM "
                        "composition_working_occurrences WHERE "
                        "composition_id = :c AND occurrence_id = :o"),
                        {"c": sel["composition_id"],
                         "o": sel["occurrence_id"]})).scalar_one()
                    if row_source != tgt["id"]:
                        raise _conflict(
                            "stale_working_version",
                            composition_id=sel["composition_id"],
                            occurrence_id=sel["occurrence_id"])
                await conn.commit()
                return _apply_result(
                    committed.id, committed.operation_hash,
                    [{"composition_id": i["composition_id"],
                      "occurrence_id": i["occurrence_id"],
                      "assessment_use_position": 0,
                      "working_version_before":
                          i["working_version_before"],
                      "working_version_after":
                          i["working_version_after"],
                      "verdict": i["verdict"],
                      "review_accepted": i["review_accepted"],
                      "translator_id": None,
                      "translator_version": None,
                      "translator_parameters_hash": None,
                      "translator_output_hash":
                          i["translator_output_hash"],
                      "before_spec_hash": i["before_spec_hash"],
                      "after_spec_hash": i["after_spec_hash"],
                      "from_revision_id": src["id"],
                      "to_revision_id": tgt["id"]}
                     for i in cdoc["items"]],
                    verified=verified, selected_keys=selected_keys,
                    idempotent=True)

            # 6-7. occurrences active, in working state, still on source
            marks = ", ".join(
                f"(:c{i}, :o{i})" for i in range(len(selected_keys)))
            params = {f"c{i}": c
                      for i, (c, _) in enumerate(selected_keys)}
            params.update({f"o{i}": o
                           for i, (_, o) in enumerate(selected_keys)})
            rows = (await conn.execute(text(
                f"SELECT w.composition_id, w.occurrence_id, "
                f"w.production_revision_id, w.display_name, w.visible, "
                f"w.x_mm, w.y_mm, w.z_mm, w.yaw_udeg, w.pitch_udeg, "
                f"w.roll_udeg FROM composition_working_occurrences w "
                f"WHERE (w.composition_id, w.occurrence_id) "
                f"IN (VALUES {marks}) "
                f"ORDER BY w.composition_id, w.occurrence_id"),
                params)).fetchall()
            working_rows = {(r.composition_id, r.occurrence_id): r
                            for r in rows}
            for key in selected_keys:
                row = working_rows.get(key)
                if row is None:
                    raise _conflict("occurrence_inactive",
                                    composition_id=key[0],
                                    occurrence_id=key[1])
                if row.production_revision_id != src["id"]:
                    raise _conflict("source_changed",
                                    composition_id=key[0],
                                    occurrence_id=key[1])
            comp_ids = sorted({cid for cid, _ in selected_keys})
            cmarks = ", ".join(f":c{i}" for i in range(len(comp_ids)))
            cparams = {f"c{i}": v for i, v in enumerate(comp_ids)}
            comps = {r.id: r for r in (await conn.execute(text(
                f"SELECT id, working_version FROM compositions "
                f"WHERE id IN ({cmarks})"), cparams)).fetchall()}

            # 8-10. rebuild contracts; exact hash + stored agreement
            sel_rows = [working_rows[k] for k in selected_keys]
            subjects = await _batched_subjects(
                conn, uses_rows=sel_rows, project_id=src["project_id"])
            features = await _batched_feature_contracts(conn, sel_rows)
            tracks, contexts = await _batched_track_contracts(
                conn, sel_rows, project_id=src["project_id"])
            src_interp = await _interpretation(conn, src["id"], src)
            tgt_interp = await _interpretation(conn, tgt["id"], tgt)

            from soloring.production_world.binding import _entry_is_identity
            from soloring.production_world.placement_consumer import (
                classify_placement_consumer_from_facts,
            )

            items = []
            for key in selected_keys:
                sel, stored = by_selection[key]
                row = working_rows[key]
                subject = subjects.get(key)
                subject_fact = None
                if subject is not None:
                    invalid = subject.get("invalid")
                    subject_fact = {
                        "kind": subject["kind"], "id": subject["id"],
                        "valid": not invalid,
                        "invalid_detail": {"reason": invalid}
                        if invalid else None}
                facts = {
                    "occurrence_id": key[1],
                    "subject": subject_fact,
                    "world_contexts": contexts.get(key, []),
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
                    raise _conflict(
                        "placement_consumer_ambiguous",
                        composition_id=key[0], occurrence_id=key[1],
                        issue=resolution["reason"])
                contract = {
                    "composition_id": key[0],
                    "occurrence_id": key[1],
                    "composition_working_version":
                        comps[key[0]].working_version,
                    "working_spec": _working_spec(row, src["id"]),
                    "authority_subject": subject,
                    "placement_contract":
                        resolution.get("placement_contract")
                        or {"owner": "A6_COMPOSITION"},
                    "active_instance_feature_contracts": features.get(
                        key, []),
                    "active_instance_spatial_tracks": tracks.get(key, []),
                    "source_revision": {
                        "id": src["id"],
                        "snapshot_hash": src["snapshot_hash"],
                        "blob_hash": src["blob_hash"],
                        "media_type": src["media_type"],
                        "spatial_interpretation_hash": src_interp[1]},
                    "target_revision": {
                        "id": tgt["id"],
                        "snapshot_hash": tgt["snapshot_hash"],
                        "blob_hash": tgt["blob_hash"],
                        "media_type": tgt["media_type"],
                        "spatial_interpretation_hash": tgt_interp[1]},
                }
                contract_value = use_contract_value(contract)
                contract_hash = canonical_hash(contract_value)
                if sel.get("expected_use_contract_hash") != contract_hash:
                    raise _conflict("stale_use_contract",
                                    composition_id=key[0],
                                    occurrence_id=key[1])
                if stored["use_contract_hash"] != contract_hash:
                    raise _conflict("stale_use_contract",
                                    composition_id=key[0],
                                    occurrence_id=key[1])
                evidence, translator = _evaluate_use(
                    src=src, tgt=tgt, contract_value=contract_value,
                    src_interp=src_interp, tgt_interp=tgt_interp)
                dimensions = dimension_results_value(evidence)
                verdict = fold_verdict(
                    {d: dimensions[d]["status"] for d in dimensions})
                stored_dims = json.loads(stored["dimension_results_json"])
                if verdict != stored["verdict"]:
                    raise internal_invariant(
                        f"recomputed verdict disagrees with stored use "
                        f"{key}")
                for d in dimensions:
                    if stored_dims[d]["status"] != dimensions[d]["status"]:
                        raise internal_invariant(
                            f"recomputed dimension disagrees with stored "
                            f"use {key}: {d}")

                # 11-13. per-use verdict law (parent summary never gates)
                if verdict == "INCOMPATIBLE":
                    raise _blocked("per_use_incompatible",
                                  composition_id=key[0],
                                  occurrence_id=key[1])
                if verdict == "REQUIRES_REVIEW" and not sel.get(
                        "review_accept"):
                    raise _blocked("review_required_without_acceptance",
                                  composition_id=key[0],
                                  occurrence_id=key[1])

                items.append({
                    "key": key,
                    "row": row,
                    "verdict": verdict,
                    "review_accept": bool(sel.get("review_accept")),
                    "translator": translator,
                    "before_spec": contract_value["working_spec"],
                    "after_spec": _working_spec(row, tgt["id"]),
                })

            # 14. exact before/after specs; 15-16. apply only the
            # source change with retained translator pins; 17. bump
            # each composition once; 18. persist the operation
            operation_id = new_uuid()
            position_by_key = {u["occurrence_id"]: u["position"]
                               for u in verified["uses"]}
            op_items = []
            for item in items:
                (cid, oid) = item["key"]
                op_items.append({
                    "composition_id": cid,
                    "occurrence_id": oid,
                    "assessment_use_position": position_by_key[oid],
                    "from_revision_id": src["id"],
                    "to_revision_id": tgt["id"],
                    "verdict": item["verdict"],
                    "review_accepted": item["review_accept"],
                    "translator_id": item["translator"]["translator_id"]
                    if item["translator"] else None,
                    "translator_version":
                        item["translator"]["translator_version"]
                    if item["translator"] else None,
                    "translator_parameters_hash":
                        item["translator"]["parameters_hash"]
                    if item["translator"] else None,
                    "translator_output_hash":
                        item["translator"]["output_hash"]
                    if item["translator"] else None,
                    "working_version_before": comps[cid].working_version,
                    "working_version_after":
                        comps[cid].working_version + 1,
                    "before_spec": item["before_spec"],
                    "after_spec": item["after_spec"],
                    "before_spec_hash": canonical_hash(
                        item["before_spec"]),
                    "after_spec_hash": canonical_hash(item["after_spec"]),
                })
            operation_value = {
                "assessment": {
                    "assessment_id": assessment_id,
                    "assessment_report_hash": parent["report_hash"],
                },
                "items": [{
                    "composition_id": i["composition_id"],
                    "occurrence_id": i["occurrence_id"],
                    "from_revision_id": i["from_revision_id"],
                    "to_revision_id": i["to_revision_id"],
                    "verdict": i["verdict"],
                    "review_accepted": i["review_accepted"],
                    "working_version_before": i["working_version_before"],
                    "working_version_after": i["working_version_after"],
                    "before_spec_hash": i["before_spec_hash"],
                    "after_spec_hash": i["after_spec_hash"],
                    "translator_output_hash": i["translator_output_hash"],
                } for i in op_items],
            }
            operation_hash = canonical_hash(operation_root(
                {"assessment_id": assessment_id,
                 "assessment_report_hash": parent["report_hash"]},
                op_items))

            created_at = (await conn.execute(text(
                f"SELECT {_now_sql()}"))).scalar_one()
            await conn.execute(text(
                "INSERT INTO production_update_operations "
                "(id, project_id, assessment_id, "
                "assessment_report_hash, schema_version, operation_json, "
                "operation_hash, created_at) VALUES "
                "(:id, :p, :a, :rh, 1, :oj, :oh, :n)"),
                {"id": operation_id, "p": src["project_id"],
                 "a": assessment_id, "rh": parent["report_hash"],
                 "oj": canonical_json_str(operation_value),
                 "oh": operation_hash, "n": created_at})
            for position, i in enumerate(op_items):
                await conn.execute(text(
                    "INSERT INTO production_update_items "
                    "(operation_id, position, assessment_id, "
                    "assessment_use_position, composition_id, "
                    "occurrence_id, from_revision_id, to_revision_id, "
                    "verdict, review_accepted, translator_id, "
                    "translator_version, translator_parameters_hash, "
                    "translator_output_hash, working_version_before, "
                    "working_version_after, before_spec_hash, "
                    "after_spec_hash) VALUES "
                    "(:op, :pos, :a, :apos, :c, :o, :f, :t, :v, :ra, "
                    ":ti, :tv, :tph, :toh, :wvb, :wva, :bsh, :ash)"),
                    {"op": operation_id, "pos": position,
                     "a": assessment_id,
                     "apos": i["assessment_use_position"],
                     "c": i["composition_id"],
                     "o": i["occurrence_id"],
                     "f": i["from_revision_id"],
                     "t": i["to_revision_id"],
                     "v": i["verdict"],
                     "ra": 1 if i["review_accepted"] else 0,
                     "ti": i["translator_id"],
                     "tv": i["translator_version"],
                     "tph": i["translator_parameters_hash"],
                     "toh": i["translator_output_hash"],
                     "wvb": i["working_version_before"],
                     "wva": i["working_version_after"],
                     "bsh": i["before_spec_hash"],
                     "ash": i["after_spec_hash"]})
            for item in items:
                (cid, oid) = item["key"]
                await conn.execute(text(
                    "UPDATE composition_working_occurrences "
                    "SET production_revision_id = :r "
                    "WHERE composition_id = :c AND occurrence_id = :o "
                    "AND production_revision_id = :old"),
                    {"r": tgt["id"], "c": cid, "o": oid,
                     "old": src["id"]})
            for cid in comp_ids:
                await conn.execute(text(
                    "UPDATE compositions SET working_version = "
                    "working_version + 1 WHERE id = :c AND "
                    "working_version = :wv"),
                    {"c": cid, "wv": comps[cid].working_version})
                row = (await conn.execute(text(
                    "SELECT working_version FROM compositions "
                    "WHERE id = :c"), {"c": cid})).scalar_one()
                if row != comps[cid].working_version + 1:
                    raise _conflict("stale_working_version",
                                    composition_id=cid)
            # 19. commit
            await conn.commit()
            return _apply_result(
                operation_id, operation_hash, op_items,
                verified=verified, selected_keys=selected_keys,
                idempotent=False)
        except Exception:
            await conn.rollback()
            raise


def _apply_result(operation_id, operation_hash, op_items, *,
                  verified, selected_keys, idempotent: bool) -> dict:
    selected_set = set(selected_keys)
    selected_comps = {c for c, _ in selected_keys}
    stale = []
    reassessment_required = False
    for u in verified["uses"]:
        key = (u["composition_id"], u["occurrence_id"])
        if key in selected_set:
            continue
        if u["composition_id"] in selected_comps:
            stale.append({"composition_id": u["composition_id"],
                          "occurrence_id": u["occurrence_id"],
                          "reason": "working_version_changed"})
            reassessment_required = True
    return {
        "operation_id": operation_id,
        "operation_hash": operation_hash,
        "updated_occurrences": [{
            "composition_id": i["composition_id"],
            "occurrence_id": i["occurrence_id"],
            "working_version_after": i["working_version_after"],
        } for i in op_items],
        "review_acknowledgements": [{
            "composition_id": i["composition_id"],
            "occurrence_id": i["occurrence_id"],
        } for i in op_items if i["review_accepted"]],
        "translator_pins": [{
            "composition_id": i["composition_id"],
            "occurrence_id": i["occurrence_id"],
            "translator_id": i["translator_id"],
            "translator_output_hash": i["translator_output_hash"],
        } for i in op_items if i["translator_id"]],
        "stale_remaining_uses": stale,
        "reassessment_required": reassessment_required,
        "idempotent": idempotent,
        "post_apply_next_actions": [
            "publish a new Composition Revision to make this change "
            "publishable",
            "derive/publish a new binding where applicable",
            "select the new binding for a current Shot when desired",
        ],
    }
