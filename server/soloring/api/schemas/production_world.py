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
