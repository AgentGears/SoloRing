"""Story World API schemas (M6 §17, §24, §28)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EntityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    name: str
    description: str | None = None


class EntityPatch(BaseModel):
    """Identity PATCH accepts ONLY name/description (M6-F2: kind immutable)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None


class EntityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    kind: str
    name: str
    description: str | None
    created_at: str
    updated_at: str
    approved_revision_id: str | None = None


class RevisionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec: dict = Field(..., description="Kind-specific design payload (v1).")


class EntityRevisionSummary(BaseModel):
    id: str
    entity_id: str
    revision_number: int
    schema_version: int
    spec_hash: str
    created_at: str


class EntityRevisionDetail(BaseModel):
    id: str
    entity_id: str
    entity_kind: str
    entity_name: str
    revision_number: int
    schema_version: int
    spec_hash: str
    created_at: str
    spec_json: str


class ApprovalPut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision_id: str
    expected_approved_revision_id: str | None = None


class ApprovalRead(BaseModel):
    entity_id: str
    revision_id: str
    approved_at: str
