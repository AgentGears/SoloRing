"""Narrative API schemas (M6B §40)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SequenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None


class SequencePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None


class SequenceRead(BaseModel):
    id: str
    project_id: str
    title: str | None
    position: int
    created_at: str
    updated_at: str


class SequenceOrderPut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence_ids: list[str]


class SceneCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    description: str | None = None


class ScenePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = None
    description: str | None = None


class SceneRead(BaseModel):
    id: str
    sequence_id: str
    title: str | None
    description: str | None
    position: int
    created_at: str
    updated_at: str


class SceneOrderPut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_ids: list[str]


class SceneShotsPut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shot_ids: list[str]
