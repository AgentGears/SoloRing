"""Reference request/response schemas (plan §11, §46)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from soloring.domain.normalize import ROLE_MAX


class ReferenceInput(BaseModel):
    """A single reference in a PUT body. No position field (server-owned)."""

    model_config = ConfigDict(extra="forbid")

    asset_id: str
    role: str = Field(max_length=ROLE_MAX)


class ReferenceSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    references: list[ReferenceInput]


class ReferenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_id: str
    role: str
    position: int
    created_at: str
