"""M5B-2 — real workflow package release gate.

The v1-GGUF HunyuanVideo I2V release (manifest v2 + API template +
descriptor) must pass the EXISTING coherent capture path: descriptor-coherent
capture_package, binding validation, content-addressed placement, and
retrieval of both artifacts by hash — independent of the installed files.

Topology provenance (M5B-2 preflight, resolved from live /object_info on
ComfyUI 0.33.0 @ b963f4a): the official 1.5 I2V template's extra model
roles (second UNET SR stage + LatentUpscaleModelLoader) are avoided by
re-authoring on the officially documented v1 I2V baseline with the single
GGUF substitution ComfyUI-GGUF documents (diffusion loader only). Every
node/field in the template is schema-verified against the live instance in
the M5B-2 report; this test pins the SoloRing-side contract.
"""

from __future__ import annotations

import json

import pytest

from soloring.executors.comfy.bindings import (
    BindingInvalid,
    validate_manifest_template_bindings,
)
from soloring.settings import BASE_DIR, Settings
from soloring.workflows.artifact_store import WorkflowArtifactStore
from soloring.workflows.manifest import load_workflow, parse_manifest

WF = BASE_DIR / "workflows" / "hunyuan_i2v_v1"


def test_release_is_descriptor_coherent_and_strict():
    template = load_workflow(WF)
    assert template.workflow_id == "hunyuan_i2v"
    assert template.workflow_version == 3
    pkg = json.loads((WF / "workflow-package.json").read_text("utf-8"))
    manifest_bytes = (WF / "manifest.json").read_bytes()
    template_bytes = (WF / "workflow.json").read_bytes()
    import hashlib

    assert pkg["manifest_hash"] == hashlib.sha256(manifest_bytes).hexdigest()
    assert pkg["workflow_template_hash"] == hashlib.sha256(
        template_bytes
    ).hexdigest()
    assert template.manifest_hash == pkg["manifest_hash"]
    assert template.workflow_template_hash == pkg["workflow_template_hash"]


def test_bindings_resolve_against_the_real_template():
    doc = parse_manifest((WF / "manifest.json").read_text("utf-8"))
    graph = json.loads((WF / "workflow.json").read_text("utf-8"))
    validate_manifest_template_bindings(doc, graph)  # raises on any miss

    by_id = {n: node for n, node in graph.items()}
    # The exact release topology: GGUF diffusion loader, dual text encoder
    # (hunyuan_video), CLIP vision, VAE, v1 conditioning, KSampler,
    # SaveAnimatedWEBP.
    assert by_id["98"]["class_type"] == "UnetLoaderGGUF"
    assert by_id["99"]["class_type"] == "DualCLIPLoader"
    assert by_id["99"]["inputs"]["type"] == "hunyuan_video"
    assert by_id["78"]["class_type"] == "HunyuanImageToVideo"
    assert by_id["78"]["inputs"]["guidance_type"] == "v1 (concat)"
    assert by_id["15"]["class_type"] == "SaveAnimatedWEBP"
    # The single input binding is the LoadImage image field; the graph
    # carries it to CLIPVisionEncode and HunyuanImageToVideo.start_image
    # by links, never by duplicate bindings.
    assert by_id["4"]["class_type"] == "LoadImage"
    assert by_id["96"]["inputs"]["image"] == ["4", 0]
    assert by_id["78"]["inputs"]["start_image"] == ["4", 0]


async def test_coherent_capture_and_hash_retrieval(settings):
    store = WorkflowArtifactStore(settings)
    captured = await store.capture_package(
        WF / "workflow-package.json", WF / "manifest.json",
        WF / "workflow.json",
    )
    await store.place_captured(captured)

    manifest_bytes = (WF / "manifest.json").read_bytes()
    template_bytes = (WF / "workflow.json").read_bytes()
    assert captured.manifest_bytes == manifest_bytes
    assert captured.template_bytes == template_bytes

    # Retrieval by hash — independent of the installed files.
    assert await store.get_manifest(captured.manifest_hash) == manifest_bytes
    assert await store.get_template(
        captured.workflow_template_hash
    ) == template_bytes

    # And a corrupted hybrid (descriptor swapped to a stale member) is
    # still rejected by the same coherent path.
    pkg = json.loads((WF / "workflow-package.json").read_text("utf-8"))
    pkg["workflow_template_hash"] = "0" * 64
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        bad_pkg = Path(td) / "workflow-package.json"
        bad_pkg.write_text(json.dumps(pkg))
        with pytest.raises(Exception):
            await store.capture_package(
                bad_pkg, WF / "manifest.json", WF / "workflow.json",
            )
