"""ContinuityFeature API schemas (M7A §47). extra=forbid everywhere."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class FeatureCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    kind: str
    value_type: str
    name: str
    description: str | None = None
    enum_values: list[str] | None = None
    unit: str | None = None
    supersedes_feature_id: str | None = None


class FeaturePatch(BaseModel):
    """Display metadata only — semantic fields are immutable (§4.2)."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None


class FeatureRead(BaseModel):
    id: str
    entity_id: str
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
