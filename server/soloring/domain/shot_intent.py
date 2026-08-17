"""ShotIntent — the creative working state of a Shot (plan §9.1, §10).

A pure value object. It NEVER contains model/executor parameters, workflow node
IDs, executor filenames, or filesystem paths. Normalization to canonical
persistent form happens in the persistence/snapshot layer (see domain.normalize
and domain.snapshots), not here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ShotIntent(BaseModel):
    """Creative working state of a Shot (plan §9.1, §10).

    Unknown fields are forbidden so model/executor parameters (steps, CFG,
    sampler, scheduler, workflow node IDs, paths, ...) can never sneak in.
    """

    model_config = ConfigDict(extra="forbid")

    subject: str
    action: str | None = None
    environment: str | None = None
    framing: str | None = None
    camera_motion: str | None = None
    lens: str | None = None
    mood: str | None = None
    duration_ms: int | None = None
