"""Continuity transition schemas (M7B §2). extra=forbid everywhere;
value is the only client-expressible value channel — value_json/value_hash
are never accepted from clients."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

_ANCHOR_TYPES = ("sequence", "scene", "shot")
_BOUNDARIES = ("start", "end")
_OPERATIONS = ("set", "clear")


class TransitionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor_type: str
    anchor_id: str
    boundary: str
    operation: str
    value: object | None = None


class TransitionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor_type: str | None = None
    anchor_id: str | None = None
    boundary: str | None = None
    operation: str | None = None
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
