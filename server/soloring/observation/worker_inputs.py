"""M14 schema-4 worker derived-input execution (frozen R2 §25.3).

Loads + verifies the persisted execution closure for one historical
schema-4 Generation and uploads the exact retained bytes to the
executor's attempt namespace:

  * the observation.world_depth artifact (generation_derived_observation_
    inputs, position 0) — verified against the workflow-spec's captured
    observation hash and the artifact row's OWN captured materializer
    contract hash (NEVER today's contract: §24 historical validity);
  * the inherited M10 entity-depth siblings (generation_derived_spatial_
    inputs, entity roles only) — verified through the frozen M10 loader.

The M10 world-depth sibling is superseded by the observation artifact at
the same manifest coordinate (§22.2: the observation binding owns the
inherited spatial.world_depth input key). Zero current
Production/Composition/binding/state/SpatialWorld resolution.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from soloring.assets.blob_store import BlobStore
from soloring.domain.canonical import canonical_hash
from soloring.errors import SoloRingError
from soloring.spatial import error_codes as ec
from soloring.spatial.worker_inputs import VerifiedDerivedInput


def _fail(code, message):
    return SoloRingError(code, message, status_code=500)


async def execute_schema4_derived_inputs(
    session: AsyncSession,
    store: BlobStore,
    *,
    generation_id: str,
    attempt_id: str,
    workflow_spec_v4: dict,
    manifest_v3: dict,
    client,
) -> list[VerifiedDerivedInput]:
    from soloring.executors.comfy.input_materializer import (
        attempt_namespace,
        validate_returned_reference,
    )
    from soloring.executors.comfy.translate import comfy_input_reference
    from soloring.spatial.worker_inputs import _split_png_frames

    observation = workflow_spec_v4["world_observation"]
    captured_spec_hash = observation["spec_hash"]

    # ---- the exact observation binding (position 0, world depth) ------
    binding = (await session.execute(text(
        "SELECT input_key, position, artifact_role, "
        "derived_observation_artifact_id, blob_hash "
        "FROM generation_derived_observation_inputs "
        "WHERE generation_id = :gid ORDER BY position"),
        {"gid": generation_id})).mappings().one_or_none()
    if binding is None:
        raise _fail(
            ec.DERIVED_SPATIAL_BLOB_MISSING,
            "Schema-4 Generation has no derived-observation binding; "
            "execution cannot proceed without the exact retained "
            "observation artifact.")

    artifact = (await session.execute(text(
        "SELECT id, project_id, observation_spec_hash, artifact_role, "
        "materializer_id, materializer_version, "
        "materializer_contract_hash, parameters_json, parameters_hash, "
        "provenance_json, provenance_hash, blob_hash "
        "FROM derived_observation_artifacts WHERE id = :aid"),
        {"aid": binding["derived_observation_artifact_id"]}
    )).mappings().one_or_none()
    if artifact is None:
        raise _fail(
            ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH,
            "Derived-observation artifact row missing for the bound id.")
    if artifact["observation_spec_hash"] != captured_spec_hash:
        raise _fail(
            ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH,
            "Derived-observation provenance pins a different observation "
            "spec hash than the stored WorkflowSpec.")
    if artifact["blob_hash"] != binding["blob_hash"]:
        raise _fail(
            ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH,
            "Derived-observation Blob identity disagrees with the "
            "Generation binding.")
    # Source review P0-2: the artifact's producing contract must be the
    # exact contract the stored WorldObservationSpec negotiated under —
    # the historical counterpart of the creation-side equality gate.
    # Still never a comparison against TODAY'S materializer.
    spec_contract = workflow_spec_v4["world_observation"]["spec"][
        "materializations"][0]["materializer"]["contract_hash"]
    if artifact["materializer_contract_hash"] != spec_contract:
        raise _fail(
            ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH,
            "Derived-observation artifact was produced under materializer "
            "contract "
            f"{artifact['materializer_contract_hash']} while the stored "
            f"WorldObservationSpec pins {spec_contract}.")
    # §24/§26: historical validity = stored consistency ONLY. The
    # provenance is verified against the artifact row's OWN captured
    # materializer-contract hash — never today's contract.
    import json as _json

    provenance = _json.loads(artifact["provenance_json"])
    if (canonical_hash(provenance) != artifact["provenance_hash"]
            or provenance.get("observation_spec_hash")
            != captured_spec_hash
            or provenance.get("materializer_contract_hash")
            != artifact["materializer_contract_hash"]):
        raise _fail(
            ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH,
            "Derived-observation canonical provenance fails historical "
            "validation against its captured contract.")
    parameters = _json.loads(artifact["parameters_json"])
    if canonical_hash(parameters) != artifact["parameters_hash"]:
        raise _fail(
            ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH,
            "Derived-observation canonical parameters disagree with "
            "parameters_hash.")

    blob_row = (await session.execute(
        text("SELECT hash FROM blobs WHERE hash = :h"),
        {"h": binding["blob_hash"]})).first()
    if blob_row is None:
        raise _fail(
            ec.DERIVED_SPATIAL_BLOB_MISSING,
            f"Historical observation Blob {binding['blob_hash']} has no "
            "Blob row.")
    from soloring.spatial.blob_integrity import blob_integrity_status

    status = await blob_integrity_status(store, binding["blob_hash"])
    if status != "valid":
        raise _fail(
            ec.DERIVED_SPATIAL_BLOB_CORRUPT
            if status == "corrupt"
            else ec.DERIVED_SPATIAL_BLOB_MISSING,
            "Historical observation artifact Blob failed integrity "
            "verification.")

    from soloring.spatial.package3 import resolve_derived_binding

    world_key, world_node, world_field = resolve_derived_binding(
        manifest_v3, "spatial.world_depth", binding["position"])
    if world_key != binding["input_key"]:
        raise _fail(
            ec.DERIVED_SPATIAL_BINDING_INVALID,
            f"Captured observation input_key {binding['input_key']!r} "
            f"disagrees with the manifest binding {world_key!r}.")

    verified = [VerifiedDerivedInput(
        input_key=binding["input_key"],
        position=binding["position"],
        artifact_role=binding["artifact_role"],
        node=world_node,
        field=world_field,
        blob_hash=binding["blob_hash"],
        local_path=str(store.path_for_hash(binding["blob_hash"])))]

    # ---- the inherited M10 entity-depth siblings (world superseded) ---
    entity_rows = (await session.execute(text(
        "SELECT gdsi.input_key, gdsi.position, gdsi.artifact_role, "
        "       gdsi.derived_spatial_artifact_id, gdsi.blob_hash "
        "FROM generation_derived_spatial_inputs gdsi "
        "WHERE gdsi.generation_id = :gid "
        "AND gdsi.artifact_role = 'spatial.entity_depth' "
        "ORDER BY gdsi.position"),
        {"gid": generation_id})).mappings().all()
    for row in entity_rows:
        art = (await session.execute(text(
            "SELECT project_id, spec_hash, runtime_fingerprint_hash, "
            "blob_hash FROM derived_spatial_artifacts WHERE id = :aid"),
            {"aid": row["derived_spatial_artifact_id"]}
        )).mappings().one_or_none()
        if art is None or art["blob_hash"] != row["blob_hash"]:
            raise _fail(
                ec.DERIVED_SPATIAL_PROVENANCE_MISMATCH,
                f"Entity-depth provenance missing/mismatched for "
                f"{row['input_key']!r}.")
        entity_status = await blob_integrity_status(
            store, row["blob_hash"])
        if entity_status != "valid":
            raise _fail(
                ec.DERIVED_SPATIAL_BLOB_CORRUPT,
                f"Entity-depth Blob failed integrity for "
                f"{row['input_key']!r}.")
        key, node, field = resolve_derived_binding(
            manifest_v3, row["artifact_role"], row["position"])
        if key != row["input_key"]:
            raise _fail(
                ec.DERIVED_SPATIAL_BINDING_INVALID,
                f"Entity-depth input_key {row['input_key']!r} disagrees "
                f"with the manifest binding {key!r}.")
        verified.append(VerifiedDerivedInput(
            input_key=row["input_key"], position=row["position"],
            artifact_role=row["artifact_role"], node=node, field=field,
            blob_hash=row["blob_hash"],
            local_path=str(store.path_for_hash(row["blob_hash"]))))

    # ---- upload the exact retained bytes (the frozen attempt ns) ------
    namespace = attempt_namespace(generation_id, attempt_id)
    for v in verified:
        data = Path(v.local_path).read_bytes()
        frames = _split_png_frames(data)
        if frames and len(frames) > 1:
            refs = []
            for i, frame in enumerate(frames):
                filename = (f"{v.input_key}_{v.blob_hash[:16]}_"
                            f"{i:03d}.png")
                name, sub = await client.upload_bytes(
                    data=frame, filename=filename, subfolder=namespace)
                validate_returned_reference(name, sub, namespace)
                refs.append(comfy_input_reference(name, sub))
            v.frame_references = tuple(refs)
        else:
            ext = ".png" if frames else ".bin"
            filename = f"{v.input_key}_{v.blob_hash[:16]}{ext}"
            name, sub = await client.upload(
                source_path=Path(v.local_path), filename=filename,
                subfolder=namespace)
            validate_returned_reference(name, sub, namespace)
            v.execution_reference = comfy_input_reference(name, sub)
    return verified
