"""Continuity transition schemas (M7B §2). extra=forbid everywhere;
value is the only client-expressible value channel — value_json/value_hash
are never accepted from clients."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

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

    # Nullable so omission (preserve) is expressible, but a NON-null value
    # must be a domain member — invalid operations are rejected 422 at the
    # request boundary, never policed by DB constraints downstream.
    anchor_type: Literal["sequence", "scene", "shot"] | None = None
    anchor_id: str | None = None
    boundary: Literal["start", "end"] | None = None
    operation: Literal["set", "clear"] | None = None
    value: object | None = None


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
