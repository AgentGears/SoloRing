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


@dataclass
class Schema5PerformanceInputs:
    """The verified per-segment uploads PLUS the per-role ordered
    segment bundles the pinned executor contract consumes natively
    (FPR32-M17CD-02)."""

    verified: list
    role_bundles: dict


def _refusal(message: str) -> SoloRingError:
    return SoloRingError(ErrorCode.PERFORMANCE_EXECUTION_BINDING_INVALID,
                         message, status_code=422)


def _read_verified_artifact(kind: str, pointer: str) -> bytes:
    """Read a retained artifact at its content address and VERIFY the
    bytes rehash to the address (the store's own content-address
    law, run here so a pointer can never address wrong bytes)."""
    import hashlib as _hl
    from pathlib import Path

    from soloring.settings import get_settings

    path = (Path(get_settings().data_dir) / "workflow-artifacts" /
            kind / "sha256" / pointer[:2] / pointer[2:4] /
            f"{pointer}.json")
    if not path.is_file():
        raise _refusal(
            f"the retained {kind} artifact addressed by the "
            f"Generation's captured pointer {pointer} is absent")
    data = path.read_bytes()
    if _hl.sha256(data).hexdigest() != pointer:
        raise _refusal(
            f"the retained {kind} artifact addressed by {pointer} "
            "does not rehash to its content address")
    return data


def _retained_profile_from_pointer(workflow_spec, generation):
    """FPR34-05: the retained realization profile for the
    Generation's EXACT captured release — the authenticated
    document's ``realization.profile.hash`` is a POINTER only; the
    content-addressed artifact is loaded, rehash-verified, bound to
    the Generation's OWN workflow identity, and parsed. No global
    workflow-id uniqueness: two lawful releases sharing a workflow
    ID each resolve their own."""
    import json as _json

    from soloring.performance.execution_spec import (
        retained_profile_pointer,
    )

    pointer = retained_profile_pointer(workflow_spec)
    data = _read_verified_artifact("realization_profiles", pointer)
    try:
        doc = _json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise _refusal(
            f"the retained realization profile {pointer} does not "
            f"parse: {exc}") from exc
    if doc.get("workflow_id") != generation["workflow_id"]:
        raise _refusal(
            f"the retained realization profile {pointer} is bound to "
            f"workflow {doc.get('workflow_id')!r}, not the "
            f"Generation's own workflow "
            f"{generation['workflow_id']!r}")
    raw_profile = data.decode("utf-8")
    if doc.get("schema_version") == 2 and "spatial" in doc:
        doc = {k: v for k, v in doc.items() if k != "spatial"}
        doc["schema_version"] = 1
        raw_profile = _json.dumps(doc)
    return pointer, raw_profile


def _retained_fingerprint_from_pointer(workflow_spec, generation,
                                       profile_doc) -> str:
    """FPR34-05: the retained execution-model fingerprint for the
    Generation's EXACT captured release — the authenticated
    document's ``model.execution_model_fingerprint_hash`` pointer,
    content-verified and bound to BOTH the Generation row's model
    identity and the retained profile's model identity."""
    import json as _json

    from soloring.performance.execution_spec import (
        retained_fingerprint_pointer,
    )

    pointer = retained_fingerprint_pointer(workflow_spec)
    data = _read_verified_artifact("execution_model_fingerprints",
                                   pointer)
    try:
        doc = _json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise _refusal(
            f"the retained execution-model fingerprint {pointer} "
            f"does not parse: {exc}") from exc
    model = doc.get("model")
    if not model:
        # the schema-3 fingerprint shape carries no model identity:
        # its release binding is the descriptor-checked release
        # MEMBERSHIP (the pointer addresses this release's own
        # fingerprint member, content-verified above) plus the
        # caller's fingerprint↔template and profile↔fingerprint
        # closure laws — the ladder enforces both on every
        # retained-3 submission
        return pointer
    for what, ident in (
            ("the Generation row", {
                "id": generation["model"],
                "version": generation["model_version"]}),
            ("the retained profile", {
                "id": profile_doc.model.id,
                "version": profile_doc.model.version})):
        if (model.get("id") != ident["id"]
                or model.get("version") != ident["version"]):
            raise _refusal(
                f"the retained execution-model fingerprint {pointer} "
                f"carries model identity {model.get('id')!r}/"
                f"{model.get('version')!r}, disagreeing with "
                f"{what} {ident['id']!r}/{ident['version']!r}")
    return pointer


async def _compile_retained(session, generation, snapshot_json,
                            profile_doc, manifest_doc, profile_hash,
                            fingerprint_hash, requirement_map):
    """Re-run the frozen M9 realization compiler over RETAINED
    authority only: the captured snapshot's visual pack + the
    CAPTURED facet requirements (FPR34-04: from the Generation's
    authenticated document, never today's mutable visual_facets
    row) + the retained profile/manifest artifacts."""
    from soloring.realization.authority import (
        build_captured_authority,
    )
    from soloring.realization.compiler import compile_realization

    snapshot = json.loads(snapshot_json)
    pack = snapshot.get("visual_reference_pack")
    if not pack:
        raise _refusal(
            "a v5-over-v2 Generation whose snapshot carries no "
            "visual reference pack cannot be reconstructed")
    authority = build_captured_authority(pack, requirement_map)
    result = compile_realization(
        captured_visual_authority=authority,
        profile=profile_doc,
        manifest=manifest_doc,
        profile_hash=profile_hash,
        execution_model_fingerprint_hash=fingerprint_hash,
    )
    if not result.ready:
        raise _refusal(
            "the retained authority no longer compiles a ready "
            "realization under the frozen M9 law")
    return result.spec


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
    # FPR31/32-M17CD-04/05: the grammar law GROUNDED in the
    # captured children + the retained immutable audio authority
    vocal_audio_hashes = {}
    for child in children:
        if child["vocal_performance_revision_id"] is not None:
            vrow = (await session.execute(_text(
                "SELECT retained_audio_blob_hash FROM "
                "vocal_performance_revisions WHERE id = :v"),
                {"v": child["vocal_performance_revision_id"]}
            )).mappings().one_or_none()
            if vrow is None:
                raise _refusal(
                    "captured vocal performance "
                    f"{child['vocal_performance_revision_id']!r} "
                    "is missing from immutable authority")
            vocal_audio_hashes[
                child["vocal_performance_revision_id"]] = \
                vrow["retained_audio_blob_hash"]
    validate_workflow_spec_v5(
        workflow_spec, captured_children=children,
        vocal_audio_hashes=vocal_audio_hashes)
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
        projection = lower_projection(workflow_spec)
        v2_profile = None
        fingerprint_hash = None
        v2_profile_hash = None
        if projection["schema_version"] == 2:
            # FPR32-M17CD-04: the EXACT v2 reconstruction — the
            # retained PROFILE artifact addressed by the row's
            # own realization_profile_hash, its override names
            # resolved against the row's parameters; the
            # fingerprint hash is the inherited artifact-chain
            # validated value
            if generation["model"] is None:
                raise _refusal(
                    "v5-over-v2 lower meaning on a Generation "
                    "with no retained model identity")
            from soloring.realization.profile import parse_profile

            # FPR34-05: the authenticated document's OWN pointers
            # address the Generation's EXACT captured release (no
            # global workflow-id uniqueness — two lawful releases
            # sharing a workflow ID each resolve their own); the
            # artifacts are content-verified + identity-bound at
            # resolution
            _rph, _raw_profile = _retained_profile_from_pointer(
                workflow_spec, generation)
            profile_doc = parse_profile(_raw_profile)
            v2_profile = profile_doc
            v2_profile_hash = _rph
            fingerprint_hash = _retained_fingerprint_from_pointer(
                workflow_spec, generation, profile_doc)
        # the visual-reference-pack identity from the CAPTURED
        # snapshot (the retained M8 authority), and the profile
        # hash from the retained artifact the profile was parsed
        # from — never phantom generations columns
        snap = (await session.execute(_text(
            "SELECT snapshot_json FROM shot_revisions "
            "WHERE id = :r"),
            {"r": generation["shot_revision_id"]})).scalar_one()
        import json as _json

        visual_pack = _json.loads(snap).get(
            "visual_reference_pack")
        from soloring.domain.canonical import (
            canonical_hash as _canon_hash,
        )

        vrph = _canon_hash(visual_pack) if visual_pack else None
        compiled_realization = None
        if v2_profile is not None:
            # FPR33-03 final: re-run the FROZEN M9 compiler over
            # the retained authority (the snapshot's captured pack +
            # the retained profile/manifest/fingerprint) — the exact
            # realization meaning, independently of the projection
            # (FPR34-04: the facet requirements come from the
            # CAPTURED document coordinates, never the mutable row)
            from soloring.performance.execution_spec import (
                captured_requirement_map,
            )

            try:
                compiled_realization = await _compile_retained(
                    session, generation, snap, v2_profile,
                    manifest_doc, v2_profile_hash, fingerprint_hash,
                    captured_requirement_map(workflow_spec))
            except SoloRingError as exc:
                raise _refusal(str(exc.message)) from exc
        expected = expected_lower_from_retained(
            generation, input_rows, manifest_doc,
            v2_profile=v2_profile,
            v2_model_fingerprint_hash=fingerprint_hash,
            v2_visual_reference_pack_hash=vrph,
            v2_profile_hash=v2_profile_hash,
            v2_compiled_realization=compiled_realization)
        if projection["schema_version"] == 2:
            from soloring.performance.execution_spec import (
                compare_lower_v2,
            )

            compare_lower_v2(projection, expected,
                             "the schema-5 worker validation")
        elif projection != expected:
            raise _refusal(
                "the v5 lower projection does not EQUAL the "
                "lower spec reconstructed from retained "
                "Generation/input/manifest facts")

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
                       row["translation_identity"],
                   "remote_name": name, "subfolder": sub}))
    # FPR32-M17CD-02 correction: the pinned executor contract
    # consumes the ordered per-segment collection NATIVELY — one
    # deterministic ROLE BUNDLE per input_key, built from the exact
    # verified rows (a projection, never a re-derivation), uploaded
    # once and bound at the manifest's declared node/field. Every
    # segment retains its auditable correspondence to role + GPI
    # position + captured segment position + exact blob identity +
    # uploaded reference.
    from soloring.domain.canonical import (
        canonical_json_str as _cj,
    )

    role_bundles: dict[str, str] = {}
    for role in ("performance.controls", "performance.vocal_audio"):
        role_rows = [v for v in verified if v.input_key == role]
        if not role_rows:
            continue
        bundle = {
            "schema_version": 1,
            "role": role,
            "translation_identity": es.TRANSLATION_IDENTITY,
            "segments": [{
                "gpi_position": v.position,
                "segment_position":
                    v.shot_revision_segment_position,
                "blob_hash": v.blob_hash,
                "uploaded": v.execution_reference,
            } for v in role_rows],
        }
        data = _cj(bundle).encode("utf-8")
        import hashlib as _hl

        digest = _hl.sha256(data).hexdigest()
        import tempfile

        tmp = store.tmp_path()
        tmp.write_bytes(data)
        await store.place(digest, tmp)
        bundle_name = f"{role}_{digest[:16]}_bundle.json"
        name, sub = await client.upload_bytes(
            data=data, filename=bundle_name, subfolder=namespace) \
            if hasattr(client, "upload_bytes") else \
            await client.upload(
                source_path=store.path_for_hash(digest),
                filename=bundle_name, subfolder=namespace)
        validate_returned_reference(name, sub, namespace)
        role_bundles[role] = comfy_input_reference(name, sub)
    return Schema5PerformanceInputs(
        verified=verified, role_bundles=role_bundles)


def submission_performance_bindings(
        result: "Schema5PerformanceInputs") -> list[dict]:
    """The submission-document enumeration (frozen plan W4): per
    performance input — the role, blob hash, input name, AND the
    segment position it realizes — plus the per-role bundle the
    graph consumes, so the A/B causality proof reads from the
    submission document, not from pixel hashes."""
    rows = [{
        "role": v.artifact_role,
        "blob_hash": v.blob_hash,
        "input_name": v.execution_reference,
        "gpi_position": v.position,
        "segment_position": v.shot_revision_segment_position,
        "translation_identity": v.extra["translation_identity"],
    } for v in result.verified]
    rows.extend({
        "role": role,
        "bundle": reference,
        "kind": "performance.segments",
    } for role, reference in sorted(result.role_bundles.items()))
    return rows
