"""M14A-1 — WorldObservationSpec schema 1 tests (frozen R2 §§8.5/10/11).

Strict grammar, canonical ordering/hashing, duplicate/conflicting-
coordinate rejection, compiler emission matrix over captured schema-6
authority, and the schema-6-first-class / no-current-resolver input
discipline (M14-OBS cells 01-08, 11, 12, 13, 16).
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path

import pytest

from soloring.errors import SoloRingError
from soloring.observation import (
    build_world_observation_spec,
    compile_world_observation_spec,
    parse_world_observation_spec,
    requirement_order_key,
    world_observation_spec_bytes,
    world_observation_spec_hash,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "m14"

SHOT_ID = "00000000-0000-0000-0000-000000000101"
SHOT_REV_ID = "11111111-1111-1111-1111-111111111111"
OCC_ID = "22222222-2222-2222-2222-222222222222"
WORLD_REV_ID = "55555555-5555-5555-5555-555555555555"
BINDING_ID = "66666666-6666-6666-6666-666666666666"
PI_OCC_ID = "88888888-8888-8888-8888-888888888888"
FEATURE_ID = "99999999-9999-9999-9999-999999999999"
CONTRACT_HASH = ("dd3511218c673e7f2727d8226c3d73bfd85222bd5f9a5edb3d"
                 "2e4779146f66d0")


def _hex(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _golden_spec() -> dict:
    return json.loads(
        (FIXTURES / "m14-f06-world-observation-spec-v1.json")
        .read_bytes().decode("utf-8"))


def _pins() -> dict:
    return json.loads(
        (FIXTURES / "m14_pins.json").read_text(encoding="utf-8"))


def _spatial_pack(frames: list[dict]) -> dict:
    return {
        "schema_version": 1,
        "spatial_world": {
            "spatial_world_id": "aaaaaaa1-0000-0000-0000-000000000001",
            "requirement": "required",
            "spatial_world_state_id":
                "aaaaaaa2-0000-0000-0000-000000000001",
            "spatial_world_revision_id": WORLD_REV_ID,
            "spatial_world_revision_hash": _hex("world-revision"),
            "location_entity_id": "aaaaaaa3-0000-0000-0000-000000000001",
            "location_entity_revision_id":
                "aaaaaaa4-0000-0000-0000-000000000001",
            "world_snapshot": {"frames": frames, "axes": []},
        },
        "staging": [],
        "shot_plan": {"camera": {"keyframes": []}},
    }


def _frame(extents: list[int] | None) -> dict:
    return {
        "frame_key": "lobby",
        "spatial_frame_id": "bbbbbbb1-0000-0000-0000-000000000001",
        "half_extents_mm": extents,
        "transform": {"translation_mm": [0, 0, 0],
                      "rotation_udeg": [0, 0, 0]},
        "bound_entity_id": None,
    }


def _feature_state(key: str) -> dict:
    return {
        "composition_id": "ccccccc1-0000-0000-0000-000000000001",
        "occurrence_id": PI_OCC_ID,
        "feature_id": FEATURE_ID,
        "feature_key": key,
        "feature_kind": "enumeration",
        "value_type": "string",
        "unit": None,
        "value": "teal",
        "value_hash": _hex(f"feature-{key}"),
        "source_anchor": {
            "anchor_type": "boundary",
            "anchor_id": "ccccccc2-0000-0000-0000-000000000001",
            "boundary": "shot_start",
        },
    }


def _production_world(feature_keys: list[str]) -> dict:
    return {
        "schema_version": 1,
        "binding": {
            "binding_id": BINDING_ID,
            "binding_hash": _hex("binding"),
            "value": {},
        },
        "instance_feature_states": [
            _feature_state(key) for key in feature_keys],
        "instance_spatial_states": [],
    }


def _schema6(*, spatial=None, visual=None, production_world=None) -> dict:
    # Schema 6 is the schema-5 base plus a selected M13 world: there is
    # no schema 6 without production_world content (frozen M13 §17.2),
    # so the helper always wraps with the pack (empty when not given).
    base: dict = {"schema_version": 5, "intent": {}, "references": [],
                  "continuity": {}}
    if spatial is not None:
        base["spatial_continuity"] = spatial
    if visual is not None:
        base["visual_reference_pack"] = visual
    if production_world is None:
        production_world = _production_world([])
    return {"schema_version": 6,
            **{k: v for k, v in base.items() if k != "schema_version"},
            "production_world": production_world}


def _compile(snapshot: dict, *, spatial_hash=None, world_hash=None,
             visual_hash=None) -> dict:
    if world_hash is None:
        world_hash = _hex("world")
    return compile_world_observation_spec(
        shot_id=SHOT_ID,
        shot_revision_id=SHOT_REV_ID,
        plan_hash=_hex("plan"),
        captured_schema_6=snapshot,
        spatial_continuity_hash=spatial_hash,
        production_world_hash=world_hash,
        visual_reference_pack_hash=visual_hash,
        materializer_contract_hash=CONTRACT_HASH,
    )


def _full_snapshot() -> dict:
    return _schema6(
        spatial=_spatial_pack([_frame([1200, 300, 300])]),
        visual={"schema_version": 2, "anchors": []},
        production_world=_production_world(["wardrobe_color"]),
    )


def _properties(spec: dict) -> list[str]:
    return [req["property"] for req in spec["requirements"]]


# ---- M14-OBS:01 strict root grammar --------------------------------------

def test_m14_obs_01() -> None:
    parse_world_observation_spec(_golden_spec())

    bad = copy.deepcopy(_golden_spec())
    bad["surprise"] = 1
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(bad)

    bad = copy.deepcopy(_golden_spec())
    del bad["captured_domains"]
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(bad)

    bad = copy.deepcopy(_golden_spec())
    bad["schema_version"] = 2
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(bad)

    bad = copy.deepcopy(_golden_spec())
    bad["compiler"]["id"] = "other.compiler"
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(bad)

    bad = copy.deepcopy(_golden_spec())
    bad["shot_revision"]["plan_hash"] = bad["shot_revision"][
        "plan_hash"].upper()
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(bad)

    bad = copy.deepcopy(_golden_spec())
    bad["captured_domains"]["spatial_continuity_hash"] = "nothex"
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(bad)

    bad = copy.deepcopy(_golden_spec())
    bad["policy"]["permitted_inference"] = list(reversed(
        bad["policy"]["permitted_inference"]))
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(bad)

    bad = copy.deepcopy(_golden_spec())
    bad["shot_revision"]["id"] = "NOT-A-UUID"
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(bad)


# ---- M14-OBS:02 canonical bytes/hash deterministic -----------------------

def test_m14_obs_02() -> None:
    golden = _golden_spec()
    pins = _pins()
    pinned = pins["f06"]["vectors"][
        "m14-f06-world-observation-spec-v1.json"]
    assert world_observation_spec_hash(golden) == pinned

    rebuilt = build_world_observation_spec(
        shot_revision_id=golden["shot_revision"]["id"],
        plan_hash=golden["shot_revision"]["plan_hash"],
        captured_domains=golden["captured_domains"],
        requirements=golden["requirements"],
        production_occurrences=golden["production_occurrences"],
        materializations=golden["materializations"])
    assert world_observation_spec_bytes(rebuilt) == world_observation_spec_bytes(
        golden)
    assert world_observation_spec_hash(rebuilt) == pinned

    reparsed = parse_world_observation_spec(
        json.loads(world_observation_spec_bytes(golden).decode("utf-8")))
    assert world_observation_spec_bytes(reparsed) == (
        world_observation_spec_bytes(golden))


# ---- M14-OBS:03 strict Requirement grammar + identity ordering -----------

def test_m14_obs_03() -> None:
    bad = copy.deepcopy(_golden_spec())
    bad["requirements"].reverse()
    with pytest.raises(SoloRingError, match="order"):
        parse_world_observation_spec(bad)

    def mutate_requirement(**changes):
        spec = copy.deepcopy(_golden_spec())
        req = spec["requirements"][0]
        req.update(changes)
        spec["requirements"] = sorted(spec["requirements"],
                                      key=requirement_order_key)
        return spec

    with pytest.raises(SoloRingError):
        parse_world_observation_spec(mutate_requirement(
            property="audio.mix"))
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(mutate_requirement(
            preservation="BOUNDED"))
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(mutate_requirement(
            enforcement="PERMITTED_INFERENCE"))
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(mutate_requirement(
            source_contract=""))
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(mutate_requirement(subkey="x"))
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(mutate_requirement(
            occurrence_id=OCC_ID))

    structure = copy.deepcopy(_golden_spec())
    target = next(r for r in structure["requirements"]
                  if r["property"] == "occurrence.structure")
    target["occurrence_id"] = None
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(structure)


# ---- M14-OBS:04 strict ProductionOccurrence grammar + order --------------

def test_m14_obs_04() -> None:
    golden = _golden_spec()
    assert len(golden["production_occurrences"]) == 1
    parse_world_observation_spec(golden)

    def mutate_occurrence(**changes):
        spec = copy.deepcopy(_golden_spec())
        spec["production_occurrences"][0].update(changes)
        return spec

    duplicate = copy.deepcopy(_golden_spec())
    duplicate["production_occurrences"].append(
        copy.deepcopy(duplicate["production_occurrences"][0]))
    with pytest.raises(SoloRingError, match="duplicate occurrence"):
        parse_world_observation_spec(duplicate)

    with pytest.raises(SoloRingError):
        parse_world_observation_spec(mutate_occurrence(placement_owner="A7"))

    missing = copy.deepcopy(_golden_spec())
    del missing["production_occurrences"][0]["interpretation"]
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(missing)

    with pytest.raises(SoloRingError):
        parse_world_observation_spec(mutate_occurrence(
            representation_contract="gltf"))

    transform = copy.deepcopy(_golden_spec())
    transform["production_occurrences"][0]["realization_local_to_world"][
        "translation_mm"] = [1.5, 0, 0]
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(transform)

    rotation = copy.deepcopy(_golden_spec())
    rotation["production_occurrences"][0]["placement"][
        "subject_local_to_world"]["rotation_udeg"] = [180_000_000, 0, 0]
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(rotation)


# ---- M14-OBS:05 strict Materialization grammar + canonical order ---------

def test_m14_obs_05() -> None:
    two = copy.deepcopy(_golden_spec())
    two["materializations"].append(copy.deepcopy(two["materializations"][0]))
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(two)

    zero = copy.deepcopy(_golden_spec())
    zero["materializations"] = []
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(zero)

    params = copy.deepcopy(_golden_spec())
    params["materializations"][0]["parameters"]["width"] = 640
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(params)

    phash = copy.deepcopy(_golden_spec())
    phash["materializations"][0]["parameters_hash"] = _hex("wrong")
    with pytest.raises(SoloRingError):
        parse_world_observation_spec(phash)

    unknown_source = copy.deepcopy(_golden_spec())
    unknown_source["materializations"][0]["source_occurrence_ids"] = [
        "12345678-1234-1234-1234-123456123456"]
    with pytest.raises(SoloRingError, match="no ProductionOccurrence"):
        parse_world_observation_spec(unknown_source)

    reordered = _compile(_full_snapshot(),
                         spatial_hash=_hex("spatial"),
                         world_hash=_hex("world"),
                         visual_hash=_hex("visual"))
    extra = copy.deepcopy(reordered)
    extra["production_occurrences"] = [
        {"occurrence_id": OCC_ID,
         "composition_revision_id":
             "33333333-3333-3333-3333-333333333333",
         "composition_revision_hash": _hex("comp"),
         "production_revision_id":
             "44444444-4444-4444-4444-444444444444",
         "production_revision_hash": _hex("prod"),
         "retained_blob_hash": _hex("blob"),
         "representation_contract": "soloring.structural_mesh.v1",
         "placement_owner": "A6",
         "interpretation": {
             "hash": _hex("interp"),
             "realization_local_to_subject_local": {
                 "translation_mm": [0, 0, 0],
                 "rotation_udeg": [0, 0, 0]}},
         "placement": {
             "source_kind": "composition_revision",
             "source_id": "33333333-3333-3333-3333-333333333333",
             "source_hash": _hex("comp"),
             "subject_local_to_world": {
                 "translation_mm": [0, 0, 0],
                 "rotation_udeg": [0, 0, 0]}},
         "realization_local_to_world": {
             "translation_mm": [0, 0, 0],
             "rotation_udeg": [0, 0, 0]}}]
    extra["materializations"][0]["source_occurrence_ids"] = [OCC_ID]
    parse_world_observation_spec(extra)


# ---- M14-OBS:06 duplicate/conflicting coordinate rejection ----------------

def test_m14_obs_06() -> None:
    duplicate = copy.deepcopy(_golden_spec())
    duplicate["requirements"].insert(
        0, copy.deepcopy(duplicate["requirements"][0]))
    with pytest.raises(SoloRingError, match="duplicate"):
        parse_world_observation_spec(duplicate)

    conflict = copy.deepcopy(_golden_spec())
    camera = next(r for r in conflict["requirements"]
                  if r["property"] == "camera.projection")
    changed = copy.deepcopy(camera)
    changed["preservation"] = "EXACT"
    changed["enforcement"] = "REQUIRED"
    conflict["requirements"].append(changed)
    conflict["requirements"] = sorted(conflict["requirements"],
                                      key=requirement_order_key)
    with pytest.raises(SoloRingError, match="conflicting"):
        parse_world_observation_spec(conflict)

    contract_conflict = copy.deepcopy(_golden_spec())
    camera = next(r for r in contract_conflict["requirements"]
                  if r["property"] == "camera.projection")
    changed = copy.deepcopy(camera)
    changed["source_contract"] = "m10.camera_projection.v2"
    contract_conflict["requirements"].append(changed)
    contract_conflict["requirements"] = sorted(
        contract_conflict["requirements"], key=requirement_order_key)
    with pytest.raises(SoloRingError, match="conflicting"):
        parse_world_observation_spec(contract_conflict)


# ---- M14-OBS:07 camera.projection emission exact --------------------------

def test_m14_obs_07() -> None:
    spatial_hash = _hex("spatial")
    spec = _compile(_schema6(spatial=_spatial_pack([_frame(None)])),
                    spatial_hash=spatial_hash)
    (camera,) = [r for r in spec["requirements"]
                 if r["property"] == "camera.projection"]
    assert camera["preservation"] == "STRUCTURAL"
    assert camera["enforcement"] == "REQUIRED"
    assert camera["subject"] == {"kind": "shot", "id": SHOT_ID}
    assert camera["authority"] == {
        "domain": "A4",
        "source_kind": "spatial_continuity_pack",
        "source_id": SHOT_REV_ID,
        "source_hash": spatial_hash}
    assert camera["source_contract"] == "m10.camera_projection.v1"

    none = _compile(_schema6(production_world=_production_world([])),
                    world_hash=_hex("world"))
    assert "camera.projection" not in _properties(none)

    with pytest.raises(SoloRingError):
        _compile(_schema6(spatial=_spatial_pack([])), spatial_hash=None)


# ---- M14-OBS:08 world.structure emission exact ----------------------------

def test_m14_obs_08() -> None:
    spec = _compile(
        _schema6(spatial=_spatial_pack(
            [_frame(None), _frame([1500, 400, 400])])),
        spatial_hash=_hex("spatial"))
    (world,) = [r for r in spec["requirements"]
                if r["property"] == "world.structure"]
    assert world["preservation"] == "STRUCTURAL"
    assert world["enforcement"] == "REQUIRED"
    assert world["subject"] == {"kind": "spatial_world",
                                "id": WORLD_REV_ID}
    assert world["authority"] == {
        "domain": "A4",
        "source_kind": "spatial_world_revision",
        "source_id": WORLD_REV_ID,
        "source_hash": _hex("world-revision")}
    assert world["source_contract"] == "m10.world_depth.v1"

    landmarks = _compile(_schema6(spatial=_spatial_pack(
        [_frame(None), _frame(None)])),
        spatial_hash=_hex("spatial"))
    assert "world.structure" not in _properties(landmarks)

    empty = _compile(_schema6(spatial=_spatial_pack([])),
                     spatial_hash=_hex("spatial"))
    assert "world.structure" not in _properties(empty)


# ---- M14-OBS:11 visual.identity conservative emission ---------------------

def test_m14_obs_11() -> None:
    visual_hash = _hex("visual")
    spec = _compile(
        _schema6(spatial=_spatial_pack([_frame([10, 10, 10])]),
                 visual={"schema_version": 2, "anchors": [
                     {"asset_id": "ddddddd1-0000-0000-0000-000000000001"}]}),
        spatial_hash=_hex("spatial"), visual_hash=visual_hash)
    (visual,) = [r for r in spec["requirements"]
                 if r["property"] == "visual.identity"]
    assert visual["preservation"] == "IDENTITY_APPEARANCE"
    assert visual["enforcement"] == "REQUIRED"
    assert visual["subject"]["kind"] == "visual_reference_pack"
    assert visual["authority"]["domain"] == "A3"
    assert visual["authority"]["source_kind"] == "visual_reference_pack"
    assert visual["authority"]["source_hash"] == visual_hash
    assert visual["source_contract"] == "m8.visual_reference_pack.v1"

    without = _compile(_schema6(spatial=_spatial_pack([_frame(None)])),
                       spatial_hash=_hex("spatial"))
    assert "visual.identity" not in _properties(without)

    with pytest.raises(SoloRingError):
        _compile(_schema6(visual={"schema_version": 2, "anchors": []}),
                 visual_hash=None)
    with pytest.raises(SoloRingError):
        _compile(_schema6(), visual_hash=visual_hash)


# ---- M14-OBS:12 every PI feature state emits; no heuristic ----------------

def test_m14_obs_12() -> None:
    keys = ["wardrobe_color", "hair_style", "prop_watch_state"]
    spec = _compile(_schema6(production_world=_production_world(keys)),
                    world_hash=_hex("world"))
    emitted = [r for r in spec["requirements"]
               if r["property"] == "continuity.instance_feature"]
    assert [r["subkey"] for r in emitted] == sorted(keys)
    for req in emitted:
        assert req["preservation"] == "EXACT"
        assert req["enforcement"] == "REQUIRED"
        assert req["subject"] == {"kind": "production_instance",
                                  "id": PI_OCC_ID}
        assert req["occurrence_id"] is None
        assert req["authority"] == {
            "domain": "A2",
            "source_kind": "production_world_pack",
            "source_id": BINDING_ID,
            "source_hash": _hex("world")}
        assert (req["source_contract"]
                == "m13.production_instance_feature.v1")

    empty = _compile(_schema6(production_world=_production_world([])),
                     world_hash=_hex("world"))
    assert "continuity.instance_feature" not in _properties(empty)


# ---- M14-OBS:13 shot.intent INFERABLE/PERMITTED_INFERENCE ----------------

def test_m14_obs_13() -> None:
    spec = _compile(_schema6(spatial=_spatial_pack([_frame(None)])),
                    spatial_hash=_hex("spatial"))
    (intent,) = [r for r in spec["requirements"]
                 if r["property"] == "shot.intent"]
    assert intent["preservation"] == "INFERABLE"
    assert intent["enforcement"] == "PERMITTED_INFERENCE"
    assert intent["subject"] == {"kind": "shot", "id": SHOT_ID}
    assert intent["authority"] == {
        "domain": "A1",
        "source_kind": "shot_revision",
        "source_id": SHOT_REV_ID,
        "source_hash": _hex("plan")}
    assert intent["source_contract"] == "lower_schema_3.prompt"


# ---- M14-OBS:16 schema-6 first-class; zero current-state resolution ------

def test_m14_obs_16() -> None:
    spec = _compile(_full_snapshot(),
                    spatial_hash=_hex("spatial"),
                    world_hash=_hex("world"),
                    visual_hash=_hex("visual"))
    assert _properties(spec) == [
        "camera.projection", "continuity.instance_feature",
        "shot.intent", "visual.identity", "world.structure"]
    assert spec["production_occurrences"] == []
    assert spec["materializations"][0]["source_occurrence_ids"] == []
    assert world_observation_spec_hash(spec) == world_observation_spec_hash(
        _compile(_full_snapshot(), spatial_hash=_hex("spatial"),
                 world_hash=_hex("world"), visual_hash=_hex("visual")))

    schema5 = {"schema_version": 5, "intent": {}, "references": [],
               "continuity": {},
               "spatial_continuity": _spatial_pack([_frame([5, 5, 5])])}
    with pytest.raises(SoloRingError, match="schema-6"):
        _compile(schema5, spatial_hash=_hex("spatial"))

    parameters = inspect.signature(compile_world_observation_spec).parameters
    assert not any(
        name in {"session", "conn", "connection", "db", "engine", "store"}
        for name in parameters), (
        "the compiler must accept captured values only — no current-state "
        "or persistence handles (frozen §9)")

    import soloring.observation.compiler as compiler_module
    imported_soloring = {
        mod.__name__ for mod in vars(compiler_module).values()
        if inspect.ismodule(mod)
        and mod.__name__.startswith("soloring")}
    assert imported_soloring <= {
        "soloring.errors", "soloring.observation.spec",
        "soloring.domain.canonical"}, (
        "the compiler may import only canonical/spec/error primitives — "
        "no current-state resolvers or persistence handles")
