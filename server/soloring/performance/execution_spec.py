"""M17C-D WorkflowSpec schema 5 — the performance execution plane
(frozen plan R2-FINAL §2.5, Decision C).

``build_workflow_spec_v5`` is a SIBLING builder (v4 behavior stays
byte-stable): v5 wraps the EXACT lower logical spec — v1 or v2 —
the Generation would otherwise carry, preserving every lower root
key verbatim (a lawful v2's ``model`` and ``realization`` are never
dropped) and adding exactly two performance keys. v3/v4 lower
meaning is REJECTED here (Decision A already refused those
compositions at the admission gates; this is the second guard,
because v4 is a true wrapper over the exact v3 meaning and silently
dropping that meaning is forbidden).

``validate_workflow_spec_v5`` is the ONE grammar law — exact
root/container/entry/vocal key sets, the lower-projection
preservation law, position uniqueness + cardinality,
``vocal``-null-iff-generic, and the frozen translation-identity
coordinate — consumed by the builder's own tests, the worker's
schema-5 dispatch, and the recovery verifier so the three surfaces
cannot drift.
"""

from __future__ import annotations

from soloring.errors import ErrorCode, SoloRingError
from soloring.performance.execution_sampler import TRANSLATION_IDENTITY

LOGICAL_WORKFLOW_SCHEMA_VERSION_5 = 5

_LOWER_ROOT_V1 = {
    "workflow_id", "workflow_version", "manifest_hash", "inputs",
    "prompt", "parameters", "outputs",
}
_LOWER_ROOT_V2 = _LOWER_ROOT_V1 | {"model", "realization"}
_PERFORMANCE_ROOT_KEYS = {"performance_translation",
                          "performance_execution"}
_V5_ROOT_V1 = _LOWER_ROOT_V1 | _PERFORMANCE_ROOT_KEYS | {
    "schema_version"}
_V5_ROOT_V2 = _LOWER_ROOT_V2 | _PERFORMANCE_ROOT_KEYS | {
    "schema_version"}

_CONTAINER_KEYS = {"rasterization", "segments"}
_RASTERIZATION_KEYS = {"fps", "frame_count"}
_ENTRY_KEYS = {
    "shot_revision_segment_position", "segment_hash", "subject_id",
    "performance_revision_id", "payload_blob_hash",
    "payload_sha256", "performance_profile_id", "performance_kind",
    "performance_start", "performance_end", "shot_anchor",
    "control_schedule_blob_hash", "vocal",
}
_VOCAL_KEYS = {
    "vocal_performance_revision_id", "vocal_audio_blob_hash",
    "source_start_sample", "source_end_sample_exclusive",
    "sample_rate_hz", "vocal_binding_hash",
    "synchronization_basis_version",
    "materialized_audio_track_blob_hash",
}


def _grammar_refusal(message: str) -> SoloRingError:
    return SoloRingError(ErrorCode.INTERNAL_INVARIANT_VIOLATION,
                         message, status_code=500)


def is_v5(spec: dict) -> bool:
    return isinstance(spec, dict) \
        and spec.get("schema_version") \
        == LOGICAL_WORKFLOW_SCHEMA_VERSION_5


def build_workflow_spec_v5(
    lower_spec: dict, *, performance_execution: dict,
) -> dict:
    """Wrap the EXACT lower logical spec (v1 or v2) with the
    performance plane. The lower document is copied key-for-key
    (minus ``schema_version``); nothing is dropped, reordered, or
    approximated."""
    if not isinstance(lower_spec, dict):
        raise _grammar_refusal("lower spec must be a JSON object")
    version = lower_spec.get("schema_version")
    if version not in (1, 2):
        # Decision A: schema-8 over the spatial/observation planes is
        # refused at the admission gates; v3/v4 lower meaning must
        # never silently lose its execution semantics here.
        raise _grammar_refusal(
            f"WorkflowSpec schema 5 wraps lower logical v1/v2 only — "
            f"refusing lower schema {version!r}")
    spec = {key: value for key, value in lower_spec.items()
            if key != "schema_version"}
    spec["schema_version"] = LOGICAL_WORKFLOW_SCHEMA_VERSION_5
    spec["performance_translation"] = TRANSLATION_IDENTITY
    spec["performance_execution"] = performance_execution
    validate_workflow_spec_v5(spec)
    return spec


def lower_projection(spec: dict) -> dict:
    """The preservation-law inverse: the v5 document minus the two
    performance root keys, with ``schema_version`` reset to the
    recovered lower version (2 iff model+realization are present)."""
    if not is_v5(spec):
        raise _grammar_refusal("lower_projection requires schema 5")
    v2_shape = "model" in spec and "realization" in spec
    lower = {key: value for key, value in spec.items()
             if key not in _PERFORMANCE_ROOT_KEYS
             and key != "schema_version"}
    lower["schema_version"] = 2 if v2_shape else 1
    return lower


def _exact_keys(obj, expected: set, what: str) -> None:
    if not isinstance(obj, dict):
        raise _grammar_refusal(f"{what} must be a JSON object")
    keys = set(obj)
    if keys != expected:
        raise _grammar_refusal(
            f"{what} keys must be exactly {sorted(expected)} — the "
            f"schema is closed (got {sorted(keys)}; unknown="
            f"{sorted(keys - expected)}, missing="
            f"{sorted(expected - keys)})")


def _rational_shape(value, what: str) -> None:
    if not isinstance(value, dict) or set(value) != {"num", "den"} \
            or type(value["num"]) is not int \
            or type(value["den"]) is not int \
            or value["den"] <= 0:
        raise _grammar_refusal(
            f"{what} must be an exact {{num, den}} rational")


def validate_workflow_spec_v5(spec: dict, *, lower_spec=None) -> None:
    """The ONE grammar law. Structural always; when the caller
    supplies the exact lower spec (builder tests, worker pre-submit
    proof), the full lower-projection EQUALITY is asserted too."""
    if not is_v5(spec):
        raise _grammar_refusal("spec is not WorkflowSpec schema 5")
    if ("model" in spec) != ("realization" in spec):
        raise _grammar_refusal(
            "schema-5 model/realization must appear together (the "
            "lawful v2 lower shape) or not at all (v1)")
    _exact_keys(spec, _V5_ROOT_V2 if (
        "model" in spec and "realization" in spec) else _V5_ROOT_V1,
        "schema-5 root")
    if spec["performance_translation"] != TRANSLATION_IDENTITY:
        raise _grammar_refusal(
            "schema-5 performance_translation must be the ONE frozen "
            f"translation identity ({TRANSLATION_IDENTITY!r})")
    container = spec["performance_execution"]
    _exact_keys(container, _CONTAINER_KEYS,
                "performance_execution")
    rasterization = container["rasterization"]
    _exact_keys(rasterization, _RASTERIZATION_KEYS,
                "performance_execution.rasterization")
    _rational_shape(rasterization["fps"],
                    "performance_execution.rasterization.fps")
    if rasterization["fps"]["num"] <= 0 \
            or type(rasterization["frame_count"]) is not int \
            or rasterization["frame_count"] < 1:
        raise _grammar_refusal(
            "performance_execution.rasterization is not a lawful "
            "picture grid")
    segments = container["segments"]
    if not isinstance(segments, list) or not segments:
        raise _grammar_refusal(
            "performance_execution.segments must be a non-empty "
            "position-ordered list")
    positions: list[int] = []
    for index, entry in enumerate(segments):
        _exact_keys(entry, _ENTRY_KEYS,
                    f"performance_execution.segments[{index}]")
        position = entry["shot_revision_segment_position"]
        if type(position) is not int or position < 0:
            raise _grammar_refusal(
                f"segments[{index}] position is not a captured "
                "segment position")
        positions.append(position)
        _rational_shape(entry["performance_start"],
                        f"segments[{index}].performance_start")
        _rational_shape(entry["performance_end"],
                        f"segments[{index}].performance_end")
        _rational_shape(entry["shot_anchor"],
                        f"segments[{index}].shot_anchor")
        for key in ("segment_hash", "payload_blob_hash",
                    "control_schedule_blob_hash"):
            if not isinstance(entry[key], str) or len(entry[key]) != 64:
                raise _grammar_refusal(
                    f"segments[{index}].{key} is not a 64-hex hash")
        vocal = entry["vocal"]
        if vocal is None:
            continue
        _exact_keys(vocal, _VOCAL_KEYS,
                    f"segments[{index}].vocal")
        for key in ("vocal_audio_blob_hash", "vocal_binding_hash",
                    "materialized_audio_track_blob_hash"):
            if not isinstance(vocal[key], str) or len(vocal[key]) != 64:
                raise _grammar_refusal(
                    f"segments[{index}].vocal.{key} is not a 64-hex "
                    "hash")
        for key in ("source_start_sample",
                    "source_end_sample_exclusive", "sample_rate_hz"):
            if type(vocal[key]) is not int or vocal[key] < 0:
                raise _grammar_refusal(
                    f"segments[{index}].vocal.{key} is not a lawful "
                    "integer sample coordinate")
    if positions != sorted(positions):
        raise _grammar_refusal(
            "performance_execution.segments must be position-ordered")
    if len(set(positions)) != len(positions):
        raise _grammar_refusal(
            "performance_execution.segments positions are not unique")
    if lower_spec is not None:
        projection = lower_projection(spec)
        if projection != lower_spec:
            raise _grammar_refusal(
                "the schema-5 lower projection does not EQUAL the "
                "exact lower logical spec — lower execution meaning "
                "was mutated or dropped")
