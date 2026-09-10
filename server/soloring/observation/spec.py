"""M14 WorldObservationSpec schema 1 — strict grammar (frozen R2 §10/§11).

One shared module produces and verifies the canonical schema-1 value:
closed field sets, closed vocabularies, the fixed preservation→enforcement
mapping, the §10.1 identity tuple with its null→"" ordering sentinel,
duplicate/conflicting-coordinate rejection, and the §10.3 materialization
cross-links. Parsers never resort stored historical bytes: canonical order
must already hold, or the value is invalid.

The parser is deliberately pure: dict in, validated dict out, no DB, no
filesystem, no current-state resolution.
"""

from __future__ import annotations

import hashlib
import re

from soloring.domain.canonical import canonical_json_bytes
from soloring.errors import validation_error
from soloring.spatial.math import JS_SAFE_MAX, JS_SAFE_MIN, UDEG_MIN

COMPILER_ID = "soloring.world_observation"
COMPILER_VERSION = 1

POLICY_ID = "structural-world-v1"
POLICY_VERSION = 1
PERMITTED_INFERENCE_LIST = (
    "incidental_reflection",
    "shot_intent_interpretation",
    "surface_microdetail",
    "unmodeled_background_detail",
)

PRESERVATION_VALUES = frozenset(
    {"EXACT", "STRUCTURAL", "IDENTITY_APPEARANCE", "INFERABLE"})
ENFORCEMENT_VALUES = frozenset({"REQUIRED", "PERMITTED_INFERENCE"})
PRESERVATION_TO_ENFORCEMENT = {
    "EXACT": "REQUIRED",
    "STRUCTURAL": "REQUIRED",
    "IDENTITY_APPEARANCE": "REQUIRED",
    "INFERABLE": "PERMITTED_INFERENCE",
}
PROPERTY_VALUES = frozenset({
    "camera.projection", "world.structure", "occurrence.structure",
    "occurrence.placement", "visual.identity",
    "continuity.instance_feature", "shot.intent"})
OCCURRENCE_PROPERTIES = frozenset(
    {"occurrence.structure", "occurrence.placement"})
SUBKEY_PROPERTY = "continuity.instance_feature"
SUBJECT_KINDS = frozenset({
    "shot", "spatial_world", "production_occurrence", "production_instance",
    "visual_reference_pack"})
AUTHORITY_DOMAINS = frozenset({"A1", "A2", "A3", "A4", "A5", "A6"})
AUTHORITY_SOURCE_KINDS = frozenset({
    "shot_revision", "spatial_continuity_pack", "spatial_world_revision",
    "visual_reference_pack", "composition_revision", "production_revision",
    "composition_spatial_binding", "production_world_pack"})

MATERIALIZER_ID = "soloring.observation.mesh_depth"
MATERIALIZER_VERSION = 1
ARTIFACT_ROLE = "observation.world_depth"
INHERITED_INPUT_ROLE = "spatial.world_depth"
MATERIALIZATION_PARAMETERS = {
    "width": 832,
    "height": 480,
    "frames": 17,
    "time_base_num": 1,
    "time_base_den": 17,
    "mode": "L",
    "background": 255,
}

REPRESENTATION_CONTRACT = "soloring.structural_mesh.v1"
PLACEMENT_OWNERS = frozenset({"A4", "A6"})
PLACEMENT_SOURCE_KINDS = frozenset(
    {"composition_revision", "composition_spatial_binding"})

ROOT_KEYS = frozenset({
    "schema_version", "compiler", "shot_revision", "captured_domains",
    "policy", "requirements", "production_occurrences",
    "materializations"})
REQUIREMENT_KEYS = frozenset({
    "property", "preservation", "enforcement", "subject", "occurrence_id",
    "subkey", "authority", "source_contract"})
AUTHORITY_KEYS = frozenset(
    {"domain", "source_kind", "source_id", "source_hash"})
OCCURRENCE_KEYS = frozenset({
    "occurrence_id", "composition_revision_id", "composition_revision_hash",
    "production_revision_id", "production_revision_hash",
    "retained_blob_hash", "representation_contract", "placement_owner",
    "interpretation", "placement", "realization_local_to_world"})
TRANSFORM_KEYS = frozenset({"translation_mm", "rotation_udeg"})
MATERIALIZATION_KEYS = frozenset({
    "artifact_role", "materializer", "input_role", "source_occurrence_ids",
    "parameters", "parameters_hash"})

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_UDEG_MAX_EXCLUSIVE = UDEG_MIN + 360_000_000


def _invalid(message: str, details: dict | None = None):
    return validation_error(f"WorldObservationSpec schema 1: {message}",
                            details)


def _require_hex64(value, what: str):
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise _invalid(f"{what} must be a lowercase 64-hex SHA-256")


def _require_uuid(value, what: str):
    if not isinstance(value, str) or not _UUID.fullmatch(value):
        raise _invalid(f"{what} must be a canonical lowercase UUID")


def _require_stable_id(value, what: str):
    # §10.1: ids are uuid-or-stable-id; the empty string is reserved as
    # the null ordering sentinel and never a valid value.
    if not isinstance(value, str) or not value:
        raise _invalid(f"{what} must be a non-empty id")


def _require_closed(value, keys: frozenset, what: str):
    if not isinstance(value, dict):
        raise _invalid(f"{what} must be an object")
    extra = set(value) - keys
    if extra:
        raise _invalid(f"{what} has unknown fields {sorted(extra)}")
    missing = keys - set(value)
    if missing:
        raise _invalid(f"{what} is missing fields {sorted(missing)}")


def _require_transform(value, what: str):
    _require_closed(value, TRANSFORM_KEYS, what)
    for field in ("translation_mm", "rotation_udeg"):
        vec = value[field]
        if (not isinstance(vec, list) or len(vec) != 3
                or any(not isinstance(v, int) or isinstance(v, bool)
                       for v in vec)):
            raise _invalid(f"{what}.{field} must be three plain integers")
        if any(not (JS_SAFE_MIN <= v <= JS_SAFE_MAX) for v in vec):
            raise _invalid(f"{what}.{field} exceeds the JS-safe range")
    for v in value["rotation_udeg"]:
        if not (UDEG_MIN <= v < _UDEG_MAX_EXCLUSIVE):
            raise _invalid(
                f"{what}.rotation_udeg outside the M13 microdegree range")


def requirement_order_key(req: dict) -> tuple[str, ...]:
    """Frozen R2 §10.1 identity tuple; stored null orders as ""."""
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


def _requirement_coordinate(req: dict) -> tuple[str, ...]:
    """The authority coordinate: everything but the claim fields."""
    return requirement_order_key(req)[:9]


def world_observation_spec_bytes(spec: dict) -> bytes:
    return canonical_json_bytes(spec)


def world_observation_spec_hash(spec: dict) -> str:
    return hashlib.sha256(world_observation_spec_bytes(spec)).hexdigest()


def parse_world_observation_spec(value: dict) -> dict:
    """Strict schema-1 parse. Returns the value unchanged; never resorts."""
    _require_closed(value, ROOT_KEYS, "root")
    if value["schema_version"] != 1:
        raise _invalid("root schema_version must be 1")
    if value["compiler"] != {"id": COMPILER_ID, "version": COMPILER_VERSION}:
        raise _invalid("compiler must be the exact schema-1 identity")

    shot_revision = value["shot_revision"]
    _require_closed(shot_revision, frozenset({"id", "plan_hash"}),
                    "shot_revision")
    _require_uuid(shot_revision["id"], "shot_revision.id")
    _require_hex64(shot_revision["plan_hash"], "shot_revision.plan_hash")

    domains = value["captured_domains"]
    _require_closed(
        domains,
        frozenset({"spatial_continuity_hash", "production_world_hash",
                   "visual_reference_pack_hash"}),
        "captured_domains")
    for key, captured in domains.items():
        if captured is not None:
            _require_hex64(captured, f"captured_domains.{key}")

    policy = value["policy"]
    _require_closed(policy, frozenset({"id", "version", "permitted_inference"}),
                    "policy")
    if policy["id"] != POLICY_ID or policy["version"] != POLICY_VERSION:
        raise _invalid("policy must be the exact structural-world-v1 identity")
    if tuple(policy["permitted_inference"]) != PERMITTED_INFERENCE_LIST:
        raise _invalid(
            "policy.permitted_inference must be the exact frozen list in "
            "canonical UTF-8 lexical order")

    _parse_requirements(value["requirements"])
    _parse_occurrences(value["production_occurrences"])
    _parse_materializations(value)
    return value


def _parse_requirements(requirements) -> None:
    if not isinstance(requirements, list):
        raise _invalid("requirements must be an array")
    seen: dict[tuple[str, ...], tuple[str, ...]] = {}
    previous_key: tuple[str, ...] | None = None
    for req in requirements:
        _require_closed(req, REQUIREMENT_KEYS, "requirement")
        if req["property"] not in PROPERTY_VALUES:
            raise _invalid(f"unknown property {req['property']!r}")
        if req["preservation"] not in PRESERVATION_VALUES:
            raise _invalid(f"unknown preservation {req['preservation']!r}")
        if req["enforcement"] not in ENFORCEMENT_VALUES:
            raise _invalid(f"unknown enforcement {req['enforcement']!r}")
        if (req["enforcement"]
                != PRESERVATION_TO_ENFORCEMENT[req["preservation"]]):
            raise _invalid(
                "preservation→enforcement mapping is fixed (§8.4)")

        subject = req["subject"]
        _require_closed(subject, frozenset({"kind", "id"}), "requirement.subject")
        if subject["kind"] not in SUBJECT_KINDS:
            raise _invalid(f"unknown subject kind {subject['kind']!r}")
        _require_stable_id(subject["id"], "requirement.subject.id")

        if req["property"] in OCCURRENCE_PROPERTIES:
            if req["occurrence_id"] is None:
                raise _invalid(
                    "occurrence properties require occurrence_id (§11.2)")
        elif req["occurrence_id"] is not None:
            raise _invalid(
                "only occurrence properties carry occurrence_id (§11.2)")
        if req["property"] == SUBKEY_PROPERTY:
            if not isinstance(req["subkey"], str) or not req["subkey"]:
                raise _invalid(
                    "continuity.instance_feature requires a subkey (§11.3)")
        elif req["subkey"] is not None:
            raise _invalid("only continuity.instance_feature carries a "
                           "subkey (§11.3)")

        authority = req["authority"]
        _require_closed(authority, AUTHORITY_KEYS, "requirement.authority")
        if authority["domain"] not in AUTHORITY_DOMAINS:
            raise _invalid(f"unknown authority domain {authority['domain']!r}")
        if authority["source_kind"] not in AUTHORITY_SOURCE_KINDS:
            raise _invalid(
                f"unknown authority source_kind "
                f"{authority['source_kind']!r}")
        _require_stable_id(authority["source_id"],
                           "requirement.authority.source_id")
        _require_hex64(authority["source_hash"],
                       "requirement.authority.source_hash")

        contract = req["source_contract"]
        if not isinstance(contract, str) or not contract:
            raise _invalid("source_contract must be non-empty and exact")

        key = requirement_order_key(req)
        if previous_key is not None and key < previous_key:
            raise _invalid(
                "requirements are not in canonical §10.1 order; parsers "
                "do not resort stored historical bytes")
        previous_key = key

        coordinate = _requirement_coordinate(req)
        claim = (req["source_contract"], req["preservation"],
                 req["enforcement"])
        if coordinate in seen:
            if seen[coordinate] != claim:
                raise _invalid(
                    "same authority coordinate with conflicting "
                    "preservation/enforcement/source_contract is "
                    "corruption, not separate requirements")
            raise _invalid("duplicate requirement identity")
        seen[coordinate] = claim


def _parse_occurrences(occurrences) -> None:
    if not isinstance(occurrences, list):
        raise _invalid("production_occurrences must be an array")
    seen_ids: set[str] = set()
    for occ in occurrences:
        _require_closed(occ, OCCURRENCE_KEYS, "production_occurrence")
        _require_uuid(occ["occurrence_id"],
                      "production_occurrence.occurrence_id")
        if occ["occurrence_id"] in seen_ids:
            raise _invalid("duplicate occurrence ids reject (§10.2)")
        seen_ids.add(occ["occurrence_id"])
        _require_uuid(occ["composition_revision_id"],
                      "production_occurrence.composition_revision_id")
        _require_hex64(occ["composition_revision_hash"],
                       "production_occurrence.composition_revision_hash")
        _require_uuid(occ["production_revision_id"],
                      "production_occurrence.production_revision_id")
        _require_hex64(occ["production_revision_hash"],
                       "production_occurrence.production_revision_hash")
        _require_hex64(occ["retained_blob_hash"],
                       "production_occurrence.retained_blob_hash")
        if occ["representation_contract"] != REPRESENTATION_CONTRACT:
            raise _invalid(
                "production_occurrence.representation_contract must be "
                f"exactly {REPRESENTATION_CONTRACT}")
        if occ["placement_owner"] not in PLACEMENT_OWNERS:
            raise _invalid("placement_owner must be exactly A4 or A6")

        interpretation = occ["interpretation"]
        _require_closed(interpretation,
                        frozenset({"hash", "realization_local_to_subject_local"}),
                        "production_occurrence.interpretation")
        _require_hex64(interpretation["hash"],
                       "interpretation.hash")
        _require_transform(
            interpretation["realization_local_to_subject_local"],
            "interpretation.realization_local_to_subject_local")

        placement = occ["placement"]
        _require_closed(
            placement,
            frozenset({"source_kind", "source_id", "source_hash",
                       "subject_local_to_world"}),
            "production_occurrence.placement")
        if placement["source_kind"] not in PLACEMENT_SOURCE_KINDS:
            raise _invalid(
                "placement.source_kind must be composition_revision or "
                "composition_spatial_binding")
        _require_stable_id(placement["source_id"], "placement.source_id")
        _require_hex64(placement["source_hash"], "placement.source_hash")
        _require_transform(placement["subject_local_to_world"],
                           "placement.subject_local_to_world")
        _require_transform(occ["realization_local_to_world"],
                           "production_occurrence.realization_local_to_world")


def _parse_materializations(spec: dict) -> None:
    materializations = spec["materializations"]
    if not isinstance(materializations, list) or len(materializations) != 1:
        raise _invalid(
            "exactly one schema-1 materialization object exists for the "
            "supported production path (§10.3)")
    mat = materializations[0]
    _require_closed(mat, MATERIALIZATION_KEYS, "materialization")
    if mat["artifact_role"] != ARTIFACT_ROLE:
        raise _invalid(f"artifact_role must be {ARTIFACT_ROLE}")
    if mat["input_role"] != INHERITED_INPUT_ROLE:
        raise _invalid(f"input_role must be {INHERITED_INPUT_ROLE}")
    materializer = mat["materializer"]
    _require_closed(materializer, frozenset({"id", "version", "contract_hash"}),
                    "materialization.materializer")
    if materializer["id"] != MATERIALIZER_ID:
        raise _invalid(f"materializer.id must be {MATERIALIZER_ID}")
    if materializer["version"] != MATERIALIZER_VERSION:
        raise _invalid("materializer.version must be 1")
    _require_hex64(materializer["contract_hash"],
                   "materialization.materializer.contract_hash")

    if mat["parameters"] != MATERIALIZATION_PARAMETERS:
        raise _invalid(
            "materialization.parameters must equal the frozen production "
            "frame grammar (§10.3/§14.1)")
    expected_hash = hashlib.sha256(
        canonical_json_bytes(mat["parameters"])).hexdigest()
    if mat["parameters_hash"] != expected_hash:
        raise _invalid("parameters_hash must be SHA-256 over canonical "
                       "parameters")

    source_ids = mat["source_occurrence_ids"]
    if not isinstance(source_ids, list):
        raise _invalid("source_occurrence_ids must be an array")
    occurrence_order = {
        occ["occurrence_id"]: position
        for position, occ in enumerate(spec["production_occurrences"])}
    positions: list[int] = []
    for source_id in source_ids:
        _require_uuid(source_id, "source_occurrence_ids entry")
        if source_id not in occurrence_order:
            raise _invalid(
                "source_occurrence_ids entry has no ProductionOccurrence "
                "object (§10.3)")
        positions.append(occurrence_order[source_id])
    if len(set(source_ids)) != len(source_ids):
        raise _invalid("source_occurrence_ids entries must be unique")
    if positions != sorted(positions):
        raise _invalid(
            "source_occurrence_ids must follow canonical captured "
            "occurrence order (§10.3)")


def build_world_observation_spec(
    *,
    shot_revision_id: str,
    plan_hash: str,
    captured_domains: dict,
    requirements: list[dict],
    production_occurrences: list[dict],
    materializations: list[dict],
) -> dict:
    """Assemble + canonically order + strictly validate a schema-1 spec."""
    ordered = sorted(requirements, key=requirement_order_key)
    spec = {
        "schema_version": 1,
        "compiler": {"id": COMPILER_ID, "version": COMPILER_VERSION},
        "shot_revision": {"id": shot_revision_id, "plan_hash": plan_hash},
        "captured_domains": captured_domains,
        "policy": {
            "id": POLICY_ID,
            "version": POLICY_VERSION,
            "permitted_inference": list(PERMITTED_INFERENCE_LIST),
        },
        "requirements": ordered,
        "production_occurrences": production_occurrences,
        "materializations": materializations,
    }
    return parse_world_observation_spec(spec)
