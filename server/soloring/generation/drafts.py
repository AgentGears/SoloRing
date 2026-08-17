"""Immutable GenerationDraft (plan §36).

A frozen persistence value carrying the complete durable execution identity.
M1 validates only structure/syntax: required strings non-empty, SHA-256 fields
64 chars, parameters_json/workflow_spec_json syntactically valid JSON. Workflow
semantics and logical-workflow hash recomputation are later concerns (M4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from soloring.generation.enums import GenerationOperation


def _require_nonempty(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"GenerationDraft.{name} must be a non-empty string.")


def _require_hash64(name: str, value: object) -> None:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"GenerationDraft.{name} must be a 64-character SHA-256 hex.")


def _require_valid_json(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"GenerationDraft.{name} must be a non-empty JSON string.")
    try:
        json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"GenerationDraft.{name} is not valid JSON: {exc}") from exc


@dataclass(frozen=True)
class GenerationDraft:
    shot_id: str
    shot_revision_id: str

    operation: GenerationOperation
    executor: str

    workflow_id: str
    workflow_version: int
    workflow_template_hash: str
    manifest_hash: str

    model: str | None
    model_version: str | None

    compiled_prompt: str
    negative_prompt: str | None
    prompt_compiler_version: str

    seed: int | None

    parameters_json: str
    workflow_spec_json: str
    workflow_spec_hash: str

    rerun_of_generation_id: str | None = None

    def __post_init__(self) -> None:
        for field in ("shot_id", "shot_revision_id"):
            _require_nonempty(field, getattr(self, field))
        if not isinstance(self.operation, GenerationOperation):
            raise ValueError("GenerationDraft.operation must be a GenerationOperation.")
        _require_nonempty("executor", self.executor)
        _require_nonempty("workflow_id", self.workflow_id)
        if not isinstance(self.workflow_version, int) or self.workflow_version < 1:
            raise ValueError("GenerationDraft.workflow_version must be a positive int.")
        _require_hash64("workflow_template_hash", self.workflow_template_hash)
        _require_hash64("manifest_hash", self.manifest_hash)
        _require_hash64("workflow_spec_hash", self.workflow_spec_hash)
        _require_nonempty("compiled_prompt", self.compiled_prompt)
        _require_nonempty("prompt_compiler_version", self.prompt_compiler_version)
        _require_valid_json("parameters_json", self.parameters_json)
        _require_valid_json("workflow_spec_json", self.workflow_spec_json)
        if self.seed is not None and not isinstance(self.seed, int):
            raise ValueError("GenerationDraft.seed must be an int or None.")
        if self.negative_prompt is not None and not self.negative_prompt.strip():
            raise ValueError("GenerationDraft.negative_prompt must be non-empty or None.")
