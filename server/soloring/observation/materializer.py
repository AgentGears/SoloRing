"""M14 mesh-depth materializer (frozen R2 §§14/24/35).

`soloring.observation.mesh_depth.v1`: transforms retained structural-mesh
triangles into world space through the B1 placement chain, composes
inherited world-frame geometry + retained occurrences + non-suppressed
proxies in the frozen canonical order through the CERTIFIED M10
rasterizer/encoder primitives, and builds the exact
MaterializerContract/provenance identity.

The zero-mesh path calls the EXACT M10 entry (`boxdepth.materialize`) —
byte-identical by construction, never a wrapper re-encode. The B1
resource caps are enforced before any rasterization allocation
(Stage A pre-decode and Stage B post-parse live in the retained loader;
the total-observation budget is re-asserted here ahead of triangle
expansion).
"""

from __future__ import annotations

import hashlib
import platform as _platform
import sys
import sysconfig
import zlib
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from soloring.domain.canonical import canonical_json_bytes
from soloring.errors import ErrorCode, SoloRingError
from soloring.observation.mesh import MAX_TOTAL_TRIANGLES_PER_OBSERVATION
from soloring.observation.retained import RetainedMeshSource
from soloring.spatial import boxdepth
from soloring.spatial.math import rotation_matrix

MATERIALIZER_ID = "soloring.observation.mesh_depth"
MATERIALIZER_VERSION = 1
ARTIFACT_ROLE = "observation.world_depth"
INHERITED_MANIFEST_ROLE = "spatial.world_depth"
PLATFORM_CONTRACT = "win-cpu-d0"
ALGORITHM_ID = "soloring.boxdepth.rasterizer"
ALGORITHM_VERSION = "1.0.0"

PARAMETERS = {
    "width": 832,
    "height": 480,
    "frames": 17,
    "time_base_num": 1,
    "time_base_den": 17,
    "mode": "L",
    "background": 255,
}


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _encoder_identity() -> dict:
    import PIL

    module = sys.modules.get("PIL._imaging")
    module_file = getattr(module, "__file__", None)
    return {
        "pillow_native_module": (Path(module_file).name
                                 if module_file else "unknown"),
        "pillow_native_module_sha256": (_file_sha256(Path(module_file))
                                        if module_file else "0" * 64),
        "python_abi_tag": (
            f"{sys.implementation.name}"
            f"{sys.version_info.major}{sys.version_info.minor}-"
            f"{sysconfig.get_platform()}"),
        "python_implementation": sys.implementation.name,
        "platform": sysconfig.get_platform(),
        "zlib_compile_version": zlib.ZLIB_VERSION,
        "zlib_runtime_version": zlib.ZLIB_RUNTIME_VERSION,
        "_pillow_version": PIL.__version__,
    }


def build_materializer_contract(
    *, resource_limits: dict | None = None) -> dict:
    """The exact §24.1 contract object with the REAL implementation and
    runtime identities. Any byte-affecting change to the materializer,
    the rasterizer, or the encoder runtime changes the contract hash."""
    import numpy

    limits = dict(resource_limits or {
        "max_retained_mesh_bytes_per_revision": 100_000_000,
        "max_vertices_per_revision": 3_000_000,
        "max_triangles_per_revision": 500_000,
        "max_total_triangles_per_observation": 500_000,
        "production_time_budget_s": 360,
    })
    encoder = _encoder_identity()
    pillow_version = encoder.pop("_pillow_version")
    return {
        "schema_version": 1,
        "materializer": {
            "id": MATERIALIZER_ID,
            "version": MATERIALIZER_VERSION,
            "implementation_sha256": _file_sha256(
                Path(__file__).resolve()),
        },
        "rasterizer": {
            "algorithm_id": ALGORITHM_ID,
            "algorithm_version": ALGORITHM_VERSION,
            "implementation_sha256": _file_sha256(
                Path(boxdepth.__file__).resolve()),
        },
        "output_grammar": {
            "artifact_digest": "sha256-concatenated-frame-bytes",
            "background": 255,
            "frames": 17,
            "height": 480,
            "mode": "L",
            "pixel_encoding": "float32-mm->per-sequence-affine-uint8",
            "time_base_den": 17,
            "time_base_num": 1,
            "width": 832,
        },
        "resource_limits": limits,
        "runtime": {
            "architecture": _platform.machine(),
            "encoder_identity": encoder,
            "numpy": numpy.__version__,
            "pillow": pillow_version,
            "platform_contract": PLATFORM_CONTRACT,
            "python": (
                f"{sys.version_info.major}.{sys.version_info.minor}."
                f"{sys.version_info.micro}"),
        },
    }


def materializer_contract_hash(contract: dict) -> str:
    return hashlib.sha256(canonical_json_bytes(contract)).hexdigest()


def build_provenance(
    *,
    project_id: str,
    observation_spec_hash: str,
    materializer_contract_hash: str,
    parameters_hash: str,
    source_retained_blob_hashes: list[str],
    execution_package: dict,
) -> dict:
    """Pure canonical function of the convergence coordinate + captured
    identities (frozen §24.2). No timestamps, durations, hostnames,
    paths, memory readings, PIDs, or random ids — ever."""
    return {
        "project_id": project_id,
        "observation_spec_hash": observation_spec_hash,
        "artifact_role": ARTIFACT_ROLE,
        "materializer_id": MATERIALIZER_ID,
        "materializer_version": MATERIALIZER_VERSION,
        "materializer_contract_hash": materializer_contract_hash,
        "parameters_hash": parameters_hash,
        "source_retained_blob_hashes": list(source_retained_blob_hashes),
        "execution_package": {
            "workflow_id": execution_package["workflow_id"],
            "workflow_version": execution_package["workflow_version"],
            "manifest_hash": execution_package["manifest_hash"],
            "workflow_template_hash": (
                execution_package["workflow_template_hash"]),
            "realization_profile_hash": (
                execution_package["realization_profile_hash"]),
            "execution_model_fingerprint_hash": (
                execution_package["execution_model_fingerprint_hash"]),
        },
    }


def provenance_hash(provenance: dict) -> str:
    return hashlib.sha256(canonical_json_bytes(provenance)).hexdigest()


def parameters_hash() -> str:
    return hashlib.sha256(canonical_json_bytes(PARAMETERS)).hexdigest()


@dataclass(frozen=True)
class MeshDepthResult:
    frames: list  # list[bytes] — 17 PNG control frames
    digest: str   # sha256 over concatenated frame bytes
    total_triangles: int
    suppressed_entity_ids: frozenset


def _world_space_triangles(source: RetainedMeshSource) -> np.ndarray:
    """Transform retained integer-millimeter vertices by the composed
    realization→world chain under the frozen Ry·Rx·Rz convention."""
    transform = source.realization_local_to_world
    rotation = np.asarray(
        rotation_matrix(tuple(transform["rotation_udeg"])),
        dtype=np.float64)
    translation = np.asarray(transform["translation_mm"], dtype=np.float64)
    vertices = np.asarray(source.mesh["vertices_mm"], dtype=np.float64)
    world = vertices @ rotation.T + translation
    triangles = np.asarray(source.mesh["triangles"], dtype=np.int64)
    return world[triangles]


def check_duplicate_conditioning(
    sources, captured_spatial_pack: dict) -> None:
    """Frozen §14.3: a CreativeEntity conditioned by BOTH a retained mesh
    in world-depth AND an inherited entity-depth stream (i.e. it is
    staged in the captured schema-5 pack) refuses with
    duplicate_structural_conditioning — no override, schema 1."""
    staged = {entry.get("entity_id") for entry
              in captured_spatial_pack.get("staging", [])}
    for source in sources:
        if (source.authority_subject_kind == "creative_entity"
                and source.authority_subject_id in staged):
            raise SoloRingError(
                ErrorCode.OBSERVATION_REQUIREMENT_UNSUPPORTED,
                "The same CreativeEntity would be conditioned by both a "
                "retained structural mesh in world-depth and an inherited "
                "entity-depth stream (duplicate_structural_conditioning); "
                "schema 1 refuses the observation before materialization.",
                status_code=409,
                details={
                    "reason": "duplicate_structural_conditioning",
                    "entity_id": source.authority_subject_id,
                    "occurrence_id": source.occurrence_id,
                })


def materialize_observation_world_depth(
    captured_spatial_pack: dict,
    sources,
) -> MeshDepthResult:
    """The frozen §14 materialization path.

    sources empty → the EXACT M10 entry (byte-identical frames/digest,
    no wrapper re-encode). sources non-empty → the composite through the
    shared rasterizer/camera/encoder primitives with the frozen input
    iteration order and identity-based proxy suppression.
    """
    sources = list(sources)
    staged = {entry.get("entity_id") for entry
              in captured_spatial_pack.get("staging", [])}
    # §14.3 suppression set: identity-matched CreativeEntity subjects
    # with a retained mesh. (Under schema 1 the staged+bound combination
    # has already refused above, so in-valid-flow this set intersects
    # staging only in the refused case; unstaged bound entities have no
    # proxy to suppress. The exclusion is still applied so the composite
    # can never double-count a suppressed identity.)
    suppressed = frozenset(
        source.authority_subject_id for source in sources
        if source.authority_subject_kind == "creative_entity")

    if not sources:
        frames = boxdepth.materialize(captured_spatial_pack)
        return MeshDepthResult(
            frames=frames,
            digest=boxdepth.artifact_digest(frames),
            total_triangles=0,
            suppressed_entity_ids=frozenset())

    # caps before rasterization allocation (B1 values are normative)
    total = sum(len(source.mesh["triangles"]) for source in sources)
    if total > MAX_TOTAL_TRIANGLES_PER_OBSERVATION:
        raise SoloRingError(
            ErrorCode.STRUCTURAL_MESH_LIMIT_EXCEEDED,
            f"observation total {total} triangles exceeds "
            f"MAX_TOTAL_TRIANGLES_PER_OBSERVATION "
            f"{MAX_TOTAL_TRIANGLES_PER_OBSERVATION}",
            status_code=409)

    mesh_tris = [_world_space_triangles(source) for source in sources]
    flat = (np.concatenate(mesh_tris, axis=0) if mesh_tris
            else np.zeros((0, 3, 3)))
    frames = boxdepth.materialize_composite(
        captured_spatial_pack, flat,
        suppressed_entity_ids=frozenset(
            eid for eid in suppressed if eid in staged))
    return MeshDepthResult(
        frames=frames,
        digest=boxdepth.artifact_digest(frames),
        total_triangles=total,
        suppressed_entity_ids=frozenset(
            eid for eid in suppressed if eid in staged))
