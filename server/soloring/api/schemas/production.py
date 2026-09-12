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


class ProductionObjectDetail(ProductionObjectRead):
    """Frozen R3 §11.1: object metadata plus revision summaries ASC."""

    revisions: list[RevisionSummary]



# --- M15 compatibility (frozen R4 §17) --------------------------------------


class CompatibilityAssessmentRequest(BaseModel):
    to_revision_id: str


class CompatibilityUseSummary(BaseModel):
    position: int
    composition_id: str
    occurrence_id: str
    composition_working_version: int
    use_contract_hash: str
    dimensions: dict[str, str]
    verdict: str
    translator_id: str | None
    translator_version: int | None
    translator_output_hash: str | None


class CompatibilityAssessmentCreated(BaseModel):
    scope_status: str
    assessment_id: str | None
    report_hash: str | None
    overall_verdict: str | None
    verdict_counts: dict[str, int] | None
    converged: bool | None
    uses: list[dict] | None


class CompatibilityAssessmentRead(BaseModel):
    assessment_id: str
    report_hash: str
    scope_hash: str
    project_id: str
    production_object_id: str
    from_revision_id: str
    from_revision_hash: str
    to_revision_id: str
    to_revision_hash: str
    evaluator_id: str
    evaluator_version: int
    overall_verdict: str
    verdict_counts: dict[str, int]
    translator_count: int
    use_count: int
    created_at: str


class CompatibilityUsePage(BaseModel):
    uses: list[CompatibilityUseSummary]
    next_cursor: int | None
