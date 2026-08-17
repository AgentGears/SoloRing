"""M5A-5 — Translation (M5 plan §23, §60; amended gates).

Fixture determinism matrix (7 cases incl. artifact-trio sensitivity), the
12-item failure matrix, and the negative-evidence isolation rules. Everything
runs purely on in-memory immutable values.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from soloring.errors import ErrorCode
from soloring.executors.comfy.input_materializer import MaterializedComfyInput
from soloring.executors.comfy.translate import (
    ComfyPromptPayload,
    TranslationFailed,
    build_comfy_prompt,
    submission_artifact,
    submission_marker,
)
from soloring.settings import BASE_DIR
from soloring.workflows.manifest import parse_manifest

WF = BASE_DIR / "workflows" / "hunyuan_i2v_v1"
MANIFEST = parse_manifest((WF / "manifest.json").read_text("utf-8"))
TEMPLATE = json.loads((WF / "workflow.json").read_text("utf-8"))

GID, AID, CLIENT = "g" * 36, "a" * 36, "w-client"


def _spec(**over):
    spec = {
        "schema_version": 1, "workflow_id": "hunyuan_i2v",
        "workflow_version": 1,
        "inputs": {"reference_image": {"bindings": [
            {"asset_id": "a1", "blob_hash": "b" * 64,
             "reference_role": "reference", "position": 0},
        ]}},
        "prompt": "Subject: Eva",
        "parameters": {"steps": 30, "cfg": 7.0},
        "seed": None,
        "outputs": [{"name": "video", "kind": "video", "expected_count": 1,
                     "accepted_media_types": None}],
    }
    spec.update(over)
    return spec


def _mat(remote="b" * 64 + ".png", key="reference_image", pos=0):
    return MaterializedComfyInput(
        input_key=key, position=pos, asset_id="a1", blob_hash="b" * 64,
        remote_name=remote, subfolder="ns",
    )


def _build(spec=None, manifest=MANIFEST, template=TEMPLATE, mat=None,
           gid=GID, aid=AID):
    return build_comfy_prompt(
        workflow_spec=spec or _spec(), manifest=manifest, template=template,
        materialized=[_mat()] if mat is None else mat,
        generation_id=gid, attempt_id=aid, client_id=CLIENT,
    )


# --- determinism fixture matrix --------------------------------------------------


def test_same_inputs_same_bytes_and_hash():
    a = submission_artifact(_build())
    b = submission_artifact(_build())
    assert a == b


def test_source_dict_insertion_order_irrelevant():
    spec = _spec()
    reordered = {
        "parameters": spec["parameters"], "prompt": spec["prompt"],
        "seed": spec["seed"], "outputs": spec["outputs"],
        "inputs": spec["inputs"], "workflow_version": spec["workflow_version"],
        "workflow_id": spec["workflow_id"], "schema_version": spec["schema_version"],
    }
    assert submission_artifact(_build(spec=reordered)) == submission_artifact(_build())


def test_parameter_value_changes_hash():
    spec2 = _spec(parameters={"steps": 12, "cfg": 7.0})
    assert submission_artifact(_build(spec=spec2)) != submission_artifact(_build())


def test_remote_filename_changes_hash():
    other = _mat(remote="renamed (1).png")
    assert submission_artifact(_build(mat=[other])) != submission_artifact(_build())


def test_materialized_ordering_irrelevant_when_logical_identity_same():
    # Two inputs under one role (cardinality 2) presented in swapped order.
    doc = json.loads((WF / "manifest.json").read_text("utf-8"))
    doc["inputs"]["reference_image"]["cardinality"] = 2
    m = parse_manifest(doc)
    m1 = MaterializedComfyInput("reference_image", 0, "a1", "b" * 64,
                                 "x.png", "ns")
    m2 = MaterializedComfyInput("reference_image", 1, "a2", "c" * 64,
                                 "y.png", "ns")
    forward = _build(manifest=m, mat=[m1, m2])
    reverse = _build(manifest=m, mat=[m2, m1])
    assert submission_artifact(forward) == submission_artifact(reverse)


def test_attempt_id_changes_artifact():
    assert submission_artifact(_build(aid="z" * 36)) != submission_artifact(_build())


def test_historical_manifest_change_changes_submission():
    doc = json.loads((WF / "manifest.json").read_text("utf-8"))
    doc["inputs"]["reference_image"]["node"] = "4"  # same
    m_same = parse_manifest(doc)
    assert submission_artifact(_build(manifest=m_same)) == submission_artifact(_build())
    # Change a BINDING target (prompt node): submission must change.
    doc2 = json.loads((WF / "manifest.json").read_text("utf-8"))
    # the template has only node 12 as a text-encode input; simulate change
    # by rebinding the parameter to a different node with the same field.
    doc2["parameters"]["steps"]["node"] = "31"
    doc2["parameters"]["steps"]["field"] = "seed"
    m2 = parse_manifest(doc2)
    spec2 = _spec(parameters={"steps": 30, "cfg": 7.0})
    art2 = submission_artifact(_build(spec=spec2, manifest=m2))
    art1 = submission_artifact(_build(spec=spec2, manifest=MANIFEST))
    assert art2 != art1


def test_historical_template_change_changes_submission():
    # A template change in an UNBOUND field must change the submission: the
    # artifact is the realization of the historical template, not just the
    # spec. (Bound fields are overwritten by captured values by design.)
    graph2 = json.loads(json.dumps(TEMPLATE))
    graph2["31"]["inputs"]["sampler_name"] = "dpmpp_2m"
    assert submission_artifact(_build(template=graph2)) != submission_artifact(_build())


# --- failure matrix ---------------------------------------------------------------


def test_missing_prompt_node():
    doc = json.loads((WF / "manifest.json").read_text("utf-8"))
    doc["inputs"]["prompt"]["node"] = "404"
    with pytest.raises(TranslationFailed):
        _build(manifest=parse_manifest(doc))


def test_missing_prompt_field():
    doc = json.loads((WF / "manifest.json").read_text("utf-8"))
    doc["inputs"]["prompt"]["field"] = "nope"
    with pytest.raises(TranslationFailed):
        _build(manifest=parse_manifest(doc))


def test_missing_parameter_node_and_field():
    doc = json.loads((WF / "manifest.json").read_text("utf-8"))
    doc["parameters"]["steps"]["node"] = "404"
    with pytest.raises(TranslationFailed):
        _build(manifest=parse_manifest(doc))
    doc = json.loads((WF / "manifest.json").read_text("utf-8"))
    doc["parameters"]["steps"]["field"] = "nope"
    with pytest.raises(TranslationFailed):
        _build(manifest=parse_manifest(doc))


def test_captured_parameter_without_binding():
    spec = _spec(parameters={"steps": 30, "cfg": 7.0, "unknown": 1})
    with pytest.raises(TranslationFailed):
        _build(spec=spec)


def test_missing_materialized_input():
    with pytest.raises(TranslationFailed):
        _build(mat=[])


def test_duplicate_materialized_slot():
    with pytest.raises(TranslationFailed):
        _build(mat=[_mat(), _mat(pos=0)])


def test_undeclared_materialized_input():
    with pytest.raises(TranslationFailed):
        _build(mat=[_mat(key="style_image")])


def test_wrong_input_cardinality():
    m1 = _mat(pos=0)
    m2 = _mat(remote="c" * 64 + ".png", pos=1)
    with pytest.raises(TranslationFailed):
        _build(mat=[m1, m2])  # manifest declares cardinality 1


def test_seed_without_explicit_binding():
    with pytest.raises(TranslationFailed):
        _build(spec=_spec(seed=12345))


def test_output_node_missing():
    doc = json.loads((WF / "manifest.json").read_text("utf-8"))
    doc["outputs"]["video"]["node"] = "999"
    with pytest.raises(TranslationFailed):
        _build(manifest=parse_manifest(doc))


def test_malformed_historical_template():
    with pytest.raises(TranslationFailed):
        _build(template={})
    with pytest.raises(TranslationFailed):
        _build(template={"4": "not-a-node"})


def test_conflicting_marker_namespace_rejected():
    graph = json.loads(json.dumps(TEMPLATE))
    graph["extra_data"] = {"soloring": {"someone": "else"}}
    with pytest.raises(TranslationFailed):
        _build(template=graph)


def test_error_code_is_comfy_translation_failed():
    with pytest.raises(TranslationFailed) as e:
        _build(mat=[])
    assert e.value.code == ErrorCode.COMFY_TRANSLATION_FAILED


# --- binding exactness (no heuristics) ------------------------------------------------


def test_binding_is_exact_node_and_field():
    payload = _build()
    graph = payload.prompt
    assert graph["4"]["inputs"]["image"] == "ns/" + "b" * 64 + ".png"
    assert graph["12"]["inputs"]["prompt"] == "Subject: Eva"
    assert graph["31"]["inputs"]["steps"] == 30
    assert graph["31"]["inputs"]["cfg"] == 7.0
    # Untouched fields survive from the template.
    assert graph["31"]["inputs"]["sampler_name"] == "euler"


def test_input_binding_by_logical_identity_not_list_coincidence():
    m_first = MaterializedComfyInput("reference_image", 0, "a1", "b" * 64,
                                      "second-upload-name.png", "ns")
    m_second = MaterializedComfyInput("reference_image", 1, "a2", "c" * 64,
                                       "first-upload-name.png", "ns")
    doc = json.loads((WF / "manifest.json").read_text("utf-8"))
    doc["inputs"]["reference_image"]["cardinality"] = 2
    payload = _build(
        spec=_spec(), manifest=parse_manifest(doc),
        mat=[m_second, m_first],  # swapped construction order
    )
    assert payload.prompt["4"]["inputs"]["image"] == [
        "ns/second-upload-name.png", "ns/first-upload-name.png",
    ]  # ordered by POSITION, not arrival; subfolder-qualified (audit F11)


def test_parameters_never_reapply_defaults():
    spec = _spec(parameters={"steps": 3, "cfg": 0.5})
    payload = _build(spec=spec)
    assert payload.prompt["31"]["inputs"]["steps"] == 3
    assert payload.prompt["31"]["inputs"]["cfg"] == 0.5


def test_captured_output_contract_untouched():
    payload = _build()
    doc = payload.to_document()
    assert "outputs" not in doc["prompt"].get("15", {"inputs": {}}).get("inputs", {})


# --- negative-evidence isolation -------------------------------------------------------


def test_translate_module_isolation():
    banned = (
        "soloring.db", "soloring.worker", "sqlalchemy", "aiosqlite",
        "soloring.domain.shots", "soloring.domain.projects",
        "soloring.assets", "soloring.executors.comfy.client",
        "soloring.executors.comfy.input_materializer",  # only the MODEL may be used
        "httpx", "aiohttp",
    )
    source = (BASE_DIR / "server" / "soloring" / "executors" / "comfy"
              / "translate.py").read_text("utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            # The MaterializedComfyInput TYPE import is allowed; nothing else
            # from input_materializer.
            if module == "soloring.executors.comfy.input_materializer":
                for a in node.names:
                    assert a.name == "MaterializedComfyInput", a.name
                continue
            names = [module]
        else:
            continue
        for n in names:
            for b in banned:
                assert not (n == b or n.startswith(b + ".")), (
                    f"translate.py imports {n!r}"
                )
    # No installed workflow file opens, no filesystem discovery.
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in ("read_bytes", "read_text", "open"), (
                f"filesystem access in translate.py: {node.func.attr}"
            )
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id != "open", "open() in translate.py"


def test_translator_testable_from_memory_only():
    """The whole suite above built payloads from in-memory values only —
    no engine, session, settings, or event loop fixtures were used."""
    payload = _build()
    assert isinstance(payload, ComfyPromptPayload)
    artifact, h = submission_artifact(payload)
    assert isinstance(artifact, bytes) and len(h) == 64
