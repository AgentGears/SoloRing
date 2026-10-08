"""M17C-D FPR33-01(c) — the performance attestation-lane battery
(non-live): the loadable-node fingerprint chain. Every class the
pinned graph names exists in the in-tree NODE_CLASS_MAPPINGS; the
performance-lane attestation loads ONLY with its exact content
hash; the predecessor GGUF lane is untouched (disjoint lanes); the
runtime laws accept/reject exactly per the explicit bindings."""

from __future__ import annotations

import json

import pytest


def _attestation_doc(whitelist, performance_hash=None):
    doc = {
        "schema_version": 4,
        "attestation": {
            "comfyui_commit": "a" * 40,
            "gguf_commit": "b" * 40,
            "executor_origin": "http://127.0.0.1:8188",
            "custom_node_policy": {
                "disable_all": True, "whitelist": list(whitelist)},
            "pid": 1234,
            "process_start_fingerprint": "fp",
            "launched_at": "2026-10-08T00:00:00+00:00",
        },
    }
    if performance_hash is not None:
        doc["attestation"]["performance_nodes_hash"] = performance_hash
    return doc


def _load(tmp_path, doc, whitelist):
    from soloring.executors.comfy.capability_record import (
        CapabilityRecordInvalid, load_deployment_attestation,
    )

    fp_dir = tmp_path / "comfy-fingerprint"
    fp_dir.mkdir(parents=True, exist_ok=True)
    (fp_dir / "deployment_attestation.json").write_text(
        json.dumps(doc), encoding="utf-8")
    return load_deployment_attestation(
        tmp_path, expected_whitelist=tuple(whitelist))


def test_every_graph_class_is_implemented():
    """FPR33-01: no invented classes — every node class the pinned
    graph names exists in the pinned in-tree implementation."""
    import sys
    from pathlib import Path

    graph = json.loads(
        (Path("workflows/performance_liveportrait_v1") /
         "workflow.json").read_text(encoding="utf-8"))
    sys.path.insert(0, str(Path(
        "server/soloring/executor_nodes").resolve()))
    import soloring_performance_nodes as nodes_pkg

    implemented = set(nodes_pkg.NODE_CLASS_MAPPINGS)
    # stock classes load with the executor core (no custom node
    # needed); every NON-stock class must be in the pinned package
    STOCK = {"LoadImage", "KSampler", "CheckpointLoaderSimple",
             "CLIPTextEncode", "VAEDecode", "VAEEncode", "EmptyLatentImage"}
    for node_id, node in graph.items():
        cls = node["class_type"]
        assert cls in implemented or cls in STOCK, (
            node_id, cls)
    # and the stock classes are genuinely stock
    assert graph["31"]["class_type"] == "KSampler"
    assert "model" in graph["31"]["inputs"]


def test_performance_lane_attestation_roundtrip(tmp_path):
    from soloring.performance.executor_runtime import (
        performance_nodes_content_hash,
    )

    true_hash = performance_nodes_content_hash()
    att = _load(
        tmp_path,
        _attestation_doc(["soloring_performance_nodes"], true_hash),
        ["soloring_performance_nodes"])
    assert att.performance_nodes_hash == true_hash
    assert att.custom_node_policy == ("soloring_performance_nodes",)


def test_performance_lane_requires_the_hash(tmp_path):
    from soloring.executors.comfy.capability_record import (
        CapabilityRecordInvalid,
    )

    with pytest.raises(CapabilityRecordInvalid) as exc:
        _load(tmp_path,
              _attestation_doc(["soloring_performance_nodes"]),
              ["soloring_performance_nodes"])
    assert "performance_nodes_hash" in str(exc.value)


def test_lanes_are_disjoint(tmp_path):
    from soloring.executors.comfy.capability_record import (
        CapabilityRecordInvalid,
    )

    # a predecessor-lane attestation carrying the performance field
    with pytest.raises(CapabilityRecordInvalid) as exc:
        _load(tmp_path,
              _attestation_doc(["ComfyUI-GGUF"], "c" * 64),
              ["ComfyUI-GGUF"])
    assert "disjoint" in str(exc.value)
    # the plain predecessor lane still loads exactly as before
    att = _load(tmp_path, _attestation_doc(["ComfyUI-GGUF"]),
                ["ComfyUI-GGUF"])
    assert att.performance_nodes_hash is None
    assert att.custom_node_policy == ("ComfyUI-GGUF",)


def test_check_performance_runtime_law():
    from soloring.realization.model_roots import ModelIncompatible
    from soloring.performance.executor_runtime import (
        check_performance_runtime, performance_nodes_content_hash,
    )

    class _Att:
        custom_node_policy = ("soloring_performance_nodes",)
        performance_nodes_hash = performance_nodes_content_hash()

    check_performance_runtime(_Att())  # passes

    class _WrongHash:
        custom_node_policy = ("soloring_performance_nodes",)
        performance_nodes_hash = "d" * 64

    with pytest.raises(ModelIncompatible):
        check_performance_runtime(_WrongHash())

    class _WrongPolicy:
        custom_node_policy = ("ComfyUI-GGUF",
                              "soloring_performance_nodes")
        performance_nodes_hash = performance_nodes_content_hash()

    with pytest.raises(ModelIncompatible):
        check_performance_runtime(_WrongPolicy())


def test_fingerprint_requiring_performance_nodes():
    """check_runtime_compatibility's explicit branch: a fingerprint
    requiring soloring_performance_nodes is satisfied ONLY by the
    attestation's content-hash field; the GGUF law unchanged."""
    from soloring.realization.model_roots import ModelIncompatible
    from soloring.realization.runtime import (
        check_runtime_compatibility,
    )
    from soloring.performance.executor_runtime import (
        performance_nodes_content_hash,
    )

    class _RR:
        comfyui_commit = "a" * 40
        custom_nodes = {
            "soloring_performance_nodes":
                performance_nodes_content_hash()}

        class custom_node_policy:
            whitelist = ("soloring_performance_nodes",)

    class _FP:
        runtime_requirements = _RR()

    class _Att:
        gguf_commit = "b" * 40
        comfyui_commit = "a" * 40
        performance_nodes_hash = performance_nodes_content_hash()
        custom_node_policy = ("soloring_performance_nodes",)

    check_runtime_compatibility(_FP(), _Att())

    class _BadAtt:
        gguf_commit = "b" * 40
        comfyui_commit = "a" * 40
        performance_nodes_hash = "e" * 64
        custom_node_policy = ("soloring_performance_nodes",)

    with pytest.raises(ModelIncompatible):
        check_runtime_compatibility(_FP(), _BadAtt())

    # an UNKNOWN node still refuses (no weakening)
    class _UnknownRR:
        comfyui_commit = "a" * 40
        custom_nodes = {"SomeOtherNode": "f" * 40}

        class custom_node_policy:
            whitelist = ("SomeOtherNode",)

    class _UnknownFP:
        runtime_requirements = _UnknownRR()

    with pytest.raises(ModelIncompatible):
        check_runtime_compatibility(_UnknownFP(), _Att())
