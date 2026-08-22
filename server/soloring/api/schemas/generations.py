"""Generation + Take response schemas (v0.1 §46, §97)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class GenerationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    shot_id: str
    shot_revision_id: str
    generation_number: int
    status: str
    operation: str
    executor: str
    workflow_id: str
    workflow_version: int
    compiled_prompt: str
    prompt_compiler_version: str
    progress_current: int | None
    progress_total: int | None
    current_node: str | None
    error_code: str | None
    error_message: str | None
    created_at: str
    updated_at: str
    queued_at: str
    started_at: str | None
    completed_at: str | None
    executor_job_id: str | None
    model: str | None = None
    model_version: str | None = None


class TakeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    shot_id: str
    generation_id: str
    output_key: str
    label: str | None
    rejected_at: str | None
    created_at: str
    is_approved: bool
    asset_id: str | None
    blob_hash: str | None
    detected_media_type: str | None
    output_kind: str | None
    blob_url: str | None
