"""M10A-4 focused tests — canonical authority schemas (directive §9)."""
import pytest

from soloring.spatial import schemas as S


def _world_doc():
    return {
        "schema_version": 1,
        "spatial_world_id": "w1",
        "location_entity_id": "loc1",
        "location_entity_revision_id": "locr1",
        "coordinate_system": {
            "handedness": "right", "right_axis": "+x", "up_axis": "+y",
            "depth_positive_axis": "+z", "forward_axis": "-z",
            "linear_unit": "millimeter", "rotation_unit": "microdegree",
            "rotation_semantics": "active_local_to_world_intrinsic_yxz",
            "vector_convention": "column", "camera_forward_axis": "-z",
        },
        "frames": [
            {"spatial_frame_id": "f2", "frame_key": "desk",
             "parent_spatial_frame_id": None, "bound_entity_id": None,
             "bound_entity_revision_id": None,
             "transform": {"translation_mm": [0, 0, 4200],
                           "rotation_udeg": [0, 0, 0]},
             "half_extents_mm": [2200, 600, 550]},
            {"spatial_frame_id": "f1", "frame_key": "lobby-origin",
             "parent_spatial_frame_id": None, "bound_entity_id": None,
             "bound_entity_revision_id": None,
             "transform": {"translation_mm": [0, 0, 0],
                           "rotation_udeg": [0, 0, 0]},
             "half_extents_mm": None},
        ],
        "axes": [
            {"spatial_axis_id": "a1", "axis_key": "desk-axis",
             "a_frame_id": "f1", "b_frame_id": "f2"},
        ],
    }


def _plan_doc():
    return {
        "schema_version": 1,
        "spatial_world_id": "w1",
        "camera": {
            "projection": "perspective", "focal_length_um": 50000,
            "sensor_width_um": 36000, "sensor_height_um": 20250,
            "keyframes": [
                {"time_ms": 0, "transform": {"translation_mm": [0, 1650, 4200],
                                             "rotation_udeg": [0, 0, 0]}},
                {"time_ms": 4000, "transform": {"translation_mm": [10, 1650, 4200],
                                                "rotation_udeg": [90000000, 0, 0]}},
            ],
        },
        "blocking": [
            {"spatial_track_id": "t2", "screen_direction": "left_to_right",
             "keyframes": [{"time_ms": 0,
                            "transform": {"translation_mm": [-900, 0, 1800],
                                          "rotation_udeg": [0, 0, 0]}}]},
            {"spatial_track_id": "t1", "screen_direction": "unspecified",
             "keyframes": [{"time_ms": 0,
                            "transform": {"translation_mm": [900, 0, 1800],
                                          "rotation_udeg": [0, 0, 0]}}]},
        ],
        "axis_constraint": {"spatial_axis_id": "a1", "camera_side": "positive"},
    }


# ---- world revision -------------------------------------------------------

def test_world_snapshot_valid_and_canonically_ordered():
    doc = S.parse_world_revision(_world_doc())
    keys = [f["frame_key"] for f in doc["frames"]]
    assert keys == sorted(keys)  # desk < lobby-origin
    assert doc["axes"][0]["axis_key"] == "desk-axis"
    assert S.world_revision_hash(doc) == S.world_revision_hash(
        S.parse_world_revision(_world_doc()))


def test_world_snapshot_shuffled_input_same_hash():
    import copy, json
    a = S.parse_world_revision(_world_doc())
    b = copy.deepcopy(_world_doc())
    b["frames"].reverse()
    b2 = S.parse_world_revision(b)
    assert S.world_revision_hash(a) == S.world_revision_hash(b2)


def test_world_parent_cycle_rejected():
    doc = _world_doc()
    doc["frames"][0]["parent_spatial_frame_id"] = "f2"
    doc["frames"][1]["parent_spatial_frame_id"] = "f1"
    with pytest.raises(S.SchemaInvalid, match="cyclic|absent"):
        S.parse_world_revision(doc)


def test_world_absent_parent_rejected():
    doc = _world_doc()
    doc["frames"][0]["parent_spatial_frame_id"] = "ghost"
    with pytest.raises(S.SchemaInvalid, match="absent"):
        S.parse_world_revision(doc)


def test_world_duplicate_frame_key_rejected():
    doc = _world_doc()
    doc["frames"][1]["frame_key"] = doc["frames"][0]["frame_key"]
    with pytest.raises(S.SchemaInvalid, match="duplicate frame_key"):
        S.parse_world_revision(doc)


def test_world_unknown_field_rejected():
    doc = _world_doc()
    doc["frames"][0]["surprise"] = 1
    with pytest.raises(S.SchemaInvalid, match="unknown fields"):
        S.parse_world_revision(doc)


def test_world_invalid_transform_and_extents():
    doc = _world_doc()
    doc["frames"][0]["transform"]["rotation_udeg"] = [0.5, 0, 0]
    with pytest.raises(S.SchemaInvalid):
        S.parse_world_revision(doc)
    doc = _world_doc()
    doc["frames"][0]["half_extents_mm"] = [10, 0, 5]
    with pytest.raises(S.SchemaInvalid, match="positive"):
        S.parse_world_revision(doc)


def test_world_axis_endpoints_must_differ_and_be_included():
    doc = _world_doc()
    doc["axes"][0]["b_frame_id"] = "f1"
    with pytest.raises(S.SchemaInvalid, match="differ"):
        S.parse_world_revision(doc)
    doc["axes"][0]["b_frame_id"] = "ghost"
    with pytest.raises(S.SchemaInvalid, match="not an included frame"):
        S.parse_world_revision(doc)


def test_world_coordinate_system_frozen():
    doc = _world_doc()
    doc["coordinate_system"]["linear_unit"] = "meter"
    with pytest.raises(S.SchemaInvalid, match="frozen"):
        S.parse_world_revision(doc)


# ---- shot plan ------------------------------------------------------------

def test_plan_valid_and_blocking_canonical_order():
    doc = S.parse_shot_plan(_plan_doc(), duration_ms=5000)
    tracks = [b["spatial_track_id"] for b in doc["blocking"]]
    assert tracks == sorted(tracks)


def test_plan_first_keyframe_must_be_zero():
    doc = _plan_doc()
    doc["camera"]["keyframes"][0]["time_ms"] = 100
    with pytest.raises(S.SchemaInvalid, match="exactly time_ms=0"):
        S.parse_shot_plan(doc, duration_ms=5000)


def test_plan_null_duration_only_t0():
    doc = _plan_doc()
    with pytest.raises(S.SchemaInvalid, match="duration is NULL"):
        S.parse_shot_plan(doc, duration_ms=None)


def test_plan_times_strictly_increasing():
    doc = _plan_doc()
    doc["camera"]["keyframes"][1]["time_ms"] = 0
    with pytest.raises(S.SchemaInvalid, match="strictly increasing"):
        S.parse_shot_plan(doc, duration_ms=5000)


def test_plan_time_exceeds_duration():
    doc = _plan_doc()
    with pytest.raises(S.SchemaInvalid, match="duration"):
        S.parse_shot_plan(doc, duration_ms=3000)


def test_plan_bad_optics_and_direction():
    doc = _plan_doc()
    doc["camera"]["focal_length_um"] = 0
    with pytest.raises(S.SchemaInvalid):
        S.parse_shot_plan(doc, duration_ms=5000)
    doc = _plan_doc()
    doc["blocking"][0]["screen_direction"] = "diagonal"
    with pytest.raises(S.SchemaInvalid, match="screen_direction"):
        S.parse_shot_plan(doc, duration_ms=5000)


# ---- continuity pack ------------------------------------------------------

def _pack_doc():
    world = _world_doc()
    from soloring.domain.canonical import canonical_hash
    return {
        "schema_version": 1,
        "spatial_world": {
            "spatial_world_id": "w1", "requirement": "required",
            "spatial_world_state_id": "st1",
            "spatial_world_revision_id": "rev1",
            "spatial_world_revision_hash": canonical_hash(world),
            "location_entity_id": "loc1",
            "location_entity_revision_id": "locr1",
            "world_snapshot": world,
        },
        "staging": [
            {"spatial_track_id": "t2", "entity_id": "e2",
             "entity_revision_id": "er2", "requirement": "required",
             "transform": {"translation_mm": [1, 2, 3],
                           "rotation_udeg": [0, 0, 0]},
             "source_transition": {"spatial_transition_id": "x1",
                                   "anchor_type": "shot", "anchor_id": "s1",
                                   "boundary": "start"}},
            {"spatial_track_id": "t1", "entity_id": "e1",
             "entity_revision_id": "er1", "requirement": "optional",
             "transform": {"translation_mm": [4, 5, 6],
                           "rotation_udeg": [0, 0, 0]},
             "source_transition": {"spatial_transition_id": "x2",
                                   "anchor_type": "shot", "anchor_id": "s1",
                                   "boundary": "start"}},
        ],
        "shot_plan": {
            "schema_version": 1, "spatial_world_id": "w1",
            "camera": {"projection": "perspective", "focal_length_um": 50000,
                       "sensor_width_um": 36000, "sensor_height_um": 20250,
                       "keyframes": [{"time_ms": 0,
                                      "transform": {"translation_mm": [0, 0, 0],
                                                    "rotation_udeg": [0, 0, 0]}}]},
            "blocking": [],
            "axis_constraint": None,
        },
    }


def test_pack_valid_and_staging_canonical_order():
    doc = S.parse_continuity_pack(_pack_doc())
    ents = [st["entity_id"] for st in doc["staging"]]
    assert ents == sorted(ents)


def test_pack_embedded_world_hash_corruption():
    doc = _pack_doc()
    doc["spatial_world"]["spatial_world_revision_hash"] = "0" * 64
    with pytest.raises(S.SchemaInvalid, match="does not hash"):
        S.parse_continuity_pack(doc)


def test_pack_embedded_plan_corruption():
    doc = _pack_doc()
    doc["shot_plan"]["camera"]["keyframes"][0]["time_ms"] = 7
    with pytest.raises(S.SchemaInvalid):
        S.parse_continuity_pack(doc)


def test_pack_duplicate_staging_rejected():
    doc = _pack_doc()
    doc["staging"][1]["spatial_track_id"] = doc["staging"][0]["spatial_track_id"]
    doc["staging"][1]["entity_id"] = doc["staging"][0]["entity_id"]
    with pytest.raises(S.SchemaInvalid, match="duplicate staging"):
        S.parse_continuity_pack(doc)
