"""Production Library API schemas (frozen R3 plan §11)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProductionObjectCreate(BaseModel):
    name: str
    description: str | None = None


class ProductionObjectPatch(BaseModel):
    name: str | None = None
    description: str | None = None


class ProductionObjectRead(BaseModel):
    id: str
    project_id: str
    name: str
    description: str | None
    created_at: str
    updated_at: str


class ClosureRead(BaseModel):
    contract_key: str
    contract_version: int
    blob_hash: str
    size_bytes: int
    media_type: str | None


class ReadinessIssue(BaseModel):
    code: str
    message: str
    details: dict = Field(default_factory=dict)


class PublicationReadinessRequest(BaseModel):
    asset_id: str


class PublicationReadinessRead(BaseModel):
    production_object_id: str
    source_asset_id: str
    ready: bool
    issues: list[ReadinessIssue]
    proposed_snapshot_hash: str | None
    closure: ClosureRead | None


class PublishRequest(BaseModel):
    asset_id: str


class RevisionSummary(BaseModel):
    revision_id: str
    revision_number: int
    snapshot_hash: str
    created_at: str


class SourceAssetSummary(BaseModel):
    asset_id: str
    created_at: str


class RevisionDetail(BaseModel):
    revision_id: str
    production_object_id: str
    project_id: str
    revision_number: int
    snapshot_json: str
    snapshot_hash: str
    created_at: str
    closure: ClosureRead
    blob_url: str
    sources: list[SourceAssetSummary]
    physical_integrity: str
