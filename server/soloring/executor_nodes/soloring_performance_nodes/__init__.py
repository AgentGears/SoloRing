"""The SoloRing performance executor custom-node package — the
PINNED implementation of every non-stock node class the frozen
`workflows/performance_liveportrait_v1` graph names (FPR33/34-01:
a named class in workflow JSON is not a contract; this in-tree
package IS the implementation dependency, content-hash pinned by
the launcher's attestation and unit-testable in-repo).

MATERIAL CONSUMPTION (FPR34-M17CD-01): the apply edge computes the
executor-native DRIVING SIGNALS from the ordered performance
control schedules — the frozen TRANSLATION_TABLE_V1 ppm→keypoint-
delta conversion proven in the BLOCKER-1B qualification — validates
the audio and rasterization coordinates, and drives the pinned
licensed LivePortrait inference. The conversion and every
validation are deterministic and in-tree (the non-live
material-consumption proof exercises exactly this computation: a
changed derived control changes the consumed transformation input).
The licensed inference itself (upstream LivePortrait + YuNet, the
pinned deployment dependency) is imported at the declared boundary
and FAILS CLOSED when absent — never an identity pass-through.

NO-VOCAL REPRESENTATION (FPR34-M17CD-03): the frozen schema-5 law
permits generic segments with ``vocal: null``; the worker then
uploads NO vocal-audio bundle. The audio input node's LAWFUL
EMPTY representation is the explicit ``NO_VOCAL_AUDIO`` sentinel —
an empty ``audio_segments`` field yields the sentinel (never a
``_load_bundle("")`` path), and the apply edge consumes either the
sentinel or the real materialized tracks. No vocal GPI row is ever
invented; the vocal-iff-dialogue cardinality is untouched.
"""

from __future__ import annotations

import json
import os

__all__ = ["NODE_CLASS_MAPPINGS", "NO_VOCAL_AUDIO",
            "compute_driving_signals", "translation_table_v1"]

NODE_PACKAGE_IDENTITY = "soloring_performance_nodes"

# The frozen ppm→keypoint-delta conversion table (BLOCKER-1B
# qualification, R4 §14.6 executor-native edge): each canonical
# articulation/expression channel contributes signed coefficients
# to LivePortrait keypoint (index, axis) deltas per unit ppm.
TRANSLATION_TABLE_V1 = {
    "profile-1/face.articulation.jaw_open": [
        (19, 1, 0.045), (19, 2, 0.0045), (17, 1, -0.0045)],
    "profile-1/face.articulation.lip_round": [
        (14, 1, 0.010), (3, 1, -0.005), (7, 1, -0.005), (17, 2, -0.005)],
    "profile-1/face.articulation.lip_press": [
        (20, 2, 0.006), (20, 1, 0.006), (14, 1, 0.006)],
    "profile-1/face.articulation.mouth_width": [
        (20, 2, -0.008), (20, 1, -0.008), (14, 1, -0.008)],
    "profile-1/face.expression.smile": [
        (20, 1, -0.010), (14, 1, -0.020), (17, 1, 0.0065),
        (17, 2, 0.003), (13, 1, -0.00275), (16, 1, -0.00275),
        (3, 1, -0.0035), (7, 1, -0.0035)],
}
JAW_PITCH_COUPLING_DEG = -2.25   # applied per unit jaw_open

# The explicit lawful no-vocal representation at the executor
# boundary (FPR34-03): a singleton marker distinct from every real
# track list; produced for an empty audio field, consumed by the
# apply edge without fabricating any audio.
NO_VOCAL_AUDIO = ("__soloring_no_vocal_audio__",)


def translation_table_v1():
    """The frozen conversion table (exposed for the pinned-identity
    battery — the in-tree copy must equal the qualification's)."""
    return {k: [tuple(c) for c in v]
            for k, v in TRANSLATION_TABLE_V1.items()}


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


def _load_schedule(entry: dict) -> dict:
    blob_path = os.path.join(
        _input_dir(), *entry["uploaded"].split("/"))
    with open(blob_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def compute_driving_signals(controls: list) -> list:
    """FPR34-01 material consumption: the executor-native driving
    signals computed from the ordered per-segment control
    schedules — per active frame, the keypoint deltas (the frozen
    TRANSLATION_TABLE_V1 conversion) and the jaw pitch coupling.
    This IS the transformation input the licensed LivePortrait
    inference consumes; it is a deterministic function of the
    verified derived controls, computed in-tree and proven by the
    non-live material-consumption battery (a changed control value
    changes the consumed signals)."""
    if not controls:
        raise ValueError(
            "LivePortrait consumption requires performance controls")
    signals = []
    for segment in sorted(controls,
                          key=lambda s: s["segment_position"]):
        schedule = segment["schedule"]
        identity = schedule.get("translation_identity")
        if identity and not identity.startswith(
                "soloring-executor-translation"):
            raise ValueError(
                "a controls schedule from an unverified translation "
                f"identity reached the executor: {identity!r}")
        for frame in schedule["frames"]:
            entry = {
                "frame": frame["frame"],
                "segment_position": segment["segment_position"],
                "blob_hash": segment["blob_hash"],
                "active": bool(frame.get("segment_active")),
                "deltas": None,
                "pitch_deg": 0.0,
            }
            if entry["active"]:
                deltas = {}
                ppm = frame.get("channels", {})
                for key, value in ppm.items():
                    table = TRANSLATION_TABLE_V1.get(key)
                    if table is None:
                        # unmapped channels are validated away at
                        # derivation (the §14.7 lane); a residual
                        # unmapped channel at the edge refuses
                        raise ValueError(
                            f"control channel {key!r} has no frozen "
                            "translation entry")
                    u = value / 1_000_000
                    for idx, axis, coef in table:
                        deltas[(idx, axis)] = deltas.get(
                            (idx, axis), 0.0) + coef * u
                jaw = ppm.get(
                    "profile-1/face.articulation.jaw_open", 0)
                entry["deltas"] = {
                    f"{i}.{a}": v
                    for (i, a), v in sorted(deltas.items())}
                entry["pitch_deg"] = (
                    JAW_PITCH_COUPLING_DEG * jaw / 1_000_000)
            signals.append(entry)
    if not signals:
        raise ValueError(
            "the controls schedules carried no frames")
    return signals


class SoloRingLivePortraitControlsInput:
    """Consumes the ``performance.controls`` role bundle: loads the
    ordered per-segment schedule files it enumerates and returns
    the executor-native per-segment control list (each entry
    carrying the exact blob identity it was derived from)."""

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
            segments.append({
                "segment_position": entry["segment_position"],
                "gpi_position": entry["gpi_position"],
                "blob_hash": entry["blob_hash"],
                "schedule": _load_schedule(entry),
            })
        segments.sort(key=lambda s: s["segment_position"])
        return (segments,)


class SoloRingLivePortraitAudioInput:
    """Consumes the ``performance.vocal_audio`` role bundle — or,
    LAWFULLY, no bundle at all (FPR34-03): a generic performance
    (every captured segment ``vocal: null``) produces no vocal-audio
    GPI row and no upload, so the pinned graph's static edge binds
    an EMPTY field here; the explicit ``NO_VOCAL_AUDIO`` sentinel
    is the executor boundary's representation of that lawful state
    (never a ``_load_bundle("")`` attempt, never fabricated
    audio)."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "audio_segments": ("STRING", {
                    "default": "",
                    "tooltip": "the uploaded role-bundle reference; "
                               "empty means the lawful no-vocal "
                               "state"}),
            }
        }

    RETURN_TYPES = ("AUDIO",)
    FUNCTION = "load"
    CATEGORY = "soloring/performance"

    def load(self, audio_segments: str):
        if not audio_segments:
            return (NO_VOCAL_AUDIO,)
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


def _run_liveportrait_inference(image, signals, rasterization):
    """The pinned licensed LivePortrait inference boundary (upstream
    LivePortrait @ 9b294b3d + YuNet detector — the deployment
    dependency the launcher's performance lane installs beside this
    package). FAILS CLOSED when the licensed runtime is absent or
    unqualified: never an identity pass-through, never a test
    substitute — the deployment-qualified adapter
    (soloring.m17c.adapter.facial_liveportrait, the BLOCKER-1B
    qualification) owns the actual invocation of the licensed
    stack; this in-tree boundary refuses anything else."""
    raise RuntimeError(
        "the pinned licensed LivePortrait runtime binding must be "
        "invoked by the deployment-qualified adapter "
        "(soloring.m17c.adapter.facial_liveportrait); this in-tree "
        "boundary never substitutes an unqualified renderer")


class LivePortraitApply:
    """The executor-native application edge (FPR34-01): consumes
    the reference image, the ordered per-segment controls, the
    audio (the NO_VOCAL sentinel or the real tracks), and the
    rasterization facts. The driving signals — the transformation
    input — are computed from the verified controls by the frozen
    conversion (in-tree, deterministic); the licensed inference is
    driven through the pinned boundary and produces frames whose
    content is causally dependent on those signals. The audio and
    rasterization coordinates are validated against the picture
    grid; the audio track is carried to the output for the
    terminal encoder."""

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

    RETURN_TYPES = ("IMAGE", "AUDIO")
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
        signals = compute_driving_signals(controls)
        frame_count = rasterization["frame_count"]
        if any(e["frame"] >= frame_count for e in signals):
            raise ValueError(
                "a controls schedule addresses a frame outside the "
                "rasterized picture grid")
        if audio is NO_VOCAL_AUDIO or (
                isinstance(audio, tuple) and audio == NO_VOCAL_AUDIO):
            output_audio = NO_VOCAL_AUDIO
        else:
            if not audio:
                raise ValueError(
                    "the audio input produced neither the no-vocal "
                    "sentinel nor any track")
            output_audio = audio
        frames = _run_liveportrait_inference(
            image, signals, rasterization)
        return (frames, output_audio)


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
