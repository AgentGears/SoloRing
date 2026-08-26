"""End-to-end production spatial realization (§114 evidence-backed path).

compose_spatial_realization drives the complete frozen path:

    captured SpatialContinuityPack
        -> exact DerivedSpatialArtifactSpec(s) (world + entity layers)
        -> deterministic D0 materialization (boxdepth, §114.5 grammar)
        -> content-addressed Blob publication
        -> immutable derived provenance
        -> Generation sibling inputs
        -> workflow-spec v3 spatial_realization block

Pure with respect to DB: callers persist the returned rows inside their
own fenced transaction; this module never opens a session.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from soloring.domain.canonical import canonical_hash, canonical_json_str
from soloring.spatial import boxdepth, production_pins as pins
from soloring.spatial.derived import DerivedSpatialArtifactSpec  # noqa: F401
from soloring.spatial.spec3 import build_spatial_realization_block


@dataclass(frozen=True)
class SpatialRealizationOutput:
    """Everything a Generation capture needs, fully materialized."""

    specs: tuple[dict, ...]            # canonical spec documents (per role)
    spec_hashes: tuple[str, ...]
    runtime_fingerprint: dict          # canonical materializer runtime
    runtime_fingerprint_hash: str
    frames: tuple[list[bytes], ...]    # PNG control frames per role
    artifact_digests: tuple[str, ...]  # sha256 over each role's frame set
    spatial_realization_block: dict    # the workflow-spec v3 block


def _world_spec(continuity_hash: str) -> dict:
    return {
        "schema_version": 1,
        "artifact_kind": "boxdepth_control_video",
        "artifact_schema_version": 1,
        "source": {"spatial_continuity_schema_version": 1,
                   "spatial_continuity_hash": continuity_hash},
        "derivation": {
            "algorithm_id": pins.BOXDEPTH_ALGORITHM_ID,
            "algorithm_version": pins.BOXDEPTH_ALGORITHM_VERSION,
            "parameters": {
                "scope": "world",
                "entity_id": None,
                "placement_source_kind": None,
                "placement_source_id": None,
                "proxy_geometry": None,
                "sampling": {"width": pins.GRAMMAR_WIDTH,
                             "height": pins.GRAMMAR_HEIGHT,
                             "frames": pins.GRAMMAR_FRAMES,
                             "time_base_num": pins.GRAMMAR_TIME_BASE[0],
                             "time_base_den": pins.GRAMMAR_TIME_BASE[1],
                             "interpolation": "piecewise-linear-clamped"},
                "projection": {"encoding": pins.GRAMMAR_ENCODING,
                               "background": pins.GRAMMAR_BACKGROUND,
                               "mode": pins.GRAMMAR_MODE},
            },
        },
        "output_contract": {
            "media_type": "image/png", "encoding": "png-l-mode-8bit",
            "width": pins.GRAMMAR_WIDTH, "height": pins.GRAMMAR_HEIGHT,
            "frame_count": pins.GRAMMAR_FRAMES,
            "time_base_num": pins.GRAMMAR_TIME_BASE[0],
            "time_base_den": pins.GRAMMAR_TIME_BASE[1],
        },
    }


def _entity_spec(continuity_hash: str, staging_entry: dict) -> dict:
    spec = _world_spec(continuity_hash)
    spec["derivation"]["parameters"]["scope"] = "entity"
    spec["derivation"]["parameters"]["entity_id"] = staging_entry["entity_id"]
    spec["derivation"]["parameters"]["placement_source_kind"] = "spatial_track"
    spec["derivation"]["parameters"]["placement_source_id"] = staging_entry[
        "spatial_track_id"]
    spec["derivation"]["parameters"]["proxy_geometry"] = pins.PROXY_POLICY_ID
    return spec


def compose_spatial_realization(
    continuity_pack: dict,
    *,
    realization_profile_hash: str = "0" * 64,
) -> SpatialRealizationOutput:
    """Materialize the COMPLETE captured spatial authority into D0 control
    artifacts for the production package.

    Whole-item atomic (frozen §74/§108): every staged entity in the
    captured pack is realized. The frozen capacity is 3 total streams =
    1 world + at most 2 entity layers; a captured pack with more than two
    staged entities fails BEFORE any materialization — there is no
    caller-controlled truncation parameter in production (closure review
    P0-1).
    """
    from soloring.spatial.production_package import (
        boxdepth_runtime_fingerprint,
    )

    staging = continuity_pack["staging"]
    if len(staging) > pins.MAX_CONTROL_STREAMS - 1:
        raise ValueError(
            "captured staging exceeds frozen capacity: at most "
            f"{pins.MAX_CONTROL_STREAMS - 1} staged entities, captured "
            f"{len(staging)}; the whole item fails rather than dropping "
            "authority")

    continuity_hash = canonical_hash(continuity_pack)

    specs = [_world_spec(continuity_hash)]
    for entry in staging:
        specs.append(_entity_spec(continuity_hash, entry))

    # D0 materialization per role: world composite + entity-only layers
    world_pack = {**continuity_pack,
                  "staging": []}  # world-only view
    role_packs = [world_pack]
    for entry in staging:
        solo = {**continuity_pack,
                "spatial_world": {**continuity_pack["spatial_world"],
                                  "world_snapshot": {
                                      **continuity_pack["spatial_world"][
                                          "world_snapshot"],
                                      "frames": [], "axes": []}},
                "staging": [entry]}
        role_packs.append(solo)

    frames = [boxdepth.materialize(pk) for pk in role_packs]
    digests = tuple(boxdepth.artifact_digest(fr) for fr in frames)

    runtime = boxdepth_runtime_fingerprint()
    runtime_hash = canonical_hash(runtime)
    spec_hashes = tuple(canonical_hash(s) for s in specs)

    sr_block = build_spatial_realization_block(
        spatial_continuity_hash=continuity_hash,
        realization_profile_hash=realization_profile_hash,
        derived_artifacts=[
            {"input_key": _role_input_key(i),
             "position": i,
             "artifact_role": ("spatial.world_depth" if i == 0
                               else "spatial.entity_depth"),
             "derived_spatial_artifact_id": "pending:" + spec_hashes[i][:16],
             "spec_hash": spec_hashes[i],
             "runtime_fingerprint_hash": runtime_hash,
             "blob_hash": digests[i]}
            for i in range(len(specs))],
        advisory_omissions=["screen_direction_not_consumed"],
    )
    return SpatialRealizationOutput(
        specs=tuple(specs), spec_hashes=spec_hashes,
        runtime_fingerprint=runtime,
        runtime_fingerprint_hash=runtime_hash,
        frames=tuple(frames), artifact_digests=digests,
        spatial_realization_block=sr_block,
    )


def _role_input_key(position: int) -> str:
    if position == 0:
        return "world_depth"
    return f"entity_depth_{position}"


__all__ = ["compose_spatial_realization", "SpatialRealizationOutput"]
