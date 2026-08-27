"""M10 profile schema 2 / manifest schema 3 / package descriptor schema 3
(frozen r3 §111, directive items 4+2.3).

Additive paths only: the published schema-1/2 parsers in realization/profile
and workflows/manifest are untouched; this module parses the M10 documents
and enforces the runtime-requirement closure rule — every declared runtime
requirement must be proven either by an exact captured ExecutionModelFinger-
print identity or by an exact node/field/value in the captured workflow
template. Descriptive-only profile text can never pass as a runtime pin.
"""
from __future__ import annotations

import json
from typing import Any

from soloring.errors import ErrorCode, SoloRingError
from soloring.spatial import error_codes as ec
from soloring.spatial.derived_inputs import (
    INITIAL_MAX_CONTROL_STREAMS,
)

ROLE_WORLD_DEPTH = "spatial.world_depth"
ROLE_ENTITY_DEPTH = "spatial.entity_depth"

PROFILE_SCHEMA_VERSION_2 = 2
MANIFEST_SCHEMA_VERSION_3 = "3"
DESCRIPTOR_SCHEMA_VERSION_3 = 3

STREAM_ROLES = (ROLE_WORLD_DEPTH, ROLE_ENTITY_DEPTH)


class Package3Invalid(SoloRingError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.SPATIAL_REALIZATION_BINDING_INVALID,
                         message, status_code=422)


def _bad(message: str) -> Package3Invalid:
    return Package3Invalid(message)


def _require_dict(value: Any, what: str) -> dict:
    if not isinstance(value, dict):
        raise _bad(f"{what} must be an object.")
    return value


def _require_str(value: Any, what: str) -> str:
    if not isinstance(value, str) or not value:
        raise _bad(f"{what} must be a non-empty string.")
    return value


def _exact_keys(doc: dict, allowed: set[str], what: str) -> None:
    unknown = sorted(set(doc) - allowed)
    if unknown:
        raise _bad(f"{what} has unknown fields {unknown}; the field set is closed.")


# --------------------------------------------------------------------------
# RealizationProfile schema 2 (§111)
# --------------------------------------------------------------------------

def parse_profile_v2(raw: Any) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError as exc:
            raise _bad(f"RealizationProfile v2 is not valid JSON: {exc}") from exc
    doc = _require_dict(raw, "RealizationProfile v2")
    _exact_keys(doc, {
        "schema_version", "profile_id", "profile_version", "workflow_id",
        "workflow_version", "model", "channels", "rules",
        "parameter_overrides", "spatial",
    }, "RealizationProfile v2")
    if doc["schema_version"] != PROFILE_SCHEMA_VERSION_2:
        raise _bad("RealizationProfile schema_version must be 2 for spatial.")

    # Inherited M9 profile-1 portion is validated by the FROZEN M9 parser
    # itself (strict unknown-field rejection, selector semantics, channel
    # bijection, min<=max): delegate, never reimplement (blocker 5). The
    # legacy parser pins schema_version==1, so validate the inherited
    # fields through a schema-1 view and keep the v2 wrapper.
    from soloring.realization.profile import (
        ProfileError as _M9ProfileError,
        parse_profile as _parse_m9_profile,
    )
    inherited = {k: v for k, v in doc.items() if k != "spatial"}
    inherited["schema_version"] = 1
    try:
        _parse_m9_profile(inherited)
    except _M9ProfileError as exc:
        raise _bad(f"Inherited profile-1 portion invalid: {exc}") from exc

    spatial = _require_dict(doc["spatial"], "spatial")
    _exact_keys(spatial, {
        "spatial_document_schema", "max_control_streams", "roles",
        "runtime_requirements", "advisory_omissions",
    }, "spatial")
    if spatial["spatial_document_schema"] != 1:
        raise _bad("spatial.spatial_document_schema must be 1.")
    if spatial["max_control_streams"] != INITIAL_MAX_CONTROL_STREAMS:
        raise _bad("Initial M10 freezes max_control_streams=3.")
    omissions = spatial["advisory_omissions"]
    if not isinstance(omissions, list) or any(
            not isinstance(o, str) for o in omissions):
        raise _bad("spatial.advisory_omissions must be a string list.")
    _validate_roles(spatial["roles"])
    _validate_runtime_requirements(spatial["runtime_requirements"])
    return doc


def _validate_roles(roles_raw: Any) -> None:
    roles = _require_dict(roles_raw, "spatial.roles")
    world = roles.get(ROLE_WORLD_DEPTH)
    entity = roles.get(ROLE_ENTITY_DEPTH)
    if not isinstance(world, dict) or not isinstance(entity, dict):
        raise _bad("roles must declare spatial.world_depth and "
                   "spatial.entity_depth.")
    for name, role in ((ROLE_WORLD_DEPTH, world), (ROLE_ENTITY_DEPTH, entity)):
        _exact_keys(role, {"kind", "capacity"}, f"roles.{name}")
        if role["kind"] not in ("derived",):
            raise _bad(f"roles.{name}.kind must be 'derived' in initial M10.")
        cap = role["capacity"]
        if name == ROLE_WORLD_DEPTH and cap != 1:
            raise _bad("spatial.world_depth capacity is exactly 1.")
        if name == ROLE_ENTITY_DEPTH and cap != 2:
            raise _bad("spatial.entity_depth capacity is exactly 2 in initial M10.")
    if any(str(r) == "spatial.camera" or str(r).startswith("structured")
           for r in roles):
        raise _bad("Initial M10 camera execution is frozen to derived "
                   "Path B; no structured spatial.camera role is declarable.")
    unknown = sorted(set(roles) - set(STREAM_ROLES))
    if unknown:
        raise _bad(f"roles has unknown streams {unknown}; initial M10 supports "
                   f"{list(STREAM_ROLES)} only.")


def _validate_runtime_requirements(reqs_raw: Any) -> None:
    reqs = _require_dict(reqs_raw, "spatial.runtime_requirements")
    for key, req in reqs.items():
        req = _require_dict(req, f"runtime_requirements.{key}")
        _exact_keys(req, {"kind", "name", "proof"}, f"runtime_requirements.{key}")
        _require_str(req["kind"], f"runtime_requirements.{key}.kind")
        _require_str(req["name"], f"runtime_requirements.{key}.name")
        proof = _require_dict(req["proof"], f"runtime_requirements.{key}.proof")
        _exact_keys(proof, {"mode", "value", "expected"},
                    f"runtime_requirements.{key}.proof")
        if proof["mode"] not in ("fingerprint_component", "template_node_field"):
            raise _bad(f"runtime_requirements.{key}.proof.mode must be "
                       "fingerprint_component or template_node_field — a "
                       "descriptive requirement cannot pass as a runtime pin.")
        _require_str(proof["value"], f"runtime_requirements.{key}.proof.value")
        if proof["mode"] == "template_node_field":
            # expected = the exact canonical JSON-domain value the captured
            # template must carry at node/field; presence alone proves
            # nothing (closure review blocker 1).
            if "expected" not in proof:
                raise _bad(f"runtime_requirements.{key}.proof.expected is "
                           "required for template_node_field proofs.")
            _validate_json_domain(proof["expected"],
                                  f"runtime_requirements.{key}.proof.expected")


def validate_schema3_fingerprint_template(fingerprint_v3: dict,
                                          template: dict) -> None:
    """Full hard-component closure for the schema-3 ExecutionModelFinger-
    print against the CAPTURED package documents (R3 §6/§18, E-012):

    1. the m10_spatial_runtime artifact set must carry exactly the four
       frozen model artifacts (wan_base, depth_controlnet,
       umt5_text_encoder, wan_vae) — removing UMT5 or the VAE leaves an
       unclosable requirement and fails package validation;
    2. every fingerprint artifact binding (node, field, declared_name)
       must cross-check against the CAPTURED TEMPLATE: the template node
       must exist, the field must exist, and the template's value at that
       node/field must EQUAL the declared_name — a captured template that
       instructs the executor to load a different, unpinned file is a
       binding-invalid package even when the legitimate pinned file still
       exists on disk.
    """
    rr = (fingerprint_v3 or {}).get("m10_spatial_runtime") or {}
    artifacts = rr.get("artifacts") or []
    keys = [a.get("artifact_key") for a in artifacts
            if isinstance(a, dict)]
    required = {"wan_base", "depth_controlnet", "umt5_text_encoder",
                "wan_vae"}
    missing = sorted(required - set(keys))
    extra = sorted(set(keys) - required)
    if missing or extra:
        raise _bad(
            f"m10_spatial_runtime.artifacts must be exactly the frozen "
            f"four {sorted(required)}; missing={missing}, extra={extra}")
    if not isinstance(template, dict) or not template:
        raise _bad("captured workflow template is empty or malformed")
    for a in artifacts:
        node, field = a.get("node"), a.get("field")
        declared = a.get("declared_name")
        what = f"fingerprint artifact {a.get('artifact_key')!r}"
        if not isinstance(node, str) or not node:
            raise _bad(f"{what}: no template node binding")
        if not isinstance(field, str) or not field:
            raise _bad(f"{what}: no template field binding")
        if not isinstance(declared, str) or not declared:
            raise _bad(f"{what}: no declared_name")
        node_doc = template.get(node)
        if not isinstance(node_doc, dict):
            raise _bad(f"{what}: template has no node {node!r}")
        inputs = node_doc.get("inputs")
        if not isinstance(inputs, dict) or field not in inputs:
            raise _bad(f"{what}: node {node!r} has no input field "
                       f"{field!r}")
        if inputs[field] != declared:
            raise _bad(
                f"{what}: captured template carries {inputs[field]!r} at "
                f"{node}/{field} but the fingerprint pins {declared!r} — "
                "the template does not execute the pinned artifact")


def check_runtime_closure(profile_spatial: dict, *, fingerprint: dict | None,
                          template: dict) -> list[str]:
    """Return the list of UNPROVEN runtime requirements (empty == closed).

    A requirement is proven when either:
      * proof.mode == fingerprint_component and the captured
        ExecutionModelFingerprint contains that exact component identity; or
      * proof.mode == template_node_field with value 'node/field' and the
        captured template carries that exact node id, input field, AND the
        expected canonical value under strict JSON-domain equality — field
        presence alone proves nothing (closure review blocker 1).
    """
    unproven: list[str] = []
    for key, req in profile_spatial["runtime_requirements"].items():
        proof = req["proof"]
        if proof["mode"] == "fingerprint_component":
            proven = _closed_by_fingerprint(req, proof, fingerprint)
        else:
            proven = _closed_by_template(proof["value"],
                                         proof.get("expected"), template)
        if not proven:
            unproven.append(key)
    return unproven


def _closed_by_fingerprint(req: dict, proof: dict,
                           fingerprint: dict | None) -> bool:
    if not fingerprint:
        return False
    name = req["name"]
    # A captured schema-3 fingerprint artifact carries its closure facts in
    # the frozen "m10_spatial_runtime" extension document (production
    # fingerprint shape); the bare root "runtime_requirements" form remains
    # accepted for documents that carry it directly (M10A test fixtures).
    rr = (fingerprint.get("runtime_requirements")
          or fingerprint.get("m10_spatial_runtime") or {})
    if rr.get("custom_nodes", {}).get(name) == proof["value"]:
        return True
    for artifact in rr.get("artifacts", []) if isinstance(rr, dict) else []:
        if artifact.get("declared_name") == name and \
                proof["value"] in (artifact.get("sha256"),):
            return True
    if proof["value"] == rr.get("comfyui_commit"):
        return True
    return False


def _closed_by_template(node_field: str, expected: object, template: dict) -> bool:
    """Exact node/field/VALUE proof: the captured template must carry the
    expected canonical value at the declared node/field under strict
    JSON-domain equality (int is never coerced to float, etc.)."""
    try:
        node_id, field = node_field.split("/", 1)
    except ValueError:
        return False
    node = template.get(node_id)
    if not isinstance(node, dict):
        return False
    inputs = node.get("inputs")
    if not isinstance(inputs, dict) or field not in inputs:
        return False
    return _json_domain_equal(inputs[field], expected)


def _json_domain_equal(a: object, b: object) -> bool:
    """Type-exact structural equality in the JSON domain: bool never
    equals int, int never equals float, composites match recursively."""
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(
            _json_domain_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(
            _json_domain_equal(x, y) for x, y in zip(a, b))
    return a == b


def _validate_json_domain(value: object, what: str) -> None:
    """Strict JSON-domain validation for dict-callers, anchored on the ONE
    canonical serializer: rejects NaN/Infinity and non-finite floats,
    tuples and any non-JSON Python object, non-string keys, floats
    entirely (runtime expected-values are int/str/bool/null/structure
    only in this contract), and integers outside the JS-safe domain."""
    from soloring.domain.canonical import canonical_json_bytes

    try:
        canonical_json_bytes(value)
    except (TypeError, ValueError) as exc:
        raise _bad(f"{what} is not a JSON-domain value: {exc}") from exc
    stack: list[object] = [value]
    while stack:
        v = stack.pop()
        if v is None or isinstance(v, (str, bool)):
            continue
        if isinstance(v, float):
            raise _bad(f"{what} contains a float; runtime closure "
                       "expected-values are int/str/bool/null/structure "
                       "only.")
        if isinstance(v, int):
            if not (-(2 ** 53) + 1 <= v <= 2 ** 53 - 1):
                raise _bad(f"{what} integer outside the JavaScript-safe "
                           "domain.")
            continue
        if isinstance(v, dict):
            if any(not isinstance(k, str) for k in v):
                raise _bad(f"{what} has non-string keys.")
            stack.extend(v.values())
        elif isinstance(v, list):
            stack.extend(v)
        else:
            raise _bad(f"{what} contains a non-JSON value of type "
                       f"{type(v).__name__}.")


# --------------------------------------------------------------------------
# Manifest schema 3 (§111: role -> input_key -> node -> field)
# --------------------------------------------------------------------------

def parse_manifest_v3(raw: Any) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError as exc:
            raise _bad(f"manifest v3 is not valid JSON: {exc}") from exc
    doc = _require_dict(raw, "manifest v3")
    _exact_keys(doc, {
        "schema_version", "version", "workflow_id", "inputs", "parameters",
        "outputs", "spatial_bindings",
    }, "manifest v3")
    if doc["schema_version"] != MANIFEST_SCHEMA_VERSION_3:
        raise _bad("manifest schema_version must be 3.")

    # Inherited manifest-2 portion is validated by the FROZEN M9 schema-2
    # parser (strict inputs/parameters/outputs, no dual source form):
    # delegate, never reimplement (blocker 5).
    from soloring.workflows.manifest import (
        WorkflowError as _M9WorkflowError,
        parse_manifest_v2 as _parse_m9_manifest_v2,
    )
    inherited = {k: v for k, v in doc.items() if k != "spatial_bindings"}
    inherited["schema_version"] = "2"
    try:
        _parse_m9_manifest_v2(inherited)
    except _M9WorkflowError as exc:
        raise _bad(f"Inherited manifest-2 portion invalid: {exc}") from exc

    bindings_raw = _require_dict(doc["spatial_bindings"],
                                 "spatial_bindings")
    if not bindings_raw:
        raise _bad("A schema-3 manifest must declare spatial bindings.")
    keys_seen: set[str] = set()
    roles_seen: dict[str, int] = {ROLE_WORLD_DEPTH: 0, ROLE_ENTITY_DEPTH: 0}
    for key, binding in bindings_raw.items():
        _require_str(key, "spatial_bindings key")
        if key in keys_seen:
            raise _bad(f"duplicate spatial binding key {key!r}.")
        keys_seen.add(key)
        binding = _require_dict(binding, f"spatial_bindings.{key}")
        _exact_keys(binding, {
            "artifact_role", "node", "field", "format",
        }, f"spatial_bindings.{key}")
        role = _require_str(binding["artifact_role"],
                            f"spatial_bindings.{key}.artifact_role")
        if role not in STREAM_ROLES:
            raise _bad(f"spatial_bindings.{key}.artifact_role must be one of "
                       f"{list(STREAM_ROLES)}.")
        roles_seen[role] += 1
        _require_str(binding["node"], f"spatial_bindings.{key}.node")
        _require_str(binding["field"], f"spatial_bindings.{key}.field")
        if binding["format"] != "soloring.spatial.v1":
            raise _bad(f"spatial_bindings.{key}.format must be "
                       "'soloring.spatial.v1'.")
    if roles_seen[ROLE_WORLD_DEPTH] != 1:
        raise _bad("Exactly one spatial.world_depth binding is required.")
    if roles_seen[ROLE_ENTITY_DEPTH] > 2:
        raise _bad("At most two spatial.entity_depth bindings are supported "
                   f"(capacity {INITIAL_MAX_CONTROL_STREAMS}).")
    # manifest input keys must exist for every binding
    manifest_inputs = doc.get("inputs") or {}
    for key in bindings_raw:
        if key not in manifest_inputs:
            raise _bad(f"spatial binding {key!r} has no manifest input.")
    return doc


def manifest_binding_map(manifest_v3: dict) -> dict[str, dict]:
    """input_key -> {artifact_role, node, field, format} (explicit only)."""
    return dict(manifest_v3["spatial_bindings"])


def validate_manifest_v3_template_bindings(manifest_v3: dict,
                                           template: dict) -> None:
    """Structural exactness for schema 3 (M10E §8.4): every declared
    binding — spatial_bindings, inherited inputs, parameters, outputs —
    resolves against the captured template graph with no heuristic
    substitute search. Raises Package3Invalid (SPATIAL_REALIZATION_BINDING_
    INVALID) on any missing node/field."""
    def _node_inputs(node_id: object, what: str) -> dict:
        if not isinstance(node_id, str) or not node_id:
            raise _bad(f"{what}: manifest declares no node binding")
        node = template.get(node_id) if isinstance(template, dict) else None
        if not isinstance(node, dict):
            raise _bad(f"{what}: template has no node {node_id!r}")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            raise _bad(f"{what}: node {node_id!r} has no inputs")
        return inputs

    def _require_field(inputs: dict, field: object, node_id: object,
                       what: str) -> None:
        if not isinstance(field, str) or not field:
            raise _bad(f"{what}: manifest declares no field binding")
        if field not in inputs:
            raise _bad(f"{what}: node {node_id!r} has no input field "
                       f"{field!r}")

    if not isinstance(template, dict) or not template:
        raise _bad("captured workflow template is empty or malformed")
    for key, binding in manifest_v3["spatial_bindings"].items():
        what = f"spatial binding {key!r}"
        inputs = _node_inputs(binding["node"], what)
        _require_field(inputs, binding["field"], binding["node"], what)
    for key, decl in (manifest_v3.get("inputs") or {}).items():
        if not isinstance(decl, dict):
            raise _bad(f"manifest input {key!r} is not an object.")
        what = f"manifest input {key!r}"
        inputs = _node_inputs(decl.get("node"), what)
        _require_field(inputs, decl.get("field"), decl.get("node"), what)
    for name, decl in (manifest_v3.get("parameters") or {}).items():
        if not isinstance(decl, dict):
            raise _bad(f"manifest parameter {name!r} is not an object.")
        what = f"manifest parameter {name!r}"
        inputs = _node_inputs(decl.get("node"), what)
        _require_field(inputs, decl.get("field"), decl.get("node"), what)
    for name, decl in (manifest_v3.get("outputs") or {}).items():
        if not isinstance(decl, dict):
            raise _bad(f"manifest output {name!r} is not an object.")
        node_id = decl.get("node")
        if not isinstance(node_id, str) or not node_id:
            raise _bad(f"manifest output {name!r}: no node binding")
        if not isinstance(template.get(node_id), dict):
            raise _bad(f"manifest output {name!r}: template has no node "
                       f"{node_id!r}")


def resolve_derived_binding(manifest_v3: dict, artifact_role: str,
                             position: int) -> tuple[str, str, str]:
    """Resolve one (role, position) to the exact manifest input_key/node/field.

    Position ordering: world stream at 0; entity streams 1..2 in canonical
    manifest-binding insertion order (the manifest author pins the mapping;
    no heuristic discovery).
    """
    bindings = manifest_v3["spatial_bindings"]
    by_role: dict[str, list[str]] = {ROLE_WORLD_DEPTH: [], ROLE_ENTITY_DEPTH: []}
    for key in sorted(bindings):
        by_role[bindings[key]["artifact_role"]].append(key)
    if artifact_role not in by_role or not by_role[artifact_role]:
        raise _bad(f"No manifest binding for role {artifact_role!r}.")
    offset = position if artifact_role == ROLE_WORLD_DEPTH else position - 1
    if offset < 0 or offset >= len(by_role[artifact_role]):
        raise _bad(f"position {position} out of range for {artifact_role!r}.")
    key = by_role[artifact_role][offset]
    b = bindings[key]
    return key, b["node"], b["field"]


# --------------------------------------------------------------------------
# Package descriptor schema 3
# --------------------------------------------------------------------------

DESCRIPTOR3_FIELDS = {
    "schema_version", "workflow_id", "workflow_version", "manifest_hash",
    "workflow_template_hash", "realization_profile_hash",
    "execution_model_fingerprint_hash",
}


def parse_descriptor_v3(raw: Any) -> dict:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError as exc:
            raise _bad(f"package descriptor v3 is not valid JSON: {exc}") from exc
    doc = _require_dict(raw, "package descriptor v3")
    _exact_keys(doc, DESCRIPTOR3_FIELDS, "package descriptor v3")
    if doc["schema_version"] != DESCRIPTOR_SCHEMA_VERSION_3:
        raise _bad("package descriptor schema_version must be 3.")
    _require_str(doc["workflow_id"], "workflow_id")
    for field in ("manifest_hash", "workflow_template_hash",
                  "realization_profile_hash",
                  "execution_model_fingerprint_hash"):
        _require_str(doc[field], field)
    return doc


__all__ = [
    "PROFILE_SCHEMA_VERSION_2", "MANIFEST_SCHEMA_VERSION_3",
    "DESCRIPTOR_SCHEMA_VERSION_3", "Package3Invalid",
    "parse_profile_v2", "parse_manifest_v3", "parse_descriptor_v3",
    "manifest_binding_map", "resolve_derived_binding",
    "validate_manifest_v3_template_bindings",
    "validate_schema3_fingerprint_template", "check_runtime_closure",
]
