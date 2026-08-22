"""ExecutionModelFingerprint schema 1 (frozen plan §6.3, §27).

Content-addressed model-weight + characterized-runtime identity. Strict
recursive unknown-field rejection; loader bindings are explicit and are
cross-validated against the captured workflow template.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from soloring.errors import ErrorCode, SoloRingError

FINGERPRINT_SCHEMA_VERSION = 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")

# Frozen schema-1 adapter vocabulary (§6.3): widening requires an explicit
# adapter-contract revision.
STORAGE_ROOT_KEYS = ("unet", "vae", "clip", "clip_vision")


class FingerprintError(SoloRingError):
    def __init__(self, message: str) -> None:
        super().__init__(
            ErrorCode.EXECUTION_MODEL_FINGERPRINT_INVALID,
            message,
            status_code=422,
        )


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CustomNodePolicy(_Strict):
    disable_all: bool
    whitelist: list[str]


class RuntimeRequirements(_Strict):
    comfyui_commit: str
    custom_nodes: dict[str, str]
    custom_node_policy: CustomNodePolicy


class FingerprintArtifact(_Strict):
    artifact_key: str
    storage_root_key: str
    node: str
    field: str
    declared_name: str
    sha256: str


class ExecutionModelFingerprintDocument(_Strict):
    schema_version: int
    model_id: str
    model_version: str
    runtime_requirements: RuntimeRequirements
    artifacts: list[FingerprintArtifact] = Field(min_length=1)


def parse_fingerprint(raw: str | dict) -> ExecutionModelFingerprintDocument:
    """Strict parse; raises EXECUTION_MODEL_FINGERPRINT_INVALID."""
    import json

    try:
        doc = raw if isinstance(raw, dict) else json.loads(raw)
    except ValueError as exc:
        raise FingerprintError(
            f"ExecutionModelFingerprint is not valid JSON: {exc}"
        )
    try:
        parsed = ExecutionModelFingerprintDocument.model_validate(doc)
    except ValidationError as exc:
        raise FingerprintError(f"Invalid ExecutionModelFingerprint: {exc}")
    _validate_semantics(parsed)
    return parsed


def validate_declared_name(name: str) -> str:
    """§6.3: a non-empty RELATIVE loader name that cannot escape its root —
    no absolute path, no `.`/`..` traversal, no drive/UNC form."""
    if not name or name.strip() != name or "\\" in name:
        raise FingerprintError(
            f"declared_name {name!r} is not a normalized relative loader "
            "name."
        )
    if name.startswith("/") or re.match(r"^[A-Za-z]:", name) or name.startswith(
        "//"
    ):
        raise FingerprintError(
            f"declared_name {name!r} must be relative, not absolute."
        )
    parts = name.split("/")
    for part in parts:
        if part in (".", "..") or part == "":
            raise FingerprintError(
                f"declared_name {name!r} contains traversal or empty "
                "segments."
            )
    return name


def _validate_semantics(doc: ExecutionModelFingerprintDocument) -> None:
    if doc.schema_version != FINGERPRINT_SCHEMA_VERSION:
        raise FingerprintError(
            f"ExecutionModelFingerprint schema_version must be "
            f"{FINGERPRINT_SCHEMA_VERSION}."
        )
    if not doc.model_id.strip() or not doc.model_version.strip():
        raise FingerprintError("Fingerprint model_id/model_version are empty.")
    rr = doc.runtime_requirements
    if not COMMIT_RE.match(rr.comfyui_commit):
        raise FingerprintError(
            f"comfyui_commit {rr.comfyui_commit!r} is not a 40-hex revision."
        )
    for node_name, commit in rr.custom_nodes.items():
        if not node_name.strip():
            raise FingerprintError("Empty custom-node name.")
        if not COMMIT_RE.match(commit):
            raise FingerprintError(
                f"Custom node {node_name!r} commit {commit!r} is not a "
                "40-hex revision."
            )
    if not rr.custom_node_policy.disable_all:
        raise FingerprintError(
            "Schema 1 requires the characterized disable-all custom-node "
            "policy."
        )
    if not rr.custom_node_policy.whitelist:
        raise FingerprintError("Custom-node whitelist is empty.")

    artifact_keys: set[str] = set()
    bindings: set[tuple[str, str]] = set()
    for artifact in doc.artifacts:
        if not artifact.artifact_key.strip():
            raise FingerprintError("Empty artifact_key.")
        if artifact.artifact_key in artifact_keys:
            raise FingerprintError(
                f"Duplicate artifact_key {artifact.artifact_key!r}."
            )
        artifact_keys.add(artifact.artifact_key)
        if artifact.storage_root_key not in STORAGE_ROOT_KEYS:
            raise FingerprintError(
                f"artifact {artifact.artifact_key!r} uses storage_root_key "
                f"{artifact.storage_root_key!r} outside the frozen adapter "
                f"vocabulary {STORAGE_ROOT_KEYS}."
            )
        binding = (artifact.node, artifact.field)
        if binding in bindings:
            raise FingerprintError(
                f"Duplicate fingerprint loader binding {binding}."
            )
        bindings.add(binding)
        validate_declared_name(artifact.declared_name)
        if not SHA256_RE.match(artifact.sha256):
            raise FingerprintError(
                f"artifact {artifact.artifact_key!r} sha256 is not "
                "lowercase 64-hex."
            )


def cross_validate_fingerprint_template(
    fingerprint: ExecutionModelFingerprintDocument, template: dict
) -> None:
    """§24: every (node, field) exists in the captured template and the
    exact template field value equals declared_name."""
    for artifact in fingerprint.artifacts:
        node = template.get(artifact.node)
        if not isinstance(node, dict):
            raise FingerprintError(
                f"Fingerprint binding refers to template node "
                f"{artifact.node!r}, which does not exist."
            )
        inputs = node.get("inputs")
        if not isinstance(inputs, dict) or artifact.field not in inputs:
            raise FingerprintError(
                f"Fingerprint binding ({artifact.node}, {artifact.field}) "
                "does not exist in the captured template."
            )
        value = inputs[artifact.field]
        if value != artifact.declared_name:
            raise FingerprintError(
                f"Fingerprint declared_name {artifact.declared_name!r} "
                f"differs from template value {value!r} at "
                f"({artifact.node}, {artifact.field})."
            )
