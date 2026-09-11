"""M14 WorldObservationSpec schema-1 compiler (frozen R2 §§8.5/9/28/29).

Projects a CAPTURED schema-6 ShotRevision value (the schema-5 semantic
base plus the M13 ``production_world`` pack) into a WorldObservationSpec
schema 1. Schema 6 is the first-class input contract (frozen §7.2): a
schema-5 value is rejected outright — this compiler never preserves the
predecessor's ``schema_version == 5`` execution assumption and never
falls back to the lower-logical projection.

The compiler is a pure function over captured values. It performs no DB,
filesystem, network, or current-state access: every authority fact comes
from the immutable captured snapshot passed in by the caller, and the
captured domain hashes are supplied as verified inputs. Occurrence and
retained-mesh projection (frozen §28 occurrence walk) belongs to the
M14B slices; this compiler emits the zero-occurrence shared subset with
exactly one materialization object whose source list is empty.
"""

from __future__ import annotations

from soloring.errors import validation_error
from soloring.observation.spec import (
    ARTIFACT_ROLE,
    INHERITED_INPUT_ROLE,
    MATERIALIZATION_PARAMETERS,
    MATERIALIZER_ID,
    MATERIALIZER_VERSION,
    build_world_observation_spec,
)
from soloring.domain.canonical import canonical_json_bytes
import hashlib

CAMERA_PROJECTION_CONTRACT = "m10.camera_projection.v1"
WORLD_STRUCTURE_CONTRACT = "m10.world_depth.v1"
VISUAL_IDENTITY_CONTRACT = "m8.visual_reference_pack.v1"
INSTANCE_FEATURE_CONTRACT = "m13.production_instance_feature.v1"
SHOT_INTENT_CONTRACT = "lower_schema_3.prompt"


def _compiler_error(message: str):
    return validation_error(
        f"WorldObservationSpec compiler: {message}")


def _require_hex64(value, what: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise _compiler_error(f"{what} must be a 64-hex SHA-256")
    try:
        int(value, 16)
    except ValueError:
        raise _compiler_error(f"{what} must be a 64-hex SHA-256") from None
    if value != value.lower():
        raise _compiler_error(f"{what} must be lowercase hex")
    return value


def _require_uuid(value, what: str) -> str:
    import re

    if not isinstance(value, str) or not re.fullmatch(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-"
            r"[0-9a-f]{12}", value):
        raise _compiler_error(f"{what} must be a canonical lowercase UUID")
    return value


def compile_world_observation_spec(
    *,
    shot_id: str,
    shot_revision_id: str,
    plan_hash: str,
    captured_schema_6: dict,
    spatial_continuity_hash: str | None,
    production_world_hash: str | None,
    visual_reference_pack_hash: str | None,
    materializer_contract_hash: str,
) -> dict:
    """Project one captured schema-6 value into a schema-1 spec.

    All inputs are captured/immutable facts: the schema-6 snapshot value
    and its captured domain hashes. There is intentionally no session,
    connection, or resolver parameter (frozen §9; M14-OBS:16).
    """
    _require_uuid(shot_id, "shot_id")
    _require_uuid(shot_revision_id, "shot_revision_id")
    _require_hex64(plan_hash, "plan_hash")
    _require_hex64(materializer_contract_hash,
                   "materializer_contract_hash")

    if not isinstance(captured_schema_6, dict):
        raise _compiler_error("captured value must be a snapshot object")
    if captured_schema_6.get("schema_version") != 6:
        # Frozen §7.2 (V1): schema 6 is the first-class captured input.
        # The predecessor's schema-5-only execution assumption is not
        # preserved here, and the lower-logical fallback does not exist
        # in the M14 compiler.
        raise _compiler_error(
            "the M14 observation compiler consumes captured schema-6 "
            f"ShotRevision values only (got schema_version="
            f"{captured_schema_6.get('schema_version')!r})")

    spatial_pack = captured_schema_6.get("spatial_continuity")
    production_world = captured_schema_6.get("production_world")
    visual_pack = captured_schema_6.get("visual_reference_pack")

    if spatial_pack is not None and spatial_continuity_hash is None:
        raise _compiler_error(
            "captured spatial pack present but its domain hash is null")
    if spatial_pack is None and spatial_continuity_hash is not None:
        raise _compiler_error(
            "spatial domain hash present without a captured spatial pack")
    if production_world is not None and production_world_hash is None:
        raise _compiler_error(
            "captured production_world pack present but its domain hash "
            "is null")
    if production_world is None and production_world_hash is not None:
        raise _compiler_error(
            "production_world domain hash present without a captured pack")
    if visual_pack is not None and visual_reference_pack_hash is None:
        raise _compiler_error(
            "captured visual pack present but its domain hash is null")
    if visual_pack is None and visual_reference_pack_hash is not None:
        raise _compiler_error(
            "visual domain hash present without a captured pack")

    requirements: list[dict] = []

    if spatial_pack is not None:
        requirements.append({
            "property": "camera.projection",
            "preservation": "STRUCTURAL",
            "enforcement": "REQUIRED",
            "subject": {"kind": "shot", "id": shot_id},
            "occurrence_id": None,
            "subkey": None,
            "authority": {
                "domain": "A4",
                "source_kind": "spatial_continuity_pack",
                "source_id": shot_revision_id,
                "source_hash": spatial_continuity_hash,
            },
            "source_contract": CAMERA_PROJECTION_CONTRACT,
        })

        world = spatial_pack.get("spatial_world", {})
        snapshot = world.get("world_snapshot", {})
        frames = snapshot.get("frames", [])
        if any(isinstance(fr, dict)
               and fr.get("half_extents_mm") is not None
               for fr in frames):
            requirements.append({
                "property": "world.structure",
                "preservation": "STRUCTURAL",
                "enforcement": "REQUIRED",
                "subject": {"kind": "spatial_world",
                            "id": world["spatial_world_revision_id"]},
                "occurrence_id": None,
                "subkey": None,
                "authority": {
                    "domain": "A4",
                    "source_kind": "spatial_world_revision",
                    "source_id": world["spatial_world_revision_id"],
                    "source_hash": world["spatial_world_revision_hash"],
                },
                "source_contract": WORLD_STRUCTURE_CONTRACT,
            })

    if visual_pack is not None:
        requirements.append({
            "property": "visual.identity",
            "preservation": "IDENTITY_APPEARANCE",
            "enforcement": "REQUIRED",
            "subject": {"kind": "visual_reference_pack",
                        "id": shot_revision_id},
            "occurrence_id": None,
            "subkey": None,
            "authority": {
                "domain": "A3",
                "source_kind": "visual_reference_pack",
                "source_id": shot_revision_id,
                "source_hash": visual_reference_pack_hash,
            },
            "source_contract": VISUAL_IDENTITY_CONTRACT,
        })

    if production_world is not None:
        binding_id = production_world["binding"]["binding_id"]
        for state in production_world.get("instance_feature_states", []):
            requirements.append({
                "property": "continuity.instance_feature",
                "preservation": "EXACT",
                "enforcement": "REQUIRED",
                "subject": {"kind": "production_instance",
                            "id": state["occurrence_id"]},
                "occurrence_id": None,
                "subkey": state["feature_key"],
                "authority": {
                    "domain": "A2",
                    "source_kind": "production_world_pack",
                    "source_id": binding_id,
                    "source_hash": production_world_hash,
                },
                "source_contract": INSTANCE_FEATURE_CONTRACT,
            })

    requirements.append({
        "property": "shot.intent",
        "preservation": "INFERABLE",
        "enforcement": "PERMITTED_INFERENCE",
        "subject": {"kind": "shot", "id": shot_id},
        "occurrence_id": None,
        "subkey": None,
        "authority": {
            "domain": "A1",
            "source_kind": "shot_revision",
            "source_id": shot_revision_id,
            "source_hash": plan_hash,
        },
        "source_contract": SHOT_INTENT_CONTRACT,
    })

    parameters = dict(MATERIALIZATION_PARAMETERS)
    materialization = {
        "artifact_role": ARTIFACT_ROLE,
        "materializer": {
            "id": MATERIALIZER_ID,
            "version": MATERIALIZER_VERSION,
            "contract_hash": materializer_contract_hash,
        },
        "input_role": INHERITED_INPUT_ROLE,
        "source_occurrence_ids": [],
        "parameters": parameters,
        "parameters_hash": hashlib.sha256(
            canonical_json_bytes(parameters)).hexdigest(),
    }

    return build_world_observation_spec(
        shot_revision_id=shot_revision_id,
        plan_hash=plan_hash,
        captured_domains={
            "spatial_continuity_hash": spatial_continuity_hash,
            "production_world_hash": production_world_hash,
            "visual_reference_pack_hash": visual_reference_pack_hash,
        },
        requirements=requirements,
        production_occurrences=[],
        materializations=[materialization],
    )
