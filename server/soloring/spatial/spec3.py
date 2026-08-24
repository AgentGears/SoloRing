"""Workflow-spec schema 3 composition and validation (frozen r3 §45/§110).

The lattice is preserved exactly:
    v1 = no M9 realization, no M10 spatial realization
    v2 = non-empty M9 realization, no M10
    v3 = non-empty M10 spatial realization (M9 optional)

Load-bearing §2.1 rule: an M10-only v3 spec RETAINS the real captured
model / execution_model_fingerprint_hash identity. "No fake M9 block" means
no fabricated ``realization`` block — never dropping model identity.
"""
from __future__ import annotations

from typing import Any

from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.errors import ErrorCode, SoloRingError
from soloring.spatial import error_codes as ec

WORKFLOW_SPEC_SCHEMA_VERSION_3 = 3
SPATIAL_REALIZATION_SCHEMA_VERSION = 1


def _bad(message: str) -> SoloRingError:
    return SoloRingError(ErrorCode.SPATIAL_REALIZATION_BINDING_INVALID,
                         message, status_code=422)


def build_spatial_realization_block(
    *,
    spatial_continuity_hash: str,
    realization_profile_hash: str,
    structured_bindings: list[dict] | None = None,
    derived_artifacts: list[dict] | None = None,
    advisory_omissions: list[str] | None = None,
) -> dict:
    """Build the canonical ``spatial_realization`` block (§110).

    structured_bindings is EMPTY in initial M10 (camera frozen to derived
    Path B). derived_artifacts reference immutable identities/hashes only —
    binary bytes are never embedded. realization_profile_hash pins the
    captured schema-2 profile artifact for hash-addressed retrieval
    (frozen §2.5: schema-3 retains profile/fingerprint content-addressed
    exactly as schema 2).
    """
    if not isinstance(spatial_continuity_hash, str) or len(
            spatial_continuity_hash) != 64:
        raise _bad("spatial_continuity_hash must be a 64-hex sha256.")
    if not isinstance(realization_profile_hash, str) or len(
            realization_profile_hash) != 64:
        raise _bad("realization_profile_hash must be a 64-hex sha256.")
    bindings = list(structured_bindings or [])
    if bindings:
        raise _bad("Initial M10 camera execution is derived Path B; "
                   "structured spatial bindings must be empty.")
    artifacts = list(derived_artifacts or [])
    if not artifacts:
        raise _bad("workflow-spec v3 requires at least one derived artifact; "
                   "no empty v3 exists.")
    seen_positions: set[int] = set()
    seen_keys: set[str] = set()
    for a in artifacts:
        _exact_keys(a, {
            "input_key", "position", "artifact_role",
            "derived_spatial_artifact_id", "spec_hash",
            "runtime_fingerprint_hash", "blob_hash",
        }, "derived_artifacts entry")
        key = a["input_key"]
        if key in seen_keys:
            raise _bad(f"duplicate derived input_key {key!r}.")
        seen_keys.add(key)
        pos = a["position"]
        if not isinstance(pos, int) or isinstance(pos, bool) or pos < 0:
            raise _bad("derived artifact position must be a non-negative int.")
        if pos in seen_positions:
            raise _bad(f"duplicate derived position {pos}.")
        seen_positions.add(pos)
        for field in ("spec_hash", "runtime_fingerprint_hash", "blob_hash"):
            v = a[field]
            if not isinstance(v, str) or len(v) != 64:
                raise _bad(f"derived artifact {field} must be 64-hex sha256.")
    omissions = list(advisory_omissions or [])
    return {
        "schema_version": SPATIAL_REALIZATION_SCHEMA_VERSION,
        "spatial_continuity_hash": spatial_continuity_hash,
        "realization_profile_hash": realization_profile_hash,
        "structured_bindings": bindings,
        "derived_artifacts": artifacts,
        "advisory_omissions": omissions,
    }


def compose_workflow_spec_v3(
    base_spec: dict,
    *,
    model: dict,
    realization: dict | None,
    spatial_realization: dict,
) -> dict:
    """Compose final workflow-spec v3 exactly once from complete identities.

    base_spec carries the captured v1-era request fields. model identity is
    ALWAYS retained (§2.1); ``realization`` appears only when non-empty M9
    visual realization exists (no fake block).
    """
    if realization is not None and not realization:
        raise _bad("realization block must be non-empty when present.")
    spec = dict(base_spec)
    spec["schema_version"] = WORKFLOW_SPEC_SCHEMA_VERSION_3
    spec["model"] = model
    if realization is not None:
        spec["realization"] = realization
    spec["spatial_realization"] = spatial_realization
    return spec


def validate_spec_v3(spec: dict) -> None:
    """Validate the v3 lattice rules and identity retention."""
    if spec.get("schema_version") != WORKFLOW_SPEC_SCHEMA_VERSION_3:
        raise _bad("workflow-spec schema_version must be 3.")
    if "model" not in spec or not isinstance(spec["model"], dict) or not {
            "id", "version", "execution_model_fingerprint_hash"} <= set(
            spec["model"]):
        raise _bad("workflow-spec v3 must retain real captured model identity "
                   "(id, version, execution_model_fingerprint_hash).")
    sr = spec.get("spatial_realization")
    if not isinstance(sr, dict) or not sr.get("derived_artifacts"):
        raise _bad("workflow-spec v3 requires non-empty spatial_realization; "
                   "no empty v3 exists.")
    realization = spec.get("realization")
    if realization is not None and not isinstance(realization, dict):
        raise _bad("realization must be an object when present.")
    return None


def spec_v3_bytes_hash(spec: dict) -> tuple[str, str]:
    return canonical_json_str(spec), canonical_hash(spec)


__all__ = [
    "WORKFLOW_SPEC_SCHEMA_VERSION_3", "SPATIAL_REALIZATION_SCHEMA_VERSION",
    "build_spatial_realization_block", "compose_workflow_spec_v3",
    "validate_spec_v3", "spec_v3_bytes_hash",
]


def _exact_keys(doc: dict, allowed: set[str], what: str) -> None:
    unknown = sorted(set(doc) - allowed)
    if unknown:
        raise _bad(f"{what} has unknown fields {unknown}.")
