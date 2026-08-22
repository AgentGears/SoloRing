"""Workflow manifest contract (v0.1 §36; hardened in M4).

The manifest is a versioned, strictly validated document. Three distinct
identities (M4 review):

    workflow_manifest_hash   identity of the validated manifest FILE (raw bytes)
    workflow_spec_hash       identity of the fully RESOLVED logical spec
    executor payload identity  M5 concern, derived from the resolved spec

Strictness rules (M4):
  * ``schema_version`` is explicit ("1") and versioned separately from
    ``workflow_id``/``workflow_version`` (interpretation vs authoring);
  * unknown fields are REJECTED recursively (root, inputs, parameters,
    outputs) — a typo must never silently drop an execution constraint;
  * parameters are typed and closed: unknown supplied / missing required /
    wrong type / out-of-range / invalid enum all reject, with NO lossy
    coercion (``isinstance(True, int)`` is explicitly guarded);
  * outputs declare kind/count and MAY declare accepted media types; logical
    kind (semantic request) stays distinct from detected MIME (byte reality);
  * input declarations are logical (source_role), never filesystem paths.

M5 may materialize captured content identities into executor-local form; this
module never sees executor filenames.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from soloring.domain.normalize import is_valid_role
from soloring.errors import ErrorCode, SoloRingError
from soloring.settings import BASE_DIR

# The single v0.1 workflow directory (plan §4).
WORKFLOW_DIR = BASE_DIR / "workflows" / "hunyuan_i2v_v1"
# M9: the current schema-2 release (frozen plan §77.11). The published
# v1/v3 package remains on disk as the golden legacy fixture.
WORKFLOW_DIR_V4 = BASE_DIR / "workflows" / "hunyuan_i2v_v4"

MANIFEST_SCHEMA_VERSION = "1"
PARAM_TYPES = ("int", "float", "string", "bool")


class WorkflowError(SoloRingError):
    def __init__(self, message: str, code: str = ErrorCode.WORKFLOW_VALIDATION_FAILED) -> None:
        super().__init__(code, message, status_code=422)


# --- Strict document models (recursive unknown-field rejection) ---------------


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ManifestInputDef(_Strict):
    node: str | None = None
    field: str | None = None
    kind: str | None = None
    required: bool = False
    source_role: str | None = None
    cardinality: int | None = Field(default=None, ge=1)


class ManifestParameterDef(_Strict):
    node: str | None = None
    field: str | None = None
    type: Literal["int", "float", "string", "bool"]
    default: int | float | str | bool | None = None
    min: float | None = None
    max: float | None = None
    enum: list[int | float | str] | None = None


class ManifestOutputDef(_Strict):
    node: str | None = None
    field: str | None = None
    kind: str
    expected_count: int = Field(default=1, ge=1)
    # Logical kind vs detected MIME stay distinct (M4 §7). When declared,
    # import verifies detected media compatibility against this list; when
    # undeclared, media compatibility is explicitly unconstrained (v0.1 fake
    # contract — production workflows declare real values in M5).
    accepted_media_types: list[str] | None = None


class ManifestDocument(_Strict):
    schema_version: str
    workflow_id: str
    version: int = Field(ge=1)
    inputs: dict[str, ManifestInputDef] = Field(default_factory=dict)
    parameters: dict[str, ManifestParameterDef] = Field(default_factory=dict)
    outputs: dict[str, ManifestOutputDef] = Field(default_factory=dict)


# --- Parsed value objects ------------------------------------------------------


@dataclass(frozen=True)
class WorkflowInputDef:
    input_key: str
    source_role: str | None
    required: bool
    cardinality: int | None


@dataclass(frozen=True)
class ExpectedOutput:
    name: str
    kind: str
    expected_count: int
    accepted_media_types: tuple[str, ...] | None  # None = explicitly unconstrained

    def output_keys(self) -> list[str]:
        return [f"{self.name}:{i}" for i in range(self.expected_count)]


@dataclass(frozen=True)
class ParameterDef:
    name: str
    type: str
    default: int | float | str | bool | None
    min: float | None
    max: float | None
    enum: tuple[int | float | str, ...] | None


@dataclass(frozen=True)
class WorkflowTemplate:
    workflow_id: str
    workflow_version: int
    manifest_schema_version: str
    manifest_hash: str          # raw manifest file bytes → SHA-256
    workflow_template_hash: str  # raw workflow.json template bytes → SHA-256
    reference_inputs: tuple[WorkflowInputDef, ...]
    parameters: tuple[ParameterDef, ...]
    outputs: tuple[ExpectedOutput, ...]
    # M9 schema-2 surface (§8/§16.3): realization-backed input keys and
    # the schema marker. Defaults keep every legacy template schema-1.
    is_schema2: bool = False
    realization_input_keys: tuple[str, ...] = ()


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_manifest(raw: str | dict) -> ManifestDocument:
    """Validate a manifest document strictly; raises WorkflowError."""
    try:
        doc = raw if isinstance(raw, dict) else json.loads(raw)
        return ManifestDocument.model_validate(doc)
    except ValidationError as exc:
        raise WorkflowError(f"Invalid workflow manifest: {exc}") from exc


def build_template(
    doc: ManifestDocument, manifest_hash: str, template_hash: str
) -> WorkflowTemplate:
    """Cross-field semantic validation + value-object construction."""
    if doc.schema_version != MANIFEST_SCHEMA_VERSION:
        raise WorkflowError(
            f"Unsupported manifest schema_version {doc.schema_version!r}; "
            f"expected {MANIFEST_SCHEMA_VERSION!r}."
        )
    if not doc.outputs:
        raise WorkflowError("Manifest must declare at least one output.")

    ref_inputs: list[WorkflowInputDef] = []
    for key, spec in doc.inputs.items():
        if spec.source_role is None:
            continue  # e.g. the prompt input: handled by the compiler
        if not is_valid_role(spec.source_role):
            raise WorkflowError(f"manifest input {key!r} has invalid source_role")
        ref_inputs.append(
            WorkflowInputDef(
                input_key=key,
                source_role=spec.source_role,
                required=spec.required,
                cardinality=spec.cardinality,
            )
        )

    parameters = tuple(
        ParameterDef(
            name=name,
            type=p.type,
            default=p.default,
            min=p.min,
            max=p.max,
            enum=tuple(p.enum) if p.enum is not None else None,
        )
        for name, p in doc.parameters.items()
    )

    outputs = tuple(
        ExpectedOutput(
            name=name,
            kind=o.kind,
            expected_count=o.expected_count,
            accepted_media_types=(
                tuple(o.accepted_media_types)
                if o.accepted_media_types is not None
                else None
            ),
        )
        for name, o in doc.outputs.items()
    )

    return WorkflowTemplate(
        workflow_id=doc.workflow_id,
        workflow_version=doc.version,
        manifest_schema_version=doc.schema_version,
        manifest_hash=manifest_hash,
        workflow_template_hash=template_hash,
        reference_inputs=tuple(ref_inputs),
        parameters=parameters,
        outputs=outputs,
    )


def load_workflow(directory: Path | None = None) -> WorkflowTemplate:
    """Load + validate the installed workflow; invalid manifests raise before
    any Generation can be created from them (M4 §12).

    Each file is read as ONE byte buffer that is BOTH parsed and hashed
    (audit F8): a separate re-read for hashing could straddle an
    installation switch and pair version-A semantics with version-B's
    SHA-256, breaking the "hash identifies captured semantics" contract.

    ``directory`` defaults to the CURRENT module-level WORKFLOW_DIR (read at
    call time, not import time) so a process-wide installed-workflow swap is
    one coherent monkeypatch point for load AND capture.
    """
    directory = directory if directory is not None else WORKFLOW_DIR
    manifest_bytes = (directory / "manifest.json").read_bytes()
    template_bytes = (directory / "workflow.json").read_bytes()
    doc = parse_manifest(manifest_bytes.decode("utf-8"))
    return build_template(
        doc,
        hashlib.sha256(manifest_bytes).hexdigest(),
        hashlib.sha256(template_bytes).hexdigest(),
    )


# --- Strict parameter resolution (M4 §4-§5) ------------------------------------


def _is_int(value: object) -> bool:
    # isinstance(True, int) is True in Python — bool must never satisfy int.
    return isinstance(value, int) and not isinstance(value, bool)


def _check_type(name: str, ptype: str, value: object) -> None:
    ok = {
        "int": _is_int,
        "float": lambda v: _is_int(v) or (isinstance(v, float)),
        "string": lambda v: isinstance(v, str),
        "bool": lambda v: isinstance(v, bool),
    }[ptype]
    if isinstance(value, bool) and ptype != "bool":
        raise WorkflowError(
            f"Parameter {name!r} expects {ptype}; bool supplied (no coercion)."
        )
    if not ok(value):
        raise WorkflowError(
            f"Parameter {name!r} expects {ptype}; got "
            f"{type(value).__name__}={value!r} (no coercion)."
        )


def resolve_parameters(
    template: WorkflowTemplate, overrides: dict | None = None
) -> dict:
    """Defaults + strict overrides → RESOLVED parameters (persisted at capture).

    unknown supplied → reject; missing required (no default) → reject;
    wrong type → reject (bool≠int, no "12"→12, no 1→true, no 12.7→12);
    out-of-range / invalid enum → reject.
    """
    overrides = overrides or {}
    known = {p.name: p for p in template.parameters}

    for key in overrides:
        if key not in known:
            raise WorkflowError(f"Unknown workflow parameter {key!r}.")

    resolved: dict = {}
    for name, p in known.items():
        if name in overrides:
            value = overrides[name]
        elif p.default is not None:
            value = p.default
        else:
            raise WorkflowError(f"Required workflow parameter {name!r} missing.")
        _check_type(name, p.type, value)
        if p.enum is not None and value not in p.enum:
            raise WorkflowError(
                f"Parameter {name!r} value {value!r} not in enum {list(p.enum)}."
            )
        if p.min is not None or p.max is not None:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                if p.min is not None and value < p.min:
                    raise WorkflowError(
                        f"Parameter {name!r} below minimum ({value} < {p.min})."
                    )
                if p.max is not None and value > p.max:
                    raise WorkflowError(
                        f"Parameter {name!r} above maximum ({value} > {p.max})."
                    )
        resolved[name] = value
    return resolved


def check_cardinality(
    template: WorkflowTemplate, resolved_counts: dict[str, int]
) -> None:
    """Enforce required/cardinality for reference inputs (v0.1 §41, §36)."""
    from soloring.errors import ErrorCode as _EC

    for inp in template.reference_inputs:
        got = resolved_counts.get(inp.input_key, 0)
        if inp.required and got == 0:
            raise WorkflowError(
                f"Workflow input {inp.input_key!r} is required but resolved "
                f"{got} reference(s).",
                code=_EC.WORKFLOW_INPUT_CARDINALITY_INVALID,
            )
        if inp.cardinality is not None and got != inp.cardinality:
            raise WorkflowError(
                f"Workflow input {inp.input_key!r} requires cardinality "
                f"{inp.cardinality}, resolved {got}.",
                code=_EC.WORKFLOW_INPUT_CARDINALITY_INVALID,
            )


# --- Manifest schema 2 (M9 frozen plan §8) -----------------------------------
# Discriminated `source` object per logical input: legacy ShotReference
# inputs (shot_reference) and M9 realization inputs (realization_channel).
# Schema 2 REJECTS legacy `source_role` — no dual form exists. Schema 1
# continues to interpret `source_role` byte-for-byte as before.


class ShotReferenceSource(_Strict):
    kind: Literal["shot_reference"]
    role: str


class RealizationChannelSource(_Strict):
    kind: Literal["realization_channel"]
    channel: str


class ManifestInputDefV2(_Strict):
    node: str | None = None
    field: str | None = None
    kind: str | None = None
    required: bool = False
    cardinality: int | None = Field(default=None, ge=1)
    source: ShotReferenceSource | RealizationChannelSource | None = None


class ManifestDocumentV2(_Strict):
    schema_version: str
    workflow_id: str
    version: int = Field(ge=1)
    inputs: dict[str, ManifestInputDefV2] = Field(default_factory=dict)
    parameters: dict[str, ManifestParameterDef] = Field(default_factory=dict)
    outputs: dict[str, ManifestOutputDef] = Field(default_factory=dict)


MANIFEST_SCHEMA_VERSION_2 = "2"


def parse_manifest_v2(raw: str | dict) -> ManifestDocumentV2:
    """Strict parse of a schema-2 manifest (§8 rules)."""
    from soloring.domain.normalize import is_valid_role

    try:
        doc = raw if isinstance(raw, dict) else json.loads(raw)
    except ValueError as exc:
        raise WorkflowError(f"Invalid workflow manifest: {exc}") from exc
    # Schema 2 must reject legacy source_role in ANY input (no dual form).
    if isinstance(doc, dict):
        for key, decl in (doc.get("inputs") or {}).items():
            if isinstance(decl, dict) and "source_role" in decl:
                raise WorkflowError(
                    f"Manifest schema 2 input {key!r} uses legacy "
                    "'source_role'; schema 2 requires the discriminated "
                    "'source' object and no dual form exists."
                )
    try:
        parsed = ManifestDocumentV2.model_validate(doc)
    except ValidationError as exc:
        raise WorkflowError(f"Invalid workflow manifest: {exc}") from exc
    if parsed.schema_version != MANIFEST_SCHEMA_VERSION_2:
        raise WorkflowError(
            f"Manifest schema_version must be {MANIFEST_SCHEMA_VERSION_2!r}."
        )
    for key, decl in parsed.inputs.items():
        if isinstance(decl.source, ShotReferenceSource):
            if not is_valid_role(decl.source.role):
                raise WorkflowError(
                    f"Manifest input {key!r} shot_reference role "
                    f"{decl.source.role!r} is not a valid predecessor "
                    "ShotReference role."
                )
    return parsed


def build_template_v2(
    doc: ManifestDocumentV2, manifest_hash: str, template_hash: str
) -> WorkflowTemplate:
    """Schema-2 template value object: byte inputs of BOTH source classes
    (shot_reference + realization_channel) participate in cardinality;
    realization keys are marked so legacy mapping skips them (§19)."""
    from soloring.realization.profile import TARGET_KINDS  # noqa: F401

    ref_inputs: list[WorkflowInputDef] = []
    realization_keys: list[str] = []
    for key, decl in doc.inputs.items():
        source = decl.source
        if source is None:
            continue
        if isinstance(source, ShotReferenceSource):
            ref_inputs.append(WorkflowInputDef(
                input_key=key, source_role=source.role,
                required=decl.required, cardinality=decl.cardinality,
            ))
        else:
            ref_inputs.append(WorkflowInputDef(
                input_key=key, source_role=None,
                required=decl.required, cardinality=decl.cardinality,
            ))
            realization_keys.append(key)
    return WorkflowTemplate(
        workflow_id=doc.workflow_id,
        workflow_version=doc.version,
        manifest_schema_version=doc.schema_version,
        manifest_hash=manifest_hash,
        workflow_template_hash=template_hash,
        reference_inputs=tuple(ref_inputs),
        parameters=tuple(
            ParameterDef(
                name=name, type=decl.type, default=decl.default,
                min=decl.min, max=decl.max,
                enum=tuple(decl.enum) if decl.enum is not None else None,
            )
            for name, decl in doc.parameters.items()
        ),
        outputs=tuple(
            ExpectedOutput(
                name=name, kind=decl.kind,
                expected_count=decl.expected_count,
                accepted_media_types=(
                    tuple(decl.accepted_media_types)
                    if decl.accepted_media_types is not None
                    else None
                ),
            )
            for name, decl in doc.outputs.items()
        ),
        is_schema2=True,
        realization_input_keys=tuple(realization_keys),
    )
