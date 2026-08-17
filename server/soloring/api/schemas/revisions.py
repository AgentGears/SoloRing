"""Revision summary schema (plan §16)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class RevisionSummary(BaseModel):
    """Summary only — snapshot_json is never exposed in the list (plan §16)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    shot_id: str
    revision_number: int
    snapshot_hash: str
    created_at: str
