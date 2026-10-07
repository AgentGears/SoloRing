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


def validate_workflow_spec_v5(spec: dict, *, lower_spec=None,
                              captured_children=None,
                              vocal_audio_hashes=None) -> None:
    """The ONE grammar law. Structural always; ``lower_spec`` is the
    caller's INDEPENDENTLY RECONSTRUCTED lower document (from the
    retained Generation/package/captured-history closure — never
    ``lower_projection(spec)`` itself, which would be tautological);
    ``captured_children`` (the schema-8 companion child rows)
    grounds the captured-set laws: exact cardinality/order, every
    frozen per-segment coordinate, and generic-vs-dialogue vocal
    closure."""
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
    if captured_children is not None:
        # FPR31-M17CD-04: the captured-set laws, grounded in the
        # schema-8 companion children — exact cardinality and order,
        # every frozen per-segment coordinate, and the
        # generic-vs-dialogue vocal closure
        children = sorted(
            captured_children,
            key=lambda c: c["shot_revision_segment_position"]
            if "shot_revision_segment_position" in c.keys()
            else c["position"])
        entries = container["segments"]
        if [e["shot_revision_segment_position"]
                for e in entries] != [c["position"] for c in children]:
            raise _grammar_refusal(
                "performance_execution.segments cardinality/order "
                "disagrees with the captured segment set")
        for entry, child in zip(entries, children):
            position = entry["shot_revision_segment_position"]
            if entry["segment_hash"] != child["segment_hash"] or \
                    entry["subject_id"] != child["subject_id"] or \
                    entry["performance_revision_id"] != \
                    child["performance_revision_id"] or \
                    entry["payload_blob_hash"] != \
                    child["performance_payload_blob_hash"] or \
                    entry["payload_sha256"] != \
                    child["performance_payload_sha256"] or \
                    entry["performance_profile_id"] != \
                    child["performance_profile_id"] or \
                    entry["performance_kind"] != \
                    child["performance_kind"]:
                raise _grammar_refusal(
                    f"segments[{position}] identity coordinates "
                    "disagree with the captured child")
            for key, num, den in (
                    ("performance_start", "performance_start_num",
                     "performance_start_den"),
                    ("performance_end", "performance_end_num",
                     "performance_end_den"),
                    ("shot_anchor", "shot_anchor_num",
                     "shot_anchor_den")):
                if entry[key] != {"num": child[num],
                                  "den": child[den]}:
                    raise _grammar_refusal(
                        f"segments[{position}].{key} disagrees with "
                        "the captured child")
            dialogue = child["vocal_performance_revision_id"] \
                is not None
            if dialogue != (entry["vocal"] is not None):
                raise _grammar_refusal(
                    f"segments[{position}] vocal closure disagrees "
                    "with the captured child (vocal must be present "
                    "iff the segment is dialogue-bound)")
            if dialogue:
                vocal = entry["vocal"]
                # FPR32-M17CD-05: the frozen vocal coordinates are
                # GROUNDED — the source-audio identity in the
                # retained immutable VP/audio authority and the
                # synchronization basis pinned to its frozen value
                if vocal["synchronization_basis_version"] != 1:
                    raise _grammar_refusal(
                        f"segments[{position}].vocal "
                        "synchronization_basis_version is not the "
                        "frozen value 1")
                if vocal_audio_hashes is not None:
                    vp_id = child["vocal_performance_revision_id"]
                    authority = vocal_audio_hashes.get(vp_id)
                    if authority is None:
                        raise _grammar_refusal(
                            f"segments[{position}].vocal references "
                            "a vocal performance absent from the "
                            "retained audio authority")
                    if vocal["vocal_audio_blob_hash"] != authority:
                        raise _grammar_refusal(
                            f"segments[{position}].vocal "
                            "vocal_audio_blob_hash disagrees with "
                            "the retained VP audio authority")
                if vocal["vocal_performance_revision_id"] != \
                        child["vocal_performance_revision_id"] or \
                        vocal["vocal_binding_hash"] != \
                        child["vocal_binding_hash"] or \
                        vocal["source_start_sample"] != \
                        child["source_start_sample"] or \
                        vocal["source_end_sample_exclusive"] != \
                        child["source_end_sample_exclusive"] or \
                        vocal["sample_rate_hz"] != \
                        child["sample_rate_hz"]:
                    raise _grammar_refusal(
                        f"segments[{position}].vocal coordinates "
                        "disagree with the captured child")


def expected_lower_from_retained(gen_row, input_rows, manifest_doc,
                                 *, v2_profile=None,
                                 v2_model_fingerprint_hash=None
                                 ) -> dict:
    """FPR31/32-M17CD-04: the INDEPENDENT lower reconstruction from
    retained facts alone — the Generation row, its GenerationInput
    rows, and the captured manifest document. For a v2 lower the
    caller supplies the retained-authority reconstructions: the
    parsed PROFILE artifact (addressed by the row's own
    realization_profile_hash — its declared override names resolved
    against the row's parameters_json) and the
    artifact-chain-validated fingerprint hash; the model and
    realization meaning (profile identity, model identity, and the
    COMPLETE parameter_overrides) are then compared EXACTLY — never
    deleted to achieve equality. Worker and recovery compare
    ``lower_projection(spec)`` against THIS value; nothing is read
    from current working state and nothing is derived from the v5
    document itself."""
    import json as _json

    inputs: dict = {}
    for row in sorted(input_rows,
                      key=lambda r: (r["input_key"], r["position"])):
        entry = inputs.setdefault(row["input_key"], {"bindings": []})
        entry["bindings"].append({
            "asset_id": row["asset_id"],
            "blob_hash": row["blob_hash"],
            "reference_role": row["reference_role"],
            "position": row["position"],
        })
    base = {
        "workflow_id": manifest_doc.workflow_id,
        "workflow_version": manifest_doc.version,
        "manifest_hash": gen_row["manifest_hash"],
        "inputs": inputs,
        "prompt": gen_row["compiled_prompt"],
        "parameters": _json.loads(gen_row["parameters_json"]),
        "outputs": [
            {
                "name": name,
                "kind": o.kind,
                "expected_count": o.expected_count,
                "accepted_media_types": (
                    list(o.accepted_media_types)
                    if o.accepted_media_types is not None
                    else None),
            }
            for name, o in manifest_doc.outputs.items()
        ],
    }
    if v2_profile is None:
        base["schema_version"] = 1
        return base
    # the exact v2 reconstruction: the profile's declared override
    # names resolved against the row's OWN resolved parameters (the
    # create-time law the service asserts), the identities from the
    # row + the retained artifacts
    parameters = base["parameters"]
    overrides = {}
    for name in v2_profile["parameter_overrides"]:
        if name not in parameters:
            raise _grammar_refusal(
                "the retained profile declares an override the "
                f"Generation's parameters do not carry ({name!r})")
        overrides[name] = parameters[name]
    base["schema_version"] = 2
    base["model"] = {
        "id": gen_row["model"],
        "version": gen_row["model_version"],
        "execution_model_fingerprint_hash":
            v2_model_fingerprint_hash,
    }
    base["realization"] = {
        "schema_version": 1,
        "profile": {
            "id": v2_profile["profile_id"],
            "version": v2_profile["profile_version"],
            "hash": gen_row["realization_profile_hash"],
        },
        "model": base["model"],
        "parameter_overrides": overrides,
    }
    return base


def compare_lower_v2(projection: dict, expected: dict,
                     what: str) -> None:
    """The FPR32-M17CD-04 comparison law: for a v2 lower, the
    identities + the COMPLETE parameter_overrides must match exactly
    (never deleted to achieve equality); the realization channel /
    omitted-optional projections remain governed by the inherited
    schema-2 historical laws (validate_schema2_historical_state /
    validate_realization_input_projection) which validate them
    against the retained input rows."""
    if projection["model"]["id"] != expected["model"]["id"] or \
            projection["model"]["version"] != \
            expected["model"]["version"]:
        raise _grammar_refusal(
            f"{what}: the v5-over-v2 model identity disagrees with "
            "the retained Generation row")
    if projection["realization"]["parameter_overrides"] != \
            expected["realization"]["parameter_overrides"]:
        raise _grammar_refusal(
            f"{what}: the v5-over-v2 realization "
            "parameter_overrides disagree with the retained "
            "profile/parameters reconstruction")
    if projection["realization"]["profile"] != \
            expected["realization"]["profile"]:
        raise _grammar_refusal(
            f"{what}: the v5-over-v2 realization profile identity "
            "disagrees with the retained authority")
    if projection["realization"].get("schema_version") != 1:
        raise _grammar_refusal(
            f"{what}: the v5-over-v2 realization schema_version is "
            "not the frozen value")
    core_projection = {k: v for k, v in projection.items()
                       if k not in ("schema_version", "model",
                                    "realization")}
    core_expected = {k: v for k, v in expected.items()
                     if k not in ("schema_version", "model",
                                  "realization")}
    if core_projection != core_expected:
        raise _grammar_refusal(
            f"{what}: the v5 lower projection does not EQUAL the "
            "lower spec reconstructed from retained facts")
