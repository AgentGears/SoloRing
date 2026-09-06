"""Composition API schemas (frozen M12 R3 §14)."""

from __future__ import annotations

from pydantic import BaseModel, Field

# frozen §14.5: limit is bounded on BOTH ends (no negative limits)


class CompositionCreate(BaseModel):
    name: str
    description: str | None = None


class CompositionPatch(BaseModel):
    expected_metadata_version: int
    name: str | None = None
    description: str | None = None


class CompositionRead(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None
    metadata_version: int
    working_version: int
    created_at: str
    updated_at: str


class CompositionDetail(CompositionRead):
    working_occurrence_count: int
    published_revision_count: int


class SourceRef(BaseModel):
    kind: str
    revision_id: str


class TransformIn(BaseModel):
    translation_mm: list[int]
    rotation_udeg: list[int]


class OccurrenceMint(BaseModel):
    scope: str
    expected_working_version: int
    display_name: str
    source: SourceRef
    visible: bool
    transform: TransformIn


class OccurrencePatch(BaseModel):
    scope: str
    expected_working_version: int
    display_name: str | None = None
    visible: bool | None = None
    transform: TransformIn | None = None
    source: SourceRef | None = None


class OccurrenceRead(BaseModel):
    occurrence_id: str
    display_name: str
    source_kind: str
    production_revision_id: str | None
    nested_composition_revision_id: str | None
    visible: int
    x_mm: int
    y_mm: int
    z_mm: int
    yaw_udeg: int
    pitch_udeg: int
    roll_udeg: int
    updated_at: str


class MintResult(BaseModel):
    occurrence_id: str
    working_version: int


class PatchResult(BaseModel):
    occurrence_id: str
    working_version: int


class IdentityOperationRequest(BaseModel):
    kind: str
    source_occurrence_ids: list[str]
    target_working_specs: list[dict]


class PreviewRequest(BaseModel):
    scope: str
    request: IdentityOperationRequest


class PreviewResult(BaseModel):
    allowed: bool
    working_version: int
    normalized_request: dict
    request_fingerprint: str
    impact_fingerprint: str
    source_occurrence_summaries: list[dict]
    historical_reference_counts: dict
    live_blocking_references: list[dict]


class ApplyRequest(BaseModel):
    scope: str
    expected_working_version: int
    expected_request_fingerprint: str
    expected_impact_fingerprint: str
    request: IdentityOperationRequest


class ApplyResult(BaseModel):
    operation_id: str
    kind: str
    working_version: int
    target_occurrence_ids: list[str]


class ReadinessResult(BaseModel):
    ready: bool
    working_version: int
    issues: list[dict]
    proposed_snapshot_hash: str | None = None
    occurrence_count: int | None = None
    direct_production_source_count: int | None = None
    direct_nested_source_count: int | None = None
    flattened_production_dependency_count: int | None = None
    flattened_nested_dependency_count: int | None = None


class PublishRequest(BaseModel):
    expected_working_version: int


class RevisionSummary(BaseModel):
    revision_id: str
    revision_number: int
    snapshot_hash: str
    created_at: str


class RevisionDetail(BaseModel):
    revision_id: str
    composition_id: str
    revision_number: int
    snapshot_json: str
    snapshot_hash: str
    created_at: str
