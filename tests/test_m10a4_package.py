"""M10A-4 focused tests — package/profile/manifest schema 3 + runtime closure
+ workflow-spec v3 lattice (directive §9)."""
import pytest

from soloring.spatial import package3 as P
from soloring.spatial import spec3 as W


def _profile():
    return {
        "schema_version": 2, "profile_id": "p", "profile_version": 1,
        "workflow_id": "wf", "workflow_version": 1,
        "model": {"id": "m", "version": "1"},
        "channels": {}, "rules": [], "parameter_overrides": {},
        "spatial": {
            "spatial_document_schema": 1, "max_control_streams": 3,
            "roles": {
                "spatial.world_depth": {"kind": "derived", "capacity": 1},
                "spatial.entity_depth": {"kind": "derived", "capacity": 2},
            },
            "runtime_requirements": {
                "controlnet": {
                    "kind": "control_model", "name": "depth-v1",
                    "proof": {"mode": "fingerprint_component",
                              "value": "a" * 64},
                },
            },
            "advisory_omissions": [],
        },
    }


def _manifest():
    return {
        "schema_version": "3", "version": 1, "workflow_id": "wf",
        "inputs": {"world_depth": {}, "eva_depth": {}},
        "parameters": {}, "outputs": {},
        "spatial_bindings": {
            "world_depth": {"artifact_role": "spatial.world_depth",
                            "node": "7", "field": "control_images",
                            "format": "soloring.spatial.v1"},
            "eva_depth": {"artifact_role": "spatial.entity_depth",
                          "node": "8", "field": "control_images",
                          "format": "soloring.spatial.v1"},
        },
    }


# ---- profile ---------------------------------------------------------------

def test_profile_v2_valid():
    P.parse_profile_v2(_profile())


def test_profile_unknown_field_rejected():
    doc = _profile()
    doc["spatial"]["mystery"] = 1
    with pytest.raises(P.Package3Invalid, match="unknown fields"):
        P.parse_profile_v2(doc)


def test_profile_capacity_must_be_three():
    doc = _profile()
    doc["spatial"]["max_control_streams"] = 5
    with pytest.raises(P.Package3Invalid, match="max_control_streams"):
        P.parse_profile_v2(doc)


def test_profile_no_structured_camera_role():
    doc = _profile()
    doc["spatial"]["roles"]["structured.camera"] = {"kind": "structured",
                                                    "capacity": 1}
    with pytest.raises(P.Package3Invalid, match="Path B"):
        P.parse_profile_v2(doc)


def test_profile_descriptive_runtime_pin_rejected():
    doc = _profile()
    doc["spatial"]["runtime_requirements"]["wrapper"] = {
        "kind": "custom_node", "name": "WanVideoWrapper",
        "proof": {"mode": "descriptive", "value": "it is installed"},
    }
    with pytest.raises(P.Package3Invalid, match="descriptive"):
        P.parse_profile_v2(doc)


# ---- manifest ---------------------------------------------------------------

def test_manifest_v3_valid():
    P.parse_manifest_v3(_manifest())


def test_manifest_requires_exactly_one_world_stream():
    doc = _manifest()
    del doc["spatial_bindings"]["world_depth"]
    with pytest.raises(P.Package3Invalid, match="world_depth"):
        P.parse_manifest_v3(doc)


def test_manifest_three_entity_streams_rejected():
    doc = _manifest()
    for name, node in (("clerk_depth", "9"), ("baggage_depth", "10")):
        doc["inputs"][name] = {}
        doc["spatial_bindings"][name] = {
            "artifact_role": "spatial.entity_depth", "node": node,
            "field": "control_images", "format": "soloring.spatial.v1"}
    with pytest.raises(P.Package3Invalid, match="At most two"):
        P.parse_manifest_v3(doc)


def test_manifest_binding_without_input_rejected():
    doc = _manifest()
    del doc["inputs"]["eva_depth"]
    with pytest.raises(P.Package3Invalid, match="no manifest input"):
        P.parse_manifest_v3(doc)


def test_manifest_bad_format_rejected():
    doc = _manifest()
    doc["spatial_bindings"]["world_depth"]["format"] = "h.264"
    with pytest.raises(P.Package3Invalid, match="format"):
        P.parse_manifest_v3(doc)


def test_resolve_binding_world_first_then_entity_sorted_keys():
    m = P.parse_manifest_v3(_manifest())
    key, node, field = P.resolve_derived_binding(m, "spatial.world_depth", 0)
    assert (key, node, field) == ("world_depth", "7", "control_images")
    key, node, field = P.resolve_derived_binding(m, "spatial.entity_depth", 1)
    assert key == "eva_depth" and node == "8"
    with pytest.raises(P.Package3Invalid):
        P.resolve_derived_binding(m, "spatial.entity_depth", 2)


# ---- runtime closure ---------------------------------------------------------

def _fingerprint():
    return {
        "runtime_requirements": {
            "comfyui_commit": "b963f4a" + "0" * 33,
            "custom_nodes": {},
            "artifacts": [{"declared_name": "depth-v1",
                           "sha256": "a" * 64}],
        },
    }


def test_closure_proven_by_fingerprint_artifact():
    prof = P.parse_profile_v2(_profile())
    unproven = P.check_runtime_closure(prof["spatial"],
                                       fingerprint=_fingerprint(),
                                       template={})
    assert unproven == []


def test_closure_unpinned_wrapper_fails():
    prof = P.parse_profile_v2(_profile())
    prof["spatial"]["runtime_requirements"]["wrapper"] = {
        "kind": "custom_node", "name": "WanVideoWrapper",
        "proof": {"mode": "fingerprint_component", "value": "b" * 64},
    }
    unproven = P.check_runtime_closure(prof["spatial"],
                                       fingerprint=_fingerprint(),
                                       template={})
    assert unproven == ["wrapper"]


def test_closure_proven_by_template_node_field():
    prof = P.parse_profile_v2(_profile())
    prof["spatial"]["runtime_requirements"]["policy"] = {
        "kind": "template_policy", "name": "scheduler",
        "proof": {"mode": "template_node_field", "value": "160/scheduler"},
    }
    template = {"160": {"class_type": "WanVideoSampler",
                        "inputs": {"scheduler": "unipc"}}}
    unproven = P.check_runtime_closure(prof["spatial"],
                                       fingerprint=_fingerprint(),
                                       template=template)
    assert unproven == []


def test_closure_template_disagreement_fails():
    prof = P.parse_profile_v2(_profile())
    prof["spatial"]["runtime_requirements"]["policy"] = {
        "kind": "template_policy", "name": "scheduler",
        "proof": {"mode": "template_node_field", "value": "160/scheduler"},
    }
    template = {"160": {"class_type": "WanVideoSampler",
                        "inputs": {"steps": 20}}}  # scheduler absent
    unproven = P.check_runtime_closure(prof["spatial"],
                                       fingerprint=_fingerprint(),
                                       template=template)
    assert unproven == ["policy"]


# ---- workflow-spec v3 lattice -------------------------------------------------

def _base_spec():
    return {"prompt": "p", "inputs": {}, "parameters": {}}


def _model():
    return {"id": "wan", "version": "1.3B",
            "execution_model_fingerprint_hash": "f" * 64}


def _sr(n=1):
    return W.build_spatial_realization_block(
        spatial_continuity_hash="c" * 64,
        derived_artifacts=[{
            "input_key": "world_depth", "position": 0,
            "artifact_role": "spatial.world_depth",
            "derived_spatial_artifact_id": "id1",
            "spec_hash": "a" * 64, "runtime_fingerprint_hash": "b" * 64,
            "blob_hash": "d" * 64}] * 1 + ([{
            "input_key": "eva", "position": 1,
            "artifact_role": "spatial.entity_depth",
            "derived_spatial_artifact_id": "id2",
            "spec_hash": "a" * 64, "runtime_fingerprint_hash": "b" * 64,
            "blob_hash": "e" * 64}] if n > 1 else []))


def test_v3_m10_only_retains_model_and_has_no_fake_m9_block():
    spec = W.compose_workflow_spec_v3(_base_spec(), model=_model(),
                                      realization=None,
                                      spatial_realization=_sr())
    W.validate_spec_v3(spec)
    assert spec["model"]["id"] == "wan"
    assert "realization" not in spec
    assert spec["spatial_realization"]["derived_artifacts"]


def test_v3_m9_plus_m10_contains_both():
    spec = W.compose_workflow_spec_v3(_base_spec(), model=_model(),
                                      realization={"channels": []},
                                      spatial_realization=_sr())
    W.validate_spec_v3(spec)
    assert "realization" in spec and "spatial_realization" in spec


def test_no_empty_v3():
    with pytest.raises(Exception):
        W.build_spatial_realization_block(spatial_continuity_hash="c" * 64)


def test_v3_structured_bindings_rejected_initial():
    with pytest.raises(Exception, match="Path B"):
        W.build_spatial_realization_block(
            spatial_continuity_hash="c" * 64,
            derived_artifacts=[_sr()["derived_artifacts"][0]],
            structured_bindings=[{"role": "spatial.camera"}])


def test_v3_missing_model_identity_rejected():
    spec = W.compose_workflow_spec_v3(_base_spec(), model=_model(),
                                      realization=None,
                                      spatial_realization=_sr())
    del spec["model"]
    with pytest.raises(Exception, match="model identity"):
        W.validate_spec_v3(spec)


def test_v3_bytes_hash_deterministic():
    a = W.compose_workflow_spec_v3(_base_spec(), model=_model(),
                                   realization=None, spatial_realization=_sr())
    b = W.compose_workflow_spec_v3(_base_spec(), model=_model(),
                                   realization=None, spatial_realization=_sr())
    assert W.spec_v3_bytes_hash(a) == W.spec_v3_bytes_hash(b)
