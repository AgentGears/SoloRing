"""Manifest ↔ template binding validation (M5A-3; M5 plan §20-§21, §7).

Pure Comfy-specific validator: every executor binding declared by the
manifest must resolve EXACTLY against the template graph — prompt, inputs,
parameters, outputs, and seed when a non-null seed is declared. No heuristic
substitute search (M5 amendment §6).

Run at CAPTURE (bad pairs never queue a Generation) and again after
HISTORICAL RETRIEVAL (corruption/parser-drift defense). Lives in the Comfy
package because node/field semantics are executor realization, not logical
workflow contract.
"""

from __future__ import annotations

from soloring.errors import ErrorCode, SoloRingError
from soloring.workflows.manifest import ManifestDocument


class BindingInvalid(SoloRingError):
    def __init__(self, message: str) -> None:
        super().__init__(ErrorCode.COMFY_TEMPLATE_BINDING_INVALID, message,
                         status_code=422)


def _node_inputs(template: dict, node_id: object, what: str) -> dict:
    if not isinstance(node_id, str) or not node_id:
        raise BindingInvalid(f"{what}: manifest declares no node binding")
    node = template.get(node_id)
    if not isinstance(node, dict):
        raise BindingInvalid(
            f"{what}: template has no node {node_id!r}"
        )
    inputs = node.get("inputs")
    if not isinstance(inputs, dict):
        raise BindingInvalid(f"{what}: template node {node_id!r} has no inputs")
    return inputs


def _require_field(inputs: dict, field: object, node_id: object, what: str) -> None:
    if not isinstance(field, str) or not field:
        raise BindingInvalid(f"{what}: manifest declares no field binding")
    if field not in inputs:
        raise BindingInvalid(
            f"{what}: template node {node_id!r} has no input field {field!r}"
        )


def validate_manifest_template_bindings(
    manifest: ManifestDocument, template: dict
) -> None:
    """Verify every executor binding resolves against the captured graph.

    `template` is the parsed Comfy API-format graph (node_id → {class_type,
    inputs: {...}}). Validation is structural only — no execution semantics.
    """
    # Reference inputs (with source_role) + the prompt input.
    for key, decl in manifest.inputs.items():
        what = f"manifest input {key!r}"
        inputs = _node_inputs(template, decl.node, what)
        _require_field(inputs, decl.field, decl.node, what)

    # Parameters.
    for name, decl in manifest.parameters.items():
        what = f"manifest parameter {name!r}"
        inputs = _node_inputs(template, decl.node, what)
        _require_field(inputs, decl.field, decl.node, what)

    # Outputs: node must exist (the field is where history reports outputs;
    # presence in the template is not structurally guaranteed, so node-level
    # validation only).
    for name, decl in manifest.outputs.items():
        what = f"manifest output {name!r}"
        if not isinstance(decl.node, str) or not decl.node:
            raise BindingInvalid(f"{what}: manifest declares no node binding")
        if not isinstance(template.get(decl.node), dict):
            raise BindingInvalid(f"{what}: template has no node {decl.node!r}")

    # Seed: only when the manifest declares an explicit binding (M5
    # amendment §6 — never search the graph heuristically).
    seed_decl = getattr(manifest, "seed", None)
    if seed_decl is not None:
        what = "manifest seed"
        inputs = _node_inputs(template, seed_decl.node, what)
        _require_field(inputs, seed_decl.field, seed_decl.node, what)
