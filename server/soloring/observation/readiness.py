"""M14 observation execution-readiness projection (frozen R2 §31).

A pure, mutation-free projection of a Shot's observation posture: the
LAST CAPTURED ShotRevision supplies every authority fact (captured
schema-6 value, companion hashes, immutable retained closure), and the
CURRENT selected workflow package supplies the policy. The surface is
the §31 minimum: policy/profile identity, ordered requirement rows
traced property → preservation → authority/source → source contract →
verdict, per-requirement explanation, the captured observation hash,
capture currency, and the latest bound derived-artifact provenance.

Nothing here captures a revision, materializes bytes, publishes an
artifact, or writes any row: readiness explains, it never reserves.
The typed refusal contract (§8.11) remains the Generation path's job;
this surface makes the SAME trace legible before a request is made.
"""

from __future__ import annotations

from sqlalchemy import text

from soloring.domain.canonical import canonical_hash


async def observation_readiness(session, settings, shot_id: str) -> dict:
    """§31 minimum surface over the Shot's captured observation posture."""
    from soloring.continuity.snapshots import (
        build_capturable_snapshot,
        effective_working_snapshot_hash,
    )
    from soloring.domain.revisions import _snapshot_one_read
    from soloring.domain.ids import is_uuid
    from soloring.errors import ErrorCode, not_found

    if not is_uuid(shot_id):
        raise not_found(
            ErrorCode.SHOT_NOT_FOUND, f"Shot {shot_id!r} not found.")

    read = await _snapshot_one_read(session, shot_id, settings=settings)
    shot, refs, resolved = read[0], read[1], read[2]
    feature_states, relation_states, visual_result = read[3], read[4], read[5]
    spatial_result = read[6]
    production_world_result = read[7]
    visual_pack = visual_result.pack if visual_result is not None else None
    spatial_pack = (
        spatial_result.pack if spatial_result is not None else None)
    production_world_pack = (
        production_world_result.pack
        if production_world_result is not None else None)
    working_snapshot, _spec = build_capturable_snapshot(
        shot, refs, resolved, feature_states, relation_states,
        visual_pack, spatial_pack, production_world_pack)
    working_hash = effective_working_snapshot_hash(
        shot, refs, resolved, feature_states, relation_states,
        visual_pack, spatial_pack, production_world_pack)

    async with session.bind.connect() as conn:
        captured = (await conn.execute(text(
            "SELECT id, snapshot_json, snapshot_hash FROM shot_revisions "
            "WHERE shot_id = :s ORDER BY revision_number DESC LIMIT 1"),
            {"s": shot_id})).mappings().one_or_none()

    base = {
        "shot_id": shot_id,
        "readiness": None,
        "ready": False,
        "capture": None,
        "policy": None,
        "requirements": [],
        "observation_hash": None,
        "artifact_provenance": await _latest_artifact_provenance(
            session, shot_id),
    }

    if captured is None:
        base["readiness"] = "not-yet-captured"
        base["explanation"] = (
            "the Shot has no captured revision yet; the observation "
            f"posture (working snapshot schema "
            f"{working_snapshot['schema_version']}) becomes addressable "
            "at its first capture")
        return base

    import json as _json

    captured_snapshot = _json.loads(captured["snapshot_json"])
    base["capture"] = {
        "revision_id": captured["id"],
        "schema_version": captured_snapshot["schema_version"],
        "is_current": captured["snapshot_hash"] == working_hash,
    }

    if captured_snapshot["schema_version"] != 6:
        base["readiness"] = "not-applicable"
        base["explanation"] = (
            "the last captured revision (schema "
            f"{captured_snapshot['schema_version']}) carries no "
            "production world; the observation plane applies only to "
            "schema-6 captures")
        return base

    if not base["capture"]["is_current"]:
        base["working_state_diverged"] = True

    # the observation-capable posture: the CURRENT selected package is
    # the policy source (read-only byte capture — never placed/mutated)
    from soloring.realization.packages import (
        capture_current_release,
        validate_package,
    )

    release = await capture_current_release(settings)
    package = validate_package(release)
    observation_block = package.profile_v2.get("observation")

    if observation_block is None:
        base["readiness"] = "refused"
        base["policy"] = {
            "verdict": "UNSUPPORTED",
            "workflow_id": release.workflow_id,
            "workflow_version": release.workflow_version,
            "profile_hash": release.realization_profile_hash,
            "capability_contract_hash": None,
            "explanation": (
                "the selected workflow profile declares no observation "
                "capability: a schema-6 ShotRevision cannot execute "
                "through this package"),
        }
        return base

    mesh_depth_materializers = sorted(
        (m for m in observation_block.get("materializers", [])
         if m.get("id") == "soloring.observation.mesh_depth"),
        key=lambda m: m["version"])
    if not mesh_depth_materializers:
        base["readiness"] = "refused"
        base["policy"] = {
            "verdict": "UNSUPPORTED",
            "workflow_id": release.workflow_id,
            "workflow_version": release.workflow_version,
            "profile_hash": release.realization_profile_hash,
            "capability_contract_hash": None,
            "explanation": (
                "the selected observation profile declares no mesh-depth "
                "materializer: the WorldObservationSpec cannot pin the "
                "one materializer contract it would require"),
        }
        return base
    materializer = mesh_depth_materializers[-1]

    from soloring.observation import (
        compile_world_observation_spec,
        negotiate,
    )
    from soloring.observation.retained import (
        load_retained_mesh_sources,
        merge_retained_into_spec,
    )
    from soloring.observation.spec import world_observation_spec_hash
    from soloring.spatial import schemas as spatial_schemas

    async with session.bind.connect() as conn:
        companions = (await conn.execute(text(
            "SELECT srsw.spatial_continuity_hash, "
            "srpw.production_world_hash FROM shot_revisions sr "
            "LEFT JOIN shot_revision_spatial_worlds srsw "
            "  ON srsw.shot_revision_id = sr.id "
            "LEFT JOIN shot_revision_production_worlds srpw "
            "  ON srpw.shot_revision_id = sr.id "
            "WHERE sr.id = :rid"), {"rid": captured["id"]})).mappings().one()

    captured_spatial_pack = captured_snapshot["spatial_continuity"]
    visual_pack_captured = captured_snapshot.get("visual_reference_pack")
    observation_spec = compile_world_observation_spec(
        shot_id=shot_id,
        shot_revision_id=captured["id"],
        plan_hash=spatial_schemas.plan_hash(
            captured_spatial_pack["shot_plan"]),
        captured_schema_6=captured_snapshot,
        spatial_continuity_hash=companions["spatial_continuity_hash"],
        production_world_hash=companions["production_world_hash"],
        visual_reference_pack_hash=(
            canonical_hash(visual_pack_captured)
            if visual_pack_captured else None),
        materializer_contract_hash=materializer["contract_hash"],
    )

    # the same set-oriented retained closure consumer (read-only)
    from soloring.assets.blob_store import BlobStore

    store = BlobStore(settings)

    def _read_blob(blob_hash: str) -> bytes:
        return store.path_for_hash(blob_hash).read_bytes()

    async with session.bind.connect() as conn:
        retained = await load_retained_mesh_sources(
            conn, _read_blob,
            captured_production_world=captured_snapshot[
                "production_world"],
            captured_spatial_pack=captured_spatial_pack)
    observation_spec = merge_retained_into_spec(observation_spec, retained)

    negotiation = negotiate(observation_spec, observation_block)

    requirements = []
    for requirement, requirement_result in zip(
            observation_spec["requirements"],
            negotiation["requirements"]):
        requirements.append({
            "position": len(requirements),
            "property": requirement["property"],
            "preservation": requirement["preservation"],
            "enforcement": requirement["enforcement"],
            "authority": requirement["authority"],
            "source_contract": requirement["source_contract"],
            "verdict": requirement_result["verdict"],
            "explanation": _explain(requirement,
                                    requirement_result["verdict"]),
        })

    refused = [r for r in requirements if r["verdict"] in (
        "UNSUPPORTED", "UNKNOWN")]
    policy_verdict = negotiation["policy"]["verdict"]
    base["readiness"] = (
        "supported" if policy_verdict == "SUPPORTED" and not refused
        else "refused")
    base["ready"] = base["readiness"] == "supported"
    base["policy"] = {
        "verdict": policy_verdict,
        "workflow_id": release.workflow_id,
        "workflow_version": release.workflow_version,
        "profile_hash": release.realization_profile_hash,
        "capability_contract_hash": canonical_hash(observation_block),
        "materializer_id": materializer["id"],
        "materializer_version": materializer["version"],
        "materializer_contract_hash": materializer["contract_hash"],
        "explanation": (
            None if policy_verdict == "SUPPORTED" and not refused else
            "the captured observation posture is not supported by the "
            "selected observation-capable profile"),
    }
    base["requirements"] = requirements
    base["observation_hash"] = world_observation_spec_hash(observation_spec)
    return base


def _explain(requirement: dict, verdict: str) -> str:
    """Deterministic per-requirement explanation from the typed trace —
    never prompt text (frozen §41)."""
    authority = requirement["authority"]
    source = (f"{authority['domain']} authority "
              f"({authority['source_kind']} {authority['source_id']})")
    coordinate = (
        f"property {requirement['property']} requires "
        f"{requirement['preservation']} preservation from {source} "
        f"under source contract {requirement['source_contract']}")
    if verdict == "SUPPORTED":
        return (f"{coordinate}: the selected profile supports this exact "
                "capability tuple")
    if verdict == "UNSUPPORTED":
        return (f"{coordinate}: the selected profile declares this "
                "property but not this exact capability tuple")
    if verdict == "UNKNOWN":
        return (f"{coordinate}: the selected profile has no declaration "
                "for this property")
    if verdict == "PERMITTED_INFERENCE":
        return (f"{coordinate}: permitted inference does not require "
                "capability support")
    return f"{coordinate}: verdict {verdict}"


async def _latest_artifact_provenance(session, shot_id: str):
    """The newest bound derived-observation artifact for this Shot's
    Generations — provenance only, from immutable rows."""
    async with session.bind.connect() as conn:
        row = (await conn.execute(text(
            "SELECT a.id, a.blob_hash, a.materializer_id, "
            "a.materializer_version, a.materializer_contract_hash, "
            "a.parameters_hash, a.provenance_hash, a.created_at, "
            "g.id AS generation_id FROM generations g "
            "JOIN generation_derived_observation_inputs i "
            "  ON i.generation_id = g.id "
            "JOIN derived_observation_artifacts a "
            "  ON a.id = i.derived_observation_artifact_id "
            "WHERE g.shot_id = :s "
            "ORDER BY g.created_at DESC, g.generation_number DESC "
            "LIMIT 1"), {"s": shot_id})).mappings().one_or_none()
    if row is None:
        return None
    provenance = dict(row)
    provenance["note"] = (
        "provenance of the most recent published observation artifact — "
        "a readiness evaluation does not reuse or mutate it")
    return provenance
