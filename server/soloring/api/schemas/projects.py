"""Project request/response schemas (plan §8, §46)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from soloring.domain.normalize import PROJECT_NAME_MAX


class ProjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=PROJECT_NAME_MAX)
    description: str | None = None


class ProjectPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, max_length=PROJECT_NAME_MAX)
    description: str | None = None


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str | None
    created_at: str
    updated_at: str
