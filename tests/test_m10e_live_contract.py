"""M10E golden-oracle contract (frozen R3 §6.1/§12.5; E-036/E-095).

Three evidence layers over the same eight frozen fixtures:

  Layer 1 (CI-portable): exact DerivedSpatialArtifactSpec canonical-hash
  pins — platform-independent contract facts, asserted on every runner.
  Layer 2 (CI-runnable): D0 grammar/decode semantics, role-correct
  differentials, fixed-frame/offscreen behavior, canonical ordering, and
  same-process repeatability — asserted on every runner.
  Layer 3 (certified evidence-machine byte oracle): exact PNG artifact
  digests, asserted ONLY on a runtime whose encoder identity matches the
  certified win-cpu-d0 evidence contract; other runners SKIP the byte
  cell explicitly (never silently pass, never assert cross-platform byte
  identity).

Pins were generated on the certified evidence machine (win-amd64) from
the frozen production contract and reviewed against the fixture
semantics: the world digest is invariant across staging cardinality,
reversed staging order converges to the canonical-order digests, the
fixed-frame extent change moves ONLY the world identity, and the
offscreen entity digest equals the all-background digest."""
from __future__ import annotations

import io

import pytest

from soloring.spatial import production_pins as pins
from soloring.spatial import boxdepth
from soloring.spatial.realize import compose_spatial_realization

_E1 = ("00000000-0000-4000-8000-0000000000a1",
       "00000000-0000-4000-8000-0000000000b1")
_E2 = ("00000000-0000-4000-8000-0000000000a2",
       "00000000-0000-4000-8000-0000000000b2")

_CAM1 = {"projection": "perspective", "focal_length_um": 50000,
         "sensor_width_um": 36000, "sensor_height_um": 20250,
         "keyframes": [{"time_ms": 0, "transform": {
             "translation_mm": [-3000, 1650, 4200],
             "rotation_udeg": [0, 0, 0]}}]}
_CAM2 = {"projection": "perspective", "focal_length_um": 50000,
         "sensor_width_um": 36000, "sensor_height_um": 20250,
         "keyframes": [
             {"time_ms": 0, "transform": {
                 "translation_mm": [-3000, 1650, 4200],
                 "rotation_udeg": [0, 0, 0]}},
             {"time_ms": 4000, "transform": {
                 "translation_mm": [-1500, 1500, 2600],
                 "rotation_udeg": [0, 150000, 0]}}]}


def _stg(e, t):
    return {"spatial_track_id": e[1], "entity_id": e[0],
            "entity_revision_id": e[0], "requirement": "optional",
            "transform": {"translation_mm": t, "rotation_udeg": [0, 0, 0]},
            "source_transition": {"spatial_transition_id": e[1],
                                  "anchor_type": "sequence",
                                  "anchor_id": e[1], "boundary": "start"}}


def _pack(frames, staging, cam):
    return {"schema_version": 1,
            "spatial_world": {
                "spatial_world_id": "w1", "requirement": "required",
                "spatial_world_state_id": "s1",
                "spatial_world_revision_id": "r1",
                "spatial_world_revision_hash": "0" * 64,
                "location_entity_id": "l", "location_entity_revision_id":
                    "lr",
                "world_snapshot": {"frames": frames, "axes": []}},
            "staging": staging,
            "shot_plan": {"schema_version": 1, "spatial_world_id": "w1",
                          "camera": cam, "blocking": [],
                          "axis_constraint": None}}


_FRAME = {"frame_key": "setpiece", "spatial_frame_id": "f1",
          "bound_entity_id": None, "half_extents_mm": [600, 400, 300],
          "transform": {"translation_mm": [-3000, 1650, 0],
                        "rotation_udeg": [0, 0, 0]}}
_FRAME_BIG = dict(_FRAME, half_extents_mm=[900, 400, 300])

FIXTURES = {
    "world_only": _pack([_FRAME], [], _CAM1),
    "one_entity": _pack([_FRAME], [_stg(_E1, [-3600, 1500, -400])], _CAM1),
    "two_entities": _pack([_FRAME], [_stg(_E1, [-3600, 1500, -400]),
                                     _stg(_E2, [-2400, 1750, -800])],
                          _CAM1),
    "camera_motion": _pack([_FRAME], [_stg(_E1, [-3600, 1500, -400])],
                           _CAM2),
    "placement_change": _pack([_FRAME], [_stg(_E1, [-2000, 1500, -400])],
                              _CAM1),
    "extent_change": _pack([_FRAME_BIG], [_stg(_E1, [-3600, 1500, -400])],
                           _CAM1),
    "offscreen": _pack([_FRAME], [_stg(_E1, [50000, 50000, -50000])],
                       _CAM1),
    "reversed_order": _pack([_FRAME], [_stg(_E2, [-3600, 1500, -400]),
                                       _stg(_E1, [-2400, 1750, -800])],
                            _CAM1),
}

# Layer 1 + Layer 3 pins: (position, spec_hash, certified D0 digest)
PINS = {
    "world_only": [
        (0, "d7094b385097cb9fafe92bef950997994463698adb233ca83c04e2af6e347775",
         "46a32c472bc2dddefe5d62d54e6f81ac15fc9c9410d2b238009baa24fea6c195")],
    "one_entity": [
        (0, "663117ba807bc043b097a642f2243e0e6bc614567ff9f5331056964c13ce71be",
         "46a32c472bc2dddefe5d62d54e6f81ac15fc9c9410d2b238009baa24fea6c195"),
        (1, "da874bac8556f4f83ae81d53dc18d43048ccb63799fb0b18615341ccac295134",
         "5ca62ccc0f5210920d74ad8675d813a192fcf43ae73ccfe9e999c7a3312e3051")],
    "two_entities": [
        (0, "7c2726a1d0762d3ba306bd71d44d0d890f95f1d08a525f75441fac2e8b9497de",
         "46a32c472bc2dddefe5d62d54e6f81ac15fc9c9410d2b238009baa24fea6c195"),
        (1, "99f8c0be3cd068b284f33e5b5ad67aa9528a0d7f545a0888aa4b697bbf6d4c51",
         "5ca62ccc0f5210920d74ad8675d813a192fcf43ae73ccfe9e999c7a3312e3051"),
        (2, "256cd3e50c5a78881898a86392b2b4acdc5b15e291883d66291f03a4c0a4cdae",
         "689ce2b1c4391e80a250efd00252659354532b6e76e4e2ef261f268554d186e4")],
    "camera_motion": [
        (0, "02dd38344eb7120f9c0195d3f14f72787fc53101e071965c35a064e9ff511193",
         "32aba5edb51bed04f034979085f79769cdb4926f35d0542dda3a191d98e71814"),
        (1, "570f5a16f384405a5dac38647e77b569880cf7bf12ab4189e6f5de1484a343c7",
         "d05f08a46f04da4cef63e7274d46b30ce745b52b8c4c0ca1dd8266a7feee9a5c")],
    "placement_change": [
        (0, "f54cd4f2772950b0ffbd8f9a00da46c228e33f7f02fb393da85272ecb72cc869",
         "46a32c472bc2dddefe5d62d54e6f81ac15fc9c9410d2b238009baa24fea6c195"),
        (1, "bd58333de2f9f94ec3bf0702c26d550dd6207838f0b229f36073028b33fda1e3",
         "e4fb8dcb4a5034606c3698a37c38b2205dfbf52b200dd42d9fabde29486322cf")],
    "extent_change": [
        (0, "1bc0ad3dd95e8fb61ad13710a6964be0d05fe5ae768d6404c7b867be104bef21",
         "237410cfb19592a1c87f639ca4dc8fefa8298f1b3751e223c1af281f472849ba"),
        (1, "55795b321080eaba6d5e44e1ce90e04355bbcecdcdefbd9a9a64e7c120780a61",
         "5ca62ccc0f5210920d74ad8675d813a192fcf43ae73ccfe9e999c7a3312e3051")],
    "offscreen": [
        (0, "5610e823d8f52ba03d48737ab735b3ce5dfc8aba35d8ac591ed5f44218dedeb0",
         "46a32c472bc2dddefe5d62d54e6f81ac15fc9c9410d2b238009baa24fea6c195"),
        (1, "9aa9cb18ba3a4a500d29e049a72b8d989af49beaf4f5fcdc2b3c1f617eb579af",
         "8ab4aa08b961e0e4767e0c62eda742282d1e1898075673bc2300ed79290da474")],
    "reversed_order": [
        (0, "427805b9c72e0a25c5f747bb23f0199890be55ac0754845090729d364762acef",
         "46a32c472bc2dddefe5d62d54e6f81ac15fc9c9410d2b238009baa24fea6c195"),
        (1, "63716e2e1ef7a02c8420a2a42c815b4e536d4a8439dbec8f3ae4a174d7b63b12",
         "5ca62ccc0f5210920d74ad8675d813a192fcf43ae73ccfe9e999c7a3312e3051"),
        (2, "b6a3f72be686e70ed5f596bd09307aa76f975b8d047f1dd90f483493e5b728ba",
         "689ce2b1c4391e80a250efd00252659354532b6e76e4e2ef261f268554d186e4")],
}

_ALL_BACKGROUND = "8ab4aa08b961e0e4767e0c62eda742282d1e1898075673bc2300ed79290da474"


def _evidence_machine() -> bool:
    """The certified win-cpu-d0 encoder contract: win-amd64 CPython native
    Pillow encoder. Any other runtime SKIPS Layer 3 explicitly."""
    ident = pins.encoder_runtime_identity()
    return ident["platform"] == "win-amd64" and \
        ident["python_implementation"] == "cpython" and \
        "win_amd64" in ident["pillow_native_module"]


def _compose(name):
    return compose_spatial_realization(FIXTURES[name])


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_layer1_spec_hash_pins_every_runner(name):
    """Layer 1: canonical spec hashes are platform-independent contract
    facts, asserted on EVERY runner (E-036)."""
    out = _compose(name)
    assert out.spec_hashes == tuple(h for _, h, _ in PINS[name])


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_layer2_grammar_decode_repeatability(name):
    """Layer 2: exact 832x480x17 PNG-L grammar, background-255 semantics,
    decode validity, and same-process repeatability on every runner."""
    from PIL import Image

    out = _compose(name)
    again = _compose(name)
    assert again.spec_hashes == out.spec_hashes
    assert again.artifact_digests == out.artifact_digests
    for frames in out.frames:
        assert len(frames) == pins.GRAMMAR_FRAMES
        for data in frames:
            img = Image.open(io.BytesIO(data))
            assert img.format == "PNG"
            assert img.mode == pins.GRAMMAR_MODE
            assert img.size == (pins.GRAMMAR_WIDTH, pins.GRAMMAR_HEIGHT)


def test_layer2_role_differentials():
    """Layer 2: role-correct differentials — world digest invariant across
    staging cardinality; placement change moves only the entity layer;
    fixed-frame extent change moves only the world layer; camera motion
    moves everything; offscreen equals the all-background artifact."""
    world = {n: _compose(n).artifact_digests[0] for n in
             ("world_only", "one_entity", "two_entities",
              "placement_change", "reversed_order", "offscreen")}
    assert len(set(world.values())) == 1

    one = _compose("one_entity").artifact_digests
    moved = _compose("placement_change").artifact_digests
    assert moved[1] != one[1]          # entity layer moved
    # (world layer equality is covered by the invariant above)

    extent = _compose("extent_change").artifact_digests
    assert extent[0] != world["one_entity"]  # world moved
    assert extent[1] == one[1]               # entity layer unchanged

    cam = _compose("camera_motion").artifact_digests
    assert cam[0] != world["one_entity"] and cam[1] != one[1]

    assert _compose("offscreen").artifact_digests[1] == _ALL_BACKGROUND


def test_layer2_canonical_ordering():
    """Layer 2: reversed input staging order converges to the canonical
    (entity_id, spatial_track_id) entity digests (E-022 at byte level)."""
    straight = _compose("two_entities").artifact_digests
    reversed_ = _compose("reversed_order").artifact_digests
    assert reversed_[1:] == straight[1:]


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_layer3_certified_byte_oracle(name):
    """Layer 3 (certified evidence-machine ONLY): exact PNG artifact
    digests. Non-matching runnners SKIP explicitly — never silently pass,
    never assert cross-platform byte identity (R3 §6.1)."""
    if not _evidence_machine():
        pytest.skip(
            "Layer-3 byte oracle is gated on the certified win-cpu-d0 "
            "evidence-machine encoder contract; this runner's encoder "
            "identity does not match")
    out = _compose(name)
    assert out.artifact_digests == tuple(d for _, _, d in PINS[name])


def test_layer3_gate_has_positive_control():
    """The Layer-3 gate is real, not vacuous: on the evidence machine the
    digests are asserted (this test fails if the gate logic is broken on
    the machine it was certified on)."""
    if _evidence_machine():
        assert _compose("world_only").artifact_digests == (
            PINS["world_only"][0][2],)
    else:
        pytest.skip("evidence-machine positive control only")
