"""M14A-3 — WorkflowSpec schema 4 + Generation integration (frozen R2
§§7.2/19/25.1, E10).

The schema-6 branching rule proven end-to-end through the REAL service
path: compile → negotiate → typed refusal before publication for
non-capable profiles (the V1 fail-open eliminated), and SUPPORTED
observations wrapping the exact lower schema-3 execution meaning as
WorkflowSpec schema 4 with the recovered M10 spatial plane.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from soloring.domain.canonical import canonical_hash
from soloring.errors import ErrorCode, SoloRingError
from soloring.generation.service import create_generation_request

from tests.m13_seed import make_composition, mint, publish, seed_base
from tests.test_m10e_generation import _spatial_seed, _spatial_settings
from tests.test_m10e_package3_production import _schema3_package
from tests.test_m13_binding import _adopt, _interpretation, _publish
from tests.test_m13_shot_capture import (
    _capture,
    _entity_approved,
    _factory,
    _full_m13_world,
    _select_binding,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "m14"


def _observation_profile() -> dict:
    """A schema-3 realization profile: the certified schema-2 profile
    plus the frozen F06 golden observation block."""
    from soloring.spatial.production_package import production_profile_v2

    profile = production_profile_v2()
    profile["schema_version"] = 3
    profile["observation"] = json.loads(
        (FIXTURES / "m14-f06-realization-profile-observation-v1.json")
        .read_bytes().decode("utf-8"))
    return profile


async def _observation_package(tmp_path: Path) -> Path:
    def _install_observation_profile(docs):
        docs["realization-profile.json"] = _observation_profile()
        return docs

    return await _schema3_package(tmp_path, mutate=_install_observation_profile)


async def _schema6_world(client, *, tag: bytes, mesh: bool = True):
    """A shot whose current capture is schema 6: full M10 world + plan +
    a selected M13 production-world binding. With mesh=True (B3 posture)
    the direct occurrence's retained Blob is a valid structural mesh —
    the merged spec negotiates SUPPORTED and the M14 materializer runs.
    With mesh=False the retained Blob is non-mesh raw bytes and the
    observation must refuse (typed unsupported representation)."""
    if mesh:
        from tests.test_m14_materializer import (
            _mesh_doc,
            _observation_world,
        )

        b, snapshot, oids, prids = await _observation_world(
            client, tag=tag,
            sources=[{"kind": "mesh", "mesh": _mesh_doc(),
                      "transform": (0, 0, 0),
                      "interpretation": (0, 0, 0)}],
            adopt_first_mesh=True,
            pi_translation=(-3000, 1500, -800))
        revision = None
        return b, {"binding_id": (
            snapshot["production_world"]["binding"]["binding_id"])}, \
            revision, snapshot
    b = await _full_m13_world(client, tag=tag)
    sel = await _select_binding(client, b)
    revision, _ = await _capture(client, b["shot"])
    snapshot = json.loads(revision.snapshot_json)
    assert snapshot["schema_version"] == 6
    return b, sel, revision, snapshot


def _comfy(client, package_dir: Path):
    settings = client._transport.app.state.settings
    return _spatial_settings(settings, package_dir)


async def _generate(client, shot: str, settings):
    async with _factory(client)() as session:
        return await create_generation_request(
            session, shot, settings=settings)


async def _stored_spec(engine, generation_id: str) -> dict:
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT workflow_spec_json, workflow_spec_hash FROM "
            "generations WHERE id = :g"), {"g": generation_id})).mappings(
        ).one()
    spec = json.loads(row["workflow_spec_json"])
    assert canonical_hash(spec) == row["workflow_spec_hash"]
    return spec


async def _generation_count(engine, shot: str) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT COUNT(*) FROM generations WHERE shot_id = :s"),
            {"s": shot})).scalar_one()


async def _world_depth_blob(engine, generation_id: str) -> str:
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT blob_hash FROM generation_derived_spatial_inputs "
            "WHERE generation_id = :g AND artifact_role = "
            "'spatial.world_depth'"), {"g": generation_id})).scalar_one()


# ---- E10 sharp regression: schema 6 + non-observation-capable v1 ------

async def test_schema6_v1_profile_package_refuses_not_lower_logical(
        client, tmp_path):
    """The V1 fail-open eliminated: a schema-6 Shot with the current
    wan21_spatial_v1 v1 package (schema-2 profile, no observation
    capability) now refuses with the typed policy outcome before any
    Generation row exists — it never reaches the lower-logical
    schema-1/2 execution the predecessor produced."""
    b, _sel, _rev, snapshot = await _schema6_world(
        client, tag=b"m14a3-e10")
    assert "production_world" in snapshot

    pkg = await _schema3_package(tmp_path)  # v2 profile, no observation
    settings = _comfy(client, pkg)
    engine = client._transport.app.state.engine

    with pytest.raises(SoloRingError) as excinfo:
        await _generate(client, b["shot"], settings)
    assert excinfo.value.code == ErrorCode.OBSERVATION_POLICY_UNSUPPORTED
    assert excinfo.value.status_code == 409
    assert await _generation_count(engine, b["shot"]) == 0, (
        "no Generation row may exist for a refused observation")


# ---- SUPPORTED shared-subset path -----------------------------------------

async def test_schema6_supported_generates_workflow_spec_v4(
        client, tmp_path):
    b, _sel, revision, snapshot = await _schema6_world(
        client, tag=b"m14a3-sup")
    pkg = await _observation_package(tmp_path)
    settings = _comfy(client, pkg)
    engine = client._transport.app.state.engine

    generation = await _generate(client, b["shot"], settings)
    spec = await _stored_spec(engine, generation.id)

    assert spec["schema_version"] == 4
    observation = spec["world_observation"]
    assert observation["spec"]["shot_revision"]["id"] == (
        revision.id if revision is not None else (
            await _latest_revision_id(engine, b["shot"])))
    assert observation["negotiation"]["verdict"] == "SUPPORTED"
    assert observation["spec"]["captured_domains"][
        "production_world_hash"] is not None

    # the recovered M10 plane: the schema-3 lower meaning carries the
    # exact spatial realization the schema-5 path produces
    lower = spec["lower_schema_3"]
    assert lower["schema_version"] == 3
    assert lower["spatial_realization"]["derived_artifacts"], (
        "the embedded M10 world-depth stream must be materialized "
        "through the established M10 path")
    assert await _world_depth_blob(engine, generation.id)

    from soloring.observation.workflow_spec import parse_workflow_spec_v4

    parse_workflow_spec_v4(spec)


async def test_schema6_mesh_changes_control_bytes_vs_m10_twin(
        client, tmp_path):
    """Anti-wrapper at the integration seam (frozen §40): a retained mesh
    in the schema-6 observation CHANGES the actual world-depth control
    bytes consumed for the observation binding — the M14 observation
    artifact digest differs from the M10-only twin's, and the mesh
    contributes non-background pixels (MAT:08 evidence at the service
    level; the zero-mesh byte-identity proof lives at the materializer
    seam in tests/test_m14_mesh_depth.py)."""
    b, _sel, _rev, _snapshot = await _schema6_world(
        client, tag=b"m14b3-antiwrapper")
    pkg = await _observation_package(tmp_path)
    settings = _comfy(client, pkg)
    engine = client._transport.app.state.engine

    gen6 = await _generate(client, b["shot"], settings)

    # the schema-5 twin: same world/plan/camera, no M13 selection
    twin = await _twin_schema5_shot(client, b)
    revision, _ = await _capture(client, twin)
    assert json.loads(revision.snapshot_json)["schema_version"] == 5
    gen5 = await _generate(client, twin, settings)

    observation_blob = (await _observation_world_blob(engine, gen6.id))
    m10_twin_blob = await _world_depth_blob(engine, gen5.id)
    assert observation_blob is not None, (
        "the schema-6 mesh observation must bind an observation artifact")
    assert observation_blob != m10_twin_blob, (
        "the retained mesh must change the world-depth control bytes "
        "(anti-wrapper: metadata-only storage cannot close M14)")


async def _observation_world_blob(engine, generation_id: str):
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT blob_hash FROM "
            "generation_derived_observation_inputs WHERE generation_id = "
            ":g AND artifact_role = 'observation.world_depth'"),
            {"g": generation_id})).mappings().one_or_none()
    return row["blob_hash"] if row else None


async def _twin_schema5_shot(client, b) -> str:
    import uuid

    from soloring.spatial import plans as plan_svc

    pid = b["pid"]
    _f = _factory(client)
    engine = client._transport.app.state.engine
    shot = str(uuid.uuid4())
    seq, scene = str(uuid.uuid4()), str(uuid.uuid4())
    async with engine.connect() as conn:
        await conn.execute(text(
            "INSERT INTO sequences (id, project_id, position, title) "
            "VALUES (:q, :p, (SELECT COALESCE(MAX(position),0)+1 FROM "
            "sequences WHERE project_id=:p), 'S2')"),
            {"q": seq, "p": pid})
        await conn.execute(text(
            "INSERT INTO scenes (id, sequence_id, position, title) "
            "VALUES (:c, :q, 0, 'C2')"), {"c": scene, "q": seq})
        await conn.execute(text(
            "INSERT INTO shots (id, project_id, shot_number, subject, "
            "duration_ms, scene_id, scene_position) VALUES (:s, :p, "
            "(SELECT COALESCE(MAX(shot_number),0)+1 FROM shots WHERE "
            "project_id=:p), 'twin', 5000, :c, 0)"),
            {"s": shot, "p": pid, "c": scene})
        for i, eid in enumerate((b["loc"], b["eva"])):
            await conn.execute(text(
                "INSERT INTO shot_entity_dependencies (shot_id, entity_id, "
                "role, position) VALUES (:s, :e, 'cast', :i)"),
                {"s": shot, "e": eid, "i": i})
        await conn.commit()
    await plan_svc.put_spatial_plan(
        _f(), shot, expected_plan_hash=None, plan_raw={
            "schema_version": 1,
            "spatial_world_id": b["world"]["id"],
            "camera": json.loads(json.dumps(_TWIN_CAM)),
            "blocking": [],
            "axis_constraint": None,
        })
    return shot


# the twin uses the exact camera of _full_m13_world's plan so both
# executions rasterize identical frames
_TWIN_CAM = {
    "projection": "perspective",
    "focal_length_um": 50000,
    "sensor_width_um": 36000,
    "sensor_height_um": 20250,
    "keyframes": [{
        "time_ms": 0,
        "transform": {"translation_mm": [-3000, 1650, 4200],
                      "rotation_udeg": [0, 0, 0]}}],
}


# ---- M14-EXEC:01 schema-4 lower_schema_3 uses one shared helper ---------

def test_m14_exec_01(monkeypatch, tmp_path) -> None:
    """The wrapper delegates lower-schema validation to THE frozen
    schema-3 validator and embeds the schema-3 value verbatim."""
    from soloring.observation import workflow_spec as workflow_spec_module
    from soloring.observation.workflow_spec import (
        build_workflow_spec_v4,
        parse_workflow_spec_v4,
    )
    from tests.test_m13_shot_capture import CAM  # noqa: F401  (parity)

    lower = _minimal_v3_spec()
    observation = _minimal_observation_pairing()

    import soloring.spatial.spec3 as spec3

    real_validate = spec3.validate_spec_v3
    calls = []

    def spy_validate(value):
        calls.append(value)
        return real_validate(value)

    monkeypatch.setattr(spec3, "validate_spec_v3", spy_validate)

    spec = build_workflow_spec_v4(
        lower_schema_3=lower,
        observation_spec=observation["spec"],
        negotiation_result=observation["negotiation"],
        profile_hash=observation["profile_hash"],
        capability_contract_hash=observation["capability_contract_hash"])
    assert calls and calls[0] is lower, (
        "the frozen schema-3 validator must be on the call path")
    assert spec["lower_schema_3"] == lower, (
        "the schema-3 value is embedded verbatim, never rebuilt")
    assert parse_workflow_spec_v4(spec) == spec


def _minimal_v3_spec() -> dict:
    import hashlib
    import uuid

    def _hex(label: str) -> str:
        return hashlib.sha256(label.encode()).hexdigest()

    return {
        "schema_version": 3,
        "workflow_id": "wan21_spatial_v1",
        "workflow_version": 1,
        "manifest_hash": _hex("manifest"),
        "inputs": {},
        "prompt": "A quiet hotel lobby at night.",
        "parameters": {"cfg": 5.0, "steps": 20},
        "outputs": [{"name": "video", "kind": "video",
                     "expected_count": 1, "accepted_media_types": None}],
        "model": {"id": "wan2.1-t2v-1.3b", "version": "fp16",
                  "execution_model_fingerprint_hash": _hex("fingerprint")},
        "spatial_realization": {
            "schema_version": 1,
            "spatial_continuity_hash": _hex("continuity"),
            "realization_profile_hash": _hex("profile"),
            "structured_bindings": [],
            "derived_artifacts": [{
                "input_key": "world_depth",
                "position": 0,
                "artifact_role": "spatial.world_depth",
                "derived_spatial_artifact_id": str(uuid.uuid4()),
                "spec_hash": _hex("d0-spec"),
                "runtime_fingerprint_hash": _hex("runtime"),
                "blob_hash": _hex("world-depth-blob"),
            }],
            "advisory_omissions": [],
        },
    }


def _minimal_observation_pairing() -> dict:
    from soloring.observation import negotiate
    from soloring.observation.compiler import compile_world_observation_spec

    import hashlib

    def _hex(label: str) -> str:
        return hashlib.sha256(label.encode()).hexdigest()

    shot_id = "00000000-0000-0000-0000-000000000201"
    shot_rev = "11111111-1111-1111-1111-111111111202"
    snapshot = {
        "schema_version": 6,
        "spatial_continuity": {
            "schema_version": 1,
            "spatial_world": {
                "spatial_world_id": shot_id,
                "requirement": "required",
                "spatial_world_state_id": shot_id,
                "spatial_world_revision_id": shot_rev,
                "spatial_world_revision_hash": _hex("world-rev"),
                "location_entity_id": shot_id,
                "location_entity_revision_id": shot_id,
                "world_snapshot": {"frames": [], "axes": []},
            },
            "staging": [],
            "shot_plan": {"camera": {"keyframes": []}},
        },
        "production_world": {
            "schema_version": 1,
            "binding": {"binding_id": shot_rev, "binding_hash": _hex("b"),
                        "value": {}},
            "instance_feature_states": [],
            "instance_spatial_states": [],
        },
    }
    spec = compile_world_observation_spec(
        shot_id=shot_id,
        shot_revision_id=shot_rev,
        plan_hash=_hex("plan"),
        captured_schema_6=snapshot,
        spatial_continuity_hash=_hex("continuity"),
        production_world_hash=_hex("world"),
        visual_reference_pack_hash=None,
        materializer_contract_hash=(
            "dd3511218c673e7f2727d8226c3d73bfd85222bd5f9a5edb3d2e477914"
            "6f66d0"),
    )
    block = json.loads(
        (FIXTURES / "m14-f06-realization-profile-observation-v1.json")
        .read_bytes().decode("utf-8"))
    negotiation = negotiate(spec, block)
    assert negotiation["verdict"] == "SUPPORTED"
    return {"spec": spec, "negotiation": negotiation,
            "profile_hash": _hex("profile"),
            "capability_contract_hash": canonical_hash(block)}


async def _latest_revision_id(engine, shot: str):
    async with engine.connect() as conn:
        return (await conn.execute(text(
            "SELECT id FROM shot_revisions WHERE shot_id = :s "
            "ORDER BY revision_number DESC LIMIT 1"),
            {"s": shot})).scalar_one()


# ---- M14-EXEC:02 materialization before Generation commit ------------------

async def test_m14_exec_02(client, tmp_path, monkeypatch):
    """M14-EXEC:02 pre-publication materialization completed before
    Generation commit (frozen §33.2 ordering).

    At the moment the Generation publication unit opens — the
    repository entry — the derived observation artifact row and its
    Blob bytes are ALREADY durable and zero Generation rows exist:
    materialization and publication ran to completion outside the
    writer fence, before the Generation transaction."""
    b, _sel, _rev, _snapshot = await _schema6_world(
        client, tag=b"m14-exec02")
    pkg = await _observation_package(tmp_path)
    settings = _comfy(client, pkg)
    engine = client._transport.app.state.engine

    from soloring.generation import repository as repo

    real_create = repo.create_generation
    observed: dict = {}

    async def _spy_create(session, draft, inputs, *args, **kwargs):
        async with engine.connect() as conn:
            rows = (await conn.execute(text(
                "SELECT id, blob_hash, provenance_hash FROM "
                "derived_observation_artifacts"))).mappings().all()
            observed["pre_commit_generation_count"] = (
                await conn.execute(text(
                    "SELECT COUNT(*) FROM generations WHERE shot_id = :s"),
                    {"s": b["shot"]})).scalar_one()
        assert rows, (
            "the observation artifact must exist before the publication "
            "unit opens")
        (observed["artifact"],) = [dict(r) for r in rows]
        blob = observed["artifact"]["blob_hash"]
        live_settings = client._transport.app.state.settings
        blob_path = (live_settings.blob_dir / "sha256" / blob[:2]
                     / blob[2:4] / blob)
        observed["blob_bytes"] = blob_path.read_bytes()
        return await real_create(session, draft, inputs, *args, **kwargs)

    monkeypatch.setattr(repo, "create_generation", _spy_create)
    generation = await _generate(client, b["shot"], settings)

    import hashlib

    assert observed["pre_commit_generation_count"] == 0, (
        "no Generation row may exist when the publication unit opens")
    assert hashlib.sha256(
        observed["blob_bytes"]).hexdigest() == (
        observed["artifact"]["blob_hash"]), (
        "the physically published Blob IS the artifact's content digest")

    # the committed binding references the exact PRE-committed artifact
    async with engine.connect() as conn:
        binding = (await conn.execute(text(
            "SELECT derived_observation_artifact_id, blob_hash FROM "
            "generation_derived_observation_inputs WHERE generation_id "
            "= :g"), {"g": generation.id})).mappings().one()
    assert binding["derived_observation_artifact_id"] == (
        observed["artifact"]["id"])
    assert binding["blob_hash"] == observed["artifact"]["blob_hash"]


# ---- M14-EXEC:03 publication unit atomicity --------------------------------

async def test_m14_exec_03(client, tmp_path, monkeypatch):
    """M14-EXEC:03 Generation + WorkflowSpec-4 + exact artifact binding
    atomic.

    A uniqueness violation fired INSIDE the publication unit (a second
    real insert of the same binding at the same coordinate) rolls the
    whole unit back: no Generation row, no WorkflowSpec, no binding
    survives. The owner-free artifact remains — publication precedes
    the Generation unit by design (§33.2/§33.3)."""
    b, _sel, _rev, _snapshot = await _schema6_world(
        client, tag=b"m14-exec03")
    pkg = await _observation_package(tmp_path)
    settings = _comfy(client, pkg)
    engine = client._transport.app.state.engine

    from soloring.errors import SoloRingError as _SRE
    from soloring.observation import publication

    real_insert = publication.insert_generation_binding
    calls = {"n": 0}

    async def _double_insert(conn, *, generation_id, binding):
        await real_insert(conn, generation_id=generation_id,
                          binding=binding)
        calls["n"] += 1
        if calls["n"] == 1:
            # the SAME real insert again: the table's own coordinate
            # uniqueness refuses inside the open publication unit
            await real_insert(conn, generation_id=generation_id,
                              binding=binding)

    monkeypatch.setattr(
        publication, "insert_generation_binding", _double_insert)

    with pytest.raises(_SRE):
        await _generate(client, b["shot"], settings)

    async with engine.connect() as conn:
        generation_count = (await conn.execute(text(
            "SELECT COUNT(*) FROM generations WHERE shot_id = :s"),
            {"s": b["shot"]})).scalar_one()
        input_count = (await conn.execute(text(
            "SELECT COUNT(*) FROM generation_inputs"))).scalar_one()
        spatial_count = (await conn.execute(text(
            "SELECT COUNT(*) FROM "
            "generation_derived_spatial_inputs"))).scalar_one()
        binding_count = (await conn.execute(text(
            "SELECT COUNT(*) FROM "
            "generation_derived_observation_inputs"))).scalar_one()
        artifact_count = (await conn.execute(text(
            "SELECT COUNT(*) FROM "
            "derived_observation_artifacts"))).scalar_one()
    assert generation_count == 0, "no half-Generation may survive"
    assert input_count == 0
    assert spatial_count == 0
    assert binding_count == 0, (
        "the failed binding insert leaves no binding row behind")
    assert artifact_count == 1, (
        "the owner-free artifact remains published — convergence "
        "preceded the Generation unit (RACE-07 posture)")
