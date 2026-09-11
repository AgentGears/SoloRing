"""M14 WorkflowSpec schema 4 (frozen R2 §19).

Schema 4 wraps the EXACT inherited schema-3 execution meaning — never a
reimplemented or structurally incomplete substitute — together with the
independently hashed WorldObservationSpec and NegotiationResult:

    {schema_version: 4, lower_schema_3, world_observation{
        spec, spec_hash, profile_hash, capability_contract_hash,
        negotiation, negotiation_hash}}

``lower_schema_3`` is validated by THE frozen schema-3 validator
(``soloring.spatial.spec3.validate_spec_v3``) and embedded verbatim; the
nested observation documents are validated by the M14 schema-1 grammar
and negotiation validators with their hashes re-derived and required.
Nothing is ever rebuilt from current state.
"""

from __future__ import annotations

import hashlib
import re

from soloring.domain.canonical import canonical_json_bytes
from soloring.errors import validation_error
from soloring.observation.capability import validate_negotiation_result
from soloring.observation.spec import parse_world_observation_spec

WORKFLOW_SPEC_SCHEMA_VERSION_4 = 4

ROOT_KEYS = frozenset({"schema_version", "lower_schema_3",
                       "world_observation"})
WORLD_OBSERVATION_KEYS = frozenset({
    "spec", "spec_hash", "profile_hash", "capability_contract_hash",
    "negotiation", "negotiation_hash"})

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _invalid(message: str):
    return validation_error(f"WorkflowSpec schema 4: {message}")


def _require_hex64(value, what: str) -> None:
    if not isinstance(value, str) or not _HEX64.fullmatch(value):
        raise _invalid(f"{what} must be a lowercase 64-hex SHA-256")


def _validate_lower_schema_3(lower) -> None:
    from soloring.spatial.spec3 import validate_spec_v3

    try:
        validate_spec_v3(lower)
    except Exception as exc:  # the frozen schema-3 validator's own error
        raise _invalid(
            f"lower_schema_3 is not a valid schema-3 WorkflowSpec: "
            f"{exc}") from exc


def _validate_world_observation(observation: dict) -> None:
    if not isinstance(observation, dict):
        raise _invalid("world_observation must be an object")
    extra = sorted(set(observation) - WORLD_OBSERVATION_KEYS)
    if extra:
        raise _invalid(f"world_observation has unknown fields {extra}")
    missing = sorted(WORLD_OBSERVATION_KEYS - set(observation))
    if missing:
        raise _invalid(f"world_observation is missing fields {missing}")

    spec = parse_world_observation_spec(observation["spec"])
    expected_spec_hash = hashlib.sha256(
        canonical_json_bytes(spec)).hexdigest()
    if observation["spec_hash"] != expected_spec_hash:
        raise _invalid("spec_hash does not match the nested "
                       "WorldObservationSpec")

    negotiation = validate_negotiation_result(observation["negotiation"])
    expected_negotiation_hash = hashlib.sha256(
        canonical_json_bytes(negotiation)).hexdigest()
    if observation["negotiation_hash"] != expected_negotiation_hash:
        raise _invalid("negotiation_hash does not match the nested "
                       "NegotiationResult")

    if len(negotiation["requirements"]) != len(spec["requirements"]):
        raise _invalid(
            "NegotiationResult requirement rows must correspond one-to-"
            "one with the WorldObservationSpec requirements in canonical "
            "order")

    _validate_negotiation_relational(spec, negotiation)

    for field in ("profile_hash", "capability_contract_hash"):
        _require_hex64(observation[field], f"world_observation.{field}")


def _validate_negotiation_relational(spec: dict,
                                     negotiation: dict) -> None:
    """Relational integrity (source review P1-4): the stored
    NegotiationResult must be the one THIS spec produces — every
    requirement row hash-matches its canonical Requirement in order,
    the policy echoes the spec's policy identity, verdict rows are
    internally consistent, and a SUPPORTED row echoes the exact
    requested capability tuple. A self-hashed but semantically
    inconsistent historical value rejects here."""
    from soloring.observation.capability import requirement_identity_hash

    for requirement, result in zip(
            spec["requirements"], negotiation["requirements"]):
        if result["requirement_identity_hash"] != (
                requirement_identity_hash(requirement)):
            raise _invalid(
                "NegotiationResult requirement row does not hash-match "
                "its canonical WorldObservationSpec Requirement (order "
                "or content diverged)")
        verdict = result["verdict"]
        capability = result["capability"]
        if verdict == "SUPPORTED":
            if not isinstance(capability, dict):
                raise _invalid(
                    "a SUPPORTED requirement row must echo the matched "
                    "capability")
            # Source review R2-P0: the echoed capability must match on
            # EVERY materializer-bearing field — the semantic tuple AND
            # the (materializer_id, materializer_version, output_role)
            # of the spec's pinned materialization.
            materializations = spec["materializations"]
            if len(materializations) != 1:
                raise _invalid(
                    "schema-4 validation requires exactly one "
                    "materialization")
            pinned = materializations[0]
            echoed_all = (
                capability.get("property"),
                capability.get("preservation"),
                capability.get("source_contract"),
                capability.get("materializer_id"),
                capability.get("materializer_version"),
                capability.get("output_role"))
            requested_all = (
                requirement["property"],
                requirement["preservation"],
                requirement["source_contract"],
                pinned["materializer"]["id"],
                pinned["materializer"]["version"],
                pinned["artifact_role"])
            if echoed_all != requested_all:
                raise _invalid(
                    "a SUPPORTED requirement row echoes a capability "
                    "tuple other than the requested one (semantic or "
                    "materializer identity diverged)")
        elif capability is not None:
            raise _invalid(
                f"a {verdict} requirement row cannot echo a capability")

    policy = negotiation["policy"]
    if (policy["id"] != spec["policy"]["id"]
            or policy["version"] != spec["policy"]["version"]):
        raise _invalid(
            "NegotiationResult policy does not echo the "
            "WorldObservationSpec policy identity")

    verdicts = {row["verdict"] for row in negotiation["requirements"]}
    if policy["verdict"] != "SUPPORTED":
        expected = "UNSUPPORTED"
    elif "UNSUPPORTED" in verdicts:
        expected = "UNSUPPORTED"
    elif "UNKNOWN" in verdicts:
        expected = "UNKNOWN"
    else:
        expected = "SUPPORTED"
    if negotiation["verdict"] != expected:
        raise _invalid(
            f"NegotiationResult verdict {negotiation['verdict']!r} is "
            f"inconsistent with its own rows ({expected!r} expected)")


def build_workflow_spec_v4(
    *,
    lower_schema_3: dict,
    observation_spec: dict,
    negotiation_result: dict,
    profile_hash: str,
    capability_contract_hash: str,
) -> dict:
    """Wrap the exact schema-3 value with the hashed observation facts."""
    _validate_lower_schema_3(lower_schema_3)
    spec = parse_world_observation_spec(observation_spec)
    negotiation = validate_negotiation_result(negotiation_result)
    if len(negotiation["requirements"]) != len(spec["requirements"]):
        raise _invalid(
            "NegotiationResult requirement rows must correspond one-to-"
            "one with the WorldObservationSpec requirements")
    _require_hex64(profile_hash, "profile_hash")
    _require_hex64(capability_contract_hash, "capability_contract_hash")

    return {
        "schema_version": WORKFLOW_SPEC_SCHEMA_VERSION_4,
        "lower_schema_3": lower_schema_3,
        "world_observation": {
            "spec": spec,
            "spec_hash": hashlib.sha256(
                canonical_json_bytes(spec)).hexdigest(),
            "profile_hash": profile_hash,
            "capability_contract_hash": capability_contract_hash,
            "negotiation": negotiation,
            "negotiation_hash": hashlib.sha256(
                canonical_json_bytes(negotiation)).hexdigest(),
        },
    }


def parse_workflow_spec_v4(value: dict) -> dict:
    """Strict schema-4 parse. Returns the value unchanged."""
    if not isinstance(value, dict):
        raise _invalid("root must be an object")
    extra = sorted(set(value) - ROOT_KEYS)
    if extra:
        raise _invalid(f"root has unknown fields {extra}")
    missing = sorted(ROOT_KEYS - set(value))
    if missing:
        raise _invalid(f"root is missing fields {missing}")
    if value["schema_version"] != WORKFLOW_SPEC_SCHEMA_VERSION_4:
        raise _invalid("schema_version must be 4")
    _validate_lower_schema_3(value["lower_schema_3"])
    _validate_world_observation(value["world_observation"])
    return value
