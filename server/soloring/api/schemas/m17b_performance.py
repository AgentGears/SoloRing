"""M17B API request/response schemas (frozen R7 §12). Every request
schema is CLOSED (`extra="forbid"`): caller fields never disappear
silently. Rational input is raw num/den — the service canonicalizes
or rejects."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RationalIn(_Closed):
    # authority integers are STRICT (correction CR-C): bool,
    # numeric strings and integral floats reject at the boundary
    # instead of being silently repaired into authority
    num: StrictInt
    den: StrictInt


class KeyframeProvenanceIn(_Closed):
    kind: Literal["AUTHORED", "DERIVED", "DERIVED_THEN_EDITED"]
    source_alignment_id: str | None = None


class KeyframeIn(_Closed):
    time_ms: RationalIn
    value: StrictInt
    provenance: KeyframeProvenanceIn


class ChannelIn(_Closed):
    channel_key: str
    domain: str
    role: str
    semantic_key: str
    value_grammar: str
    keyframes: list[KeyframeIn]


class TemporalDomainIn(_Closed):
    start: RationalIn
    end: RationalIn


class PerformanceCandidateCreate(_Closed):
    performance_kind: Literal["BODY", "FACIAL", "BODY_FACIAL"]
    performance_profile_id: str
    temporal_domain: TemporalDomainIn
    channels: list[ChannelIn]
    source_provenance: "_ProvenanceIn"


class _ProvenanceIn(_Closed):
    schema_version: Literal[1] = 1
    source_kind: Literal["authored", "performance_capture", "tracking",
                         "reconstruction", "generated", "simulated",
                         "procedural", "imported"] = "authored"
    producer_id: str
    producer_version: str
    source_identity: str | None = None
    parameters_sha256: str | None = None


PerformanceCandidateCreate.model_rebuild()


class AdoptRequest(_Closed):
    adopted_by: str = Field(min_length=1, max_length=255)


class RetargetAssessmentCreate(_Closed):
    from_production_revision_id: str
    to_production_revision_id: str


class ReviewCreate(_Closed):
    decision: Literal["ACCEPT_FOR_NEW_CANDIDATE", "REJECT"]
    reviewed_by: str = Field(min_length=1, max_length=255)
    rationale: str | None = Field(default=None, max_length=4096)


class RetargetCandidateCreate(_Closed):
    assessment_id: str
    accepted_review_id: str
    producer_id: str = Field(min_length=1, max_length=255)
    producer_version: str = Field(min_length=1, max_length=255)
    source_identity: str | None = Field(default=None, max_length=1024)
    parameters_sha256: str | None = Field(
        default=None, min_length=64, max_length=64)


# --------------------------- read models ---------------------------


class PerformanceCandidateRead(BaseModel):
    id: str
    project_id: str
    subject_id: str
    performance_kind: str
    performance_profile_id: str
    temporal_start_ms: dict
    temporal_end_ms: dict
    canonical_channel_payload_sha256: str
    canonical_channel_payload_blob_hash: str
    payload_schema_version: int
    source_kind: str
    provenance_hash: str
    created_at: str


class PerformanceCandidateCollection(BaseModel):
    candidates: list[PerformanceCandidateRead]
    next_cursor: tuple[str, str] | None = None


class PerformanceRevisionRead(BaseModel):
    id: str
    project_id: str
    subject_id: str
    performance_kind: str
    performance_profile_id: str
    temporal_start_ms: dict
    temporal_end_ms: dict
    canonical_channel_payload_sha256: str
    canonical_channel_payload_blob_hash: str
    payload_schema_version: int
    source_kind: str
    provenance_hash: str
    adopted_candidate_id: str
    adoption_id: str
    adopted_by: str
    adopted_at: str


class PerformanceRevisionCollection(BaseModel):
    revisions: list[PerformanceRevisionRead]
    next_cursor: tuple[str, str] | None = None


class RetargetAssessmentRead(BaseModel):
    id: str
    project_id: str
    performance_revision_id: str
    from_production_revision_id: str
    from_production_revision_hash: str
    to_production_revision_id: str
    to_production_revision_hash: str
    schema_version: int
    evaluator_id: str
    evaluator_version: int
    scope_hash: str
    report_hash: str
    overall_verdict: str
    created_at: str
    physical_revision_compatibility_only: bool = True
    subject_binding_assessed: bool = False
    executor_qualification_assessed: bool = False


class RetargetReviewRead(BaseModel):
    id: str
    assessment_id: str
    decision: str
    reviewed_by: str
    reviewed_at: str
    rationale: str | None = None


class RetargetReviewCollection(BaseModel):
    reviews: list[RetargetReviewRead]
    next_cursor: tuple[str, str] | None = None
