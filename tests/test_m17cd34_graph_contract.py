"""M17C-D FPR34-01/03 — the real executor-graph contract battery:
the complete graph verified against the IMPLEMENTED node signatures
(connection types, output indexes, input fields, the terminal
media-output node) — never class-name presence; the frozen
TRANSLATION_TABLE_V1 pinned identity; the non-live
material-consumption proof (a changed derived control changes the
consumed transformation input — the driving signals); the lawful
no-vocal sentinel; and the fail-closed inference boundary."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
NODES_DIR = REPO / "server" / "soloring" / "executor_nodes"
PKG = REPO / "workflows" / "performance_liveportrait_v1"

sys.path.insert(0, str(NODES_DIR))
import soloring_performance_nodes as nodes_pkg  # noqa: E402

# ComfyUI core types that LoadImage/SaveAnimatedWEBP provide without
# a custom node
STOCK_CLASSES = {
    "LoadImage": {"outputs": ["IMAGE", "MASK"], "inputs": {"image"}},
    "SaveAnimatedWEBP": {
        "outputs": [], "inputs": {"images", "filename_prefix",
                                   "fps", "lossless", "quality",
                                   "method"}},
}


def _graph():
    return json.loads((PKG / "workflow.json").read_text(
        encoding="utf-8"))


def _manifest():
    return json.loads((PKG / "manifest.json").read_text(
        encoding="utf-8"))


def _declared_outputs(cls_type):
    if cls_type in STOCK_CLASSES:
        return STOCK_CLASSES[cls_type]["outputs"]
    return list(nodes_pkg.NODE_CLASS_MAPPINGS[cls_type].RETURN_TYPES)


def _declared_inputs(cls_type):
    if cls_type in STOCK_CLASSES:
        return STOCK_CLASSES[cls_type]["inputs"]
    return set(nodes_pkg.NODE_CLASS_MAPPINGS[cls_type]
               .INPUT_TYPES()["required"])


def test_every_non_stock_class_is_implemented():
    graph = _graph()
    for node_id, node in graph.items():
        cls = node["class_type"]
        assert cls in nodes_pkg.NODE_CLASS_MAPPINGS \
            or cls in STOCK_CLASSES, (node_id, cls)


def test_graph_connection_contract():
    """Every edge's cited OUTPUT INDEX exists on the source node and
    the cited field is a declared input of the target — against
    the IMPLEMENTED signatures, not the JSON's say-so."""
    graph = _graph()
    for node_id, node in graph.items():
        declared = _declared_inputs(node["class_type"])
        for field, value in node["inputs"].items():
            assert field in declared, (
                node_id, node["class_type"], field)
            if not isinstance(value, list):
                continue  # a literal, not a connection
            src_id, out_idx = value
            assert src_id in graph, (node_id, src_id)
            src = graph[src_id]
            outputs = _declared_outputs(src["class_type"])
            assert 0 <= out_idx < len(outputs), (
                node_id, field, src_id, out_idx, outputs)


def test_terminal_media_output_node():
    """The manifest's video output names a REAL media-output node
    (SaveAnimatedWEBP) whose images input receives the apply edge's
    IMAGE output — a genuine output-producing terminal, not a
    sampler field."""
    graph = _graph()
    manifest = _manifest()
    out = manifest["outputs"]["video"]
    terminal = graph[out["node"]]
    assert terminal["class_type"] == "SaveAnimatedWEBP"
    assert out["field"] in _declared_inputs(terminal["class_type"])
    source = terminal["inputs"][out["field"]]
    assert graph[source[0]]["class_type"] == "LivePortraitApply"
    apply_outputs = _declared_outputs("LivePortraitApply")
    assert apply_outputs[source[1]] == "IMAGE"
    # no KSampler remains anywhere in the graph
    assert all(node["class_type"] != "KSampler"
               for node in graph.values())


def test_apply_edge_consumes_every_performance_input():
    """The apply edge's declared inputs bind image, controls, audio,
    AND rasterization — each from the correct producing node with a
    type-matching output."""
    graph = _graph()
    apply_node = graph["50"]
    assert apply_node["class_type"] == "LivePortraitApply"
    expected = {"image": ("10", "IMAGE"),
                "controls": ("40", "CONTROLS"),
                "audio": ("41", "AUDIO"),
                "rasterization": ("30", "RASTERIZATION")}
    for field, (src_id, out_type) in expected.items():
        src_id_expected, out_type_expected = expected[field]
        connection = apply_node["inputs"][field]
        assert connection[0] == src_id_expected, field
        outputs = _declared_outputs(graph[connection[0]]["class_type"])
        assert outputs[connection[1]] == out_type_expected, field


def test_frozen_translation_table_identity():
    """The in-tree conversion table is byte-identical to the
    BLOCKER-1B qualification's frozen table (the pinned
    implementation identity)."""
    qual = Path("_m17c_1b/soloring_facial_liveportrait_adapter.py")
    if not qual.is_file():
        pytest.skip("the untracked qualification build is not "
                    "present (its pinned hash is recorded in the "
                    "correction record)")
    import ast

    tree = ast.parse(qual.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(
                node.targets[0], "id", "") == "TRANSLATION_TABLE_V1":
            table = ast.literal_eval(node.value)
            assert table == {
                k: [tuple(c) for c in v]
                for k, v in nodes_pkg.TRANSLATION_TABLE_V1.items()}
            return
    raise AssertionError("the qualification table was not found")


def _segment(ppm_value):
    return {
        "segment_position": 0,
        "blob_hash": "a" * 64,
        "schedule": {
            "translation_identity":
                "soloring-executor-translation-facial-liveportrait/1",
            "frames": [
                {"frame": 0, "segment_active": True,
                 "channels": {
                     "profile-1/face.articulation.jaw_open":
                         ppm_value}},
            ]}}


def test_material_consumption_proof():
    """FPR34-01's decisive non-live proof: changing a valid derived
    control changes the renderer's consumed transformation input —
    the driving signals computed from the schedules. Identity
    pass-through is impossible (the signals are a non-trivial
    causal function of the control values)."""
    low = nodes_pkg.compute_driving_signals([_segment(250_000)])
    high = nodes_pkg.compute_driving_signals([_segment(500_000)])
    assert low[0]["deltas"] != high[0]["deltas"]
    # exact frozen coefficients: 0.045/unit ppm on keypoint 19.1
    assert low[0]["deltas"]["19.1"] == pytest.approx(0.045 * 0.25)
    assert high[0]["deltas"]["19.1"] == pytest.approx(0.045 * 0.5)
    assert low[0]["pitch_deg"] == pytest.approx(-2.25 * 0.25)
    # every consumed signal names its exact derived blob identity
    assert all(s["blob_hash"] == "a" * 64 for s in low)
    # inactive frames consume nothing (neutral by law §14.6b)
    two = nodes_pkg.compute_driving_signals([{
        "segment_position": 0, "blob_hash": "a" * 64,
        "schedule": {
            "translation_identity":
                "soloring-executor-translation-facial-liveportrait/1",
            "frames": [
                {"frame": 0, "segment_active": True,
                 "channels": {
                     "profile-1/face.expression.smile": 100_000}},
                {"frame": 1, "segment_active": False,
                 "channels": {}},
            ]}}])
    assert two[0]["deltas"] is not None
    assert two[1]["deltas"] is None and two[1]["pitch_deg"] == 0.0


def test_consumption_refusals():
    """No controls, an unmapped channel, an unverified translation
    identity, and an out-of-grid frame each refuse."""
    with pytest.raises(ValueError):
        nodes_pkg.compute_driving_signals([])
    with pytest.raises(ValueError,
                       match="unverified translation"):
        nodes_pkg.compute_driving_signals([{
            "segment_position": 0, "blob_hash": "a" * 64,
            "schedule": {
                "translation_identity": "other/9",
                "frames": [{"frame": 0, "segment_active": True,
                            "channels": {}}]}}])
    with pytest.raises(ValueError, match="no frames"):
        nodes_pkg.compute_driving_signals([{
            "segment_position": 0, "blob_hash": "a" * 64,
            "schedule": {
                "translation_identity":
                    "soloring-executor-translation-"
                    "facial-liveportrait/1",
                "frames": []}}])


def test_no_vocal_sentinel_law():
    """FPR34-03: the empty audio field yields the explicit
    NO_VOCAL_AUDIO sentinel (never a _load_bundle("") attempt),
    and the apply edge accepts it without fabricating audio."""
    audio_node = nodes_pkg.SoloRingLivePortraitAudioInput()
    sentinel = audio_node.load("")[0]
    assert sentinel == nodes_pkg.NO_VOCAL_AUDIO
    assert sentinel != []  # distinct from an empty track list
    # the apply edge validates the sentinel path without touching
    # the inference boundary (proved by the typed refusal below,
    # not an identity pass-through)
    apply_node = nodes_pkg.LivePortraitApply()
    raster = {"fps_num": 25, "fps_den": 1, "frame_count": 25}
    with pytest.raises(RuntimeError, match="licensed"):
        apply_node.apply(
            object(),  # the image placeholder never reached
            [_segment(250_000)], sentinel, raster)


def test_inference_boundary_fails_closed():
    """The licensed LivePortrait inference boundary refuses in this
    process (no licensed runtime) — never an identity
    pass-through."""
    with pytest.raises(RuntimeError, match="licensed "
                       "LivePortrait runtime"):
        nodes_pkg._run_liveportrait_inference(
            object(), [], {"fps_num": 25, "fps_den": 1,
                           "frame_count": 25})
