"""M13 production-world API schemas (frozen R3 §24). extra=forbid."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

# M13-INTERP:03: the integral grammar is enforced at the boundary — a JSON
# float or boolean is never silently coerced into an integer component.
StrictInt = Annotated[int, Field(strict=True)]


class TransformIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    translation_mm: list[StrictInt] = Field(min_length=3, max_length=3)
    rotation_udeg: list[StrictInt] = Field(min_length=3, max_length=3)


class SpatialInterpretationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    realization_local_to_subject_local: TransformIn


class SpatialInterpretationRead(BaseModel):
    production_revision_id: str
    production_revision_hash: str
    retained_blob_hash: str
    schema_version: int
    interpretation_hash: str
    coordinate_system: dict
    origin_semantics: str
    realization_local_to_subject_local: dict
    created_at: str


class AuthoritySubjectAdopt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    creative_entity_id: str | None = None


class AuthoritySubjectRead(BaseModel):
    composition_id: str
    occurrence_id: str
    subject_kind: str
    subject_id: str | None
    creative_entity_id: str | None
    created_at: str | None


class PIFeatureCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    kind: str
    value_type: str
    name: str
    description: str | None = None
    enum_values: list[str] | None = None
    unit: str | None = None
    supersedes_feature_id: str | None = None


class PIFeaturePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None


class PIFeatureRead(BaseModel):
    id: str
    composition_id: str
    occurrence_id: str
    key: str
    kind: str
    value_type: str
    name: str
    description: str | None
    enum_values_json: str | None
    unit: str | None
    supersedes_feature_id: str | None
    created_at: str
    updated_at: str


class PITransitionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor_type: str
    anchor_id: str
    boundary: str
    operation: str
    value: object | None = None


class PITrackCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    occurrence_id: str
    requirement: str


class PITrackRead(BaseModel):
    id: str
    spatial_world_id: str
    composition_id: str
    occurrence_id: str
    requirement: str


class PITrackTransitionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor_type: str
    anchor_id: str
    boundary: str
    operation: str
    transform: dict | None = None


class BindingPairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spatial_world_revision_id: str


class BindingReadinessRead(BaseModel):
    ready: bool
    issues: list[dict]
    proposed_binding_hash: str
    composition_revision_id: str
    composition_revision_hash: str
    spatial_world_revision_id: str
    spatial_world_revision_hash: str
    subject_summaries: list[dict]
    entry_summaries: list[dict]


class BindingRead(BaseModel):
    binding_id: str
    binding_hash: str
    schema_version: int
    composition_id: str
    composition_revision_id: str
    composition_revision_hash: str
    spatial_world_revision_id: str
    spatial_world_revision_hash: str
    subjects: list[dict]
    entries: list[dict]
    created_at: str


class SelectionPut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    binding_id: str
    expected_binding_id: str | None = None


class SelectionDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_binding_id: str


class SelectionRead(BaseModel):
    shot_id: str
    binding_id: str | None
    updated_at: str | None
    binding: dict | None = None
