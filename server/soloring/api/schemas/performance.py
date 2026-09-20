"""M17A API request/response schemas (frozen R5 §10; source review
findings 4/5/9). Every request schema is a CLOSED canonical surface:
`extra="forbid"` so caller fields are rejected — never silently
discarded before canonical hashing — and declared schema versions are
exact literals, so a payload claiming another version cannot be
rewritten into v1."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _Closed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DialogueLineCreate(_Closed):
    pass


class DialogueLineRead(BaseModel):
    id: str
    project_id: str
    created_at: str


class DialogueLineCollection(BaseModel):
    lines: list[DialogueLineRead]
    next_cursor: tuple[str, str] | None = None


class DialogueLineRevisionCreate(_Closed):
    speaker_subject_id: str
    # frozen wording is the EXACT approved Unicode text: no length cap
    # (the service enforces non-whitespace-only), no trimming here
    wording: str
    language: str


class DialogueLineRevisionRead(BaseModel):
    id: str
    dialogue_line_id: str
    revision_number: int
    speaker_subject_id: str
    language: str
    wording: str
    spec_hash: str
    created_at: str


class ProvenanceIn(_Closed):
    schema_version: Literal[1] = 1
    source_kind: Literal["recorded", "adr", "imported", "generated"]
    generator_id: str | None = None
    generator_version: str | None = None
    workflow_id: str | None = None
    workflow_version: str | None = None


class VocalCandidateCreate(_Closed):
    retained_audio_blob_hash: str = Field(min_length=64, max_length=64)
    source_provenance: ProvenanceIn
    trim_start_sample: int | None = None
    trim_end_sample_exclusive: int | None = None


class VocalCandidateRead(BaseModel):
    id: str
    dialogue_line_revision_id: str
    retained_audio_blob_hash: str
    native_sample_rate_hz: int
    retained_sample_count: int
    trim_start_sample: int
    trim_end_sample_exclusive: int
    source_kind: str
    provenance_hash: str
    created_at: str


class AdoptRequest(_Closed):
    adopted_by: str = Field(min_length=1, max_length=255)


class VocalPerformanceRead(BaseModel):
    id: str
    dialogue_line_revision_id: str
    revision_number: int
    speaker_subject_id: str
    retained_audio_blob_hash: str
    native_sample_rate_hz: int
    retained_sample_count: int
    trim_start_sample: int
    trim_end_sample_exclusive: int
    adopted_candidate_id: str
    adoption_id: str
    adopted_by: str
    adopted_at: str


class SelectionPut(_Closed):
    vocal_performance_revision_id: str | None = None
    selected_by: str = Field(min_length=1, max_length=255)


class SelectionRead(BaseModel):
    dialogue_line_revision_id: str
    state: str
    selected_vocal_performance_revision_id: str | None = None
    selected_by: str | None = None
    selected_at: str | None = None


class RationalIn(_Closed):
    num: int
    den: int


class SegmentMappingPut(_Closed):
    vocal_performance_revision_id: str
    source_start_sample: int
    source_end_sample_exclusive: int
    sample_rate_hz: int
    performance_origin_ms: RationalIn
    shot_anchor_ms: RationalIn


class InputDigestIn(_Closed):
    vocal_performance_revision_id: str
    retained_audio_blob_sha256: str = Field(min_length=64, max_length=64)


class DerivationRunIn(_Closed):
    schema_version: Literal[1] = 1
    run_timestamp_utc: str
    host_context: str = Field(min_length=1, max_length=1024)
    input_digest: InputDigestIn


class AlignmentEntryIn(_Closed):
    start_sample: int
    end_sample_exclusive: int
    label: str = Field(min_length=1, max_length=256)


class AlignmentDocumentIn(_Closed):
    schema_version: Literal[1] = 1
    # all three arrays are REQUIRED: a closed schema never defaults a
    # missing array into existence (source review finding 5)
    words: list[AlignmentEntryIn]
    phonemes: list[AlignmentEntryIn]
    viseme_classes: list[AlignmentEntryIn]


class AlignmentCreate(_Closed):
    analyzer_id: str = Field(min_length=1, max_length=255)
    analyzer_version: str = Field(min_length=1, max_length=255)
    model_identity: str = Field(min_length=1, max_length=255)
    runtime_identity: str = Field(min_length=1, max_length=255)
    parameters_sha256: str = Field(min_length=64, max_length=64)
    alignment_document: AlignmentDocumentIn
    derivation_run: DerivationRunIn


class AlignmentRead(BaseModel):
    id: str
    vocal_performance_revision_id: str
    analyzer_id: str
    analyzer_version: str
    model_identity: str
    runtime_identity: str
    parameters_sha256: str
    retained_sha256: str
    derivation_run_hash: str
    derivation_run_identity: str
    created_at: str


class CompatibilityRead(BaseModel):
    evaluator_id: str
    evaluator_version: int
    vocal_performance_revision_id: str
    source_dialogue_line_revision_id: str
    target_dialogue_line_revision_id: str
    verdict: str
