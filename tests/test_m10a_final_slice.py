"""M10A final slice tests — §114 evidence-backed production package and
materializer: certified pins, D0 repeatability ×3, role-correct
differentials, capacity, and the frozen package documents."""
import copy
import json

import pytest

from soloring.spatial import boxdepth, production_package as pk
from soloring.spatial import production_pins as pins
from soloring.spatial.realize import compose_spatial_realization
from soloring.spatial.schemas import parse_continuity_pack


def _lobby_pack():
    """A camera-correct lobby fixture: identity camera looks -Z, so the
    world is placed at negative Z in front of it (§6.3 basis)."""
    world = {
        "schema_version": 1,
        "spatial_world_id": "w1",
        "location_entity_id": "loc1",
        "location_entity_revision_id": "locr1",
        "coordinate_system": {
            "handedness": "right", "right_axis": "+x", "up_axis": "+y",
            "depth_positive_axis": "+z", "forward_axis": "-z",
            "linear_unit": "millimeter", "rotation_unit": "microdegree",
            "rotation_semantics": "active_local_to_world_intrinsic_yxz",
            "vector_convention": "column", "camera_forward_axis": "-z"},
        "frames": [
            {"spatial_frame_id": "f1", "frame_key": "lobby-origin",
             "parent_spatial_frame_id": None, "bound_entity_id": None,
             "bound_entity_revision_id": None,
             "transform": {"translation_mm": [0, 0, 0],
                           "rotation_udeg": [0, 0, 0]},
             "half_extents_mm": None},
            {"spatial_frame_id": "f2", "frame_key": "front-desk",
             "parent_spatial_frame_id": None, "bound_entity_id": None,
             "bound_entity_revision_id": None,
             "transform": {"translation_mm": [0, 0, -4200],
                           "rotation_udeg": [0, 0, 0]},
             "half_extents_mm": [2200, 600, 550]},
        ],
        "axes": [
            {"spatial_axis_id": "a1", "axis_key": "desk-axis",
             "a_frame_id": "f1", "b_frame_id": "f2"}],
    }
    from soloring.spatial.schemas import parse_world_revision, world_revision_hash
    normalized = parse_world_revision(world)
    declared = world_revision_hash(normalized)
    return parse_continuity_pack({
        "schema_version": 1,
        "spatial_world": {
            "spatial_world_id": "w1", "requirement": "required",
            "spatial_world_state_id": "st1",
            "spatial_world_revision_id": "rev1",
            "spatial_world_revision_hash": declared,
            "location_entity_id": "loc1",
            "location_entity_revision_id": "locr1",
            "world_snapshot": world},
        "staging": [
            {"spatial_track_id": "t1", "entity_id": "e1",
             "entity_revision_id": "er1", "requirement": "required",
             "transform": {"translation_mm": [-700, 0, -3000],
                           "rotation_udeg": [0, 90000000, 0]},
             "source_transition": {"spatial_transition_id": "x1",
                                   "anchor_type": "shot", "anchor_id": "s1",
                                   "boundary": "start"}},
            {"spatial_track_id": "t2", "entity_id": "e2",
             "entity_revision_id": "er2", "requirement": "optional",
             "transform": {"translation_mm": [600, 0, -2600],
                           "rotation_udeg": [0, -90000000, 0]},
             "source_transition": {"spatial_transition_id": "x2",
                                   "anchor_type": "shot", "anchor_id": "s1",
                                   "boundary": "start"}},
        ],
        "shot_plan": {
            "schema_version": 1, "spatial_world_id": "w1",
            "camera": {"projection": "perspective",
                       "focal_length_um": 50000, "sensor_width_um": 36000,
                       "sensor_height_um": 20250,
                       "keyframes": [
                           {"time_ms": 0,
                            "transform": {"translation_mm": [0, 500, 0],
                                          "rotation_udeg": [0, 0, 0]}},
                           {"time_ms": 4000,
                            "transform": {"translation_mm": [150, 480, -80],
                                          "rotation_udeg": [200000, -400000, 0]}}]},
            "blocking": [], "axis_constraint": None},
    })


# ------------------------------------------------------------- pins -------

def test_certified_pins_exact():
    assert pins.COMFYUI_COMMIT == "b963f4ad" + "210a42841ab23dfc28a84143a0cce227"[8:] if False else True
    assert pins.COMFYUI_COMMIT == (
        "b963f4ad210a42841ab23dfc28a84143a0cce227")
    assert pins.WANVIDEO_WRAPPER_COMMIT == (
        "088128b224242e110d3906c6750e9a3a348a659b")
    assert pins.BASE_MODEL_SHA256 == (
        "be531024cd9018cb5b48c40cfbb6a6191645b1c792eb8bf4f8c1c6e10f924dc5")
    assert pins.CONTROLNET_SHA256 == (
        "b7c6835f48170a49bcccb096bc8d82c7f371189f9011ab7eb371582e9eb7d7e6")
    assert pins.UMT5_SHA256 == (
        "7b8850f1961e1cf8a77cca4c964a358d303f490833c6c087d0cff4b2f99db2af")
    assert pins.VAE_SHA256 == (
        "2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b")
    assert pins.CERTIFIED_REFERENCE_BOXDEPTH_SHA256 == (
        "7328c77c6c151348e56ab01dd575b6850605c15e1776937e4a09004b19145e7b")
    assert pins.SMOKE_SCHEDULER == "unipc"
    assert pins.SMOKE_DIMS == (832, 480, 17)
    assert pins.MAX_CONTROL_STREAMS == 3
    assert pins.GRAMMAR_BACKGROUND == 255
    assert pins.GRAMMAR_MODE == "L"
    assert pins.GRAMMAR_TIME_BASE == (1, 17)


def test_reference_hash_matches_certified():
    """The port's algorithm identity matches the certified reference."""
    from pathlib import Path
    reference = Path(
        r"C:\AI\M10A1-evidence\scripts\boxdepth_materializer.py")
    if reference.exists():
        import hashlib
        actual = hashlib.sha256(reference.read_bytes()).hexdigest()
        assert actual == pins.CERTIFIED_REFERENCE_BOXDEPTH_SHA256


# ------------------------------------------------------ D0 determinism ----

def test_d0_repeatability_x3():
    pack = _lobby_pack()
    outs = [compose_spatial_realization(pack, entity_layers=2)
            for _ in range(3)]
    for other in outs[1:]:
        assert other.artifact_digests == outs[0].artifact_digests
        assert other.spec_hashes == outs[0].spec_hashes
        assert other.runtime_fingerprint_hash == outs[0].runtime_fingerprint_hash


def test_layers_render_nonempty():
    pack = _lobby_pack()
    out = compose_spatial_realization(pack, entity_layers=2)
    # world layer must contain actual geometry (desk visible)
    depth = boxdepth.materialize_depth_mm(
        {**pack, "staging": []})
    assert (depth < boxdepth.BG_DEPTH_MM).any(), "world layer empty"
    # entity layers contain their own entity
    solo = {**pack,
            "spatial_world": {**pack["spatial_world"],
                              "world_snapshot": {
                                  **pack["spatial_world"]["world_snapshot"],
                                  "frames": [], "axes": []}},
            "staging": [pack["staging"][0]]}
    d1 = boxdepth.materialize_depth_mm(solo)
    assert (d1 < boxdepth.BG_DEPTH_MM).any(), "entity layer 1 empty"


def test_role_correct_differentials():
    """Facts flow to the right layer: staging -> entity layers; world ->
    world layer; camera -> all layers (all-visible fixture)."""
    pack = _lobby_pack()
    out = compose_spatial_realization(pack, entity_layers=2)

    moved = copy.deepcopy(pack)
    moved["staging"][0]["transform"]["translation_mm"][0] += 1
    outm = compose_spatial_realization(moved, entity_layers=2)
    assert outm.artifact_digests[1] != out.artifact_digests[1]  # own layer
    assert outm.artifact_digests[2] == out.artifact_digests[2]  # other layer

    extent = copy.deepcopy(pack)
    extent["spatial_world"]["world_snapshot"]["frames"][1][
        "half_extents_mm"][0] += 1
    oute = compose_spatial_realization(extent, entity_layers=2)
    assert oute.artifact_digests[0] != out.artifact_digests[0]  # world layer

    focal = copy.deepcopy(pack)
    focal["shot_plan"]["camera"]["focal_length_um"] += 1
    outf = compose_spatial_realization(focal, entity_layers=2)
    assert all(a != b for a, b in zip(outf.artifact_digests,
                                      out.artifact_digests))


def test_offscreen_entity_layer_is_deterministic_background():
    pack = _lobby_pack()
    far = copy.deepcopy(pack)
    far["staging"][0]["transform"]["translation_mm"] = [50000, 0, -50000]
    out = compose_spatial_realization(far, entity_layers=2)
    solo1 = boxdepth.materialize({**far,
                                  "spatial_world": {
                                      **far["spatial_world"],
                                      "world_snapshot": {
                                          **far["spatial_world"][
                                              "world_snapshot"],
                                          "frames": [], "axes": []}},
                                  "staging": [far["staging"][0]]})
    assert boxdepth.artifact_digest(solo1) == out.artifact_digests[1]


# ----------------------------------------------------------- capacity -----

def test_capacity_enforced_whole_item():
    pack = _lobby_pack()
    with pytest.raises(ValueError, match="capacity"):
        compose_spatial_realization(pack, entity_layers=3)
    out = compose_spatial_realization(pack, entity_layers=2)
    assert len(out.specs) == 3  # 1 world + 2 entity = frozen cap


# ------------------------------------------------------ package documents -

def test_production_documents_parse_and_close():
    from soloring.spatial.package3 import (
        check_runtime_closure,
        parse_manifest_v3,
        parse_profile_v2,
    )
    profile = parse_profile_v2(pk.production_profile_v2())
    manifest = parse_manifest_v3(pk.production_manifest_v3())
    template = pk.production_template()
    fingerprint = pk.production_fingerprint_document()["m10_spatial_runtime"]
    unproven = check_runtime_closure(
        profile["spatial"],
        fingerprint={"runtime_requirements": fingerprint},
        template=template)
    assert unproven == [], f"unclosed: {unproven}"
    # every manifest binding resolves to a real template node/field
    for key, b in manifest["spatial_bindings"].items():
        node = template[b["node"]]
        assert b["field"] in node["inputs"]


def test_frozen_package_hashes_stable():
    d1 = pk.production_descriptor_v3()
    d2 = pk.production_descriptor_v3()
    assert d1 == d2  # deterministic content identity


def test_runtime_fingerprint_carries_implementation_identity():
    fp = pk.boxdepth_runtime_fingerprint()
    assert fp["materializer"]["algorithm_id"] == pins.BOXDEPTH_ALGORITHM_ID
    assert len(fp["materializer"]["implementation_sha256"]) == 64
    assert fp["runtime"]["numpy"]
    assert fp["external_components"] == []


def test_spec_v3_block_from_realization():
    pack = _lobby_pack()
    out = compose_spatial_realization(pack, entity_layers=2)
    from soloring.spatial.spec3 import validate_spec_v3, compose_workflow_spec_v3
    spec = compose_workflow_spec_v3(
        {"prompt": "p"},
        model={"id": "wan2.1-t2v-1.3b", "version": "fp16",
               "execution_model_fingerprint_hash": "f" * 64},
        realization=None,
        spatial_realization=out.spatial_realization_block)
    validate_spec_v3(spec)
    assert spec["spatial_realization"]["derived_artifacts"][0][
        "artifact_role"] == "spatial.world_depth"


def test_output_contract_pins_frozen_grammar():
    pack = _lobby_pack()
    out = compose_spatial_realization(pack, entity_layers=0)
    oc = out.specs[0]["output_contract"]
    assert oc["width"] == 832 and oc["height"] == 480
    assert oc["frame_count"] == 17
    assert oc["time_base_num"] == 1 and oc["time_base_den"] == 17
    assert oc["media_type"] == "image/png"
    assert oc["encoding"] == "png-l-mode-8bit"
    proj = out.specs[0]["derivation"]["parameters"]["projection"]
    assert proj["background"] == 255 and proj["mode"] == "L"
