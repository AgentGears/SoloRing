"""Frozen production spatial execution package (§114 evidence-backed).

The single production profile-2 / manifest-3 / template / descriptor set
derived from the certified §114 smoke. Every value is pinned from
production_pins (the certified evidence import); nothing is invented here.
"""
from __future__ import annotations

import hashlib

from soloring.spatial import production_pins as pins


def production_template() -> dict:
    """The captured workflow template the §114 smoke executed: Wan2.1 1.3B
    T2V + TheDenk depth ControlNet, control_images at node/field, unipc.

    M10E §5.2 completion to the CERTIFIED executable shape: the M10A
    fragment carried the loaders/applies/sampler skeleton without the
    model/text/decode/output LINK wiring (and no output node wiring), so
    it could never satisfy prompt validation. The links below mirror the
    certified §114 workflow_A.json exactly: model chain 1→101→111→121→60,
    text_embeds 3→60, decode 60→70 (vae 2), save 70→80. The three
    control_images placeholders ([\"__INPUT__\", 0]) are replaced at
    translation by the frozen soloring.spatial.v1 frame-chain expansion."""
    return {
        "1": {"class_type": "WanVideoModelLoader", "inputs": {
            "model": pins.BASE_MODEL_NAME, "base_precision": "fp16",
            "quantization": "disabled", "load_device": "main_device"}},
        "2": {"class_type": "WanVideoVAELoader", "inputs": {
            "model_name": pins.VAE_NAME, "precision": "fp16"}},
        "3": {"class_type": "WanVideoTextEncode", "inputs": {
            "t5": ["4", 0], "positive_prompt": "", "negative_prompt": ""}},
        "4": {"class_type": "LoadWanVideoT5TextEncoder", "inputs": {
            "model_name": pins.UMT5_NAME, "precision": "bf16"}},
        "50": {"class_type": "WanVideoEmptyEmbeds", "inputs": {
            "width": pins.GRAMMAR_WIDTH, "height": pins.GRAMMAR_HEIGHT,
            "num_frames": pins.GRAMMAR_FRAMES}},
        "60": {"class_type": "WanVideoSampler", "inputs": {
            "model": ["121", 0],
            "image_embeds": ["50", 0], "text_embeds": ["3", 0],
            "seed": pins.SMOKE_SEED,
            "scheduler": pins.SMOKE_SCHEDULER,
            "cfg": pins.SMOKE_CFG, "shift": pins.SMOKE_SHIFT,
            "steps": pins.SMOKE_STEPS, "force_offload": True,
            "riflex_freq_index": 0}},
        "70": {"class_type": "WanVideoDecode", "inputs": {
            "samples": ["60", 0], "vae": ["2", 0],
            "enable_vae_tiling": True, "tile_x": 512, "tile_y": 352,
            "tile_stride_x": 256, "tile_stride_y": 192}},
        "80": {"class_type": "SaveAnimatedWEBP", "inputs": {
            "images": ["70", 0], "filename_prefix": "soloring",
            "fps": 8.0, "lossless": True, "quality": 100,
            "method": "default"}},
        # world_depth control stream (position 0)
        "100": {"class_type": "WanVideoControlnetLoader", "inputs": {
            "model": pins.CONTROLNET_NAME, "base_precision": "fp16",
            "quantization": "disabled", "load_device": "main_device"}},
        "101": {"class_type": "WanVideoControlnet", "inputs": {
            "model": ["1", 0],
            "controlnet": ["100", 0], "control_images": ["__INPUT__", 0],
            "strength": 1.0, "control_stride": pins.SMOKE_CONTROL_STRIDE,
            "control_start_percent": 0.0, "control_end_percent": 1.0}},
        # entity_depth stream 1 (position 1)
        "110": {"class_type": "WanVideoControlnetLoader", "inputs": {
            "model": pins.CONTROLNET_NAME, "base_precision": "fp16",
            "quantization": "disabled", "load_device": "main_device"}},
        "111": {"class_type": "WanVideoControlnet", "inputs": {
            "model": ["101", 0],
            "controlnet": ["110", 0], "control_images": ["__INPUT__", 0],
            "strength": 1.0, "control_stride": pins.SMOKE_CONTROL_STRIDE,
            "control_start_percent": 0.0, "control_end_percent": 1.0}},
        # entity_depth stream 2 (position 2)
        "120": {"class_type": "WanVideoControlnetLoader", "inputs": {
            "model": pins.CONTROLNET_NAME, "base_precision": "fp16",
            "quantization": "disabled", "load_device": "main_device"}},
        "121": {"class_type": "WanVideoControlnet", "inputs": {
            "model": ["111", 0],
            "controlnet": ["120", 0], "control_images": ["__INPUT__", 0],
            "strength": 1.0, "control_stride": pins.SMOKE_CONTROL_STRIDE,
            "control_start_percent": 0.0, "control_end_percent": 1.0}},
    }


def production_profile_v2() -> dict:
    return {
        "schema_version": 2,
        "profile_id": "wan21-spatial-depth-v1",
        "profile_version": 1,
        "workflow_id": "wan21_spatial_v1",
        "workflow_version": 1,
        "model": {"id": "wan2.1-t2v-1.3b", "version": "fp16"},
        "channels": {},
        "rules": [],
        "parameter_overrides": {},
        "spatial": {
            "spatial_document_schema": 1,
            "max_control_streams": pins.MAX_CONTROL_STREAMS,
            "roles": {
                "spatial.world_depth": {"kind": "derived", "capacity": 1},
                "spatial.entity_depth": {"kind": "derived", "capacity": 2},
            },
            "runtime_requirements": {
                "comfyui": {
                    "kind": "executor_core",
                    "name": "ComfyUI",
                    "proof": {"mode": "fingerprint_component",
                              "value": pins.COMFYUI_COMMIT},
                },
                "wrapper": {
                    "kind": "custom_node",
                    "name": "ComfyUI-WanVideoWrapper",
                    "proof": {"mode": "fingerprint_component",
                              "value": pins.WANVIDEO_WRAPPER_COMMIT},
                },
                "base_model": {
                    "kind": "model_weights",
                    "name": pins.BASE_MODEL_NAME,
                    "proof": {"mode": "fingerprint_component",
                              "value": pins.BASE_MODEL_SHA256},
                },
                "controlnet": {
                    "kind": "control_model",
                    "name": pins.CONTROLNET_NAME,
                    "proof": {"mode": "fingerprint_component",
                              "value": pins.CONTROLNET_SHA256},
                },
                "scheduler": {
                    "kind": "template_policy",
                    "name": "scheduler",
                    "proof": {"mode": "template_node_field",
                              "value": "60/scheduler",
                              "expected": pins.SMOKE_SCHEDULER},
                },
            },
            "advisory_omissions": ["screen_direction_not_consumed"],
        },
    }


def production_manifest_v3() -> dict:
    """The certified schema-3 manifest, carrying the inherited ordinary
    prompt/output contract (M10F PD-1C, R6 §5.5).

    The retained template executes WanVideoTextEncode at node 3
    (positive_prompt) and SaveAnimatedWEBP at node 80; declaring those
    ordinary bindings is the truthful contract. Historical M10E schema-3
    manifests that captured the outputless form remain immutable history
    and are never backfilled. accepted_media_types stays null: the frozen
    media detector recognizes only JPEG/PNG and M10F does not widen it.
    """
    return {
        "schema_version": "3",
        "version": 1,
        "workflow_id": "wan21_spatial_v1",
        "inputs": {
            "prompt": {
                "node": "3", "field": "positive_prompt", "kind": "string",
                "required": True,
            },
            "world_depth": {
                "node": "101", "field": "control_images", "kind": "image",
                "required": True, "cardinality": 1,
                "source": {"kind": "shot_reference", "role": "spatial.world_depth"},
            },
            "entity_depth_1": {
                "node": "111", "field": "control_images", "kind": "image",
                "required": True, "cardinality": 1,
                "source": {"kind": "shot_reference", "role": "spatial.entity_depth"},
            },
            "entity_depth_2": {
                "node": "121", "field": "control_images", "kind": "image",
                "required": True, "cardinality": 1,
                "source": {"kind": "shot_reference", "role": "spatial.entity_depth"},
            },
        },
        "parameters": {},
        "outputs": {
            "video": {
                "node": "80", "field": "images", "kind": "video",
                "expected_count": 1, "accepted_media_types": None,
            },
        },
        "spatial_bindings": {
            "world_depth": {
                "artifact_role": "spatial.world_depth", "node": "101",
                "field": "control_images", "format": "soloring.spatial.v1"},
            "entity_depth_1": {
                "artifact_role": "spatial.entity_depth", "node": "111",
                "field": "control_images", "format": "soloring.spatial.v1"},
            "entity_depth_2": {
                "artifact_role": "spatial.entity_depth", "node": "121",
                "field": "control_images", "format": "soloring.spatial.v1"},
        },
    }


def production_descriptor_v3() -> dict:
    return {
        "schema_version": 3,
        "workflow_id": "wan21_spatial_v1",
        "workflow_version": 1,
        "manifest_hash": _hash_json(production_manifest_v3()),
        "workflow_template_hash": _hash_json(production_template()),
        "realization_profile_hash": _hash_json(production_profile_v2()),
        "execution_model_fingerprint_hash": _production_fingerprint_hash(),
    }


def production_fingerprint_document() -> dict:
    """The M10 execution fingerprint extension for the spatial path: the
    captured §114 runtime identities beyond the M9 base fingerprint."""
    return {
        "schema_version": 1,
        "m10_spatial_runtime": {
            "comfyui_commit": pins.COMFYUI_COMMIT,
            "custom_nodes": {
                "ComfyUI-WanVideoWrapper": pins.WANVIDEO_WRAPPER_COMMIT,
            },
            "artifacts": [
                {"artifact_key": "wan_base", "storage_root_key": "diffusion_models",
                 "node": "1", "field": "model",
                 "declared_name": pins.BASE_MODEL_NAME,
                 "sha256": pins.BASE_MODEL_SHA256},
                {"artifact_key": "depth_controlnet", "storage_root_key": "controlnet",
                 "node": "100", "field": "model",
                 "declared_name": pins.CONTROLNET_NAME,
                 "sha256": pins.CONTROLNET_SHA256},
                {"artifact_key": "umt5_text_encoder", "storage_root_key": "text_encoders",
                 "node": "4", "field": "model_name",
                 "declared_name": pins.UMT5_NAME,
                 "sha256": pins.UMT5_SHA256},
                {"artifact_key": "wan_vae", "storage_root_key": "vae",
                 "node": "2", "field": "model_name",
                 "declared_name": pins.VAE_NAME,
                 "sha256": pins.VAE_SHA256},
            ],
        },
    }


def _hash_json(doc: dict) -> str:
    from soloring.domain.canonical import canonical_hash
    return canonical_hash(doc)


def _production_fingerprint_hash() -> str:
    return _hash_json(production_fingerprint_document())


def boxdepth_implementation_sha256() -> str:
    """SHA-256 of this package's production boxdepth module — the D0
    materializer implementation identity for the runtime fingerprint."""
    return hashlib.sha256(
        __import__("soloring.spatial.boxdepth", fromlist=["x"]).__file__.encode(
        ) if False else
        _module_bytes()).hexdigest()


def _module_bytes() -> bytes:
    import soloring.spatial.boxdepth as m
    from pathlib import Path
    return Path(m.__file__).read_bytes()


def boxdepth_runtime_fingerprint() -> dict:
    import sys
    return pins.production_runtime_fingerprint(
        implementation_sha256=boxdepth_implementation_sha256(),
        python_version=sys.version.split()[0],
        numpy_version=__import__("numpy").__version__,
        pillow_version=__import__("PIL").__version__,
        encoder_identity=pins.encoder_runtime_identity())


__all__ = [
    "production_template", "production_profile_v2",
    "production_manifest_v3", "production_descriptor_v3",
    "production_fingerprint_document", "boxdepth_runtime_fingerprint",
    "boxdepth_implementation_sha256",
]
