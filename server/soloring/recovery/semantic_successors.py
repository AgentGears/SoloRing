"""M16-P0 successor semantic verification for recovery heads 0015/0016.

The M10F recovery engine already proves structural DB integrity, exact Blob
liveness and the M11-M13 semantic layers.  M14 and M15 added durable
historical rows without extending that semantic succession.  This module
closes that predecessor hole without inventing a second recovery system:
it verifies the immutable M14 observation and M15 compatibility contracts
immediately before the existing liveness enumeration on a coherent staged
DB.

The verifier is deliberately database-only.  Physical Blob bytes remain the
existing recovery layer's responsibility; this layer proves that durable
rows, canonical JSON/hash pairs, normalized projections and predecessor
identities agree before those bytes can be certified.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import ModuleType
from typing import Any

from soloring.domain.canonical import canonical_hash, canonical_json_str


_HEX = frozenset("0123456789abcdef")
_M15_TABLES = frozenset({
    "production_compatibility_assessments",
    "production_compatibility_uses",
    "composition_occurrence_revision_tracking",
    "production_update_operations",
    "production_update_items",
})


def _corrupt(message: str):
    # Lazy import avoids a backup.py <-> semantic_successors import cycle.
    from soloring.recovery.backup import RecoveryCorruption

    return RecoveryCorruption(message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise _corrupt(message)


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HEX


def _json_value(raw: object, what: str) -> Any:
    if not isinstance(raw, str):
        raise _corrupt(f"{what} is not stored JSON text.")
    try:
        return json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise _corrupt(f"{what} is not valid JSON: {exc}") from exc


def _canonical_pair(raw: object, digest: object, what: str) -> Any:
    value = _json_value(raw, what)
    if canonical_json_str(value) != raw:
        raise _corrupt(f"{what} is not canonical JSON.")
    if not _is_hash(digest) or canonical_hash(value) != digest:
        raise _corrupt(f"{what} hash mismatch.")
    return value


def _tables(con: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _require_tables(con: sqlite3.Connection, names: set[str] | frozenset[str],
                    layer: str) -> None:
    missing = set(names) - _tables(con)
    if missing:
        raise _corrupt(
            f"{layer} semantic verification is missing table(s) "
            f"{sorted(missing)}."
        )


def _row_exists(con: sqlite3.Connection, table: str, where: str,
                params: tuple) -> bool:
    return con.execute(
        f"SELECT 1 FROM {table} WHERE {where} LIMIT 1", params
    ).fetchone() is not None


# ---------------------------------------------------------------------------
# M14 — immutable retained observation execution evidence
# ---------------------------------------------------------------------------


def verify_m14_observation_state(staged_db: Path) -> None:
    """Verify every M14 retained observation artifact and Generation binding.

    This is the synchronous recovery analogue of the production retained
    artifact reader: canonical parameter/provenance bytes and hashes,
    materializer identity, source-retained closure, execution-package pins,
    Project/Blob existence and normalized Generation binding equality are all
    proven from the staged historical graph only.
    """
    from soloring.observation.retained import (
        MATERIALIZER_CONTRACT_HASH,
        MATERIALIZER_ID,
        MATERIALIZER_VERSION,
        input_key_for_role,
    )

    con = sqlite3.connect(str(staged_db))
    con.row_factory = sqlite3.Row
    try:
        _require_tables(
            con,
            {"derived_observation_artifacts",
             "generation_derived_observation_inputs"},
            "M14",
        )
        tables = _tables(con)
        artifacts: dict[str, sqlite3.Row] = {}
        rows = con.execute(
            "SELECT id, project_id, observation_spec_hash, artifact_role, "
            "materializer_id, materializer_version, "
            "materializer_contract_hash, parameters_json, parameters_hash, "
            "provenance_json, provenance_hash, blob_hash "
            "FROM derived_observation_artifacts ORDER BY id"
        ).fetchall()
        for row in rows:
            aid = row["id"]
            _require(_is_hash(row["observation_spec_hash"]),
                     f"M14 artifact {aid}: observation_spec_hash invalid.")
            _require(_is_hash(row["blob_hash"]),
                     f"M14 artifact {aid}: blob_hash invalid.")
            try:
                expected_input_key = input_key_for_role(row["artifact_role"])
            except Exception as exc:
                raise _corrupt(
                    f"M14 artifact {aid}: artifact_role violates the frozen "
                    f"grammar: {exc}"
                ) from exc

            parameters = _canonical_pair(
                row["parameters_json"], row["parameters_hash"],
                f"M14 artifact {aid} parameters_json",
            )
            _require(isinstance(parameters, dict),
                     f"M14 artifact {aid}: parameters root is not an object.")
            provenance = _canonical_pair(
                row["provenance_json"], row["provenance_hash"],
                f"M14 artifact {aid} provenance_json",
            )
            _require(isinstance(provenance, dict),
                     f"M14 artifact {aid}: provenance root is not an object.")
            _require(provenance.get("schema_version") == 1,
                     f"M14 artifact {aid}: provenance schema_version != 1.")

            _require(row["materializer_id"] == MATERIALIZER_ID,
                     f"M14 artifact {aid}: materializer_id mismatch.")
            _require(row["materializer_version"] == MATERIALIZER_VERSION,
                     f"M14 artifact {aid}: materializer_version mismatch.")
            _require(row["materializer_contract_hash"] ==
                     MATERIALIZER_CONTRACT_HASH,
                     f"M14 artifact {aid}: materializer_contract_hash mismatch.")

            pinned = {
                "project_id": row["project_id"],
                "observation_spec_hash": row["observation_spec_hash"],
                "artifact_role": row["artifact_role"],
                "materializer_id": row["materializer_id"],
                "materializer_version": row["materializer_version"],
                "materializer_contract_hash": row["materializer_contract_hash"],
                "parameters_hash": row["parameters_hash"],
            }
            for key, expected in pinned.items():
                _require(provenance.get(key) == expected,
                         f"M14 artifact {aid}: provenance {key} mismatch.")

            source_hashes = provenance.get("source_retained_blob_hashes")
            _require(isinstance(source_hashes, list),
                     f"M14 artifact {aid}: source_retained_blob_hashes is "
                     "not an array.")
            _require(len(source_hashes) == len(set(source_hashes)),
                     f"M14 artifact {aid}: duplicate source retained Blob.")
            for source_hash in source_hashes:
                _require(_is_hash(source_hash),
                         f"M14 artifact {aid}: invalid source retained Blob hash.")
                if "blobs" in tables:
                    _require(_row_exists(con, "blobs", "hash = ?", (source_hash,)),
                             f"M14 artifact {aid}: source retained Blob "
                             f"{source_hash} is missing.")

            execution = provenance.get("execution_package")
            expected_execution_keys = {
                "manifest_hash", "workflow_template_hash",
                "realization_profile_hash",
                "execution_model_fingerprint_hash",
            }
            _require(isinstance(execution, dict) and
                     set(execution) == expected_execution_keys,
                     f"M14 artifact {aid}: execution_package grammar mismatch.")
            for key in expected_execution_keys:
                _require(_is_hash(execution[key]),
                         f"M14 artifact {aid}: execution_package.{key} invalid.")

            if "projects" in tables:
                _require(_row_exists(con, "projects", "id = ?",
                                     (row["project_id"],)),
                         f"M14 artifact {aid}: owning Project is missing.")
            if "blobs" in tables:
                _require(_row_exists(con, "blobs", "hash = ?",
                                     (row["blob_hash"],)),
                         f"M14 artifact {aid}: retained Blob is missing.")

            artifacts[aid] = row
            # Retain the exact expected input key for the child check without
            # mutating the immutable row object.
            artifacts[f"{aid}:input_key"] = expected_input_key  # type: ignore[assignment]

        bindings = con.execute(
            "SELECT generation_id, input_key, position, artifact_role, "
            "derived_observation_artifact_id, blob_hash "
            "FROM generation_derived_observation_inputs "
            "ORDER BY generation_id, input_key, position"
        ).fetchall()
        for binding in bindings:
            aid = binding["derived_observation_artifact_id"]
            artifact = artifacts.get(aid)
            _require(isinstance(artifact, sqlite3.Row),
                     f"M14 Generation binding references missing artifact {aid}.")
            _require(binding["blob_hash"] == artifact["blob_hash"],
                     f"M14 Generation binding {aid}: blob_hash mismatch.")
            _require(binding["artifact_role"] == artifact["artifact_role"],
                     f"M14 Generation binding {aid}: artifact_role mismatch.")
            _require(binding["input_key"] == artifacts[f"{aid}:input_key"],
                     f"M14 Generation binding {aid}: input_key mismatch.")
            _require(isinstance(binding["position"], int) and
                     not isinstance(binding["position"], bool) and
                     binding["position"] >= 0,
                     f"M14 Generation binding {aid}: invalid position.")
            if "generations" in tables:
                _require(_row_exists(con, "generations", "id = ?",
                                     (binding["generation_id"],)),
                         f"M14 Generation binding {aid}: Generation is missing.")
    finally:
        con.close()


# ---------------------------------------------------------------------------
# M15 — immutable compatibility/update evidence
# ---------------------------------------------------------------------------


def _fold_verdict(statuses: dict[str, str]) -> str:
    if any(value == "BLOCKED" for value in statuses.values()):
        return "INCOMPATIBLE"
    if any(value == "REVIEW_REQUIRED" for value in statuses.values()):
        return "REQUIRES_REVIEW"
    if any(value == "TRANSLATION_REQUIRED" for value in statuses.values()):
        return "COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION"
    return "COMPATIBLE_AS_IS"


def _fold_summary(verdicts: list[str]) -> str:
    precedence = {
        "INCOMPATIBLE": 0,
        "REQUIRES_REVIEW": 1,
        "COMPATIBLE_VIA_DETERMINISTIC_TRANSLATION": 2,
        "COMPATIBLE_AS_IS": 3,
    }
    return min(verdicts, key=lambda value: precedence[value])


def verify_m16_intra_shot_state(staged_db: Path) -> None:
    """Full M16-depth recovery verification for head 0017 (frozen R6
    §16.2). Companion-row-only reconstruction shared with the historical
    inspector; read-only — no proposal/review product operation is
    performed, only canonical integrity of whatever rows exist."""
    import sqlite3

    from soloring.continuity.intra_shot_canonical import (
        MAX_PROPOSAL_CANONICAL_BYTES,
    )
    from soloring.continuity.intra_shot_history import (
        verify_intra_shot_history_sync,
        verify_working_event_row,
    )
    from soloring.domain.canonical import canonical_hash, canonical_json_str

    con = sqlite3.connect(str(staged_db))
    try:
        def rows(query, params=()):
            return con.execute(query, params).fetchall()

        for row in rows(
                "SELECT id, shot_id, time_ms, ordinal, target_kind, "
                "entity_feature_id, entity_relation_id, "
                "production_instance_feature_id, before_state_json, "
                "before_state_hash, after_state_json, after_state_hash, "
                "persistence_mode, source_kind, source_proposal_id, "
                "event_json, event_hash FROM shot_intra_shot_events "
                "WHERE deleted_at IS NULL"):
            verify_working_event_row(_Row(row, WORKING_EVENT_COLUMNS))
            if row[13] == "proposal_adoption" and row[14] is None:
                _corrupt(
                    f"working event {row[0]} claims proposal_adoption "
                    "without a source proposal")

        for rev_id, in rows(
                "SELECT DISTINCT shot_revision_id FROM "
                "shot_revision_intra_shot_events"):
            snapshot = rows(
                "SELECT snapshot_json FROM shot_revisions WHERE id = :r",
                {"r": rev_id})
            if not snapshot:
                _corrupt(
                    f"intra_shot companions reference missing "
                    f"ShotRevision {rev_id}")
            import json as _json

            verify_intra_shot_history_sync(
                con, rev_id, snapshot=_json.loads(snapshot[0][0]))

        for row in rows(
                "SELECT id, proposal_json, proposal_hash FROM "
                "shot_intra_shot_event_proposals"):
            doc = _json_loads(row[1])
            if canonical_json_str(doc) != row[1] or                     canonical_hash(doc) != row[2]:
                _corrupt(f"proposal {row[0]} is not canonical")
            if len(row[1].encode("utf-8")) > MAX_PROPOSAL_CANONICAL_BYTES:
                _corrupt(f"proposal {row[0]} exceeds the frozen byte cap")

        for row in rows(
                "SELECT id, operation_json, operation_hash FROM "
                "persistent_consequence_reviews"):
            doc = _json_loads(row[1])
            if canonical_json_str(doc) != row[1] or                     canonical_hash(doc) != row[2]:
                _corrupt(f"review {row[0]} is not canonical")
    finally:
        con.close()


WORKING_EVENT_COLUMNS = (
    "id", "shot_id", "time_ms", "ordinal", "target_kind",
    "entity_feature_id", "entity_relation_id",
    "production_instance_feature_id", "before_state_json",
    "before_state_hash", "after_state_json", "after_state_hash",
    "persistence_mode", "source_kind", "source_proposal_id",
    "event_json", "event_hash",
)


class _Row:
    def __init__(self, values, columns):
        self._map = dict(zip(columns, values))

    def __getattr__(self, name):
        return self._map[name]


def _json_loads(raw: str):
    import json

    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        _corrupt("stored M16 canonical JSON is malformed")


def verify_m15_compatibility_state(staged_db: Path) -> None:
    """Verify all immutable M15 assessment/use/update evidence at head 0016."""
    from soloring.compatibility.canonical import (
        CONSUMER_KIND,
        DIMENSIONS,
        DIMENSION_STATUSES,
        EVALUATOR_ID,
        EVALUATOR_VERSION,
        VERDICTS,
        operation_root,
        report_root,
        scope_root,
        use_contract_value,
    )

    con = sqlite3.connect(str(staged_db))
    con.row_factory = sqlite3.Row
    try:
        _require_tables(con, _M15_TABLES, "M15")
        tables = _tables(con)
        assessment_rows = con.execute(
            "SELECT id, project_id, production_object_id, from_revision_id, "
            "from_revision_hash, to_revision_id, to_revision_hash, "
            "schema_version, evaluator_id, evaluator_version, scope_json, "
            "scope_hash, report_json, report_hash, overall_verdict "
            "FROM production_compatibility_assessments ORDER BY id"
        ).fetchall()
        assessments: dict[str, tuple[sqlite3.Row, list[sqlite3.Row]]] = {}

        for row in assessment_rows:
            aid = row["id"]
            _require(row["schema_version"] == 1 and
                     row["evaluator_id"] == EVALUATOR_ID and
                     row["evaluator_version"] == EVALUATOR_VERSION,
                     f"M15 assessment {aid}: evaluator identity mismatch.")
            _require(_is_hash(row["from_revision_hash"]) and
                     _is_hash(row["to_revision_hash"]),
                     f"M15 assessment {aid}: revision hash invalid.")
            _require(row["overall_verdict"] in VERDICTS,
                     f"M15 assessment {aid}: overall_verdict invalid.")

            if "projects" in tables:
                _require(_row_exists(con, "projects", "id = ?", (row["project_id"],)),
                         f"M15 assessment {aid}: Project missing.")
            if "production_objects" in tables:
                obj = con.execute(
                    "SELECT project_id FROM production_objects WHERE id = ?",
                    (row["production_object_id"],),
                ).fetchone()
                _require(obj is not None and obj[0] == row["project_id"],
                         f"M15 assessment {aid}: Production Object/Project mismatch.")
            if "production_revisions" in tables:
                for column, hash_column in (
                    ("from_revision_id", "from_revision_hash"),
                    ("to_revision_id", "to_revision_hash"),
                ):
                    revision = con.execute(
                        "SELECT production_object_id, snapshot_hash FROM "
                        "production_revisions WHERE id = ?", (row[column],),
                    ).fetchone()
                    _require(revision is not None,
                             f"M15 assessment {aid}: {column} missing.")
                    _require(revision[0] == row["production_object_id"] and
                             revision[1] == row[hash_column],
                             f"M15 assessment {aid}: {column} identity mismatch.")

            uses = con.execute(
                "SELECT position, composition_id, occurrence_id, "
                "composition_working_version, use_contract_json, "
                "use_contract_hash, dimension_results_json, "
                "dimension_results_hash, verdict, translator_id, "
                "translator_version, translator_parameters_json, "
                "translator_parameters_hash, translator_output_hash "
                "FROM production_compatibility_uses WHERE assessment_id = ? "
                "ORDER BY position",
                (aid,),
            ).fetchall()
            _require(bool(uses), f"M15 assessment {aid}: zero use rows.")
            _require([u["position"] for u in uses] == list(range(len(uses))),
                     f"M15 assessment {aid}: use positions are not dense.")

            normalized_uses: list[dict] = []
            verdicts: list[str] = []
            for use in uses:
                pos = use["position"]
                dimensions = _canonical_pair(
                    use["dimension_results_json"], use["dimension_results_hash"],
                    f"M15 assessment {aid} use {pos} dimension_results_json",
                )
                _require(isinstance(dimensions, dict) and
                         set(dimensions) == set(DIMENSIONS),
                         f"M15 assessment {aid} use {pos}: dimension grammar "
                         "mismatch.")
                statuses: dict[str, str] = {}
                for dimension in DIMENSIONS:
                    entry = dimensions.get(dimension)
                    _require(isinstance(entry, dict) and
                             set(entry) == {"status", "evidence"},
                             f"M15 assessment {aid} use {pos}: {dimension} "
                             "entry grammar mismatch.")
                    _require(entry["status"] in DIMENSION_STATUSES,
                             f"M15 assessment {aid} use {pos}: {dimension} "
                             "status invalid.")
                    statuses[dimension] = entry["status"]
                verdict = _fold_verdict(statuses)
                _require(use["verdict"] == verdict and verdict in VERDICTS,
                         f"M15 assessment {aid} use {pos}: verdict mismatch.")

                contract = _canonical_pair(
                    use["use_contract_json"], use["use_contract_hash"],
                    f"M15 assessment {aid} use {pos} use_contract_json",
                )
                _require(isinstance(contract, dict),
                         f"M15 assessment {aid} use {pos}: use contract root "
                         "is not an object.")
                try:
                    normalized_contract = use_contract_value(contract)
                except Exception as exc:
                    raise _corrupt(
                        f"M15 assessment {aid} use {pos}: use contract grammar "
                        f"invalid: {exc}"
                    ) from exc
                _require(normalized_contract == contract and
                         contract.get("consumer_kind") == CONSUMER_KIND,
                         f"M15 assessment {aid} use {pos}: use contract is not "
                         "the frozen canonical root.")
                _require(contract["composition_id"] == use["composition_id"] and
                         contract["occurrence_id"] == use["occurrence_id"] and
                         contract["composition_working_version"] ==
                         use["composition_working_version"],
                         f"M15 assessment {aid} use {pos}: use coordinate mismatch.")
                _require(contract["source_revision"].get("id") ==
                         row["from_revision_id"] and
                         contract["target_revision"].get("id") ==
                         row["to_revision_id"],
                         f"M15 assessment {aid} use {pos}: revision coordinate "
                         "mismatch.")

                needs_translator = (
                    statuses["spatial_interpretation"] == "TRANSLATION_REQUIRED"
                )
                has_translator = use["translator_id"] is not None
                _require(needs_translator == has_translator,
                         f"M15 assessment {aid} use {pos}: translator invariant "
                         "violated.")
                if needs_translator:
                    _require(isinstance(use["translator_version"], int) and
                             not isinstance(use["translator_version"], bool),
                             f"M15 assessment {aid} use {pos}: translator_version "
                             "invalid.")
                    params = _canonical_pair(
                        use["translator_parameters_json"],
                        use["translator_parameters_hash"],
                        f"M15 assessment {aid} use {pos} translator_parameters_json",
                    )
                    _require(isinstance(params, dict),
                             f"M15 assessment {aid} use {pos}: translator "
                             "parameters root is not an object.")
                    _require(_is_hash(use["translator_output_hash"]),
                             f"M15 assessment {aid} use {pos}: translator output "
                             "hash invalid.")
                else:
                    _require(all(use[name] is None for name in (
                        "translator_id", "translator_version",
                        "translator_parameters_json", "translator_parameters_hash",
                        "translator_output_hash",
                    )), f"M15 assessment {aid} use {pos}: translator fields "
                        "present without translation requirement.")

                normalized_uses.append({
                    "composition_id": use["composition_id"],
                    "occurrence_id": use["occurrence_id"],
                    "use_contract_hash": use["use_contract_hash"],
                    "dimension_results_hash": use["dimension_results_hash"],
                    "verdict": use["verdict"],
                    "translator_output_hash": use["translator_output_hash"],
                })
                verdicts.append(verdict)

            scope = scope_root(normalized_uses)
            _require(canonical_json_str(scope) == row["scope_json"] and
                     canonical_hash(scope) == row["scope_hash"],
                     f"M15 assessment {aid}: scope_json/scope_hash mismatch.")
            summary = _fold_summary(verdicts)
            _require(summary == row["overall_verdict"],
                     f"M15 assessment {aid}: overall verdict fold mismatch.")
            report = report_root(
                {
                    "from_revision_id": row["from_revision_id"],
                    "from_revision_hash": row["from_revision_hash"],
                    "to_revision_id": row["to_revision_id"],
                    "to_revision_hash": row["to_revision_hash"],
                },
                normalized_uses,
                summary,
            )
            _require(canonical_json_str(report) == row["report_json"] and
                     canonical_hash(report) == row["report_hash"],
                     f"M15 assessment {aid}: report_json/report_hash mismatch.")
            assessments[aid] = (row, uses)

        tracking = con.execute(
            "SELECT composition_id, occurrence_id, mode, policy_version FROM "
            "composition_occurrence_revision_tracking ORDER BY composition_id, "
            "occurrence_id"
        ).fetchall()
        for row in tracking:
            _require(row["mode"] in ("PINNED", "TRACK_COMPATIBLE") and
                     isinstance(row["policy_version"], int) and
                     row["policy_version"] >= 1,
                     "M15 occurrence tracking row violates mode/policy grammar.")
            if "composition_occurrences" in tables:
                _require(_row_exists(
                    con, "composition_occurrences",
                    "id = ? AND composition_id = ?",
                    (row["occurrence_id"], row["composition_id"]),
                ), "M15 occurrence tracking row references a missing occurrence.")

        operations = con.execute(
            "SELECT id, project_id, assessment_id, assessment_report_hash, "
            "schema_version, operation_json, operation_hash FROM "
            "production_update_operations ORDER BY id"
        ).fetchall()
        for operation in operations:
            oid = operation["id"]
            _require(operation["schema_version"] == 1,
                     f"M15 update operation {oid}: schema_version != 1.")
            parent_pair = assessments.get(operation["assessment_id"])
            _require(parent_pair is not None,
                     f"M15 update operation {oid}: assessment missing.")
            parent = parent_pair[0]
            _require(operation["project_id"] == parent["project_id"] and
                     operation["assessment_report_hash"] == parent["report_hash"],
                     f"M15 update operation {oid}: assessment identity mismatch.")

            items = con.execute(
                "SELECT position, assessment_id, assessment_use_position, "
                "composition_id, occurrence_id, from_revision_id, "
                "to_revision_id, verdict, review_accepted, translator_id, "
                "translator_version, translator_parameters_hash, "
                "translator_output_hash, working_version_before, "
                "working_version_after, before_spec_hash, after_spec_hash "
                "FROM production_update_items WHERE operation_id = ? "
                "ORDER BY position", (oid,),
            ).fetchall()
            _require(bool(items), f"M15 update operation {oid}: zero items.")
            _require([item["position"] for item in items] ==
                     list(range(len(items))),
                     f"M15 update operation {oid}: item positions are not dense.")
            normalized_items: list[dict] = []
            uses_by_position = {u["position"]: u for u in parent_pair[1]}
            for item in items:
                pos = item["position"]
                use = uses_by_position.get(item["assessment_use_position"])
                _require(item["assessment_id"] == operation["assessment_id"] and
                         use is not None,
                         f"M15 update operation {oid} item {pos}: assessment/use "
                         "identity mismatch.")
                _require(item["composition_id"] == use["composition_id"] and
                         item["occurrence_id"] == use["occurrence_id"],
                         f"M15 update operation {oid} item {pos}: use coordinate "
                         "mismatch.")
                _require(item["from_revision_id"] == parent["from_revision_id"] and
                         item["to_revision_id"] == parent["to_revision_id"] and
                         item["verdict"] == use["verdict"],
                         f"M15 update operation {oid} item {pos}: revision/verdict "
                         "mismatch.")
                _require(item["review_accepted"] in (0, 1),
                         f"M15 update operation {oid} item {pos}: review flag "
                         "invalid.")
                _require(isinstance(item["working_version_before"], int) and
                         isinstance(item["working_version_after"], int) and
                         item["working_version_after"] ==
                         item["working_version_before"] + 1,
                         f"M15 update operation {oid} item {pos}: working-version "
                         "step mismatch.")
                _require(_is_hash(item["before_spec_hash"]) and
                         _is_hash(item["after_spec_hash"]),
                         f"M15 update operation {oid} item {pos}: spec hash invalid.")
                _require(item["translator_id"] == use["translator_id"] and
                         item["translator_version"] == use["translator_version"] and
                         item["translator_parameters_hash"] ==
                         use["translator_parameters_hash"] and
                         item["translator_output_hash"] ==
                         use["translator_output_hash"],
                         f"M15 update operation {oid} item {pos}: translator pins "
                         "mismatch.")
                normalized_items.append({
                    "composition_id": item["composition_id"],
                    "occurrence_id": item["occurrence_id"],
                    "from_revision_id": item["from_revision_id"],
                    "to_revision_id": item["to_revision_id"],
                    "verdict": item["verdict"],
                    "review_accepted": bool(item["review_accepted"]),
                    "working_version_before": item["working_version_before"],
                    "working_version_after": item["working_version_after"],
                    "before_spec_hash": item["before_spec_hash"],
                    "after_spec_hash": item["after_spec_hash"],
                    "translator_output_hash": item["translator_output_hash"],
                })

            expected_operation = operation_root(
                {
                    "assessment_id": operation["assessment_id"],
                    "assessment_report_hash": operation["assessment_report_hash"],
                },
                normalized_items,
            )
            _require(canonical_json_str(expected_operation) ==
                     operation["operation_json"] and
                     canonical_hash(expected_operation) ==
                     operation["operation_hash"],
                     f"M15 update operation {oid}: operation_json/operation_hash "
                     "mismatch.")

        # No item may exist without the immutable operation parent; real
        # schema FKs enforce this, but recovery also fails closed if a damaged
        # DB reaches this semantic layer with FK checks disabled upstream.
        orphan_count = con.execute(
            "SELECT COUNT(*) FROM production_update_items i LEFT JOIN "
            "production_update_operations o ON o.id = i.operation_id "
            "WHERE o.id IS NULL"
        ).fetchone()[0]
        _require(orphan_count == 0, "M15 contains orphan update item rows.")
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Integration with the existing M10F recovery engine
# ---------------------------------------------------------------------------


def install_successor_semantics(recovery: ModuleType) -> None:
    """Install the missing 0015/0016 semantic succession at the liveness seam.

    ``backup.py`` already invokes M11->M13 before its exact liveness walk.
    Its restore path does the same before ``_verify_liveness_equal``.  The
    one shared seam used by both is ``_enumerate_liveness``; extending that
    seam preserves the existing coherent staged DB, ordering, fail-closed
    behavior and physical-byte machinery while adding only the two missing
    successor contracts.
    """
    if getattr(recovery, "_m16_p0_successor_semantics_installed", False):
        return

    recovery._verify_m14_observation_state = verify_m14_observation_state
    recovery._verify_m15_compatibility_state = verify_m15_compatibility_state

    def _verify_head_semantics(staged_db: Path, head: str) -> None:
        supported = recovery.SUPPORTED_RESTORE_ALEMBIC_HEADS
        if head not in supported:
            raise _corrupt(f"unsupported recovery head {head!r}.")
        if head == recovery.PRE_M11_ALEMBIC_HEAD:
            return
        recovery._verify_m11_production_state(staged_db)
        if head == recovery.M11_ALEMBIC_HEAD:
            return
        recovery._verify_m12_composition_state(staged_db)
        if head == recovery.M12_ALEMBIC_HEAD:
            return
        recovery._verify_m13_world_state(staged_db)
        if head == recovery.M13_ALEMBIC_HEAD:
            return
        recovery._verify_m14_observation_state(staged_db)
        if head == recovery.M14_ALEMBIC_HEAD:
            return
        recovery._verify_m15_compatibility_state(staged_db)

    recovery._verify_head_semantics = _verify_head_semantics

    original_enumerate = recovery._enumerate_liveness

    def _enumerate_with_successor_semantics(
        staged_db: Path, expected_columns=None
    ):
        head = recovery._staged_db_head(staged_db)
        if head in (recovery.M14_ALEMBIC_HEAD, recovery.M15_ALEMBIC_HEAD):
            recovery._verify_m14_observation_state(staged_db)
        if head == recovery.M15_ALEMBIC_HEAD:
            recovery._verify_m15_compatibility_state(staged_db)
        return original_enumerate(staged_db, expected_columns)

    recovery._enumerate_liveness = _enumerate_with_successor_semantics
    recovery._m16_p0_successor_semantics_installed = True
