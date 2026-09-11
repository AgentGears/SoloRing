"""M14 historical observation inspector (frozen R2 §31 advanced surface).

Reads ONE schema-4 Generation's captured observation facts from the
stored bytes and their bound derived-observation artifact — nothing is
recompiled, re-negotiated, or re-materialized, and the current
materializer/runtime is reported ONLY as a separately labeled
environment observation that never alters the captured values
(the §42/HIST:12 separation, at the inspection seam).
"""

from __future__ import annotations

import json

from sqlalchemy import text

from soloring.domain.canonical import canonical_json_str
from soloring.errors import ErrorCode, not_found
from soloring.domain.ids import is_uuid


async def read_captured_observation(session, generation_id: str) -> dict:
    """The captured observation + artifact provenance for one Generation.

    Fails closed on any stored-byte corruption (the strict schema-4
    parser re-validates the exact persisted WorkflowSpec bytes); never
    consults current production-world state, the current package, or
    the current materializer for the captured values."""
    if not is_uuid(generation_id):
        raise not_found(
            ErrorCode.GENERATION_NOT_FOUND,
            f"Generation {generation_id!r} not found.")

    async with session.bind.connect() as conn:
        row = (await conn.execute(text(
            "SELECT id, shot_id, shot_revision_id, workflow_spec_json, "
            "workflow_spec_hash FROM generations WHERE id = :g"),
            {"g": generation_id})).mappings().one_or_none()
        if row is None:
            raise not_found(
                ErrorCode.GENERATION_NOT_FOUND,
                f"Generation {generation_id!r} not found.")

        spec = json.loads(row["workflow_spec_json"])
        if row["workflow_spec_json"] != canonical_json_str(spec):
            from soloring.errors import internal_invariant

            raise internal_invariant(
                f"Generation {generation_id}: stored WorkflowSpec bytes "
                "are not the canonical encoding")

        from soloring.observation.workflow_spec import (
            parse_workflow_spec_v4,
        )

        if spec.get("schema_version") != 4:
            raise not_found(
                ErrorCode.GENERATION_NOT_FOUND,
                f"Generation {generation_id} carries WorkflowSpec schema "
                f"{spec.get('schema_version')} — no captured observation "
                "block exists for pre-M14 Generations.")
        spec = parse_workflow_spec_v4(spec)

        # Source review P1-4 (inspector hardening): the presented bytes
        # are verified against the Generation's OWN persisted hash before
        # anything is shown as captured provenance.
        from soloring.domain.canonical import canonical_hash

        if canonical_hash(spec) != row["workflow_spec_hash"]:
            from soloring.errors import internal_invariant

            raise internal_invariant(
                f"Generation {generation_id}: stored WorkflowSpec hash "
                "disagrees with the canonicalized bytes")

        observation = spec["world_observation"]
        binding = (await conn.execute(text(
            "SELECT input_key, position, artifact_role, "
            "derived_observation_artifact_id, blob_hash FROM "
            "generation_derived_observation_inputs WHERE generation_id "
            "= :g"), {"g": generation_id})).mappings().one_or_none()
        artifact = None
        if binding is not None:
            artifact_row = (await conn.execute(text(
                "SELECT id, blob_hash, materializer_id, "
                "materializer_version, materializer_contract_hash, "
                "parameters_json, parameters_hash, provenance_json, "
                "provenance_hash, created_at FROM "
                "derived_observation_artifacts WHERE id = :a"),
                {"a": binding["derived_observation_artifact_id"]}
            )).mappings().one_or_none()
            if artifact_row is not None:
                # Source review P1-4 (inspector hardening): the displayed
                # binding/artifact identities are cross-checked against
                # each other AND against the spec's materializer contract
                # before presentation as captured provenance.
                from soloring.domain.canonical import canonical_hash
                from soloring.errors import internal_invariant

                if artifact_row["id"] != binding[
                        "derived_observation_artifact_id"]:
                    raise internal_invariant(
                        f"Generation {generation_id}: bound artifact id "
                        "disagrees with the loaded artifact row.")
                if artifact_row["blob_hash"] != binding["blob_hash"]:
                    raise internal_invariant(
                        f"Generation {generation_id}: bound Blob hash "
                        "disagrees with the artifact row.")
                provenance = json.loads(artifact_row["provenance_json"])
                if canonical_hash(provenance) != (
                        artifact_row["provenance_hash"]):
                    raise internal_invariant(
                        f"Generation {generation_id}: captured "
                        "observation provenance disagrees with its hash.")
                spec_contract = observation["spec"][
                    "materializations"][0]["materializer"][
                        "contract_hash"]
                if (artifact_row["materializer_contract_hash"]
                        != spec_contract):
                    raise internal_invariant(
                        f"Generation {generation_id}: the captured "
                        "artifact's producing contract disagrees with the "
                        "stored WorldObservationSpec materializer "
                        "contract.")
                artifact = {
                    "artifact_id": artifact_row["id"],
                    "blob_hash": artifact_row["blob_hash"],
                    "materializer_id": artifact_row["materializer_id"],
                    "materializer_version": (
                        artifact_row["materializer_version"]),
                    "materializer_contract_hash": (
                        artifact_row["materializer_contract_hash"]),
                    "parameters_hash": artifact_row["parameters_hash"],
                    "provenance_hash": artifact_row["provenance_hash"],
                    "created_at": artifact_row["created_at"],
                    "source_retained_blob_hashes": provenance.get(
                        "source_retained_blob_hashes"),
                    "execution_package": provenance.get(
                        "execution_package"),
                }

    requirements = []
    for requirement, requirement_result in zip(
            observation["spec"]["requirements"],
            observation["negotiation"]["requirements"]):
        requirements.append({
            "property": requirement["property"],
            "preservation": requirement["preservation"],
            "enforcement": requirement["enforcement"],
            "authority": requirement["authority"],
            "source_contract": requirement["source_contract"],
            "verdict": requirement_result["verdict"],
        })
    occurrences = [
        {
            "occurrence_id": occ["occurrence_id"],
            "production_revision_id": occ["production_revision_id"],
            "production_revision_hash": occ["production_revision_hash"],
            "retained_blob_hash": occ.get("retained_blob_hash"),
        }
        for occ in observation["spec"].get("production_occurrences", [])
    ]

    return {
        "generation_id": generation_id,
        "shot_id": row["shot_id"],
        "shot_revision_id": row["shot_revision_id"],
        "captured": {
            "note": (
                "every value below is read from the stored schema-4 "
                "bytes and their bound artifact — never recomputed from "
                "current state"),
            "observation_spec_hash": observation["spec_hash"],
            "negotiation_hash": observation["negotiation_hash"],
            "policy_verdict": observation["negotiation"]["policy"][
                "verdict"],
            "profile_hash": observation["profile_hash"],
            "capability_contract_hash": (
                observation["capability_contract_hash"]),
            "requirements": requirements,
            "production_occurrences": occurrences,
            "artifact": artifact,
        },
        "current_environment": await _current_environment(artifact),
    }


async def _current_environment(artifact) -> dict:
    """Environment observation ONLY (§31 separation): whether today's
    materializer contract identity equals the captured one. It never
    upgrades, downgrades, or otherwise alters any captured value."""
    environment = {
        "note": (
            "environment observation only — the captured values above "
            "are verified against their own captured contract, never "
            "against today's materializer/runtime"),
        "materializer_contract_hash": None,
        "contract_matches_captured": None,
    }
    if artifact is None:
        return environment
    from soloring.observation.materializer import (
        build_materializer_contract,
        materializer_contract_hash,
    )

    current_hash = materializer_contract_hash(
        build_materializer_contract())
    environment["materializer_contract_hash"] = current_hash
    environment["contract_matches_captured"] = (
        current_hash == artifact["materializer_contract_hash"])
    return environment
