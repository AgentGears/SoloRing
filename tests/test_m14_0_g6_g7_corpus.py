"""M14-0 G6/G7 golden fixture corpus (frozen R2 §§10.4/17/19/20/24).

Design-contract representation proof: the six frozen F06 canonical
vectors parse, canonicalize, hash, cross-link, and vocabulary-check
exactly as the frozen plan specifies — with no production M14 code and
no M13 authority mutation. This is the M14-0 gate ("all design-contract
examples can be represented without changing M13 authority") plus the
golden-vector proof-map cells OBS:18 / CAP:11 / PKG:09.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from soloring.domain.canonical import canonical_json_bytes

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "m14"

VECTOR_NAMES = {
    "spec": "m14-f06-world-observation-spec-v1.json",
    "negotiation": "m14-f06-negotiation-result-v1.json",
    "observation_block": "m14-f06-realization-profile-observation-v1.json",
    "workflow_v4": "m14-f06-workflow-spec-v4.json",
    "materializer_contract": "m14-f06-materializer-contract-v1.json",
    "profile_full": "m14-f06-realization-profile-v3-full.json",
}

PRESERVATION_VALUES = {
    "EXACT", "STRUCTURAL", "IDENTITY_APPEARANCE", "INFERABLE"}
ENFORCEMENT_VALUES = {"REQUIRED", "PERMITTED_INFERENCE"}
PRESERVATION_TO_ENFORCEMENT = {
    "EXACT": "REQUIRED",
    "STRUCTURAL": "REQUIRED",
    "IDENTITY_APPEARANCE": "REQUIRED",
    "INFERABLE": "PERMITTED_INFERENCE",
}
PROPERTIES = {
    "camera.projection", "world.structure", "occurrence.structure",
    "occurrence.placement", "visual.identity",
    "continuity.instance_feature", "shot.intent"}
SUBJECT_KINDS = {
    "shot", "spatial_world", "production_occurrence", "production_instance",
    "visual_reference_pack"}
AUTHORITY_SOURCE_KINDS = {
    "shot_revision", "spatial_continuity_pack", "spatial_world_revision",
    "visual_reference_pack", "composition_revision", "production_revision",
    "composition_spatial_binding", "production_world_pack"}
AUTHORITY_DOMAINS = {"A1", "A2", "A3", "A4", "A5", "A6"}
OCCURRENCE_PROPERTIES = {"occurrence.structure", "occurrence.placement"}


def _pins() -> dict:
    return json.loads(
        (FIXTURES / "m14_pins.json").read_text(encoding="utf-8"))


def _vector_bytes(name: str) -> bytes:
    return (FIXTURES / VECTOR_NAMES[name]).read_bytes()


def _vector(name: str) -> dict:
    return json.loads(_vector_bytes(name))


def _sha(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _requirement_order_key(req: dict) -> tuple[str, ...]:
    """Frozen R2 §10.1 identity-tuple order; null sorts as empty string."""
    return (
        req["property"],
        req["subject"]["kind"],
        req["subject"]["id"],
        req["occurrence_id"] or "",
        req["subkey"] or "",
        req["authority"]["domain"],
        req["authority"]["source_kind"],
        req["authority"]["source_id"],
        req["authority"]["source_hash"],
        req["source_contract"],
        req["preservation"],
        req["enforcement"],
    )


def test_pins_and_fixture_identities() -> None:
    pins = _pins()
    for key, filename in VECTOR_NAMES.items():
        raw = _vector_bytes(key)
        digest = hashlib.sha256(raw).hexdigest()
        assert digest == pins["f06"]["vectors"][filename], filename
        assert len(raw) == pins["f06"]["vector_bytes"][filename], filename
    assert pins["frozen_plan"]["sha256"] == (
        "68f910f5ff132fe00345fc41fa07f25e650d74ccd3f7ec445822194c03bde860")
    assert pins["frozen_plan"]["proof_cells"] == 90
    assert pins["frozen_plan"]["stop_conditions"] == 36
    assert pins["implementation_predecessor"]["commit"] == (
        "20429b3bf2ead3ca6c1d2402d5028e500bd4f9e8")
    assert pins["implementation_predecessor"]["tree"] == (
        "0a755efeeb9c87f1168f77e6905413affa435240")
    assert pins["migration_predecessor"] == "0014_m13_authority_complete_world"


def test_canonical_round_trip_all_vectors() -> None:
    for key in VECTOR_NAMES:
        raw = _vector_bytes(key)
        parsed = json.loads(raw.decode("utf-8"))
        assert canonical_json_bytes(parsed) == raw, key


def test_spec_root_grammar_closed() -> None:
    spec = _vector("spec")
    assert set(spec) == {
        "schema_version", "compiler", "shot_revision", "captured_domains",
        "policy", "requirements", "production_occurrences",
        "materializations"}
    assert spec["schema_version"] == 1
    assert spec["compiler"] == {
        "id": "soloring.world_observation", "version": 1}
    assert set(spec["captured_domains"]) == {
        "spatial_continuity_hash", "production_world_hash",
        "visual_reference_pack_hash"}
    assert set(spec["policy"]) == {"id", "version", "permitted_inference"}
    assert spec["policy"]["id"] == "structural-world-v1"
    assert spec["policy"]["version"] == 1
    assert spec["policy"]["permitted_inference"] == sorted(
        spec["policy"]["permitted_inference"])


def test_requirement_grammar_and_ordering() -> None:
    spec = _vector("spec")
    reqs = spec["requirements"]
    assert reqs, "golden vector must carry requirements"
    for req in reqs:
        assert set(req) == {
            "property", "preservation", "enforcement", "subject",
            "occurrence_id", "subkey", "authority", "source_contract"}
        assert req["property"] in PROPERTIES
        assert req["preservation"] in PRESERVATION_VALUES
        assert req["enforcement"] in ENFORCEMENT_VALUES
        assert (req["enforcement"]
                == PRESERVATION_TO_ENFORCEMENT[req["preservation"]])
        assert set(req["subject"]) == {"kind", "id"}
        assert req["subject"]["kind"] in SUBJECT_KINDS
        assert set(req["authority"]) == {
            "domain", "source_kind", "source_id", "source_hash"}
        assert req["authority"]["domain"] in AUTHORITY_DOMAINS
        assert (req["authority"]["source_kind"]
                in AUTHORITY_SOURCE_KINDS)
        assert req["source_contract"]
        if req["property"] in OCCURRENCE_PROPERTIES:
            assert req["occurrence_id"] is not None
        else:
            assert req["occurrence_id"] is None
        if req["property"] == "continuity.instance_feature":
            assert req["subkey"] is not None
        else:
            assert req["subkey"] is None
    keys = [_requirement_order_key(r) for r in reqs]
    assert keys == sorted(keys), "requirements must be in §10.1 order"


def test_production_occurrence_grammar() -> None:
    spec = _vector("spec")
    occurrences = spec["production_occurrences"]
    assert occurrences, "golden vector must carry one occurrence"
    for occ in occurrences:
        assert set(occ) == {
            "occurrence_id", "composition_revision_id",
            "composition_revision_hash", "production_revision_id",
            "production_revision_hash", "retained_blob_hash",
            "representation_contract", "placement_owner", "interpretation",
            "placement", "realization_local_to_world"}
        assert occ["placement_owner"] in {"A4", "A6"}
        assert occ["representation_contract"] == "soloring.structural_mesh.v1"
        assert set(occ["interpretation"]) == {
            "hash", "realization_local_to_subject_local"}
        assert set(occ["placement"]) == {
            "source_kind", "source_id", "source_hash",
            "subject_local_to_world"}
        for transform in (occ["interpretation"]
                          ["realization_local_to_subject_local"],
                          occ["placement"]["subject_local_to_world"],
                          occ["realization_local_to_world"]):
            assert set(transform) == {"translation_mm", "rotation_udeg"}
    ids = [o["occurrence_id"] for o in occurrences]
    assert len(ids) == len(set(ids)), "duplicate occurrence ids reject"


def test_materialization_grammar() -> None:
    spec = _vector("spec")
    mats = spec["materializations"]
    assert len(mats) == 1
    mat = mats[0]
    assert set(mat) == {
        "artifact_role", "materializer", "input_role",
        "source_occurrence_ids", "parameters", "parameters_hash"}
    assert mat["artifact_role"] == "observation.world_depth"
    assert mat["input_role"] == "spatial.world_depth"
    assert set(mat["materializer"]) == {"id", "version", "contract_hash"}
    assert set(mat["parameters"]) == {
        "width", "height", "frames", "time_base_num", "time_base_den",
        "mode", "background"}
    assert mat["parameters"] == {
        "width": 832, "height": 480, "frames": 17, "time_base_num": 1,
        "time_base_den": 17, "mode": "L", "background": 255}
    assert mat["parameters_hash"] == _sha(mat["parameters"])
    occurrence_ids = [o["occurrence_id"]
                      for o in spec["production_occurrences"]]
    assert mat["source_occurrence_ids"] == [
        oid for oid in occurrence_ids
        if oid in set(mat["source_occurrence_ids"])]


def test_observation_block_grammar() -> None:
    block = _vector("observation_block")
    assert set(block) == {
        "schema_version", "supported_policies", "capabilities",
        "materializers"}
    assert block["schema_version"] == 1
    for policy in block["supported_policies"]:
        assert set(policy) == {"id", "version"}
    for cap in block["capabilities"]:
        assert set(cap) == {
            "property", "preservation", "source_contract",
            "materializer_id", "materializer_version", "output_role"}
        assert cap["property"] in PROPERTIES
        assert cap["preservation"] in PRESERVATION_VALUES
        assert cap["output_role"] == "observation.world_depth"
    for mat in block["materializers"]:
        assert set(mat) == {
            "id", "version", "contract_hash", "output_role",
            "inherited_manifest_role"}
        assert mat["output_role"] == "observation.world_depth"
        assert mat["inherited_manifest_role"] == "spatial.world_depth"
    materializer_ids = {(m["id"], m["version"])
                        for m in block["materializers"]}
    for cap in block["capabilities"]:
        assert ((cap["materializer_id"], cap["materializer_version"])
                in materializer_ids), "capability must resolve"


def test_workflow_v4_grammar_and_links() -> None:
    workflow = _vector("workflow_v4")
    assert set(workflow) == {"schema_version", "lower_schema_3",
                             "world_observation"}
    assert workflow["schema_version"] == 4
    obs = workflow["world_observation"]
    assert set(obs) == {
        "spec", "spec_hash", "profile_hash", "capability_contract_hash",
        "negotiation", "negotiation_hash"}
    assert obs["spec_hash"] == _sha(obs["spec"])
    assert obs["spec_hash"] == hashlib.sha256(
        _vector_bytes("spec")).hexdigest()
    assert obs["negotiation_hash"] == _sha(obs["negotiation"])
    assert obs["negotiation_hash"] == hashlib.sha256(
        _vector_bytes("negotiation")).hexdigest()
    assert obs["capability_contract_hash"] == _sha(
        _vector("observation_block"))
    assert obs["profile_hash"] == _sha(_vector("profile_full"))
    lower = workflow["lower_schema_3"]
    assert lower["schema_version"] == 3
    assert set(("id", "version",
                "execution_model_fingerprint_hash")) <= set(lower["model"])
    sr = lower["spatial_realization"]
    assert sr["schema_version"] == 1
    assert sr["structured_bindings"] == []
    assert sr["derived_artifacts"]
    assert sr["derived_artifacts"][0]["position"] == 0
    assert sr["derived_artifacts"][0][
        "artifact_role"] == "spatial.world_depth"


def test_negotiation_result_grammar_and_links() -> None:
    neg = _vector("negotiation")
    assert set(neg) == {
        "schema_version", "operation_status", "verdict", "policy",
        "requirements"}
    assert neg["schema_version"] == 1
    assert neg["operation_status"] == "COMPLETED"
    assert neg["verdict"] in {"SUPPORTED", "UNSUPPORTED", "UNKNOWN"}
    assert set(neg["policy"]) == {"id", "version", "verdict"}
    spec = _vector("spec")
    block = _vector("observation_block")
    cap_by_tuple = {
        (c["property"], c["preservation"], c["source_contract"]): c
        for c in block["capabilities"]}
    assert len(neg["requirements"]) == len(spec["requirements"])
    for req, result in zip(spec["requirements"], neg["requirements"]):
        assert set(result) == {
            "requirement_identity_hash", "verdict", "capability"}
        assert result["requirement_identity_hash"] == _sha(req)
        if req["enforcement"] == "PERMITTED_INFERENCE":
            assert result["verdict"] == "PERMITTED_INFERENCE"
            assert result["capability"] is None
        else:
            assert result["verdict"] == "SUPPORTED"
            expected = cap_by_tuple[
                (req["property"], req["preservation"],
                 req["source_contract"])]
            assert result["capability"] == expected


def test_materializer_contract_grammar_and_caps() -> None:
    contract = _vector("materializer_contract")
    assert set(contract) == {
        "schema_version", "materializer", "rasterizer", "output_grammar",
        "resource_limits", "runtime"}
    assert contract["schema_version"] == 1
    assert set(contract["materializer"]) == {
        "id", "version", "implementation_sha256"}
    assert set(contract["rasterizer"]) == {
        "algorithm_id", "algorithm_version", "implementation_sha256"}
    assert set(contract["output_grammar"]) == {
        "artifact_digest", "background", "frames", "height", "mode",
        "pixel_encoding", "time_base_den", "time_base_num", "width"}
    assert contract["output_grammar"] == {
        "artifact_digest": "sha256-concatenated-frame-bytes",
        "background": 255, "frames": 17, "height": 480, "mode": "L",
        "pixel_encoding": "float32-mm->per-sequence-affine-uint8",
        "time_base_den": 17, "time_base_num": 1, "width": 832}
    assert set(contract["runtime"]) == {
        "architecture", "encoder_identity", "numpy", "pillow",
        "platform_contract", "python"}
    assert set(contract["runtime"]["encoder_identity"]) == {
        "pillow_native_module", "pillow_native_module_sha256",
        "python_abi_tag", "python_implementation", "platform",
        "zlib_compile_version", "zlib_runtime_version"}

    pins = _pins()["resource_policy"]
    limits = contract["resource_limits"]
    assert set(limits) == {
        "max_retained_mesh_bytes_per_revision",
        "max_total_triangles_per_observation",
        "max_triangles_per_revision", "max_vertices_per_revision",
        "production_time_budget_s"}
    assert limits == pins, "B1 caps must match the frozen pins exactly"

    spec = _vector("spec")
    block = _vector("observation_block")
    contract_hash = _sha(contract)
    assert (spec["materializations"][0]["materializer"]["contract_hash"]
            == contract_hash)
    assert (block["materializers"][0]["contract_hash"]
            == contract_hash)


def test_m14_obs_18() -> None:
    """M14-OBS:18 golden WorldObservationSpec fixture bytes/hash exact."""
    pins = _pins()
    assert hashlib.sha256(_vector_bytes("spec")).hexdigest() == pins[
        "f06"]["vectors"][VECTOR_NAMES["spec"]]
    assert json.loads(_vector_bytes("spec")) == _vector("workflow_v4")[
        "world_observation"]["spec"]


def test_m14_cap_11() -> None:
    """M14-CAP:11 NegotiationResult golden bytes/hash exact."""
    pins = _pins()
    assert hashlib.sha256(_vector_bytes("negotiation")).hexdigest() == pins[
        "f06"]["vectors"][VECTOR_NAMES["negotiation"]]
    assert json.loads(_vector_bytes("negotiation")) == _vector(
        "workflow_v4")["world_observation"]["negotiation"]


def test_m14_pkg_09() -> None:
    """M14-PKG:09 profile schema-3 observation golden fixture/hash exact."""
    pins = _pins()
    assert hashlib.sha256(
        _vector_bytes("observation_block")).hexdigest() == pins["f06"][
        "vectors"][VECTOR_NAMES["observation_block"]]
    profile = _vector("profile_full")
    assert profile["schema_version"] == 3
    assert profile["observation"] == _vector("observation_block")
