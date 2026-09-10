"""M14 RealizationProfile schema 3 + capability negotiation (frozen R2
§§8.9-8.11/17/20/21/36.1).

Three strictly separated layers:

  parse_profile_v3        — schema 3 = the frozen schema-2 profile plus
                            exactly one closed ``observation`` block; the
                            inherited schema-2 semantics are validated by
                            DELEGATING to the frozen schema-2 parser
                            (``soloring.spatial.package3.parse_profile_v2``),
                            never reimplemented;
  negotiate               — a PURE function over (WorldObservationSpec,
                            observation block) returning NegotiationResult
                            schema 1. Matching is exact on property /
                            preservation / source-contract (+ the entry's
                            resolved materializer and output role); no
                            broader preservation tier, source-contract
                            wildcard, node presence, or prompt fallback can
                            satisfy a REQUIRED coordinate. Runtime/discovery
                            state is not an input and cannot alter a
                            verdict. Parser/integrity failures are
                            operation failures (APR-111): COMPLETED domain
                            verdicts are never fabricated from them;
  require_publication_allowed — the typed pre-publication refusal contract
                            (§8.11/§36.1) consumed by the M14A-3
                            orchestration: REQUIRED + UNSUPPORTED/UNKNOWN
                            and policy-incompatible observations refuse
                            with the exact §41 trace.
"""

from __future__ import annotations

import hashlib
import re

from soloring.domain.canonical import canonical_json_bytes
from soloring.errors import ErrorCode, SoloRingError, validation_error
from soloring.observation.spec import (
    PRESERVATION_VALUES,
    PROPERTY_VALUES,
    parse_world_observation_spec,
)
from soloring.spatial.package3 import parse_profile_v2

PROFILE_SCHEMA_VERSION_3 = 3
OBSERVATION_BLOCK_SCHEMA_VERSION = 1
CAPABILITY_OUTPUT_ROLE = "observation.world_depth"
MATERIALIZER_INHERITED_ROLE = "spatial.world_depth"

PROFILE_V3_KEYS = frozenset({
    "schema_version", "profile_id", "profile_version", "workflow_id",
    "workflow_version", "model", "channels", "rules",
    "parameter_overrides", "spatial", "observation"})
OBSERVATION_BLOCK_KEYS = frozenset({
    "schema_version", "supported_policies", "capabilities",
    "materializers"})
SUPPORTED_POLICY_KEYS = frozenset({"id", "version"})
CAPABILITY_KEYS = frozenset({
    "property", "preservation", "source_contract", "materializer_id",
    "materializer_version", "output_role"})
MATERIALIZER_KEYS = frozenset({
    "id", "version", "contract_hash", "output_role",
    "inherited_manifest_role"})

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _bad(message: str):
    return validation_error(
        f"RealizationProfile schema 3: {message}")


def _require_closed(value, keys: frozenset, what: str) -> None:
    if not isinstance(value, dict):
        raise _bad(f"{what} must be an object")
    extra = sorted(set(value) - keys)
    if extra:
        raise _bad(f"{what} has unknown fields {extra}; the field set is "
                   "closed")
    missing = sorted(keys - set(value))
    if missing:
        raise _bad(f"{what} is missing fields {missing}")


def validate_observation_block(block) -> dict:
    """Strict closed observation block (frozen §17). Returns the block."""
    _require_closed(block, OBSERVATION_BLOCK_KEYS, "observation")
    if block["schema_version"] != OBSERVATION_BLOCK_SCHEMA_VERSION:
        raise _bad("observation.schema_version must be 1")

    seen_policies: set[tuple[str, int]] = set()
    for policy in block["supported_policies"]:
        _require_closed(policy, SUPPORTED_POLICY_KEYS,
                        "observation.supported_policies entry")
        key = (policy["id"], policy["version"])
        if key in seen_policies:
            raise _bad("duplicate supported policy entry")
        seen_policies.add(key)

    materializers: dict[tuple[str, int], dict] = {}
    for materializer in block["materializers"]:
        _require_closed(materializer, MATERIALIZER_KEYS,
                        "observation.materializers entry")
        key = (materializer["id"], materializer["version"])
        if key in materializers:
            raise _bad(
                f"duplicate materializer entry {key[0]}@{key[1]}")
        if not _HEX64.fullmatch(str(materializer["contract_hash"])):
            raise _bad("materializer.contract_hash must be lowercase "
                       "64-hex SHA-256")
        if materializer["output_role"] != CAPABILITY_OUTPUT_ROLE:
            raise _bad(
                f"materializer.output_role must be {CAPABILITY_OUTPUT_ROLE}")
        if (materializer["inherited_manifest_role"]
                != MATERIALIZER_INHERITED_ROLE):
            raise _bad("materializer.inherited_manifest_role must be "
                       f"{MATERIALIZER_INHERITED_ROLE}")
        materializers[key] = materializer

    seen_capability_tuples: set[tuple[str, str, str]] = set()
    for capability in block["capabilities"]:
        _require_closed(capability, CAPABILITY_KEYS,
                        "observation.capabilities entry")
        if capability["property"] not in PROPERTY_VALUES:
            raise _bad(f"unknown capability property "
                       f"{capability['property']!r}")
        if capability["preservation"] not in PRESERVATION_VALUES:
            raise _bad(f"unknown capability preservation "
                       f"{capability['preservation']!r}")
        if capability["output_role"] != CAPABILITY_OUTPUT_ROLE:
            raise _bad(
                "capability.output_role must be "
                f"{CAPABILITY_OUTPUT_ROLE}")
        if (capability["materializer_id"],
                capability["materializer_version"]) not in materializers:
            raise _bad(
                "capability materializer "
                f"{capability['materializer_id']}@"
                f"{capability['materializer_version']} does not resolve "
                "to an exact materializers entry")
        tuple_key = (capability["property"], capability["preservation"],
                     capability["source_contract"])
        if tuple_key in seen_capability_tuples:
            raise _bad(
                "duplicate capability tuple "
                f"{tuple_key} — exact matching requires uniqueness")
        seen_capability_tuples.add(tuple_key)
    return block


def parse_profile_v3(raw) -> dict:
    """Strict schema-3 parse with delegated schema-2 semantics."""
    if isinstance(raw, str):
        import json as _json

        try:
            raw = _json.loads(raw)
        except ValueError as exc:
            raise _bad(f"profile is not valid JSON: {exc}") from exc
    _require_closed(raw, PROFILE_V3_KEYS, "profile root")
    if raw["schema_version"] != PROFILE_SCHEMA_VERSION_3:
        raise _bad("schema_version must be 3")

    # The inherited schema-2 semantics are validated by THE frozen
    # schema-2 parser through a schema-2 view — delegated, never
    # reimplemented (frozen §17; same pattern parse_profile_v2 itself
    # uses against the M9 parser).
    schema_2_view = {key: value for key, value in raw.items()
                     if key != "observation"}
    schema_2_view["schema_version"] = 2
    parse_profile_v2(schema_2_view)

    validate_observation_block(raw["observation"])
    return raw


def capability_contract_hash(profile_v3: dict) -> str:
    """SHA-256 over the canonical observation block only (frozen §17)."""
    return hashlib.sha256(
        canonical_json_bytes(profile_v3["observation"])).hexdigest()


def _requirement_hash(requirement: dict) -> str:
    return hashlib.sha256(
        canonical_json_bytes(requirement)).hexdigest()


def negotiate(spec: dict, observation_block: dict) -> dict:
    """Pure capability negotiation → NegotiationResult schema 1.

    Exact-match semantics (frozen §8.10/§17): a REQUIRED coordinate is
    SUPPORTED only when the profile declares the exact property /
    preservation / source-contract tuple (whose materializer and output
    role resolved at block validation). The function reads nothing but
    its two arguments — runtime discovery is structurally absent.
    """
    spec = parse_world_observation_spec(spec)
    block = validate_observation_block(observation_block)

    policy_supported = any(
        policy["id"] == spec["policy"]["id"]
        and policy["version"] == spec["policy"]["version"]
        for policy in block["supported_policies"])

    capabilities = {
        (c["property"], c["preservation"], c["source_contract"]): c
        for c in block["capabilities"]}
    known_properties = {c["property"] for c in block["capabilities"]}

    requirement_results = []
    for requirement in spec["requirements"]:
        if requirement["enforcement"] == "PERMITTED_INFERENCE":
            requirement_results.append({
                "requirement_identity_hash": _requirement_hash(requirement),
                "verdict": "PERMITTED_INFERENCE",
                "capability": None,
            })
            continue

        capability = capabilities.get(
            (requirement["property"], requirement["preservation"],
             requirement["source_contract"]))
        if capability is not None:
            verdict = "SUPPORTED"
        elif requirement["property"] in known_properties:
            verdict = "UNSUPPORTED"
        else:
            verdict = "UNKNOWN"
        requirement_results.append({
            "requirement_identity_hash": _requirement_hash(requirement),
            "verdict": verdict,
            "capability": capability,
        })

    if not policy_supported:
        overall = "UNSUPPORTED"
    elif any(result["verdict"] == "UNSUPPORTED"
             for result in requirement_results):
        overall = "UNSUPPORTED"
    elif any(result["verdict"] == "UNKNOWN"
             for result in requirement_results):
        overall = "UNKNOWN"
    else:
        overall = "SUPPORTED"

    return {
        "schema_version": 1,
        "operation_status": "COMPLETED",
        "verdict": overall,
        "policy": {
            "id": spec["policy"]["id"],
            "version": spec["policy"]["version"],
            "verdict": "SUPPORTED" if policy_supported else "UNSUPPORTED",
        },
        "requirements": requirement_results,
    }


NEGOTIATION_ROOT_KEYS = frozenset({
    "schema_version", "operation_status", "verdict", "policy",
    "requirements"})
NEGOTIATION_POLICY_KEYS = frozenset({"id", "version", "verdict"})
NEGOTIATION_REQUIREMENT_KEYS = frozenset({
    "requirement_identity_hash", "verdict", "capability"})
NEGOTIATION_VERDICTS = frozenset({
    "SUPPORTED", "UNSUPPORTED", "UNKNOWN", "PERMITTED_INFERENCE"})


def validate_negotiation_result(result) -> dict:
    """Strict NegotiationResult schema-1 validation (frozen §20).

    Only COMPLETED domain results are representable: operation failures
    are exceptions, never verdict objects (APR-111).
    """
    if not isinstance(result, dict):
        raise _bad("NegotiationResult must be an object")
    extra = sorted(set(result) - NEGOTIATION_ROOT_KEYS)
    if extra:
        raise _bad(f"NegotiationResult has unknown fields {extra}")
    missing = sorted(NEGOTIATION_ROOT_KEYS - set(result))
    if missing:
        raise _bad(f"NegotiationResult is missing fields {missing}")
    if result["schema_version"] != 1:
        raise _bad("NegotiationResult schema_version must be 1")
    if result["operation_status"] != "COMPLETED":
        raise _bad("NegotiationResult operation_status must be COMPLETED "
                   "(APR-111: operation failures never fabricate domain "
                   "verdicts)")
    if result["verdict"] not in ("SUPPORTED", "UNSUPPORTED", "UNKNOWN"):
        raise _bad(f"unknown overall verdict {result['verdict']!r}")
    policy = result["policy"]
    _require_closed(policy, NEGOTIATION_POLICY_KEYS,
                    "NegotiationResult.policy")
    if policy["verdict"] not in ("SUPPORTED", "UNSUPPORTED"):
        raise _bad("policy.verdict must be SUPPORTED or UNSUPPORTED")
    if not isinstance(result["requirements"], list):
        raise _bad("NegotiationResult.requirements must be an array")
    for row in result["requirements"]:
        _require_closed(row, NEGOTIATION_REQUIREMENT_KEYS,
                        "NegotiationResult.requirements entry")
        if not _HEX64.fullmatch(str(row["requirement_identity_hash"])):
            raise _bad("requirement_identity_hash must be lowercase "
                       "64-hex SHA-256")
        if row["verdict"] not in NEGOTIATION_VERDICTS:
            raise _bad(f"unknown requirement verdict {row['verdict']!r}")
        capability = row["capability"]
        if capability is not None:
            _require_closed(capability, CAPABILITY_KEYS,
                            "negotiation capability echo")
    return result


def negotiation_result_bytes(result: dict) -> bytes:
    return canonical_json_bytes(result)


def negotiation_result_hash(result: dict) -> str:
    return hashlib.sha256(negotiation_result_bytes(result)).hexdigest()


def require_publication_allowed(result: dict, spec: dict) -> None:
    """Typed pre-publication refusal contract (frozen §8.11/§36.1/§41).

    Returns None only when every REQUIRED coordinate is SUPPORTED under
    a SUPPORTED policy; otherwise raises the exact friendly refusal with
    the full property → preservation → authority/source → contract →
    verdict trace. This slice defines the contract; the M14A-3
    orchestration wires it ahead of Generation publication.
    """
    if (not isinstance(result, dict)
            or result.get("schema_version") != 1
            or result.get("operation_status") != "COMPLETED"):
        raise validation_error(
            "publication decision requires a COMPLETED NegotiationResult "
            "schema 1 — an operation failure never fabricates a domain "
            "verdict (APR-111)")
    spec = parse_world_observation_spec(spec)

    traces = []
    for requirement, requirement_result in zip(
            spec["requirements"], result["requirements"]):
        if requirement_result["verdict"] not in (
                "UNSUPPORTED", "UNKNOWN"):
            continue
        traces.append({
            "property": requirement["property"],
            "preservation": requirement["preservation"],
            "enforcement": requirement["enforcement"],
            "authority": requirement["authority"],
            "source_contract": requirement["source_contract"],
            "verdict": requirement_result["verdict"],
        })

    if result["policy"]["verdict"] != "SUPPORTED":
        raise SoloRingError(
            ErrorCode.OBSERVATION_POLICY_UNSUPPORTED,
            "The captured observation policy is not supported by the "
            "selected observation-capable profile.",
            status_code=409,
            details={"policy": result["policy"], "requirements": traces})
    if any(trace["verdict"] == "UNSUPPORTED" for trace in traces):
        raise SoloRingError(
            ErrorCode.OBSERVATION_REQUIREMENT_UNSUPPORTED,
            "A REQUIRED observation requirement is unsupported by the "
            "selected observation-capable profile; the observation "
            "refuses before Generation publication.",
            status_code=409,
            details={"requirements": traces})
    if traces:
        raise SoloRingError(
            ErrorCode.OBSERVATION_REQUIREMENT_UNKNOWN,
            "A REQUIRED observation requirement names a property the "
            "selected profile has no capability declaration for; the "
            "observation refuses before Generation publication.",
            status_code=409,
            details={"requirements": traces})
