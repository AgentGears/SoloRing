"""M15 canonical compatibility grammars and stored-integrity checks
(frozen R4 §5/§12).

Every immutable JSON/hash pair is mechanically re-derived on read;
builders and validators are the same code. Vocabulary is closed and
mirrors tests/fixtures/m15/g4_contract.json exactly.
"""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.errors import internal_invariant

EVALUATOR_ID = "soloring.production_revision_compatibility"
EVALUATOR_VERSION = 1
CONSUMER_KIND = "composition_working_occurrence/v1"

VERDICTS = (
    "COMPATIBLE_AS_IS",
    "COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION",
    "REQUIRES_REVIEW",
    "INCOMPATIBLE",
)
DIMENSION_STATUSES = (
    "SATISFIED",
    "TRANSLATION_REQUIRED",
    "REVIEW_REQUIRED",
    "BLOCKED",
    "NOT_APPLICABLE",
)
DIMENSIONS = (
    "production_lineage",
    "retained_consumption",
    "media_type",
    "spatial_interpretation",
    "persistent_state_subject_identity",
)
# §5.1/§5.4 severity precedence, most severe first
_PRECEDENCE = (
    "INCOMPATIBLE",
    "REQUIRES_REVIEW",
    "COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION",
    "COMPATIBLE_AS_IS",
)


def fold_verdict(statuses: dict[str, str]) -> str:
    """§5.2 mapping from per-dimension statuses to the four-verdict."""
    values = list(statuses.values())
    for status in values:
        if status not in DIMENSION_STATUSES:
            raise internal_invariant(
                f"unknown dimension status {status!r}")
    if any(s == "BLOCKED" for s in values):
        return "INCOMPATIBLE"
    if any(s == "REVIEW_REQUIRED" for s in values):
        return "REQUIRES_REVIEW"
    if any(s == "TRANSLATION_REQUIRED" for s in values):
        return "COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION"
    return "COMPATIBLE_AS_IS"


def fold_summary(verdicts: list[str]) -> str:
    """§5.4 ordered summary fold — diagnostic only, never an apply gate."""
    for verdict in verdicts:
        if verdict not in VERDICTS:
            raise internal_invariant(f"unknown verdict {verdict!r}")
    rank = {v: i for i, v in enumerate(_PRECEDENCE)}
    return min(verdicts, key=lambda v: rank[v])


def use_contract_value(contract: dict) -> dict:
    """Canonical use-contract root (§8) — exact key set, closed vocab."""
    placement = contract["placement_contract"]
    if placement["owner"] == "A6_COMPOSITION":
        placement_out = {"owner": "A6_COMPOSITION"}
    elif placement["owner"] == "A4_SPATIAL":
        placement_out = {
            "owner": "A4_SPATIAL",
            "spatial_world_id": placement["spatial_world_id"],
            "spatial_world_revision_id":
                placement["spatial_world_revision_id"],
            "spatial_world_revision_hash":
                placement["spatial_world_revision_hash"],
            "target_kind": placement["target_kind"],
            "target_id": placement["target_id"],
        }
    else:
        raise internal_invariant(
            f"unknown placement owner {placement['owner']!r}")
    return {
        "consumer_kind": CONSUMER_KIND,
        "composition_id": contract["composition_id"],
        "occurrence_id": contract["occurrence_id"],
        "composition_working_version":
            contract["composition_working_version"],
        "working_spec": contract["working_spec"],
        "authority_subject": contract["authority_subject"],
        "placement_contract": placement_out,
        "active_instance_feature_contracts":
            contract["active_instance_feature_contracts"],
        "active_instance_spatial_tracks":
            contract["active_instance_spatial_tracks"],
        "source_revision": contract["source_revision"],
        "target_revision": contract["target_revision"],
    }


def use_contract_hash(value: dict) -> str:
    return canonical_hash(use_contract_value(value))


def dimension_results_value(evidence: dict) -> dict:
    """Canonical per-dimension results root — status per dimension plus
    the dimension's recorded evidence; every status is closed."""
    out: dict = {}
    for dimension in DIMENSIONS:
        entry = evidence[dimension]
        if entry["status"] not in DIMENSION_STATUSES:
            raise internal_invariant(
                f"{dimension}: unknown status {entry['status']!r}")
        out[dimension] = {"status": entry["status"],
                          "evidence": entry.get("evidence")}
    return out


def scope_root(uses: list[dict]) -> list[dict]:
    """§12.1 scope root — ordered (composition, occurrence, hash)."""
    return [
        {"composition_id": u["composition_id"],
         "occurrence_id": u["occurrence_id"],
         "use_contract_hash": u["use_contract_hash"]}
        for u in uses
    ]


def report_root(identity: dict, uses: list[dict], summary: str) -> dict:
    """§12.1 report root — identity + ordered per-use hashes + summary."""
    return {
        "source_revision": {
            "id": identity["from_revision_id"],
            "snapshot_hash": identity["from_revision_hash"]},
        "target_revision": {
            "id": identity["to_revision_id"],
            "snapshot_hash": identity["to_revision_hash"]},
        "evaluator": {"id": EVALUATOR_ID, "version": EVALUATOR_VERSION},
        "uses": [
            {"composition_id": u["composition_id"],
             "occurrence_id": u["occurrence_id"],
             "verdict": u["verdict"],
             "dimension_results_hash": u["dimension_results_hash"],
             "use_contract_hash": u["use_contract_hash"],
             "translator_output_hash": u.get("translator_output_hash")}
            for u in uses
        ],
        "summary_verdict": summary,
    }


def operation_root(identity: dict, items: list[dict]) -> dict:
    """§12.2 operation root — pinned assessment identity + ordered items
    with frozen before/after snapshots."""
    return {
        "assessment": {
            "assessment_id": identity["assessment_id"],
            "report_hash": identity["assessment_report_hash"]},
        "items": [
            {"composition_id": i["composition_id"],
             "occurrence_id": i["occurrence_id"],
             "from_revision_id": i["from_revision_id"],
             "to_revision_id": i["to_revision_id"],
             "verdict": i["verdict"],
             "review_accepted": bool(i["review_accepted"]),
             "working_version_before": i["working_version_before"],
             "working_version_after": i["working_version_after"],
             "before_spec_hash": i["before_spec_hash"],
             "after_spec_hash": i["after_spec_hash"],
             "translator_output_hash": i.get("translator_output_hash")}
            for i in items
        ],
    }


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise internal_invariant(f"stored assessment corrupt: {message}")


async def verify_stored_assessment(
        conn: AsyncConnection, assessment_id: str) -> dict:
    """§12.1/§12.3 — re-derive every hash from normalized rows.

    Returns the verified parent + ordered uses; any disagreement is
    invariant failure, never a friendly verdict."""
    row = (await conn.execute(text(
        "SELECT id, project_id, production_object_id, from_revision_id, "
        "from_revision_hash, to_revision_id, to_revision_hash, "
        "schema_version, evaluator_id, evaluator_version, scope_json, "
        "scope_hash, report_json, report_hash, overall_verdict, "
        "created_at "
        "FROM production_compatibility_assessments WHERE id = :a"),
        {"a": assessment_id})).one_or_none()
    _check(row is not None, f"assessment {assessment_id!r} missing")
    uses = (await conn.execute(text(
        "SELECT position, composition_id, occurrence_id, "
        "composition_working_version, use_contract_json, "
        "use_contract_hash, dimension_results_json, "
        "dimension_results_hash, verdict, translator_id, "
        "translator_version, translator_parameters_json, "
        "translator_parameters_hash, translator_output_hash "
        "FROM production_compatibility_uses "
        "WHERE assessment_id = :a ORDER BY position"),
        {"a": assessment_id})).fetchall()
    _check(bool(uses), "zero children")
    _check([u.position for u in uses] == list(range(len(uses))),
           "positions not dense/ordered")
    _check(row.schema_version == 1 and row.evaluator_id == EVALUATOR_ID
           and row.evaluator_version == EVALUATOR_VERSION,
           "evaluator identity mismatch")

    root = scope_root([
        {"composition_id": u.composition_id,
         "occurrence_id": u.occurrence_id,
         "use_contract_hash": u.use_contract_hash} for u in uses])
    _check(canonical_hash(root) == row.scope_hash, "scope_hash mismatch")
    _check(row.scope_json == canonical_json_str(root),
           "scope_json not canonical")

    verdicts = []
    for u in uses:
        dimensions = json.loads(u.dimension_results_json)
        _check(u.dimension_results_json ==
               canonical_json_str(dimensions),
               f"use {u.position}: dimension json not canonical")
        _check(canonical_hash(dimensions) == u.dimension_results_hash,
               f"use {u.position}: dimension_results_hash mismatch")
        folded = fold_verdict(
            {d: dimensions[d]["status"] for d in DIMENSIONS})
        _check(folded == u.verdict,
               f"use {u.position}: verdict {u.verdict!r} disagrees with "
               f"folded {folded!r}")
        contract = json.loads(u.use_contract_json)
        _check(u.use_contract_json == canonical_json_str(contract),
               f"use {u.position}: use-contract json not canonical")
        _check(canonical_hash(contract) == u.use_contract_hash,
               f"use {u.position}: use_contract_hash mismatch")
        needs_translator = (
            dimensions["spatial_interpretation"]["status"]
            == "TRANSLATION_REQUIRED")
        has_translator = u.translator_id is not None
        _check(needs_translator == has_translator,
               f"use {u.position}: translator-field invariant violated")
        if needs_translator:
            params = json.loads(u.translator_parameters_json)
            _check(canonical_hash(params) ==
                   u.translator_parameters_hash,
                   f"use {u.position}: translator parameters hash mismatch")
        verdicts.append(u.verdict)

    summary = fold_summary(verdicts)
    _check(summary == row.overall_verdict,
           f"overall_verdict {row.overall_verdict!r} disagrees with "
           f"folded {summary!r}")
    rep = report_root(
        {"from_revision_id": row.from_revision_id,
         "from_revision_hash": row.from_revision_hash,
         "to_revision_id": row.to_revision_id,
         "to_revision_hash": row.to_revision_hash},
        [{"composition_id": u.composition_id,
          "occurrence_id": u.occurrence_id,
          "verdict": u.verdict,
          "dimension_results_hash": u.dimension_results_hash,
          "use_contract_hash": u.use_contract_hash,
          "translator_output_hash": u.translator_output_hash}
         for u in uses],
        summary)
    _check(canonical_hash(rep) == row.report_hash, "report_hash mismatch")
    _check(row.report_json == canonical_json_str(rep),
           "report_json not canonical")

    return {"parent": row._mapping, "uses": [u._mapping for u in uses]}
