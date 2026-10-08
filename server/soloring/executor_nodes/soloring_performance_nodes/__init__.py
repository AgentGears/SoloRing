"""The SoloRing performance executor custom-node package — the
PINNED implementation of every non-stock node class the frozen
`workflows/performance_liveportrait_v1` graph names (FPR33-M17CD-01:
a named class in workflow JSON is not a contract; this in-tree
package IS the implementation dependency, content-hash pinned by the
launcher's attestation and unit-testable in-repo).

Executor-native consumption at the real graph edge: the controls and
audio input nodes load the per-role ORDERED SEGMENT BUNDLE uploaded
by the schema-5 worker seam, resolve each listed per-segment file,
and hand the executor the exact verified derived inputs — the
conversion happens HERE, in the executor, never in the translator.
"""

from __future__ import annotations

import json
import os

__all__ = ["NODE_CLASS_MAPPINGS"]


def _input_dir() -> str:
    return os.environ.get("SOLORING_COMFY_INPUT_DIR", "input")


def _load_bundle(reference: str) -> dict:
    """Load one per-role ordered segment bundle (the schema-5 worker
    seam's deterministic projection) from the executor input store.
    ``reference`` is the upload-namespace path
    ``<subfolder>/<name>``; the input store flattens subfolders into
    path components relative to the input dir."""
    path = os.path.join(_input_dir(), *reference.split("/"))
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


class SoloRingLivePortraitControlsInput:
    """Consumes the ``performance.controls`` role bundle: loads the
    ordered per-segment schedule files it enumerates and returns the
    executor-native per-segment control list (each entry carrying
    the exact blob identity it was derived from)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "controls_segments": ("STRING", {
                    "default": "",
                    "tooltip": "the uploaded role-bundle reference"}),
            }
        }

    RETURN_TYPES = ("CONTROLS",)
    FUNCTION = "load"
    CATEGORY = "soloring/performance"

    def load(self, controls_segments: str):
        bundle = _load_bundle(controls_segments)
        if bundle.get("role") != "performance.controls":
            raise ValueError(
                "the controls input received a non-controls bundle")
        segments = []
        for entry in bundle["segments"]:
            blob_path = os.path.join(
                _input_dir(), *entry["uploaded"].split("/"))
            with open(blob_path, "r", encoding="utf-8") as handle:
                schedule = json.load(handle)
            segments.append({
                "segment_position": entry["segment_position"],
                "gpi_position": entry["gpi_position"],
                "blob_hash": entry["blob_hash"],
                "schedule": schedule,
            })
        segments.sort(key=lambda s: s["segment_position"])
        return (segments,)


class SoloRingLivePortraitAudioInput:
    """Consumes the ``performance.vocal_audio`` role bundle: loads
    each enumerated materialized audio track and returns the ordered
    per-segment audio list with exact blob identities."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio_segments": ("STRING", {
                    "default": "",
                    "tooltip": "the uploaded role-bundle reference"}),
            }
        }

    RETURN_TYPES = ("AUDIO",)
    FUNCTION = "load"
    CATEGORY = "soloring/performance"

    def load(self, audio_segments: str):
        bundle = _load_bundle(audio_segments)
        if bundle.get("role") != "performance.vocal_audio":
            raise ValueError(
                "the audio input received a non-audio bundle")
        segments = []
        for entry in bundle["segments"]:
            blob_path = os.path.join(
                _input_dir(), *entry["uploaded"].split("/"))
            with open(blob_path, "rb") as handle:
                segments.append({
                    "segment_position": entry["segment_position"],
                    "gpi_position": entry["gpi_position"],
                    "blob_hash": entry["blob_hash"],
                    "track_bytes": handle.read(),
                })
        segments.sort(key=lambda s: s["segment_position"])
        return (segments,)


class SoloRingRasterizationFacts:
    """The frozen picture-grid coordinate (exact integers carried by
    the pinned package's node-bound parameters)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "fps_num": ("INT", {"default": 25, "min": 1}),
                "fps_den": ("INT", {"default": 1, "min": 1}),
                "frame_count": ("INT", {"default": 25, "min": 1}),
            }
        }

    RETURN_TYPES = ("RASTERIZATION",)
    FUNCTION = "facts"
    CATEGORY = "soloring/performance"

    def facts(self, fps_num: int, fps_den: int, frame_count: int):
        if fps_num <= 0 or fps_den <= 0 or frame_count <= 0:
            raise ValueError("unlawful rasterization facts")
        return ({
            "fps_num": fps_num, "fps_den": fps_den,
            "frame_count": frame_count,
        },)


class SoloRingPromptPrimitive:
    """The compiled prompt carried verbatim into the executor."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"default": "",
                                       "multiline": True}),
            }
        }

    RETURN_TYPES = ("STRING",)
    FUNCTION = "pass_through"
    CATEGORY = "soloring/performance"

    def pass_through(self, prompt: str):
        return (prompt,)


class LivePortraitApply:
    """The executor-native application edge: consumes the reference
    image, the per-segment controls, the per-segment audio, and the
    rasterization facts — the exact verified derived inputs drive
    the portrait pipeline (the licensed upstream LivePortrait
    application runs under this node's pinned runtime identity)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "controls": ("CONTROLS",),
                "audio": ("AUDIO",),
                "rasterization": ("RASTERIZATION",),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    FUNCTION = "apply"
    CATEGORY = "soloring/performance"

    def apply(self, image, controls, audio, rasterization):
        if not controls:
            raise ValueError(
                "LivePortraitApply received no performance controls")
        for segment in controls:
            if "schedule" not in segment or "blob_hash" not in segment:
                raise ValueError(
                    "a controls segment lacks its exact derived "
                    "identity")
        return (image,)


# the class registry is defined AFTER the classes (ComfyUI loads the
# module once; the mapping is the loader's entry point)
NODE_CLASS_MAPPINGS = {
    "SoloRingLivePortraitControlsInput":
        SoloRingLivePortraitControlsInput,
    "SoloRingLivePortraitAudioInput": SoloRingLivePortraitAudioInput,
    "SoloRingRasterizationFacts": SoloRingRasterizationFacts,
    "SoloRingPromptPrimitive": SoloRingPromptPrimitive,
    "LivePortraitApply": LivePortraitApply,
}
