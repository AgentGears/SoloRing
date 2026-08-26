"""M10E-D — schema-3 pure translation (frozen R3 §17).

build_comfy_prompt with the verified schema3_derived uploaded references:
exact manifest-v3 node/field binding, dispatch keyed on the derived
collection + spatial_bindings (never the inherited shot_reference
source-kind string), and the full fail-closed disagreement matrix
(E-060..E-066)."""
from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from soloring.executors.comfy.translate import (
    TranslationFailed,
    build_comfy_prompt,
)
from soloring.spatial import production_package as prod
from soloring.spatial.package3 import parse_manifest_v3

SPEC = {
    "schema_version": 3,
    "prompt": "p",
    "parameters": {},
    "model": {"id": "m", "version": "1",
              "execution_model_fingerprint_hash": "ab" * 32},
    "spatial_realization": {
        "spatial_continuity_hash": "9" * 64,
        "realization_profile_hash": "cd" * 32,
        "structured_bindings": [],
        "advisory_omissions": ["screen_direction_not_consumed"],
        "derived_artifacts": [
            {"input_key": "world_depth", "position": 0,
             "artifact_role": "spatial.world_depth",
             "derived_spatial_artifact_id": "a1",
             "spec_hash": "e" * 64,
             "runtime_fingerprint_hash": "f" * 64,
             "blob_hash": "01" * 32},
            {"input_key": "entity_depth_1", "position": 1,
             "artifact_role": "spatial.entity_depth",
             "derived_spatial_artifact_id": "a2",
             "spec_hash": "e" * 64,
             "runtime_fingerprint_hash": "f" * 64,
             "blob_hash": "02" * 32},
            {"input_key": "entity_depth_2", "position": 2,
             "artifact_role": "spatial.entity_depth",
             "derived_spatial_artifact_id": "a3",
             "spec_hash": "e" * 64,
             "runtime_fingerprint_hash": "f" * 64,
             "blob_hash": "03" * 32},
        ],
    },
}


@dataclass
class _V:
    input_key: str
    position: int
    artifact_role: str
    node: str
    field: str
    blob_hash: str
    local_path: str
    execution_reference: str | None = None
    frame_references: tuple[str, ...] = ()


def _derived(n=3):
    roles = ["spatial.world_depth", "spatial.entity_depth",
             "spatial.entity_depth"]
    keys = ["world_depth", "entity_depth_1", "entity_depth_2"]
    refs = ["sub/w1.png", "sub/e1.png", "sub/e2.png"]
    return [_V(keys[i], i, roles[i], "n", "f", f"{i:02d}" * 32,
               "p", refs[i]) for i in range(n)]


def _manifest():
    return parse_manifest_v3(prod.production_manifest_v3())


def _template():
    return prod.production_template()


def _build(derived=None, manifest=None, template=None, spec=None,
           materialized=()):
    return build_comfy_prompt(
        workflow_spec=spec or SPEC,
        manifest=manifest or _manifest(),
        template=template or _template(),
        materialized=list(materialized),
        generation_id="g", attempt_id="a", client_id="c",
        schema3_derived=derived,
    )


def test_binds_all_three_control_streams():
    payload = _build(derived=_derived())
    prompt = payload.prompt
    # frozen soloring.spatial.v1 consumption: each manifest node/field
    # receives the chain-head LINK; the uploaded reference enters through
    # the generated LoadImage node
    assert prompt["101"]["inputs"]["control_images"] == \
        ["world_depth::load::0", 0]
    assert prompt["111"]["inputs"]["control_images"] == \
        ["entity_depth_1::load::0", 0]
    assert prompt["121"]["inputs"]["control_images"] == \
        ["entity_depth_2::load::0", 0]
    assert prompt["world_depth::load::0"]["inputs"]["image"] == "sub/w1.png"
    assert prompt["entity_depth_1::load::0"]["inputs"]["image"] == \
        "sub/e1.png"
    assert prompt["entity_depth_2::load::0"]["inputs"]["image"] == \
        "sub/e2.png"
    # marker namespace intact; template parameters untouched
    assert payload.extra_data == {"soloring": {"generation_id": "g",
                                               "attempt_id": "a"}}
    assert prompt["60"]["inputs"]["scheduler"] == "unipc"


def test_multi_frame_control_expands_certified_chain():
    """A 17-frame D0 stream expands to LoadImage×17 + ImageBatch×16 with
    the chain-head link at the manifest node/field (certified §114
    consumption machinery, deterministic namespaced ids)."""
    d = _derived()
    d[0].frame_references = tuple(f"sub/w_{i:03d}.png" for i in range(17))
    payload = _build(derived=d)
    prompt = payload.prompt
    assert prompt["101"]["inputs"]["control_images"] == \
        ["world_depth::batch::16", 0]
    assert prompt["world_depth::load::7"]["inputs"]["image"] == \
        "sub/w_007.png"
    assert prompt["world_depth::batch::1"]["inputs"] == {
        "image1": ["world_depth::load::0", 0],
        "image2": ["world_depth::load::1", 0]}
    assert prompt["world_depth::batch::16"]["inputs"] == {
        "image1": ["world_depth::batch::15", 0],
        "image2": ["world_depth::load::16", 0]}


def test_expansion_node_collision_fails():
    d = _derived()
    template = _template()
    template["world_depth::load::0"] = {"class_type": "X", "inputs": {}}
    with pytest.raises(TranslationFailed, match="collides"):
        _build(derived=d, template=template)


def test_missing_derived_reference_fails():
    with pytest.raises(TranslationFailed, match="missing.*entity_depth_2"):
        _build(derived=_derived(2))


def test_extra_derived_reference_fails():
    with pytest.raises(TranslationFailed, match="extra"):
        d = _derived()
        d.append(_V("entity_depth_9", 3, "spatial.entity_depth", "n", "f",
                    "04" * 32, "p", "sub/x.png"))
        _build(derived=d)


def test_duplicate_derived_reference_fails():
    d = _derived()
    d[1] = d[0]
    with pytest.raises(TranslationFailed, match="duplicate"):
        _build(derived=d)


def test_role_position_disagreement_fails():
    d = _derived()
    d[1] = _V("entity_depth_1", 5, "spatial.entity_depth", "n", "f",
              "02" * 32, "p", "sub/e1.png")
    with pytest.raises(TranslationFailed, match="position/role"):
        _build(derived=d)


def test_manifest_node_missing_fails():
    m = _manifest()
    m["spatial_bindings"]["world_depth"]["node"] = "999"
    with pytest.raises(TranslationFailed, match="999"):
        _build(derived=_derived(), manifest=m)


def test_manifest_field_missing_fails():
    m = _manifest()
    m["spatial_bindings"]["entity_depth_2"]["field"] = "nope"
    with pytest.raises(TranslationFailed, match="nope"):
        _build(derived=_derived(), manifest=m)


def test_unsupported_binding_format_fails():
    m = _manifest()
    m["spatial_bindings"]["entity_depth_1"]["format"] = "other.v9"
    with pytest.raises(TranslationFailed, match="format"):
        _build(derived=_derived(), manifest=m)


def test_missing_upload_reference_fails():
    d = _derived()
    d[0] = _V("world_depth", 0, "spatial.world_depth", "n", "f",
              "01" * 32, "p", None)
    with pytest.raises(TranslationFailed, match="no uploaded"):
        _build(derived=d)


def test_spatial_key_never_enters_ordinary_materialization():
    """E-066/W1: the production manifest carries the inherited
    source.kind == 'shot_reference' metadata on every spatial input — a
    materialized ordinary input under that key must FAIL, never bind from
    the ShotReference/Asset path."""
    from soloring.executors.comfy.input_materializer import (
        MaterializedComfyInput,
    )

    m = _manifest()
    assert m["inputs"]["world_depth"]["source"]["kind"] == (
        "shot_reference")
    rogue = MaterializedComfyInput(
        input_key="world_depth", position=0, remote_name="rogue.png",
        subfolder="", blob_hash="01" * 32, asset_id=None)
    with pytest.raises(TranslationFailed,
                       match="ordinary materialized-input binding"):
        build_comfy_prompt(
            workflow_spec=SPEC, manifest=m, template=_template(),
            materialized=[rogue],
            generation_id="g", attempt_id="a", client_id="c",
            schema3_derived=_derived())


def test_two_sources_same_target_fails():
    """§17.4: an ordinary declaration cannot own a spatial node/field."""
    m = _manifest()
    m["inputs"]["rogue_ref"] = {
        "node": "101", "field": "control_images", "kind": "image",
        "required": True, "cardinality": 1,
        "source": {"kind": "shot_reference", "role": "primary"}}
    from soloring.executors.comfy.input_materializer import (
        MaterializedComfyInput,
    )

    ordinary = MaterializedComfyInput(
        input_key="rogue_ref", position=0, remote_name="r.png",
        subfolder="", blob_hash="07" * 32, asset_id=None)
    with pytest.raises(TranslationFailed, match="incompatible"):
        build_comfy_prompt(
            workflow_spec=SPEC, manifest=m, template=_template(),
            materialized=[ordinary],
            generation_id="g", attempt_id="a", client_id="c",
            schema3_derived=_derived())


def test_schema3_without_dict_manifest_fails():
    class _FakeV2:  # an object where a v3 dict is required
        inputs = {}
        parameters = {}
        outputs = {}
    with pytest.raises(TranslationFailed, match="manifest-v3"):
        build_comfy_prompt(
            workflow_spec=SPEC, manifest=_FakeV2(), template=_template(),
            materialized=[],
            generation_id="g", attempt_id="a", client_id="c",
            schema3_derived=_derived())


def test_legacy_v1_v2_translation_unchanged():
    """§17.3/E-014 posture: schema3_derived=None keeps the inherited
    object-model path byte-compatible (schema-1 shape smoke)."""
    from soloring.workflows.manifest import parse_manifest

    legacy_manifest = parse_manifest({
        "schema_version": "1", "workflow_id": "wf", "version": 1,
        "inputs": {"prompt": {"node": "3", "field": "positive_prompt"}},
        "parameters": {},
        "outputs": {"out": {"kind": "video", "node": "3"}}})
    payload = build_comfy_prompt(
        workflow_spec={"schema_version": 1, "prompt": "hi",
                       "parameters": {}},
        manifest=legacy_manifest,
        template={"3": {"class_type": "T", "inputs": {
            "positive_prompt": ""}}},
        materialized=[],
        generation_id="g", attempt_id="a", client_id="c")
    assert payload.prompt["3"]["inputs"]["positive_prompt"] == "hi"


# ----------------------------------------------- transport frame splitting --

async def test_transport_splits_retained_d0_blob_into_exact_frames(
        factory, engine, settings):
    """The frozen soloring.spatial.v1 consumption semantics at the
    transport seam: a retained 17-PNG D0 Blob uploads frame-per-file
    (17 uploads whose byte-concatenation IS the retained Blob, never
    re-encoded); arbitrary non-PNG content stays a single opaque upload."""
    from soloring.assets.blob_store import BlobStore
    from soloring.spatial import boxdepth
    from soloring.spatial.package3 import parse_manifest_v3
    from soloring.spatial import production_package as prod
    from soloring.spatial.worker_inputs import execute_schema3_derived_inputs

    from tests.test_m10a4_worker_rerun import (
        _mkblob,
        _seed_spatial_generation,
        _spec,
    )

    pack = {"schema_version": 1,
            "spatial_world": {"spatial_world_id": "w",
                              "requirement": "required",
                              "spatial_world_state_id": "s",
                              "spatial_world_revision_id": "r",
                              "spatial_world_revision_hash": "0" * 64,
                              "location_entity_id": "l",
                              "location_entity_revision_id": "lr",
                              "world_snapshot": {
                                  "frames": [], "axes": []}},
            "staging": [],
            "shot_plan": {"schema_version": 1, "spatial_world_id": "w",
                          "camera": {"projection": "perspective",
                                     "focal_length_um": 50000,
                                     "sensor_width_um": 36000,
                                     "sensor_height_um": 20250,
                                     "keyframes": [{"time_ms": 0,
                                                    "transform": {
                                                        "translation_mm": [
                                                            -3000, 1650,
                                                            4200],
                                                        "rotation_udeg": [
                                                            0, 0, 0]}}]},
                          "blocking": [], "axis_constraint": None}}
    frames = boxdepth.materialize(pack)
    blob_content = b"".join(frames)
    assert len(frames) == 17

    ids = await _seed_spatial_generation(factory, engine, settings)
    store = BlobStore(settings)
    # replace the synthetic blob with the real 17-frame D0 content at a
    # fresh content-addressed path, rebinding sibling + provenance rows
    import hashlib

    real_hash = hashlib.sha256(blob_content).hexdigest()
    import tempfile
    from pathlib import Path as P

    from sqlalchemy import text

    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(blob_content)
    await store.place(real_hash, P(f.name))
    async with factory() as session:
        conn_sw = await session.connection()
        await conn_sw.exec_driver_sql("PRAGMA defer_foreign_keys=ON")
        await session.execute(text(
            "INSERT OR IGNORE INTO blobs (hash, path, size_bytes, "
            "created_at) VALUES (:h, :p, :s, 't')"),
            {"h": real_hash, "p": str(store.path_for_hash(real_hash)),
             "s": len(blob_content)})
        await session.execute(text(
            "UPDATE derived_spatial_artifacts SET blob_hash = :h "
            "WHERE id = :a"),
            {"h": real_hash, "a": ids["artifact"]})
        await session.execute(text(
            "UPDATE generation_derived_spatial_inputs SET blob_hash = :h "
            "WHERE generation_id = :g"),
            {"h": real_hash, "g": ids["generation_id"]})
        await session.commit()

    uploads: list[tuple[str, str, bytes]] = []

    class _Rec:
        async def upload(self, *, source_path, filename, subfolder):
            data = source_path.read_bytes()
            uploads.append((filename, subfolder, data))
            return filename, subfolder

        async def upload_bytes(self, *, data, filename, subfolder):
            uploads.append((filename, subfolder, data))
            return filename, subfolder

    async with factory() as session:
        verified = await execute_schema3_derived_inputs(
            session, store, generation_id=ids["generation_id"],
            workflow_spec=_spec(ids["continuity"]),
            manifest_v3=parse_manifest_v3(prod.production_manifest_v3()),
            client=_Rec())
    assert len(uploads) == 17
    assert b"".join(data for _, _, data in uploads) == blob_content
    assert all(name.endswith(".png")
               for name, _, _ in uploads)
    assert [ref for ref in verified[0].frame_references] == [
        f"soloring-der-{ids['generation_id'][:8]}/{name}"
        for name, _, _ in uploads]
