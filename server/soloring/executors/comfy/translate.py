"""Pure logical-spec → Comfy-prompt translation (M5A-5; M5 plan §23, §60).

build_comfy_prompt consumes EXACTLY:

    captured GenerationExecutionSpec (workflow_spec + identity)
    + historical manifest document (retrieved by manifest_hash)
    + historical template graph (retrieved by workflow_template_hash)
    + MaterializedComfyInput[] (validated remote references)
    + (generation_id, attempt_id) submission marker

and produces the ComfyPromptPayload whose canonical bytes/hash become
executor_submission_json/hash. No settings lookup, no current manifest/
template, no DB, no Shot state, no filesystem discovery, no network, no
uploader, no submission-state helpers — testable entirely from in-memory
immutable values.

Every graph mutation comes from an EXPLICIT captured binding: exact node ID,
exact field. Missing target = failure. No heuristics (no "first KSampler",
no widget-resembling-seed search). Inputs bind by logical identity
(input_key, position), never filename or list coincidence. Parameters use
already-RESOLVED captured values — translation never applies defaults.
"""

from __future__ import annotations

import copy
import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from soloring.domain.canonical import canonical_json_bytes
from soloring.errors import ErrorCode, SoloRingError
from soloring.executors.comfy.input_materializer import MaterializedComfyInput
from soloring.workflows.manifest import ManifestDocument


class TranslationFailed(SoloRingError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.COMFY_TRANSLATION_FAILED, message,
                         status_code=422)


@dataclass(frozen=True)
class ComfyPromptPayload:
    """The complete executor submission artifact (graph + marker + client id).

    kind is discriminator; prompt graph is the translated template; the
    marker is nested under extra_data.soloring exactly (M5 §32).
    """

    prompt: dict
    extra_data: dict
    client_id: str

    def to_document(self) -> dict:
        return {"prompt": self.prompt, "extra_data": self.extra_data,
                "client_id": self.client_id}


def submission_marker(generation_id: str, attempt_id: str) -> dict:
    return {"soloring": {"generation_id": generation_id,
                         "attempt_id": attempt_id}}


def comfy_input_reference(remote_name: str, subfolder: str) -> str:
    """The executor-local input reference for an uploaded file (audit F11).

    The materializer's returned (remote_name, subfolder) is the authoritative
    executor identity — the attempt-scoped namespace is PART of the
    reference, never discarded: a basename-only binding would collide with
    unrelated files in Comfy's flat input root and defeat the isolation the
    upload namespace exists to provide. The exact wire form expected by the
    LoadImage/input node family is pinned against the live API-format graph
    in M5B-2.
    """
    return f"{subfolder}/{remote_name}" if subfolder else remote_name


def _node_inputs(template: dict, node_id: object, what: str) -> dict:
    if not isinstance(node_id, str) or not node_id:
        raise TranslationFailed(f"{what}: manifest declares no node binding")
    node = template.get(node_id)
    if not isinstance(node, dict):
        raise TranslationFailed(f"{what}: template has no node {node_id!r}")
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        raise TranslationFailed(f"{what}: node {node_id!r} has no inputs")
    return inputs


def _bind(node_inputs: dict, field: object, value: Any,
          node_id: object, what: str) -> None:
    if not isinstance(field, str) or not field:
        raise TranslationFailed(f"{what}: manifest declares no field binding")
    if field not in node_inputs:
        raise TranslationFailed(
            f"{what}: node {node_id!r} has no input field {field!r}"
        )
    node_inputs[field] = value


def build_comfy_prompt(
    *,
    workflow_spec: dict,
    manifest,
    template: dict,
    materialized: Sequence[MaterializedComfyInput],
    generation_id: str,
    attempt_id: str,
    client_id: str,
    schema3_derived: Sequence | None = None,
) -> ComfyPromptPayload:
    """Translate the captured triple into a complete Comfy submission payload.

    Deterministic: same inputs → same canonical bytes (fixture-pinned).
    Fails on any missing binding, cardinality mismatch, undeclared input,
    seed-without-binding, or marker conflict — BEFORE any artifact persists.

    Schema-3 dispatch (M10E §17.3/§17.5): when ``schema3_derived`` is
    supplied, ``manifest`` must be the captured manifest-v3 document (a
    dict validated upstream by the frozen package3 parser). The inherited
    manifest-2 portion is re-parsed through the FROZEN M9 schema-2 parser
    — one grammar, never a second translator. The manifest's inherited
    ``source.kind == "shot_reference"`` string is NOT a dispatch
    authority: spatial binding keys are excluded from ordinary
    materialized-input binding entirely and bind ONLY from the verified
    ``schema3_derived`` uploaded references at the exact captured
    manifest-v3 node/field."""
    if not isinstance(template, dict) or not template:
        raise TranslationFailed("historical template is empty or malformed")

    graph = copy.deepcopy(template)

    spatial_keys: frozenset[str] = frozenset()
    if schema3_derived is not None:
        if not isinstance(manifest, dict):
            raise TranslationFailed(
                "schema3_derived supplied without a captured manifest-v3 "
                "document")
        from soloring.workflows.manifest import parse_manifest_v2

        spatial_keys = frozenset(manifest["spatial_bindings"])
        inherited = {k: v for k, v in manifest.items()
                     if k != "spatial_bindings"}
        inherited["schema_version"] = "2"
        manifest_doc = parse_manifest_v2(inherited)
    else:
        manifest_doc = manifest

    # --- inputs: bind by LOGICAL identity (input_key, position) ------------
    by_slot: dict[tuple[str, int], MaterializedComfyInput] = {}
    declared_keys: set[str] = set()
    bound_targets: set[tuple[str, str]] = set()
    for m in materialized:
        slot = (m.input_key, m.position)
        if slot in by_slot:
            raise TranslationFailed(
                f"duplicate materialized input {m.input_key}:{m.position}"
            )
        by_slot[slot] = m

    for key, decl in manifest_doc.inputs.items():
        if key in spatial_keys:
            continue  # derived spatial input: bound below from uploads only
        if (
            getattr(decl, "source_role", None) is None
            and not getattr(decl, "is_realization_input", False)
        ):
            continue  # the prompt input: handled below, not a reference input
        declared_keys.add(key)
        what = f"input {key!r}"
        node_inputs = _node_inputs(graph, decl.node, what)
        bound_targets.add((decl.node, decl.field))

        slots = sorted(
            (m for m in materialized if m.input_key == key),
            key=lambda m: m.position,
        )
        if not slots:
            raise TranslationFailed(f"{what}: no materialized input supplied")
        if decl.cardinality is not None and len(slots) != decl.cardinality:
            raise TranslationFailed(
                f"{what}: cardinality {decl.cardinality} required, "
                f"{len(slots)} materialized"
            )
        values = [
            comfy_input_reference(m.remote_name, m.subfolder) for m in slots
        ]
        _bind(
            node_inputs, decl.field,
            values[0] if decl.cardinality == 1 and len(values) == 1 else values,
            decl.node, what,
        )

    for m in materialized:
        if m.input_key in spatial_keys:
            raise TranslationFailed(
                f"derived spatial input {m.input_key!r} reached ordinary "
                "materialized-input binding; schema-3 derived controls "
                "bind only from the verified schema3_derived uploads"
            )
        if m.input_key not in declared_keys:
            raise TranslationFailed(
                f"materialized input {m.input_key!r} is not declared by the "
                "captured manifest"
            )

    # --- schema-3 derived controls: exact manifest-v3 node/field ------------
    if schema3_derived is not None:
        _bind_schema3_derived(
            graph, manifest, schema3_derived, workflow_spec, bound_targets)

    # --- prompt ---------------------------------------------------------------
    prompt_decl = manifest_doc.inputs.get("prompt")
    if prompt_decl is not None:
        node_inputs = _node_inputs(graph, prompt_decl.node, "prompt")
        _bind(node_inputs, prompt_decl.field,
              workflow_spec["prompt"], prompt_decl.node, "prompt")

    # --- parameters: RESOLVED captured values, never defaults -----------------
    for name, value in workflow_spec.get("parameters", {}).items():
        decl = manifest_doc.parameters.get(name)
        what = f"parameter {name!r}"
        if decl is None:
            raise TranslationFailed(
                f"{what}: captured parameter has no manifest binding"
            )
        node_inputs = _node_inputs(graph, decl.node, what)
        _bind(node_inputs, decl.field, value, decl.node, what)

    # --- seed: only when the manifest explicitly binds it ----------------------
    seed_decl = getattr(manifest_doc, "seed", None)
    captured_seed = workflow_spec.get("seed")
    if captured_seed is not None:
        if seed_decl is None:
            raise TranslationFailed(
                "captured seed is non-null but the historical manifest "
                "declares no seed binding"
            )
        node_inputs = _node_inputs(graph, seed_decl.node, "seed")
        _bind(node_inputs, seed_decl.field, captured_seed,
              seed_decl.node, "seed")

    # --- outputs: nodes must exist; the captured contract is untouched ---------
    for name, decl in manifest_doc.outputs.items():
        if not isinstance(decl.node, str) or not decl.node:
            raise TranslationFailed(f"output {name!r}: no node binding")
        if not isinstance(graph.get(decl.node), dict):
            raise TranslationFailed(
                f"output {name!r}: template has no node {decl.node!r}"
            )

    # --- marker: exact namespace, conflict-rejected ------------------------------
    marker = submission_marker(generation_id, attempt_id)
    conflicting = template.get("extra_data")
    if isinstance(conflicting, dict) and "soloring" in conflicting:
        raise TranslationFailed(
            "historical template already contains extra_data.soloring; "
            "refusing to overwrite unrelated identity"
        )

    return ComfyPromptPayload(prompt=graph, extra_data=marker,
                             client_id=client_id)


def _bind_schema3_derived(
    graph: dict,
    manifest_v3: dict,
    derived: Sequence,
    workflow_spec: dict,
    bound_targets: set[tuple[str, str]],
) -> None:
    """Bind each verified uploaded schema-3 derived reference to the exact
    node/field certified by the captured manifest v3 (M10E §17.4).

    Fails closed on: workflow-spec expectation vs transport disagreement
    (missing/extra/duplicate/mismatched role/position/input_key), missing
    manifest binding, unsupported binding format, absent upload reference,
    missing template node/field, or two logical sources targeting one
    node/field incompatibly. Dispatch keys on the verified derived
    collection + spatial_bindings — never the inherited
    ``source.kind == "shot_reference"`` string."""
    spec_entries = {
        e["input_key"]: e
        for e in (
            (workflow_spec.get("spatial_realization") or {}).get(
                "derived_artifacts") or []
        )
    }
    supplied: dict[str, object] = {}
    for v in derived:
        if v.input_key in supplied:
            raise TranslationFailed(
                f"duplicate derived input {v.input_key!r}")
        supplied[v.input_key] = v

    if set(spec_entries) != set(supplied):
        missing = sorted(set(spec_entries) - set(supplied))
        extra = sorted(set(supplied) - set(spec_entries))
        raise TranslationFailed(
            f"derived input disagreement versus the workflow spec "
            f"(missing={missing}, extra={extra})"
        )

    bindings = manifest_v3["spatial_bindings"]
    for key in sorted(spec_entries):
        entry = spec_entries[key]
        v = supplied[key]
        if (
            entry["position"] != v.position
            or entry["artifact_role"] != v.artifact_role
        ):
            raise TranslationFailed(
                f"derived input {key!r}: workflow spec and verified "
                "transport disagree on position/role"
            )
        binding = bindings.get(key)
        if binding is None:
            raise TranslationFailed(
                f"derived input {key!r} has no captured manifest-v3 "
                "spatial binding"
            )
        if binding["format"] != "soloring.spatial.v1":
            raise TranslationFailed(
                f"derived input {key!r}: unsupported binding format "
                f"{binding['format']!r}"
            )
        if binding["artifact_role"] != entry["artifact_role"]:
            raise TranslationFailed(
                f"derived input {key!r}: manifest role disagrees with the "
                "workflow spec"
            )
        if not v.execution_reference:
            raise TranslationFailed(
                f"derived input {key!r} has no uploaded executor reference"
            )
        node, field = binding["node"], binding["field"]
        target = (node, field)
        if target in bound_targets:
            raise TranslationFailed(
                f"derived input {key!r}: node/field {node}/{field} is "
                "already owned by an incompatible ordinary binding"
            )
        bound_targets.add(target)
        what = f"derived input {key!r}"
        node_inputs = _node_inputs(graph, node, what)
        _bind(node_inputs, field, v.execution_reference, node, what)


def submission_artifact(payload: ComfyPromptPayload) -> tuple[bytes, str]:
    """Canonical bytes + SHA-256. The persisted bytes ARE the hashed bytes."""
    artifact = canonical_json_bytes(payload.to_document())
    return artifact, hashlib.sha256(artifact).hexdigest()
