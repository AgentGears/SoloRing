"""Continuity transition schemas (M7B §2). extra=forbid everywhere;
value is the only client-expressible value channel — value_json/value_hash
are never accepted from clients."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

_ANCHOR_TYPES = ("sequence", "scene", "shot")
_BOUNDARIES = ("start", "end")
_OPERATIONS = ("set", "clear")


class TransitionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor_type: Literal["sequence", "scene", "shot"]
    anchor_id: str
    boundary: Literal["start", "end"]
    operation: Literal["set", "clear"]
    value: object | None = None


class TransitionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Omission means preserve; explicit null on any NON-NULLABLE field is
    # 422 at the request boundary — never a value that reaches the DB and
    # becomes an integrity/500 problem downstream.
    anchor_type: Literal["sequence", "scene", "shot"] | None = None
    anchor_id: str | None = None
    boundary: Literal["start", "end"] | None = None
    operation: Literal["set", "clear"] | None = None
    value: object | None = None

    @model_validator(mode="after")
    def _reject_explicit_nulls(self) -> "TransitionPatch":
        for field in ("anchor_type", "anchor_id", "boundary", "operation"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(
                    f"{field} is not nullable — omit the field to preserve "
                    "its current value."
                )
        return self


class TransitionRead(BaseModel):
    id: str
    feature_id: str
    anchor_type: str
    anchor_id: str
    boundary: str
    operation: str
    value_json: str | None
    value_hash: str | None
    created_at: str
    updated_at: str
