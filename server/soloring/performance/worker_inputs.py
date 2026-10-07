"""M17C-D W4 — the worker schema-5 performance lane (frozen plan
R2-FINAL W4): pre-submit integrity + exact submission.

``execute_schema5_performance_inputs`` is the schema-5 analogue of
the schema-3/4 derived-input executors: it loads the claimed
Generation's GPI rows, requires EXACTLY the expected sibling set
(the ONE ``expected_gpi_rows`` law — missing, duplicate, extra,
wrong-key, wrong-position, wrong-role rows are terminal typed
refusals), proves the §14.4 per-segment equality chain — captured
schema-8 segment ↔ ``performance_execution.segments`` entry ↔ GPI
rows INCLUDING re-derived derived bytes (the shared §14.6 sampler
re-run on the captured inputs, byte-compared with the retained
blobs) ↔ the bindings being submitted — and then uploads the EXACT
retained derived bytes through the Comfy attempt namespace.

Every refusal fires BEFORE any upload or submission.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path

from soloring.errors import ErrorCode, SoloRingError


@dataclass
class VerifiedPerformanceInput:
    """One verified performance derived input bound to its exact
    captured segment — the record the submission document
    enumerates (role, blob hash, input name, segment position)."""

    input_key: str
    position: int
    artifact_role: str
    shot_revision_segment_position: int
    blob_hash: str
    local_path: str
    execution_reference: str | None = None
    extra: dict = field(default_factory=dict)


def _refusal(message: str) -> SoloRingError:
    return SoloRingError(ErrorCode.PERFORMANCE_EXECUTION_BINDING_INVALID,
                         message, status_code=422)


async def execute_schema5_performance_inputs(
    session, store, *,
    generation_id: str,
    attempt_id: str,
    workflow_spec: dict,
    client,
    manifest_doc=None,
) -> list[VerifiedPerformanceInput]:
    from sqlalchemy import text as _text

    from soloring.performance import execution_sampler as es
    from soloring.performance.execution_spec import (
        expected_lower_from_retained, lower_projection,
        validate_workflow_spec_v5,
    )

    generation = (await session.execute(_text(
        "SELECT * FROM generations WHERE id = :g"),
        {"g": generation_id})).mappings().one_or_none()
    if generation is None:
        raise _refusal(f"Generation {generation_id} does not exist")
    revision_id = generation["shot_revision_id"]

    children = (await session.execute(_text(
        "SELECT * FROM shot_revision_performance_segments "
        "WHERE shot_revision_id = :r ORDER BY position"),
        {"r": revision_id})).mappings().all()
    # FPR31-M17CD-04: the grammar law GROUNDED in the captured
    # children — cardinality/order, every per-segment coordinate,
    # and the generic-vs-dialogue vocal closure
    validate_workflow_spec_v5(
        workflow_spec, captured_children=children)
    # the independent lower reconstruction from RETAINED facts — the
    # Generation row + its input rows + the captured manifest —
    # compared against the v5 lower projection (never a
    # self-projection)
    if manifest_doc is not None:
        input_rows = (await session.execute(_text(
            "SELECT input_key, position, asset_id, blob_hash, "
            "reference_role FROM generation_inputs "
            "WHERE generation_id = :g ORDER BY input_key, position"),
            {"g": generation_id})).mappings().all()
        expected = expected_lower_from_retained(
            generation, input_rows, manifest_doc)
        projection = lower_projection(workflow_spec)
        if projection["schema_version"] == 2:
            # the v2 additions (model/realization) are the retained
            # package's own; their fingerprint/attestation closure is
            # enforced by the schema-2 historical laws the dispatch
            # runs for a v2 lower — here the v1 core must match and
            # the model identity must agree with the Generation row
            if generation["model"] is None:
                raise _refusal(
                    "v5-over-v2 lower meaning on a Generation with "
                    "no retained model identity")
            if projection["model"]["id"] != generation["model"] or \
                    projection["model"]["version"] != \
                    generation["model_version"]:
                raise _refusal(
                    "v5-over-v2 model identity disagrees with the "
                    "retained Generation row")
            projection = {k: v for k, v in projection.items()
                          if k not in ("schema_version", "model",
                                       "realization")}
            expected = {k: v for k, v in expected.items()
                        if k != "schema_version"}
        if projection != expected:
            raise _refusal(
                "the v5 lower projection does not EQUAL the lower "
                "spec reconstructed from retained Generation/input/"
                "manifest facts")

    container = workflow_spec["performance_execution"]
    fps = Fraction(container["rasterization"]["fps"]["num"],
                   container["rasterization"]["fps"]["den"])
    frame_count = container["rasterization"]["frame_count"]
    child_dicts = [{
        "shot_revision_segment_position": c["position"],
        "performance_revision_id": c["performance_revision_id"],
        "segment_hash": c["segment_hash"],
        "vocal_performance_revision_id":
            c["vocal_performance_revision_id"],
        "vocal_binding_hash": c["vocal_binding_hash"],
    } for c in children]
    expected_rows = list(es.expected_gpi_rows(
        child_dicts, es.TRANSLATION_IDENTITY))
    expected_keys = {
        (r["input_key"], r["position"]): r for r in expected_rows}

    persisted = (await session.execute(_text(
        "SELECT * FROM generation_performance_inputs "
        "WHERE generation_id = :g ORDER BY input_key, position"),
        {"g": generation_id})).mappings().all()
    persisted_keys = [(r["input_key"], r["position"])
                      for r in persisted]
    if len(set(persisted_keys)) != len(persisted_keys):
        raise _refusal(
            "duplicate generation_performance_inputs coordinates "
            f"for {generation_id}")
    for row in persisted:
        key = (row["input_key"], row["position"])
        want = expected_keys.get(key)
        if want is None:
            raise _refusal(
                f"generation performance input {key!r} is not in the "
                "expected sibling set (extra or wrong-key/position "
                "row)")
        for column in ("artifact_role",
                       "shot_revision_segment_position",
                       "performance_revision_id",
                       "vocal_performance_revision_id",
                       "binding_hash", "segment_hash",
                       "translation_identity"):
            if row[column] != want[column]:
                raise _refusal(
                    f"generation performance input {key!r} "
                    f"{column} disagrees with the expected shape "
                    f"({row[column]!r} != {want[column]!r})")
    for key in expected_keys:
        if key not in set(persisted_keys):
            raise _refusal(
                f"generation performance input {key!r} is MISSING "
                "from the expected sibling set")

    # the spec-entry coordinate equalities per segment
    entries = {e["shot_revision_segment_position"]: e
               for e in container["segments"]}
    for row in persisted:
        entry = entries[row["shot_revision_segment_position"]]
        if entry["segment_hash"] != row["segment_hash"]:
            raise _refusal(
                "WorkflowSpec segment_hash disagrees with the GPI "
                "tie-back")
        if row["artifact_role"] == "performance.controls":
            if entry["control_schedule_blob_hash"] != row["blob_hash"]:
                raise _refusal(
                    "WorkflowSpec control_schedule_blob_hash "
                    "disagrees with the GPI controls blob")
        else:
            vocal = entry["vocal"]
            if vocal is None or vocal[
                    "materialized_audio_track_blob_hash"] != \
                    row["blob_hash"]:
                raise _refusal(
                    "WorkflowSpec materialized audio track hash "
                    "disagrees with the GPI vocal-audio blob")

    # re-derive under the ONE sampler and byte-compare the retained
    # bytes (the §14.4 chain's derived-bytes link)
    from soloring.performance.execution_translation import derive_all

    settings = store.settings if hasattr(store, "settings") else None
    derived = await derive_all(
        session, settings, revision_id=revision_id,
        fps=fps, frame_count=frame_count)
    rederived: dict[tuple[str, int], bytes] = {}
    for item in derived:
        position = item["child"]["position"]
        rederived[("performance.controls", position)] = \
            item["schedule_bytes"]
        if item["audio_bytes"] is not None:
            rederived[("performance.vocal_audio", position)] = \
                item["audio_bytes"]
    for row in persisted:
        data = Path(store.path_for_hash(row["blob_hash"])).read_bytes()
        if hashlib.sha256(data).hexdigest() != row["blob_hash"]:
            raise _refusal(
                "retained derived-input blob does not rehash to its "
                "content address")
        expected_bytes = rederived.get(
            (row["input_key"], row["shot_revision_segment_position"]))
        if expected_bytes is None or data != expected_bytes:
            raise _refusal(
                f"retained {row['input_key']} bytes for segment "
                f"{row['shot_revision_segment_position']} do not "
                "equal the re-derived §14.6 bytes")

    # upload the EXACT retained bytes in the frozen attempt namespace
    from soloring.executors.comfy.input_materializer import (
        attempt_namespace, validate_returned_reference,
    )
    from soloring.executors.comfy.translate import comfy_input_reference

    namespace = attempt_namespace(generation_id, attempt_id)
    verified: list[VerifiedPerformanceInput] = []
    for row in persisted:
        local = store.path_for_hash(row["blob_hash"])
        ext = ".json" if row["artifact_role"] == \
            "performance.controls" else ".wav"
        filename = (f"{row['input_key']}_{row['blob_hash'][:16]}"
                    f"_seg{row['shot_revision_segment_position']}"
                    f"{ext}")
        name, sub = await client.upload(
            source_path=local, filename=filename,
            subfolder=namespace)
        validate_returned_reference(name, sub, namespace)
        verified.append(VerifiedPerformanceInput(
            input_key=row["input_key"], position=row["position"],
            artifact_role=row["artifact_role"],
            shot_revision_segment_position=(
                row["shot_revision_segment_position"]),
            blob_hash=row["blob_hash"], local_path=str(local),
            execution_reference=comfy_input_reference(name, sub),
            extra={"segment_position":
                   row["shot_revision_segment_position"],
                   "translation_identity":
                       row["translation_identity"]}))
    return verified


def submission_performance_bindings(
        verified: list[VerifiedPerformanceInput]) -> list[dict]:
    """The submission-document enumeration (frozen plan W4): per
    performance input — the role, blob hash, input name, AND the
    segment position it realizes — so the A/B causality proof reads
    from the submission document, not from pixel hashes."""
    return [{
        "role": v.artifact_role,
        "blob_hash": v.blob_hash,
        "input_name": v.execution_reference,
        "segment_position": v.shot_revision_segment_position,
        "translation_identity": v.extra["translation_identity"],
    } for v in verified]
