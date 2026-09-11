"""M14A-2 — Profile schema 3 + capability negotiation (frozen R2
§§8.9-8.11/17/20/36.1). Proof cells CAP:01-10 and CAP:12.

Exact matching (no broader tier, wildcard, node presence, or prompt
fallback), SUPPORTED/UNSUPPORTED/UNKNOWN with APR-111 operation/domain
separation, the typed pre-publication refusal contract, and runtime
discovery structurally outside the negotiation result.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
from pathlib import Path

import pytest

from soloring.errors import ErrorCode, SoloRingError
from soloring.observation import (
    capability_contract_hash,
    negotiate,
    negotiation_result_bytes,
    parse_profile_v3,
    require_publication_allowed,
    validate_observation_block,
)
from soloring.observation.spec import (
    build_world_observation_spec,
    parse_world_observation_spec,
)
from soloring.spatial.production_package import production_profile_v2

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "m14"

SHOT_ID = "00000000-0000-0000-0000-000000000101"
SHOT_REV_ID = "11111111-1111-1111-1111-111111111111"
WORLD_REV_ID = "55555555-5555-5555-5555-555555555555"
CONTRACT_HASH = ("dd3511218c673e7f2727d8226c3d73bfd85222bd5f9a5edb3d"
                 "2e4779146f66d0")


def _hex(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _load(name: str) -> dict:
    return json.loads(
        (FIXTURES / name).read_bytes().decode("utf-8"))


def _golden_spec() -> dict:
    return _load("m14-f06-world-observation-spec-v1.json")


def _golden_block() -> dict:
    return _load("m14-f06-realization-profile-observation-v1.json")


def _profile_v3(block: dict | None = None) -> dict:
    """A source-true schema-3 profile: the certified schema-2 profile
    plus the (default: golden) observation block."""
    profile = production_profile_v2()
    profile["schema_version"] = 3
    profile["observation"] = copy.deepcopy(
        block if block is not None else _golden_block())
    return profile


def _requirement(property_: str, preservation: str, enforcement: str,
                 contract: str, **authority) -> dict:
    authority.setdefault("domain", "A4")
    authority.setdefault("source_kind", "spatial_continuity_pack")
    authority.setdefault("source_id", SHOT_REV_ID)
    authority.setdefault("source_hash", _hex("source"))
    subject_kind = "shot"
    occurrence_id = None
    if property_.startswith("occurrence."):
        subject_kind = "production_occurrence"
        occurrence_id = authority.pop(
            "occurrence_id", "22222222-2222-2222-2222-222222222222")
    elif property_ == "continuity.instance_feature":
        subject_kind = "production_instance"
    elif property_ == "visual.identity":
        subject_kind = "visual_reference_pack"
    elif property_ == "world.structure":
        subject_kind = "spatial_world"
    return {
        "property": property_,
        "preservation": preservation,
        "enforcement": enforcement,
        "subject": {"kind": subject_kind,
                    "id": authority.get("subject_id", SHOT_ID)},
        "occurrence_id": occurrence_id,
        "subkey": authority.pop("subkey", None),
        "authority": authority,
        "source_contract": contract,
    }


def _spec(requirements: list[dict]) -> dict:
    return build_world_observation_spec(
        shot_revision_id=SHOT_REV_ID,
        plan_hash=_hex("plan"),
        captured_domains={
            "spatial_continuity_hash": _hex("spatial"),
            "production_world_hash": None,
            "visual_reference_pack_hash": None},
        requirements=requirements,
        production_occurrences=[],
        materializations=[{
            "artifact_role": "observation.world_depth",
            "materializer": {
                "id": "soloring.observation.mesh_depth",
                "version": 1,
                "contract_hash": CONTRACT_HASH},
            "input_role": "spatial.world_depth",
            "source_occurrence_ids": [],
            "parameters": {
                "width": 832, "height": 480, "frames": 17,
                "time_base_num": 1, "time_base_den": 17, "mode": "L",
                "background": 255},
            "parameters_hash": hashlib.sha256(json.dumps(
                {"background": 255, "frames": 17, "height": 480,
                 "mode": "L", "time_base_den": 17, "time_base_num": 1,
                 "width": 832},
                sort_keys=True, separators=(",", ":")).encode(
                    "utf-8")).hexdigest(),
        }])


# ---- CAP:01 strict profile schema-3 parser --------------------------------

def test_m14_cap_01() -> None:
    parse_profile_v3(_profile_v3())

    unknown_root = _profile_v3()
    unknown_root["surprise"] = 1
    with pytest.raises(SoloRingError):
        parse_profile_v3(unknown_root)

    missing = _profile_v3()
    del missing["observation"]
    with pytest.raises(SoloRingError):
        parse_profile_v3(missing)

    version = _profile_v3()
    version["schema_version"] = 2
    with pytest.raises(SoloRingError):
        parse_profile_v3(version)

    nested_unknown = _profile_v3()
    nested_unknown["observation"]["extra"] = 1
    with pytest.raises(SoloRingError):
        parse_profile_v3(nested_unknown)

    block_version = _profile_v3()
    block_version["observation"]["schema_version"] = 2
    with pytest.raises(SoloRingError):
        parse_profile_v3(block_version)

    capability_unknown = _profile_v3()
    capability_unknown["observation"]["capabilities"][0]["tier"] = "high"
    with pytest.raises(SoloRingError):
        parse_profile_v3(capability_unknown)

    unresolved = _profile_v3()
    unresolved["observation"]["capabilities"][0]["materializer_id"] = (
        "soloring.observation.other")
    with pytest.raises(SoloRingError, match="resolve"):
        parse_profile_v3(unresolved)

    duplicate_materializer = _profile_v3()
    duplicate_materializer["observation"]["materializers"].append(
        copy.deepcopy(
            duplicate_materializer["observation"]["materializers"][0]))
    with pytest.raises(SoloRingError, match="duplicate materializer"):
        parse_profile_v3(duplicate_materializer)

    duplicate_capability = _profile_v3()
    duplicate_capability["observation"]["capabilities"].append(
        copy.deepcopy(
            duplicate_capability["observation"]["capabilities"][0]))
    with pytest.raises(SoloRingError, match="duplicate capability"):
        parse_profile_v3(duplicate_capability)

    assert (capability_contract_hash(_profile_v3())
            == hashlib.sha256(json.dumps(
                _golden_block(), sort_keys=True, separators=(",", ":"),
                ensure_ascii=False).encode("utf-8")).hexdigest())


# ---- CAP:02 inherited profile-2 semantics delegated -----------------------

def test_m14_cap_02(monkeypatch) -> None:
    real = _profile_v3()
    parse_profile_v3(real)

    corrupt_base = _profile_v3()
    corrupt_base["spatial"]["max_control_streams"] = 5
    with pytest.raises(SoloRingError, match="max_control_streams"):
        parse_profile_v3(corrupt_base)

    corrupt_model = _profile_v3()
    corrupt_model["model"]["version"] = None
    with pytest.raises(SoloRingError):
        parse_profile_v3(corrupt_model)

    # The delegation itself is mechanical: the frozen schema-2 parser is
    # on the call path.
    import soloring.observation.capability as capability_module

    calls = []

    def spying(view):
        calls.append(view)
        return view

    monkeypatch.setattr(capability_module, "parse_profile_v2", spying)
    parse_profile_v3(_profile_v3())
    assert calls and calls[0]["schema_version"] == 2
    assert "observation" not in calls[0]


# ---- CAP:03 policy identity exact-match gate -------------------------------

def test_m14_cap_03() -> None:
    block = copy.deepcopy(_golden_block())
    block["supported_policies"] = [{"id": "structural-world-v1",
                                    "version": 2}]
    result = negotiate(_golden_spec(), block)
    assert result["policy"]["verdict"] == "UNSUPPORTED"
    assert result["verdict"] == "UNSUPPORTED"

    block = copy.deepcopy(_golden_block())
    block["supported_policies"] = [{"id": "structural-world-v2",
                                    "version": 1}]
    result = negotiate(_golden_spec(), block)
    assert result["policy"]["verdict"] == "UNSUPPORTED"

    result = negotiate(_golden_spec(), _golden_block())
    assert result["policy"] == {"id": "structural-world-v1", "version": 1,
                                "verdict": "SUPPORTED"}


# ---- CAP:04 exact tuple match ----------------------------------------------

def test_m14_cap_04() -> None:
    spec = _spec([
        _requirement("camera.projection", "STRUCTURAL", "REQUIRED",
                     "m10.camera_projection.v1"),
        _requirement("world.structure", "STRUCTURAL", "REQUIRED",
                     "m10.world_depth.v1"),
    ])
    result = negotiate(spec, _golden_block())
    verdicts = [res["verdict"] for res in result["requirements"]]
    assert verdicts == ["SUPPORTED", "SUPPORTED"]
    assert result["verdict"] == "SUPPORTED"

    # no broader preservation tier: the same property + source-contract
    # under EXACT never matches the declared STRUCTURAL capability
    spec = _spec([
        _requirement("world.structure", "EXACT", "REQUIRED",
                     "m10.world_depth.v1"),
    ])
    result = negotiate(spec, _golden_block())
    assert result["requirements"][0]["verdict"] == "UNSUPPORTED"
    assert result["requirements"][0]["capability"] is None

    supported = negotiate(_golden_spec(), _golden_block())
    echo = next(
        res["capability"] for req, res in
        zip(_golden_spec()["requirements"], supported["requirements"])
        if req["property"] == "occurrence.structure")
    golden_capability = next(
        cap for cap in _golden_block()["capabilities"]
        if cap["property"] == "occurrence.structure")
    assert echo == golden_capability

    # third-review ledger correction: the COMPLETE claimed tuple includes
    # the materializer identity — a block carrying mesh_depth v1 AND v2
    # whose occurrence.structure capability points at v2 does NOT
    # support the spec's pinned v1 materialization (the semantic triple
    # alone is never the coordinate)
    import copy

    two_materializer_block = copy.deepcopy(_golden_block())
    v2 = copy.deepcopy(two_materializer_block["materializers"][0])
    v2["version"] = 2
    v2["contract_hash"] = "a" * 64
    two_materializer_block["materializers"].append(v2)
    for capability in two_materializer_block["capabilities"]:
        if (capability["property"],
                capability["source_contract"]) == (
                "occurrence.structure",
                "soloring.structural_mesh.v1"):
            capability["materializer_version"] = 2
    result = negotiate(_golden_spec(), two_materializer_block)
    structure_row = next(
        res for req, res in
        zip(_golden_spec()["requirements"], result["requirements"])
        if req["property"] == "occurrence.structure")
    assert structure_row["verdict"] == "UNSUPPORTED", (
        "a capability for a different materializer version is a "
        "different tuple — never support for the pinned one")
    assert structure_row["capability"] is None
    assert result["verdict"] == "UNSUPPORTED"


# ---- CAP:05 supported hard requirement → SUPPORTED (+ golden bytes) -------

def test_m14_cap_05() -> None:
    result = negotiate(_golden_spec(), _golden_block())
    assert result["verdict"] == "SUPPORTED"
    assert result["operation_status"] == "COMPLETED"
    assert all(
        res["verdict"] in ("SUPPORTED", "PERMITTED_INFERENCE")
        for res in result["requirements"])

    golden = _load("m14-f06-negotiation-result-v1.json")
    assert negotiation_result_bytes(result) == (
        FIXTURES / "m14-f06-negotiation-result-v1.json").read_bytes()
    assert result == golden


# ---- CAP:06 property-known tuple mismatch → UNSUPPORTED -------------------

def test_m14_cap_06() -> None:
    spec = _spec([
        _requirement("world.structure", "STRUCTURAL", "REQUIRED",
                     "m10.world_depth.v9"),
    ])
    result = negotiate(spec, _golden_block())
    assert result["requirements"][0]["verdict"] == "UNSUPPORTED"
    assert result["requirements"][0]["capability"] is None
    assert result["verdict"] == "UNSUPPORTED"


# ---- CAP:07 property absent → UNKNOWN --------------------------------------

def _block_without_property(property_name: str) -> dict:
    """A block declaring the property in NEITHER list — the distinct
    UNKNOWN case per §8.10 as amended by Erratum E-1."""
    import copy

    block = copy.deepcopy(_golden_block())
    block["capabilities"] = [c for c in block["capabilities"]
                             if c["property"] != property_name]
    block["unsupported_capabilities"] = [
        c for c in block["unsupported_capabilities"]
        if c["property"] != property_name]
    return block


def test_m14_cap_07() -> None:
    # property absent from BOTH the supported and unsupported
    # declarations → the distinct UNKNOWN verdict
    spec = _spec([
        _requirement("occurrence.placement", "STRUCTURAL", "REQUIRED",
                     "m14.placement.v1"),
    ])
    result = negotiate(spec, _block_without_property("occurrence.placement"))
    assert result["requirements"][0]["verdict"] == "UNKNOWN"
    assert result["requirements"][0]["capability"] is None
    assert result["verdict"] == "UNKNOWN"

    # a property DECLARED in the unsupported list with the exact tuple →
    # UNSUPPORTED — the frozen §15 v2 rows (N1/N2)
    spec = _spec([
        _requirement("visual.identity", "IDENTITY_APPEARANCE", "REQUIRED",
                     "m8.visual_reference_pack.v1", domain="A3",
                     source_kind="visual_reference_pack"),
    ])
    result = negotiate(spec, _golden_block())
    assert result["requirements"][0]["verdict"] == "UNSUPPORTED"
    assert result["verdict"] == "UNSUPPORTED"


# ---- CAP:08 PERMITTED_INFERENCE needs no capability ------------------------

def test_m14_cap_08() -> None:
    spec = _spec([
        _requirement("shot.intent", "INFERABLE", "PERMITTED_INFERENCE",
                     "lower_schema_3.prompt", domain="A1",
                     source_kind="shot_revision"),
    ])
    result = negotiate(spec, _golden_block())
    (intent,) = result["requirements"]
    assert intent["verdict"] == "PERMITTED_INFERENCE"
    assert intent["capability"] is None
    assert result["verdict"] == "SUPPORTED"


# ---- CAP:09 overall verdict precedence exact --------------------------------

def test_m14_cap_09() -> None:
    # precedence under the amended law: UNKNOWN (property absent from
    # both declarations) + UNSUPPORTED (known property, unmatched tuple)
    # → overall UNSUPPORTED dominates
    mixed = _spec([
        _requirement("occurrence.placement", "STRUCTURAL", "REQUIRED",
                     "m14.placement.v1"),
        _requirement("world.structure", "STRUCTURAL", "REQUIRED",
                     "m10.world_depth.v9"),
    ])
    result = negotiate(mixed, _block_without_property(
        "occurrence.placement"))
    assert result["requirements"][0]["verdict"] == "UNKNOWN"
    assert result["requirements"][1]["verdict"] == "UNSUPPORTED"
    assert result["verdict"] == "UNSUPPORTED"  # UNSUPPORTED dominates UNKNOWN

    unknown_only = _spec([
        _requirement("occurrence.placement", "STRUCTURAL", "REQUIRED",
                     "m14.placement.v1"),
    ])
    assert negotiate(unknown_only, _block_without_property(
        "occurrence.placement"))["verdict"] == "UNKNOWN"

    all_supported = negotiate(_golden_spec(), _golden_block())
    assert all_supported["verdict"] == "SUPPORTED"


# ---- CAP:10 pre-publication refusal contract -------------------------------

def test_m14_cap_10() -> None:
    supported = negotiate(_golden_spec(), _golden_block())
    assert require_publication_allowed(supported,
                                       _golden_spec()) is None

    unknown = negotiate(_spec([
        _requirement("occurrence.placement", "STRUCTURAL", "REQUIRED",
                     "m14.placement.v1"),
    ]), _block_without_property("occurrence.placement"))
    spec = parse_world_observation_spec(_spec([
        _requirement("occurrence.placement", "STRUCTURAL", "REQUIRED",
                     "m14.placement.v1"),
    ]))
    with pytest.raises(SoloRingError) as excinfo:
        require_publication_allowed(unknown, spec)
    assert excinfo.value.code == (
        ErrorCode.OBSERVATION_REQUIREMENT_UNKNOWN)
    assert excinfo.value.status_code == 409
    (trace,) = excinfo.value.details["requirements"]
    assert trace["property"] == "occurrence.placement"
    assert trace["verdict"] == "UNKNOWN"

    # the frozen §15 v2 rows: REQUIRED visual.identity under the initial
    # profile → UNSUPPORTED (N1), never UNKNOWN
    n1 = negotiate(_spec([
        _requirement("visual.identity", "IDENTITY_APPEARANCE", "REQUIRED",
                     "m8.visual_reference_pack.v1", domain="A3",
                     source_kind="visual_reference_pack"),
    ]), _golden_block())
    n1_spec = parse_world_observation_spec(_spec([
        _requirement("visual.identity", "IDENTITY_APPEARANCE", "REQUIRED",
                     "m8.visual_reference_pack.v1", domain="A3",
                     source_kind="visual_reference_pack"),
    ]))
    with pytest.raises(SoloRingError) as excinfo:
        require_publication_allowed(n1, n1_spec)
    assert excinfo.value.code == (
        ErrorCode.OBSERVATION_REQUIREMENT_UNSUPPORTED)

    unsupported = negotiate(_spec([
        _requirement("world.structure", "STRUCTURAL", "REQUIRED",
                     "m10.world_depth.v9"),
    ]), _golden_block())
    spec = parse_world_observation_spec(_spec([
        _requirement("world.structure", "STRUCTURAL", "REQUIRED",
                     "m10.world_depth.v9"),
    ]))
    with pytest.raises(SoloRingError) as excinfo:
        require_publication_allowed(unsupported, spec)
    assert excinfo.value.code == (
        ErrorCode.OBSERVATION_REQUIREMENT_UNSUPPORTED)

    block = copy.deepcopy(_golden_block())
    block["supported_policies"] = [{"id": "structural-world-v1",
                                    "version": 2}]
    policy_bad = negotiate(_golden_spec(), block)
    with pytest.raises(SoloRingError) as excinfo:
        require_publication_allowed(policy_bad, _golden_spec())
    assert excinfo.value.code == ErrorCode.OBSERVATION_POLICY_UNSUPPORTED

    with pytest.raises(SoloRingError, match="APR-111"):
        require_publication_allowed(
            {"schema_version": 1, "operation_status": "FAILED"},
            _golden_spec())


# ---- CAP:12 runtime discovery cannot upgrade a verdict ---------------------

def test_m14_cap_12() -> None:
    spec = _spec([
        _requirement("world.structure", "STRUCTURAL", "REQUIRED",
                     "m10.world_depth.v9"),
    ])
    result = negotiate(spec, _golden_block())
    assert result["verdict"] == "UNSUPPORTED"

    # Runtime availability is structurally not an input: no parameter,
    # no module state, and re-negotiation is byte-stable. A fabricated
    # "installed node" record has nowhere to go.
    parameters = inspect.signature(negotiate).parameters
    assert set(parameters) == {"spec", "observation_block"}
    with pytest.raises(TypeError):
        negotiate(spec, _golden_block(),
                  runtime_availability={"nodes": ["WanDepth"]})

    again = negotiate(spec, _golden_block())
    assert negotiation_result_bytes(again) == (
        negotiation_result_bytes(result))

    import soloring.observation.capability as capability_module
    soloring_modules = {
        mod.__name__ for mod in vars(capability_module).values()
        if inspect.ismodule(mod)
        and mod.__name__.startswith("soloring")}
    assert soloring_modules <= {
        "soloring.errors", "soloring.observation.spec",
        "soloring.domain.canonical", "soloring.spatial.package3"}, (
        "negotiation may not import runtime/executor/discovery modules")
