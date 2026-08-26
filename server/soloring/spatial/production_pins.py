"""Certified §114 production constants (frozen r3 §114 evidence import).

Every value below is mechanically imported from the certified companion
evidence tree C:\\AI\\M10R3-evidence (91-file SHA256SUMS companion record
named in the M10 r3 freeze record). Sources are cited per block; nothing
here is inferred, abbreviated, or reconstructed from prefixes.
"""
from __future__ import annotations

# --- §114.3 exact runtime pins -------------------------------------------
# Source: M10R3-evidence/certification/section-114-final-sourcefit-report.md
# §114.3 + weight-hashes.txt (full SHA-256 digests, mechanically recorded).
COMFYUI_COMMIT = "b963f4ad210a42841ab23dfc28a84143a0cce227"
WANVIDEO_WRAPPER_COMMIT = "088128b224242e110d3906c6750e9a3a348a659b"

BASE_MODEL_NAME = "wan2.1_t2v_1.3B_fp16.safetensors"
BASE_MODEL_SHA256 = (
    "be531024cd9018cb5b48c40cfbb6a6191645b1c792eb8bf4f8c1c6e10f924dc5")

CONTROLNET_NAME = "wan2.1-t2v-1.3b-controlnet-depth-v1.safetensors"
CONTROLNET_SHA256 = (
    "b7c6835f48170a49bcccb096bc8d82c7f371189f9011ab7eb371582e9eb7d7e6")

UMT5_NAME = "umt5_xxl_fp16.safetensors"
UMT5_SHA256 = (
    "7b8850f1961e1cf8a77cca4c964a358d303f490833c6c087d0cff4b2f99db2af")
# NOTE: the fp8-scaled UMT5 was downloaded during §114 but the wrapper's
# T5 loader rejects fp8-scaled encoders; the fp16 encoder is the one the
# certified smoke executed with. Both digests are pinned; only fp16 is a
# production runtime requirement.
UMT5_FP8_SCALED_SHA256 = (
    "c3355d30191f1f066b26d93fba017ae9809dce6c627dda5f6a66eaa651204f68")

VAE_NAME = "wan_2.1_vae.safetensors"
VAE_SHA256 = (
    "2fc39d31359a4b0a64f55876d8ff7fa8d780956ae2cb13463b0223e15148976b")

# --- §114.2 smoke execution parameters ------------------------------------
# Source: M10R3-evidence/smoke/smoke-report.json (fixed-seed A/B/C runs).
SMOKE_SEED = 20260823
SMOKE_STEPS = 20
SMOKE_SCHEDULER = "unipc"
SMOKE_CFG = 5.0
SMOKE_SHIFT = 5.0
SMOKE_DIMS = (832, 480, 17)          # width, height, frames
SMOKE_CONTROL_STRIDE = 1             # full-frame control video (17 frames
                                     # → 5 latent frames matching hidden)

# --- §114.5 media/tensor grammar (as smoked) -------------------------------
# Source: M10R3-evidence/smoke/controls/grammar.json +
# section-114 report §114.5. The production artifact grammar freezes the
# as-smoked encoding exactly.
GRAMMAR_ENCODING = "boxdepth-fp32-mm -> affine-uint8 (per-spec d_min/d_max)"
GRAMMAR_BACKGROUND = 255             # background sentinel -> 255 (far)
GRAMMAR_MODE = "L"                   # PNG grayscale mode
GRAMMAR_TIME_BASE = (1, 17)          # num/den
GRAMMAR_WIDTH, GRAMMAR_HEIGHT, GRAMMAR_FRAMES = SMOKE_DIMS

# --- §114.6/§114.7 capacity ------------------------------------------------
MAX_CONTROL_STREAMS = 3              # 1 world + up to 2 entity (frozen)

# --- certified D0 reference materializer identity --------------------------
# Source: M10A1-evidence SHA256SUMS (reference implementation the §114
# controls were exercised with; sha256 of scripts/boxdepth_materializer.py).
CERTIFIED_REFERENCE_BOXDEPTH_SHA256 = (
    "7328c77c6c151348e56ab01dd575b6850605c15e1776937e4a09004b19145e7b")
BOXDEPTH_ALGORITHM_ID = "soloring.boxdepth.rasterizer"
BOXDEPTH_ALGORITHM_VERSION = "1.0.0"

# --- proxy geometry policy (frozen r3 §115, initial policy) ----------------
# Movable Entities render as execution-only oriented boxes whose half
# extents are captured derivation parameters (defaults from the §114
# fixture); never authority, no runtime inference.
PROXY_DEFAULT_ENTITY_HALF_EXTENTS_MM = (200, 700, 200)  # Eva-class standin
PROXY_POLICY_ID = "box-standin-v1"


def encoder_runtime_identity() -> dict:
    """Identity of the ACTUAL loaded byte-producing PNG encoder stack.

    A PyPI release version alone is NOT encoder identity: one Pillow
    release ships many wheels (interpreter/ABI/platform variants, each
    with its own hash), and the PNG writer compresses through a linked
    zlib whose build is below the Pillow.__version__ string. The
    defensible identity is the loaded native encoder module's bytes plus
    the interpreter/ABI/arch it was built for, plus the in-process zlib
    build identities (Pillow wheels link zlib statically into _imaging
    on Windows — covered by the module hash — while the process-level
    zlib versions cover dynamically linked builds).
    """
    import hashlib
    import sys
    import sysconfig
    import zlib
    from pathlib import Path

    import PIL
    import PIL._imaging

    native = Path(PIL._imaging.__file__)
    return {
        "pillow_release": PIL.__version__,
        "pillow_native_module": native.name,
        "pillow_native_module_sha256": hashlib.sha256(
            native.read_bytes()).hexdigest(),
        "python_implementation": sys.implementation.name,
        "python_abi_tag": sysconfig.get_config_var("SOABI") or "",
        "platform": sysconfig.get_platform(),
        "zlib_compile_version": zlib.ZLIB_VERSION,
        "zlib_runtime_version": zlib.ZLIB_RUNTIME_VERSION,
    }


def production_runtime_fingerprint(implementation_sha256: str,
                                   python_version: str,
                                   numpy_version: str,
                                   pillow_version: str,
                                   encoder_identity: dict) -> dict:
    """The frozen materializer runtime fingerprint shape (§104/M10A-1
    contract section 3 + closure reviews P0-2/r2): implementation hash +
    exact python/numpy + the full loaded-encoder identity. The D0
    artifact bytes are the ENCODED PNG bytes, so the actual encoder
    binary (Pillow native module + ABI + linked zlib), not merely the
    release string, is the determinative dependency."""
    return {
        "schema_version": 1,
        "materializer": {
            "algorithm_id": BOXDEPTH_ALGORITHM_ID,
            "algorithm_version": BOXDEPTH_ALGORITHM_VERSION,
            "implementation_sha256": implementation_sha256,
        },
        "runtime": {
            "python": python_version,
            "numpy": numpy_version,
            "pillow_png_encoder": pillow_version,
            "encoder_identity": encoder_identity,
            "platform_contract": "win-cpu-d0",
        },
        "external_components": [
            {
                "kind": "png_encoder",
                "name": "Pillow",
                "version_or_commit": pillow_version,
                # the pinnable byte identity: the LOADED native encoder
                # module — distinguishes ABI/platform wheels and their
                # statically linked compression under one release string
                "sha256": encoder_identity["pillow_native_module_sha256"],
            },
        ],
    }


__all__ = [name for name in dir() if name.isupper()] + [
    "production_runtime_fingerprint",
]
