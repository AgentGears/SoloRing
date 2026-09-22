"""M16-P0 source-true recovery succession for M14/M15 history.

This module is the integration shim installed by ``soloring.recovery``.  It
keeps the existing M10F backup/restore engine and adds the two durable
semantic layers that were published later:

* M14 retained observation artifacts + Generation bindings;
* M15 compatibility/update evidence (implemented in the companion verifier).

Historical validity is stored-consistency only.  In particular, an M14
artifact is checked against its own captured materializer-contract hash and
stored WorldObservationSpec; recovery never compares old history with today's
runtime materializer contract.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import ModuleType

from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.recovery import semantic_successors
from soloring.recovery.semantic_successors import (
    verify_m15_compatibility_state,
)

_HEX = frozenset("0123456789abcdef")


def _corrupt(message: str):
    # Lazy import avoids a backup.py <-> successor verifier import cycle.
    from soloring.recovery.backup import RecoveryCorruption

    return RecoveryCorruption(message)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise _corrupt(message)


def _is_hash(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _HEX


def _canonical_pair(raw: object, digest: object, what: str):
    if not isinstance(raw, str):
        raise _corrupt(f"{what} is not stored JSON text.")
    try:
        value = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise _corrupt(f"{what} is not valid JSON: {exc}") from exc
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


def _exists(con: sqlite3.Connection, table: str, where: str,
            params: tuple) -> bool:
    return con.execute(
        f"SELECT 1 FROM {table} WHERE {where} LIMIT 1", params
    ).fetchone() is not None


def verify_m14_observation_state(staged_db: Path) -> None:
    """Verify every retained M14 artifact and immutable Generation binding.

    The proof mirrors M14's historical worker contract, but remains entirely
    database-side: physical Blob bytes are verified by the surrounding M10F
    recovery engine.  Orphan artifacts are legal because publication precedes
    the Generation transaction; they still must be internally canonical and
    provenance-complete.
    """
    from soloring.observation.materializer import (
        ARTIFACT_ROLE,
        MATERIALIZER_ID,
        MATERIALIZER_VERSION,
        PARAMETERS,
    )
    from soloring.observation.workflow_spec import parse_workflow_spec_v4

    con = sqlite3.connect(str(staged_db))
    con.row_factory = sqlite3.Row
    try:
        tables = _tables(con)
        required = {
            "derived_observation_artifacts",
            "generation_derived_observation_inputs",
        }
        missing = required - tables
        if missing:
            raise _corrupt(
                "M14 semantic verification is missing table(s) "
                f"{sorted(missing)}."
            )

        artifact_rows = con.execute(
            "SELECT id, project_id, observation_spec_hash, artifact_role, "
            "materializer_id, materializer_version, "
            "materializer_contract_hash, parameters_json, parameters_hash, "
            "provenance_json, provenance_hash, blob_hash "
            "FROM derived_observation_artifacts ORDER BY id"
        ).fetchall()
        artifacts = {row["id"]: row for row in artifact_rows}

        expected_provenance_keys = {
            "project_id",
            "observation_spec_hash",
            "artifact_role",
            "materializer_id",
            "materializer_version",
            "materializer_contract_hash",
            "parameters_hash",
            "source_retained_blob_hashes",
            "execution_package",
        }
        expected_execution_keys = {
            "workflow_id",
            "workflow_version",
            "manifest_hash",
            "workflow_template_hash",
            "realization_profile_hash",
            "execution_model_fingerprint_hash",
        }
        expected_parameter_hash = canonical_hash(PARAMETERS)

        for row in artifact_rows:
            aid = row["id"]
            _require(_is_hash(row["observation_spec_hash"]),
                     f"M14 artifact {aid}: observation_spec_hash invalid.")
            _require(_is_hash(row["materializer_contract_hash"]),
                     f"M14 artifact {aid}: materializer_contract_hash invalid.")
            _require(_is_hash(row["blob_hash"]),
                     f"M14 artifact {aid}: blob_hash invalid.")
            _require(row["artifact_role"] == ARTIFACT_ROLE,
                     f"M14 artifact {aid}: artifact_role mismatch.")
            _require(row["materializer_id"] == MATERIALIZER_ID,
                     f"M14 artifact {aid}: materializer_id mismatch.")
            _require(row["materializer_version"] == MATERIALIZER_VERSION,
                     f"M14 artifact {aid}: materializer_version mismatch.")

            parameters = _canonical_pair(
                row["parameters_json"], row["parameters_hash"],
                f"M14 artifact {aid} parameters_json",
            )
            _require(parameters == PARAMETERS and
                     row["parameters_hash"] == expected_parameter_hash,
                     f"M14 artifact {aid}: parameters differ from the frozen "
                     "schema-1 frame grammar.")

            provenance = _canonical_pair(
                row["provenance_json"], row["provenance_hash"],
                f"M14 artifact {aid} provenance_json",
            )
            _require(isinstance(provenance, dict) and
                     set(provenance) == expected_provenance_keys,
                     f"M14 artifact {aid}: provenance grammar mismatch.")
            for key in (
                "project_id", "observation_spec_hash", "artifact_role",
                "materializer_id", "materializer_version",
                "materializer_contract_hash", "parameters_hash",
            ):
                _require(provenance.get(key) == row[key],
                         f"M14 artifact {aid}: provenance {key} mismatch.")

            source_hashes = provenance["source_retained_blob_hashes"]
            _require(isinstance(source_hashes, list),
                     f"M14 artifact {aid}: source_retained_blob_hashes is "
                     "not an array.")
            # Repeated retained bytes are legal when several occurrences use
            # the same Production Revision; preserve list semantics exactly.
            for source_hash in source_hashes:
                _require(_is_hash(source_hash),
                         f"M14 artifact {aid}: invalid source retained Blob hash.")
                if "blobs" in tables:
                    _require(_exists(con, "blobs", "hash = ?", (source_hash,)),
                             f"M14 artifact {aid}: source retained Blob "
                             f"{source_hash} is missing.")

            execution = provenance["execution_package"]
            _require(isinstance(execution, dict) and
                     set(execution) == expected_execution_keys,
                     f"M14 artifact {aid}: execution_package grammar mismatch.")
            _require(isinstance(execution["workflow_id"], str) and
                     bool(execution["workflow_id"]),
                     f"M14 artifact {aid}: workflow_id invalid.")
            _require(isinstance(execution["workflow_version"], int) and
                     not isinstance(execution["workflow_version"], bool),
                     f"M14 artifact {aid}: workflow_version invalid.")
            for key in (
                "manifest_hash", "workflow_template_hash",
                "realization_profile_hash",
                "execution_model_fingerprint_hash",
            ):
                _require(_is_hash(execution[key]),
                         f"M14 artifact {aid}: execution_package.{key} invalid.")

            if "projects" in tables:
                _require(_exists(con, "projects", "id = ?", (row["project_id"],)),
                         f"M14 artifact {aid}: owning Project is missing.")
            if "blobs" in tables:
                _require(_exists(con, "blobs", "hash = ?", (row["blob_hash"],)),
                         f"M14 artifact {aid}: retained Blob is missing.")

        # Every immutable Generation binding must resolve exactly one artifact
        # and agree with its composite Blob identity.  Position 0 is frozen by
        # the schema-4 worker; the input key itself is package-specific and is
        # validated against the retained manifest by historical execution.
        bindings = con.execute(
            "SELECT generation_id, input_key, position, artifact_role, "
            "derived_observation_artifact_id, blob_hash "
            "FROM generation_derived_observation_inputs "
            "ORDER BY generation_id, input_key, position"
        ).fetchall()
        by_generation: dict[str, list[sqlite3.Row]] = {}
        for binding in bindings:
            aid = binding["derived_observation_artifact_id"]
            artifact = artifacts.get(aid)
            _require(artifact is not None,
                     f"M14 Generation binding references missing artifact {aid}.")
            _require(binding["artifact_role"] == ARTIFACT_ROLE and
                     binding["artifact_role"] == artifact["artifact_role"],
                     f"M14 Generation binding {aid}: artifact_role mismatch.")
            _require(binding["blob_hash"] == artifact["blob_hash"],
                     f"M14 Generation binding {aid}: blob_hash mismatch.")
            _require(binding["position"] == 0,
                     f"M14 Generation binding {aid}: position must be 0.")
            _require(isinstance(binding["input_key"], str) and
                     bool(binding["input_key"]),
                     f"M14 Generation binding {aid}: input_key invalid.")
            if "generations" in tables:
                _require(_exists(con, "generations", "id = ?",
                                 (binding["generation_id"],)),
                         f"M14 Generation binding {aid}: Generation is missing.")
            by_generation.setdefault(binding["generation_id"], []).append(binding)

        # For retained schema-4 Generations, use the ONE strict M14 parser and
        # prove the bound artifact was produced for that exact stored
        # WorldObservationSpec and captured materializer contract.  This is
        # stored-history agreement, never a comparison with today's runtime
        # implementation hash.
        if "generations" in tables:
            generation_rows = con.execute(
                "SELECT id, workflow_spec_json, workflow_spec_hash FROM "
                "generations ORDER BY id"
            ).fetchall()
            for generation in generation_rows:
                try:
                    spec = json.loads(generation["workflow_spec_json"])
                except (ValueError, TypeError) as exc:
                    raise _corrupt(
                        f"Generation {generation['id']}: WorkflowSpec is not "
                        f"valid JSON: {exc}"
                    ) from exc
                if not isinstance(spec, dict) or spec.get("schema_version") != 4:
                    _require(not by_generation.get(generation["id"]),
                             f"Generation {generation['id']}: non-schema-4 "
                             "history carries an M14 observation binding.")
                    continue
                try:
                    parsed = parse_workflow_spec_v4(spec)
                except Exception as exc:
                    raise _corrupt(
                        f"Generation {generation['id']}: stored schema-4 "
                        f"WorkflowSpec violates the frozen M14 grammar: {exc}"
                    ) from exc
                _require(canonical_hash(parsed) == generation["workflow_spec_hash"],
                         f"Generation {generation['id']}: WorkflowSpec hash "
                         "mismatch.")
                owned = by_generation.get(generation["id"], [])
                _require(len(owned) == 1,
                         f"Generation {generation['id']}: schema-4 history must "
                         "carry exactly one observation binding.")
                binding = owned[0]
                artifact = artifacts[binding["derived_observation_artifact_id"]]
                observation = parsed["world_observation"]
                materialization = observation["spec"]["materializations"][0]
                materializer = materialization["materializer"]
                _require(artifact["observation_spec_hash"] ==
                         observation["spec_hash"],
                         f"Generation {generation['id']}: artifact pins a "
                         "different observation spec.")
                _require(artifact["materializer_id"] == materializer["id"] and
                         artifact["materializer_version"] ==
                         materializer["version"] and
                         artifact["materializer_contract_hash"] ==
                         materializer["contract_hash"],
                         f"Generation {generation['id']}: artifact materializer "
                         "identity disagrees with the stored observation spec.")
                _require(artifact["parameters_hash"] ==
                         materialization["parameters_hash"],
                         f"Generation {generation['id']}: artifact parameters "
                         "disagree with the stored observation spec.")
    finally:
        con.close()


def install_successor_semantics(recovery: ModuleType) -> None:
    """Install M14/M15 semantic checks at the shared liveness seam."""
    if getattr(recovery, "_m16_p0_successor_semantics_installed", False):
        return

    recovery._verify_m14_observation_state = verify_m14_observation_state
    recovery._verify_m15_compatibility_state = verify_m15_compatibility_state
    recovery._verify_m16_intra_shot_state = (
        semantic_successors.verify_m16_intra_shot_state)
    from soloring.recovery.m17a_verifier import (
        verify_m17a_dialogue_vocal_state,
    )
    recovery._verify_m17a_dialogue_vocal_state = (
        verify_m17a_dialogue_vocal_state)
    from soloring.recovery.m17b_verifier import (
        verify_m17b_performance_state,
    )
    recovery._verify_m17b_performance_state = (
        verify_m17b_performance_state)

    def _verify_head_semantics(staged_db: Path, head: str) -> None:
        if head not in recovery.SUPPORTED_RESTORE_ALEMBIC_HEADS:
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
        if head == recovery.M15_ALEMBIC_HEAD:
            return
        recovery._verify_m16_intra_shot_state(staged_db)
        if head == recovery.M16_ALEMBIC_HEAD:
            return
        recovery._verify_m17a_dialogue_vocal_state(staged_db)
        if head == getattr(recovery, "M17A_ALEMBIC_HEAD", None):
            return
        recovery._verify_m17b_performance_state(staged_db)

    recovery._verify_head_semantics = _verify_head_semantics

    original_enumerate = recovery._enumerate_liveness

    def _enumerate_with_successor_semantics(staged_db: Path,
                                            expected_columns=None):
        head = recovery._staged_db_head(staged_db)
        if head in (recovery.M14_ALEMBIC_HEAD, recovery.M15_ALEMBIC_HEAD,
                    recovery.M16_ALEMBIC_HEAD,
                    getattr(recovery, "M17A_ALEMBIC_HEAD", None)):
            recovery._verify_m14_observation_state(staged_db)
        if head in (recovery.M15_ALEMBIC_HEAD, recovery.M16_ALEMBIC_HEAD,
                    getattr(recovery, "M17A_ALEMBIC_HEAD", None)):
            recovery._verify_m15_compatibility_state(staged_db)
        if head in (recovery.M16_ALEMBIC_HEAD,
                    getattr(recovery, "M17A_ALEMBIC_HEAD", None)):
            recovery._verify_m16_intra_shot_state(staged_db)
        if head == getattr(recovery, "M17A_ALEMBIC_HEAD", None):
            recovery._verify_m17a_dialogue_vocal_state(staged_db)
        if head in (getattr(recovery, "M17A_ALEMBIC_HEAD", None),
                    getattr(recovery, "M17B_ALEMBIC_HEAD", None)):
            recovery._verify_m17a_dialogue_vocal_state(staged_db)
        if head == getattr(recovery, "M17B_ALEMBIC_HEAD", None):
            recovery._verify_m17b_performance_state(staged_db)
        return original_enumerate(staged_db, expected_columns)

    recovery._enumerate_liveness = _enumerate_with_successor_semantics
    recovery._m16_p0_successor_semantics_installed = True
